"""
navicane — Smart Blind Stick main entry point.

Multithreaded architecture:
  - Main thread:     hardware init, startup, mode toggle, graceful shutdown
  - Sensor thread:   reads ultrasonic distances + IMU at 20 Hz
  - Camera thread:   captures frames + runs YOLO inference
  - Fall thread:     monitors accelerometer for fall events
  - GPS thread:      (started by gps_tracker module internally)

All shared state is protected by threading.Lock.

Satisfies:
  Issue #23 — Build multithreaded main loop with thread safety
  Issue #25 — Pre-cache TTS audio for all common alert phrases
  Issue #27 — Add indoor/outdoor sensitivity toggle via physical button
"""

import cv2
import os
import sys
import time
import threading
import logging
from collections import Counter

# ── Bootstrap: add project root to sys.path ──────────────────
_project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

# ── Config (must import before gpiozero) ─────────────────────
from src.config.settings import (
    MODEL_CUSTOM_PATH, MODEL_FALLBACK_PATH, LOG_PATH,
    HEADLESS, MOCK_HARDWARE, STOP_SIGNAL_PATH,
    DETECTION_THRESHOLD_M, CONFIDENCE_THRESHOLD, DETECTION_COOLDOWN_S,
    ELEVATION_COOLDOWN_S, ELEVATION_THRESHOLDS,
    SENSOR_POLL_INTERVAL_S,
    MODE_TOGGLE_PIN, MODE_DEFAULT, SENSITIVITY_PROFILES,
)

# ── gpiozero (mock pin factory already set by settings.py if needed)
from gpiozero import DistanceSensor, OutputDevice, Button

# ── Conditional camera import ────────────────────────────────
if not MOCK_HARDWARE:
    try:
        from picamera2 import Picamera2
    except ImportError:
        Picamera2 = None
else:
    Picamera2 = None

# ── YOLO ─────────────────────────────────────────────────────
from ultralytics import YOLO

# ── Our modules ──────────────────────────────────────────────
from src.modules import feedback, imu, gps_tracker
from src.modules.elevation import ElevationDetector
from src.modules.sensor_fusion import AlertManager, AlertEvent

