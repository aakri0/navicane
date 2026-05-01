import cv2
import time
import threading
from collections import Counter
from ultralytics import YOLO
import os
import sys
from time import sleep
import smbus2
import subprocess
import logging

# ── Load config (must happen before gpiozero imports) ────────
# Adds the project root to sys.path so 'src.config' is importable
_project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

from src.config.settings import (
    MODEL_CUSTOM_PATH, MODEL_FALLBACK_PATH, LOG_PATH,
    HEADLESS, MOCK_HARDWARE, STOP_SIGNAL_PATH,
    DETECTION_THRESHOLD_M, CONFIDENCE_THRESHOLD, DETECTION_COOLDOWN_S,
    ELEVATION_COOLDOWN_S, ELEVATION_THRESHOLDS,
    MPU6050_ADDR, MPU6050_PWR_MGMT_1,
    MPU6050_GYRO_XOUT_H, MPU6050_GYRO_YOUT_H, MPU6050_GYRO_ZOUT_H,
)

# Now safe to import gpiozero (mock pin factory already set if needed)
from gpiozero import DistanceSensor, OutputDevice

# Import picamera2 only when real hardware is available
if not MOCK_HARDWARE:
    try:
        from picamera2 import Picamera2
    except ImportError:
        print("⚠️  picamera2 not available — camera disabled")
        Picamera2 = None
else:
    Picamera2 = None

# Set up logging for debugging and monitoring
os.makedirs(os.path.dirname(LOG_PATH), exist_ok=True)
logging.basicConfig(
    filename=LOG_PATH,
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

print("Initializing Smart Blind Stick System (Offline Mode)...")
logging.info("Starting Smart Blind Stick System - Offline Mode")

# ===========================
# PIN CONNECTIONS SUMMARY
# ===========================
# Top Ultrasonic Sensor (Head Level)
#   VCC  -> Pi 5V (Pin 2 or 4)
#   GND  -> Pi GND (Pin 6 or 9)
#   Trig -> GPIO17 (Pin 11)
#   Echo -> GPIO27 (Pin 13)
# Bottom Ultrasonic Sensor (Ground Level)
#   VCC  -> Pi 5V (shared)
#   GND  -> Pi GND (shared)
#   Trig -> GPIO22 (Pin 15)
#   Echo -> GPIO24 (Pin 18)
# MPU6050 Gyroscope (I2C)
#   VCC  -> Pi 3.3V (Pin 1)
#   GND  -> Pi GND (Pin 6)
#   SDA  -> GPIO2 (Pin 3)
#   SCL  -> GPIO3 (Pin 5)
# Buzzer (via BC557 PNP transistor)
#   Emitter   -> Pi 3.3V (Pin 1)
#   Collector -> Buzzer (+)
#   Buzzer (–) -> Pi GND
#   Base      -> GPIO5 (Pin 29)
# ===========================

# Offline Text-to-Speech function using espeak
def speak_text_offline(text, speed=150, voice='en'):
    """
    Offline text-to-speech using espeak
    Args:
        text: Text to speak
        speed: Speech speed (words per minute)
        voice: Voice language/accent
    """
    try:
        # Use espeak for offline speech synthesis
        subprocess.run(['espeak', '-s', str(speed), '-v', voice, text], 
                      check=True, capture_output=True, timeout=10)
        logging.info(f"Spoke: {text[:50]}...")
        print(f"🔊 Speaking: {text}")
    except subprocess.TimeoutExpired:
        logging.error(f"Speech timeout for: {text}")
        print(f"Speech timeout: {text}")
    except FileNotFoundError:
        logging.error("espeak not found. Install with: sudo apt install espeak")
        print("Error: espeak not installed")
    except Exception as e:
        logging.error(f"Speech error: {e}")
        print(f"Speech error: {e}")

# Load YOLO model — path comes from config / env var
try:
    model = YOLO(MODEL_CUSTOM_PATH)
    logging.info("Custom YOLOv8 model loaded successfully")
    print("✅ Custom YOLOv8 model loaded successfully")
    
    # Print model information
    print("="*50)
    print("Custom Model Information:")
    print(f"Model classes: {list(model.names.values())}")
    print(f"Number of classes: {len(model.names)}")
    print("="*50)
    logging.info(f"Model has {len(model.names)} classes: {list(model.names.values())}")
    
except Exception as e:
    logging.error(f"Failed to load custom model: {e}")
    print(f"❌ Failed to load custom model: {e}")
    print("Falling back to standard YOLOv8 model...")
    model = YOLO(MODEL_FALLBACK_PATH)

# Gyroscope (MPU6050) setup — constants come from config
try:
    bus = smbus2.SMBus(1)
    bus.write_byte_data(MPU6050_ADDR, MPU6050_PWR_MGMT_1, 0)
    gyroscope_available = True
    print("✅ MPU6050 gyroscope initialized successfully")
    logging.info("MPU6050 gyroscope initialized successfully")
except Exception as e:
    print(f"⚠️ Gyroscope initialization failed: {e}")
    logging.warning(f"Gyroscope initialization failed: {e}")
    gyroscope_available = False

# Initialize sensors and peripherals
try:
    sensor_top = DistanceSensor(echo=27, trigger=17)      # Top (head-level)
    sensor_bottom = DistanceSensor(echo=24, trigger=22)   # Bottom (ground-level)
    print("✅ Ultrasonic sensors initialized successfully")
    logging.info("Ultrasonic sensors initialized successfully")
except Exception as e:
    print(f"❌ Ultrasonic sensor initialization failed: {e}")
    logging.error(f"Ultrasonic sensor initialization failed: {e}")
    exit(1)

try:
    buzzer = OutputDevice(5, active_high=False, initial_value=True)  # GPIO5, active-low for PNP
    print("✅ Buzzer initialized on GPIO5")
    logging.info("Buzzer initialized on GPIO5")
except Exception as e:
    print(f"⚠️ Buzzer initialization failed: {e}")
    logging.warning(f"Buzzer initialization failed: {e}")
    buzzer = None

picam2 = None
if Picamera2 is not None:
    try:
        picam2 = Picamera2()
        picam2.preview_configuration.main.size = (1280, 720)
        picam2.preview_configuration.main.format = "RGB888"
        picam2.preview_configuration.align()
        picam2.configure("preview")
        picam2.start()
        print("✅ Camera initialized successfully")
        logging.info("Camera initialized successfully")
    except Exception as e:
        print(f"❌ Camera initialization failed: {e}")
        logging.error(f"Camera initialization failed: {e}")
        picam2 = None
else:
    print("ℹ️  Camera disabled (mock mode or picamera2 unavailable)")
    logging.info("Camera disabled — running without live feed")

# Parameters — use values from central config
detection_threshold = DETECTION_THRESHOLD_M
confidence_threshold = CONFIDENCE_THRESHOLD
last_detection_time = 0
last_elevation_time = 0
elevation_cooldown = ELEVATION_COOLDOWN_S
elevation_thresholds = ELEVATION_THRESHOLDS

prev_distance_top = None
prev_distance_bottom = None
distance_history_top = []
distance_history_bottom = []
gyro_print_counter = 0

def read_raw_data(addr):
    """Read raw data from MPU6050 gyroscope"""
    try:
        high = bus.read_byte_data(MPU6050_ADDR, addr)
        low = bus.read_byte_data(MPU6050_ADDR, addr+1)
        value = ((high << 8) | low)
        if value > 32768:
            value = value - 65536
        return value
    except Exception as e:
        logging.error(f"Error reading gyroscope data: {e}")
        return 0

def get_gyro_data():
    """Get gyroscope data in degrees/sec"""
    if not gyroscope_available:
        return 0, 0, 0
    try:
        gx = read_raw_data(MPU6050_GYRO_XOUT_H) / 131.0
        gy = read_raw_data(MPU6050_GYRO_YOUT_H) / 131.0
        gz = read_raw_data(MPU6050_GYRO_ZOUT_H) / 131.0
        return gx, gy, gz
    except Exception as e:
        logging.error(f"Error getting gyroscope data: {e}")
        return 0, 0, 0

def detect_elevation_changes(current_distance, prev_distance, distance_history, gx, gy, gz):
    """Detect elevation changes using distance and gyroscope data"""
    elevation_type = None
    alert_type = None
    distance_history.append(current_distance)
    if len(distance_history) > 10:
        distance_history.pop(0)
    
    if prev_distance is not None and len(distance_history) >= 3:
        vertical_change = abs(current_distance - prev_distance)
        if vertical_change >= elevation_thresholds['small_step']:
            elevation_type = "Small step or drop detected"
            alert_type = "short_buzzer"
        if vertical_change >= elevation_thresholds['large_step']:
            elevation_type = "Large step or drop detected"
            alert_type = "vibration_voice"
        if len(distance_history) >= 3:
            recent_changes = [abs(distance_history[i] - distance_history[i-1])
                              for i in range(1, len(distance_history))]
            if any(change >= elevation_thresholds['uneven_terrain'] for change in recent_changes[-3:]):
                if elevation_type is None:
                    elevation_type = "Uneven terrain detected"
                    alert_type = "mild_vibration"
    
    if gyroscope_available and abs(gy) >= elevation_thresholds['steep_slope']:
        elevation_type = "Steep slope detected"
        alert_type = "voice_alert"
    
    return elevation_type, alert_type

def handle_elevation_alert(elevation_type, alert_type, level):
    """Handle different types of elevation alerts"""
    def speak_thread():
        try:
            if level == "head":
                prefix = "Warning: Obstacle ahead at head level. "
            else:
                prefix = "Warning: Obstacle ahead at ground level. "
                
            if "steep slope" in elevation_type.lower():
                text = prefix + "Steep slope ahead. Proceed with caution."
            elif "large step" in elevation_type.lower():
                text = prefix + "Large elevation change detected. Watch your step."
            elif "small step" in elevation_type.lower():
                text = prefix + "Small step detected."
            elif "uneven terrain" in elevation_type.lower():
                text = prefix + "Uneven terrain ahead. Be careful."
            else:
                text = prefix + elevation_type
                
            logging.info(f"Speaking elevation alert: {text}")
            speak_text_offline(text)
        except Exception as e:
            logging.error(f"Elevation speech error: {e}")

    def short_buzzer():
        if buzzer:
            for _ in range(3):
                buzzer.on()
                sleep(0.2)
                buzzer.off()
                sleep(0.1)

    def vibration_voice():
        if buzzer:
            for _ in range(5):
                buzzer.on()
                sleep(0.1)
                buzzer.off()
                sleep(0.1)
        speak_thread()

    def mild_vibration():
        if buzzer:
            for _ in range(2):
                buzzer.on()
                sleep(0.3)
                buzzer.off()
                sleep(0.2)

    if alert_type == "short_buzzer":
        threading.Thread(target=short_buzzer, daemon=True).start()
    elif alert_type == "vibration_voice":
        threading.Thread(target=vibration_voice, daemon=True).start()
    elif alert_type == "voice_alert":
        threading.Thread(target=speak_thread, daemon=True).start()
    elif alert_type == "mild_vibration":
        threading.Thread(target=mild_vibration, daemon=True).start()

def print_gyro_values_terminal(gx, gy, gz, distance_top, distance_bottom):
    """Print sensor values to terminal for monitoring"""
    global gyro_print_counter
    if gyro_print_counter % 10 == 0:
        timestamp = time.strftime("%H:%M:%S", time.localtime())
        gyro_status = "ACTIVE" if gyroscope_available else "DISABLED"
        print(f"[{timestamp}] Top: {distance_top:6.2f}m | Bottom: {distance_bottom:6.2f}m | "
              f"Gyro ({gyro_status}): X: {gx:7.2f}°/s, Y: {gy:7.2f}°/s, Z: {gz:7.2f}°/s")
        print("-" * 80)
    gyro_print_counter += 1

def extract_detected_objects(results):
    """Extract object names from YOLO results"""
    detected_objects = []
    if len(results) > 0 and results[0].boxes is not None:
        for box in results[0].boxes:
            class_id = int(box.cls[0])
            class_name = model.names[class_id]
            confidence = float(box.conf[0])
            if confidence >= confidence_threshold:
                detected_objects.append(class_name)
    return detected_objects

def speak_detection_results(objects_list, level):
    """Convert detection results to speech announcements.

    Uses a simple Counter since the custom model has flat class names
    (Ambulance, Bus, Car, Tempo, Tractor, Truck) — no category grouping needed.
    """
    if not objects_list:
        return
    try:
        object_counts = Counter(objects_list)
        parts = []
        for obj, count in object_counts.items():
            if count == 1:
                parts.append(f"1 {obj}")
            else:
                parts.append(f"{count} {obj}s")

        prefix = "At head level: " if level == "head" else "At ground level: "
        speech_text = prefix + f"Detected: {', '.join(parts)}"
        print(f"🔊 Speaking objects: {speech_text}")
        logging.info(f"Object detection speech: {speech_text}")
        speak_text_offline(speech_text)

    except Exception as e:
        logging.error(f"Detection speech error: {e}")
        print(f"Speech error: {e}")

def startup_announcement():
    """Announce system startup"""
    startup_message = "Smart Blind Stick System is now active and ready."
    print(f"🔊 {startup_message}")
    logging.info("System startup announcement")
    speak_text_offline(startup_message)

def main():
    """Main system loop"""
    global prev_distance_top, prev_distance_bottom, last_detection_time, last_elevation_time
    global gyro_print_counter
    
    print("\n" + "="*60)
    print("🦯 SMART BLIND STICK SYSTEM - OFFLINE MODE")
    print("="*60)
    print("Top sensor (Trig/Echo): GPIO17/GPIO27")
    print("Bottom sensor (Trig/Echo): GPIO22/GPIO24")
    print("Buzzer (via BC557): GPIO5")
    print("MPU6050 Gyro: I2C (GPIO2/GPIO3)")
    print("Custom YOLOv8 Model: Indian Roads Detection")
    print("Text-to-Speech: espeak (offline)")
    print("="*60)
    print("System Status: RUNNING")
    print("Press Ctrl+C to stop gracefully")
    print("="*60)
    
    logging.info("Main system loop starting")
    
    # Wait a moment for everything to initialize
    time.sleep(2)
    
    # Startup announcement
    startup_announcement()
    
    try:
        frame_count = 0
        while True:
            # Check for stop signal file
            if os.path.exists(STOP_SIGNAL_PATH):
                logging.info("Stop signal file detected")
                break
                
            try:
                distance_top = sensor_top.distance
                distance_bottom = sensor_bottom.distance
            except Exception as e:
                logging.error(f"Sensor read error: {e}")
                distance_top = float('inf')
                distance_bottom = float('inf')

            current_time = time.time()
            gx, gy, gz = get_gyro_data() if gyroscope_available else (0, 0, 0)
            print_gyro_values_terminal(gx, gy, gz, distance_top, distance_bottom)

            # Elevation detection (priority: top sensor)
            elevation_type_top, alert_type_top = detect_elevation_changes(
                distance_top, prev_distance_top, distance_history_top, gx, gy, gz)
            elevation_type_bottom, alert_type_bottom = detect_elevation_changes(
                distance_bottom, prev_distance_bottom, distance_history_bottom, gx, gy, gz)
            prev_distance_top = distance_top
            prev_distance_bottom = distance_bottom

            elevation_detected = False

            if elevation_type_top and (current_time - last_elevation_time) > elevation_cooldown:
                print(f"🚨 Elevation alert (head level): {elevation_type_top}")
                logging.info(f"Elevation alert (head level): {elevation_type_top}")
                handle_elevation_alert(elevation_type_top, alert_type_top, "head")
                last_elevation_time = current_time
                elevation_detected = True
            elif elevation_type_bottom and (current_time - last_elevation_time) > elevation_cooldown:
                print(f"🚨 Elevation alert (ground level): {elevation_type_bottom}")
                logging.info(f"Elevation alert (ground level): {elevation_type_bottom}")
                handle_elevation_alert(elevation_type_bottom, alert_type_bottom, "ground")
                last_elevation_time = current_time
                elevation_detected = True

            # Object detection using custom model
            try:
                if picam2 is not None:
                    frame = picam2.capture_array()
                    results = model(frame, conf=confidence_threshold)
                else:
                    # No camera — skip detection this cycle
                    time.sleep(0.1)
                    continue
                
                # GUI display (skipped in headless / Docker mode)
                if not HEADLESS:
                    annotated_frame = results[0].plot()
                    cv2.putText(annotated_frame, f"Top: {distance_top:.2f}m", (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 255, 0), 2)
                    cv2.putText(annotated_frame, f"Bottom: {distance_bottom:.2f}m", (10, 70), cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 200, 255), 2)
                    cv2.putText(annotated_frame, "Custom YOLOv8 - OFFLINE", (10, 110), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 0), 2)
                    
                    if elevation_detected:
                        cv2.putText(annotated_frame, "ELEVATION ALERT ACTIVE", (10, 150), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 255, 255), 2)
                    
                    cv2.imshow("Smart Blind Stick - Indian Roads Detection", annotated_frame)
                
            except Exception as e:
                logging.error(f"Camera/detection error: {e}")
                continue

            # Proximity and alert logic (priority: top sensor)
            if (distance_top <= detection_threshold or distance_bottom <= detection_threshold) and (current_time - last_detection_time) > 5:
                detected_objects = extract_detected_objects(results)
                if detected_objects:
                    print(f"🎯 Detected objects: {detected_objects}")
                    logging.info(f"Detected objects: {detected_objects}")
                    
                    # If elevation alert active, wait before object announcement
                    if elevation_detected:
                        time.sleep(2)
                    
                    if distance_top <= detection_threshold:
                        speak_detection_results(detected_objects, "head")
                    elif distance_bottom <= detection_threshold:
                        speak_detection_results(detected_objects, "ground")
                    last_detection_time = current_time

            # Handle exit: GUI key press or headless sleep
            if not HEADLESS:
                if cv2.waitKey(1) & 0xFF == ord('q'):
                    break
            else:
                time.sleep(0.05)
            
            frame_count += 1
            if frame_count % 1000 == 0:
                logging.info(f"System running normally - {frame_count} frames processed")
                
    except KeyboardInterrupt:
        print("\n🛑 Stopping Smart Blind Stick System...")
        logging.info("System stopped by user (Ctrl+C)")
    except Exception as e:
        print(f"❌ Unexpected error: {e}")
        logging.error(f"Unexpected error in main loop: {e}")
    finally:
        cleanup_system()

def cleanup_system():
    """Clean up resources before exit"""
    try:
        if buzzer:
            buzzer.off()
        if picam2 is not None:
            picam2.stop()
        if not HEADLESS:
            cv2.destroyAllWindows()
        print("✅ Smart Blind Stick System stopped successfully.")
        logging.info("System cleanup completed successfully")
        
        # Final announcement
        speak_text_offline("Smart Blind Stick System has been stopped.")
        
    except Exception as e:
        print(f"⚠️ Error during cleanup: {e}")
        logging.error(f"Error during cleanup: {e}")

if __name__ == '__main__':
    main()