# ── Logging ──────────────────────────────────────────────────
os.makedirs(os.path.dirname(LOG_PATH), exist_ok=True)
logging.basicConfig(
    filename=LOG_PATH,
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger("navicane")


# =====================================================================
#  Shared state (protected by _lock)
# =====================================================================
_lock = threading.Lock()

# Sensor readings
_distance_top: float = float("inf")
_distance_bottom: float = float("inf")
_gx: float = 0.0
_gy: float = 0.0
_gz: float = 0.0

# Detection results
_last_detected: list[str] = []
_last_results = None

# Mode toggle (#27)
_current_mode: str = MODE_DEFAULT   # "indoor" or "outdoor"

# Control flags
_running = True
_frame_count = 0


# =====================================================================
#  Hardware initialisation
# =====================================================================

def init_hardware():
    """Initialise all hardware. Returns (model, sensor_top, sensor_bottom, buzzer, picam2, mode_button)."""

    print("Initializing Smart Blind Stick System (Offline Mode)...")
    logger.info("Starting Smart Blind Stick System - Offline Mode")

    # ── YOLO model ───────────────────────────────────────────
    try:
        model = YOLO(MODEL_CUSTOM_PATH)
        print(f"✅ YOLOv8 model loaded — {len(model.names)} classes: {list(model.names.values())}")
        logger.info("Custom YOLOv8 model loaded: %s", list(model.names.values()))
    except Exception as e:
        logger.error("Custom model load failed: %s — falling back", e)
        model = YOLO(MODEL_FALLBACK_PATH)

    # ── Ultrasonic sensors ───────────────────────────────────
    try:
        sensor_top = DistanceSensor(echo=27, trigger=17)
        sensor_bottom = DistanceSensor(echo=24, trigger=22)
        print("✅ Ultrasonic sensors initialised")
        logger.info("Ultrasonic sensors initialised")
    except Exception as e:
        logger.error("Ultrasonic init failed: %s", e)
        sensor_top = sensor_bottom = None

    # ── Buzzer ───────────────────────────────────────────────
    buzzer = None
    try:
        buzzer = OutputDevice(5, active_high=False, initial_value=True)
        print("✅ Buzzer initialised on GPIO5")
    except Exception as e:
        logger.warning("Buzzer init failed: %s", e)

    # ── IMU (gyroscope + accelerometer) ──────────────────────
    imu.setup()

    # ── Feedback module (buzzer + TTS) ───────────────────────
    feedback.setup()

    # ── Pre-cache TTS audio for common phrases (Issue #25) ───
    print("🔊 Pre-caching TTS phrases...")
    feedback.precache_phrases()

    # ── Camera ───────────────────────────────────────────────
    picam2 = None
    if Picamera2 is not None:
        try:
            picam2 = Picamera2()
            profile = SENSITIVITY_PROFILES[_current_mode]
            picam2.preview_configuration.main.size = profile["camera_resolution"]
            picam2.preview_configuration.main.format = "RGB888"
            picam2.preview_configuration.align()
            picam2.configure("preview")
            picam2.start()
            print("✅ Camera initialised")
        except Exception as e:
            logger.error("Camera init failed: %s", e)
            picam2 = None
    else:
        print("ℹ️  Camera disabled (mock mode)")

    # ── GPS (Issue #17) ──────────────────────────────────────
    gps_tracker.setup()

    # ── Mode toggle button (Issue #27) ───────────────────────
    mode_button = None
    try:
        mode_button = Button(MODE_TOGGLE_PIN, pull_up=True, bounce_time=0.3)
        mode_button.when_pressed = _on_mode_toggle
        print(f"✅ Mode toggle button on GPIO{MODE_TOGGLE_PIN} (current: {_current_mode})")
    except Exception as e:
        logger.warning("Mode button init failed: %s — toggle via env var only", e)

    return model, sensor_top, sensor_bottom, buzzer, picam2, mode_button


# =====================================================================
#  Mode toggle (Issue #27)
# =====================================================================

def _on_mode_toggle():
    """Called when the physical mode button is pressed."""
    global _current_mode
    with _lock:
        _current_mode = "indoor" if _current_mode == "outdoor" else "outdoor"
    mode = _current_mode
    logger.info("Mode toggled to: %s", mode)
    feedback.speak(f"Switched to {mode} mode")


def get_active_profile() -> dict:
    """Return the sensitivity profile for the current mode."""
    with _lock:
        return SENSITIVITY_PROFILES[_current_mode]


# =====================================================================
#  Worker threads (Issue #23)
# =====================================================================

def sensor_thread(sensor_top, sensor_bottom):
    """Read ultrasonic distances + IMU gyroscope at ~20 Hz.

    Updates shared state behind _lock.
    """
    global _distance_top, _distance_bottom, _gx, _gy, _gz

    logger.info("Sensor thread started")
    while _running:
        try:
            dt = sensor_top.distance if sensor_top else float("inf")
            db = sensor_bottom.distance if sensor_bottom else float("inf")
        except Exception as e:
            logger.error("Sensor read error: %s", e)
            dt = db = float("inf")

        gx, gy, gz = imu.get_gyro_data()

        with _lock:
            _distance_top = dt
            _distance_bottom = db
            _gx, _gy, _gz = gx, gy, gz

        time.sleep(SENSOR_POLL_INTERVAL_S)

    logger.info("Sensor thread stopped")


def camera_thread(model, picam2):
    """Capture frames and run YOLO inference in a loop.

    Updates _last_detected and _last_results behind _lock.
    """
    global _last_detected, _last_results, _frame_count

    logger.info("Camera thread started")
    while _running:
        if picam2 is None:
            time.sleep(0.5)
            continue

        try:
            frame = picam2.capture_array()
            profile = get_active_profile()
            results = model(frame, conf=profile["confidence_threshold"])

            detected = []
            if len(results) > 0 and results[0].boxes is not None:
                for box in results[0].boxes:
                    cls_id = int(box.cls[0])
                    conf = float(box.conf[0])
                    if conf >= profile["confidence_threshold"]:
                        detected.append(model.names[cls_id])

            with _lock:
                _last_detected = detected
                _last_results = results
                _frame_count += 1

            # GUI display (non-headless only)
            if not HEADLESS:
                with _lock:
                    dt, db = _distance_top, _distance_bottom
                annotated = results[0].plot()
                cv2.putText(annotated, f"Top: {dt:.2f}m", (10, 30),
                            cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 255, 0), 2)
                cv2.putText(annotated, f"Bottom: {db:.2f}m", (10, 70),
                            cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 200, 255), 2)
                cv2.putText(annotated, f"Mode: {_current_mode.upper()}", (10, 110),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 0), 2)
                cv2.imshow("navicane", annotated)
                if cv2.waitKey(1) & 0xFF == ord("q"):
                    break

        except Exception as e:
            logger.error("Camera/inference error: %s", e)
            time.sleep(0.1)

    logger.info("Camera thread stopped")


def fall_detection_thread(alert_mgr):
    """Monitor accelerometer for fall events at ~20 Hz.

    Falls are always dispatched immediately (priority 100, cooldown 0).
    """
    logger.info("Fall detection thread started")
    while _running:
        if imu.is_available() and imu.is_fall():
            event = AlertEvent(
                source="fall",
                message="Fall detected, are you okay",
                action="vibrate+speak",
            )
            if alert_mgr.should_alert(event):
                alert_mgr.dispatch(event)

        time.sleep(SENSOR_POLL_INTERVAL_S)

    logger.info("Fall detection thread stopped")


# =====================================================================
#  Alert logic
# =====================================================================

def build_speech(objects_list: list[str], level: str) -> str:
    """Build a TTS announcement string from detected object names."""
    counts = Counter(objects_list)
    parts = [f"{c} {n}" if c == 1 else f"{c} {n}s" for n, c in counts.items()]
    prefix = "At head level: " if level == "head" else "At ground level: "
    return prefix + f"Detected: {', '.join(parts)}"


# =====================================================================
#  Main loop
# =====================================================================

def main():
    global _running

    model, sensor_top, sensor_bottom, buzzer, picam2, mode_button = init_hardware()
    alert_mgr = AlertManager()
    elev_top = ElevationDetector()
    elev_bottom = ElevationDetector()

    # ── Print system banner ──────────────────────────────────
    print("\n" + "=" * 60)
    print("🦯 SMART BLIND STICK SYSTEM")
    print("=" * 60)
    print(f"  Mode:      {_current_mode.upper()}")
    print(f"  Camera:    {'ACTIVE' if picam2 else 'DISABLED'}")
    print(f"  IMU:       {'ACTIVE' if imu.is_available() else 'DISABLED'}")
    print(f"  GPS:       {'ACTIVE' if gps_tracker.is_available() else 'DISABLED'}")
    print(f"  Headless:  {HEADLESS}")
    print("=" * 60)
    print("Press Ctrl+C to stop gracefully")
    print("=" * 60)

    # ── Start worker threads (Issue #23) ─────────────────────
    threads = []

    t_sensor = threading.Thread(target=sensor_thread, args=(sensor_top, sensor_bottom), daemon=True)
    t_sensor.start()
    threads.append(t_sensor)

    t_camera = threading.Thread(target=camera_thread, args=(model, picam2), daemon=True)
    t_camera.start()
    threads.append(t_camera)

    t_fall = threading.Thread(target=fall_detection_thread, args=(alert_mgr,), daemon=True)
    t_fall.start()
    threads.append(t_fall)

    logger.info("All threads started — entering main arbitration loop")

    # ── Startup announcement ─────────────────────────────────
    time.sleep(2)
    feedback.speak_cached("Smart stick ready")

    # ── Main arbitration loop ────────────────────────────────
    try:
        while _running:
            if os.path.exists(STOP_SIGNAL_PATH):
                logger.info("Stop signal file detected")
                break

            profile = get_active_profile()

            # Read shared sensor state
            with _lock:
                dt = _distance_top
                db = _distance_bottom
                gx, gy, gz = _gx, _gy, _gz
                detected = list(_last_detected)

            # ── Elevation alerts ─────────────────────────────
            elev_type_top, elev_action_top = elev_top.update(dt, gx, gy, gz)
            elev_type_bottom, elev_action_bottom = elev_bottom.update(db, gx, gy, gz)

            if elev_type_top:
                event = AlertEvent("elevation", elev_type_top, elev_action_top or "buzz+speak")
                if alert_mgr.should_alert(event):
                    alert_mgr.dispatch(event)

            elif elev_type_bottom:
                event = AlertEvent("elevation", elev_type_bottom, elev_action_bottom or "buzz+speak")
                if alert_mgr.should_alert(event):
                    alert_mgr.dispatch(event)

            # ── Object detection alerts ──────────────────────
            thresh = profile["detection_threshold_m"]
            if detected and (dt <= thresh or db <= thresh):
                level = "head" if dt <= thresh else "ground"
                msg = build_speech(detected, level)
                event = AlertEvent("camera", msg, "buzz+speak")
                if alert_mgr.should_alert(event):
                    alert_mgr.dispatch(event)

            # ── GPS periodic announcement ────────────────────
            if gps_tracker.is_available() and gps_tracker.has_fix():
                event = AlertEvent("gps", gps_tracker.format_location(), "speak")
                if alert_mgr.should_alert(event):
                    alert_mgr.dispatch(event)

            # ── Terminal monitoring (every 10th cycle) ───────
            if _frame_count % 10 == 0 and _frame_count > 0:
                ts = time.strftime("%H:%M:%S")
                imu_status = "ON" if imu.is_available() else "OFF"
                print(f"[{ts}] Top:{dt:5.2f}m Bot:{db:5.2f}m "
                      f"Gyro({imu_status}): X:{gx:6.1f} Y:{gy:6.1f} Z:{gz:6.1f} "
                      f"Mode:{_current_mode} Frames:{_frame_count}")

            time.sleep(SENSOR_POLL_INTERVAL_S * 2)

    except KeyboardInterrupt:
        print("\n🛑 Stopping...")
        logger.info("System stopped by user (Ctrl+C)")
    except Exception as e:
        print(f"❌ Unexpected error: {e}")
        logger.error("Unexpected error: %s", e)
    finally:
        _running = False
        time.sleep(0.3)  # let threads wind down
        cleanup(picam2, buzzer)


def cleanup(picam2, buzzer):
    """Release all hardware resources."""
    try:
        feedback.silence()
        if buzzer:
            buzzer.off()
        if picam2:
            picam2.stop()
        gps_tracker.stop()
        if not HEADLESS:
            cv2.destroyAllWindows()
        print("✅ System stopped successfully.")
        logger.info("Cleanup complete")
        feedback.speak("Smart Blind Stick System has been stopped.", blocking=True)
    except Exception as e:
        logger.error("Cleanup error: %s", e)


if __name__ == "__main__":
    main()
