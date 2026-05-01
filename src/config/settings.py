"""
navicane — Central configuration and constants.

All hardware pin assignments, detection thresholds, and model paths
are defined here so they can be changed in one place.

Every path and toggle can be overridden via environment variables,
which is how Docker injects configuration at runtime.
"""

import os

# ── Runtime mode ─────────────────────────────────────────────
# NAVICANE_HEADLESS=1  → skip cv2.imshow (for Docker / systemd)
# NAVICANE_MOCK=1      → use mock GPIO pin factory (for Mac dev)
HEADLESS = os.environ.get("NAVICANE_HEADLESS", "0") == "1"
MOCK_HARDWARE = os.environ.get("NAVICANE_MOCK", "0") == "1"

# If mock mode requested, set gpiozero to use mock pin factory
# (must be set BEFORE any gpiozero import)
if MOCK_HARDWARE:
    os.environ.setdefault("GPIOZERO_PIN_FACTORY", "mock")

# ── Paths (overridable via env vars) ─────────────────────────
BASE_DIR = os.environ.get(
    "NAVICANE_BASE_DIR",
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
)
MODEL_CUSTOM_PATH = os.environ.get(
    "NAVICANE_MODEL_PATH",
    os.path.join(BASE_DIR, "models", "best.pt"),
)
MODEL_FALLBACK_PATH = os.environ.get(
    "NAVICANE_MODEL_FALLBACK",
    os.path.join(BASE_DIR, "models", "yolov8n.pt"),
)
LOG_PATH = os.environ.get(
    "NAVICANE_LOG_PATH",
    os.path.join(BASE_DIR, "logs", "blind_stick.log"),
)
AUDIO_CACHE_DIR = os.path.join(BASE_DIR, "audio_cache")
STOP_SIGNAL_PATH = os.environ.get(
    "NAVICANE_STOP_SIGNAL",
    "/tmp/stop_blind_stick",
)

# ── GPIO Pin Assignments ─────────────────────────────────────
# Top Ultrasonic Sensor (Head Level)
ULTRASONIC_TOP_TRIGGER = 17   # GPIO17 (Pin 11)
ULTRASONIC_TOP_ECHO = 27      # GPIO27 (Pin 13)

# Bottom Ultrasonic Sensor (Ground Level)
ULTRASONIC_BOTTOM_TRIGGER = 22  # GPIO22 (Pin 15)
ULTRASONIC_BOTTOM_ECHO = 24     # GPIO24 (Pin 18)

# Buzzer (via BC557 PNP transistor)
BUZZER_PIN = 5                  # GPIO5 (Pin 29)
BUZZER_ACTIVE_HIGH = False      # PNP transistor: active-low

# ── MPU-6050 IMU (I2C) ──────────────────────────────────────
MPU6050_ADDR = 0x68
MPU6050_PWR_MGMT_1 = 0x6B
MPU6050_GYRO_XOUT_H = 0x43
MPU6050_GYRO_YOUT_H = 0x45
MPU6050_GYRO_ZOUT_H = 0x47

# ── Detection Parameters ────────────────────────────────────
DETECTION_THRESHOLD_M = 1.0       # metres — alert if object closer than this
CONFIDENCE_THRESHOLD = 0.3        # YOLOv8 confidence floor
BUZZER_DURATION_S = 3             # seconds
DETECTION_COOLDOWN_S = 5          # seconds between same-source alerts

# ── Elevation Detection ──────────────────────────────────────
ELEVATION_COOLDOWN_S = 2          # seconds
ELEVATION_THRESHOLDS = {
    "small_step": 0.025,          # metres
    "large_step": 0.10,
    "uneven_terrain": 0.015,
    "steep_slope": 10.0,          # degrees/sec (gyro Y-axis)
}

# ── TTS ──────────────────────────────────────────────────────
TTS_SPEED = 150                   # espeak words-per-minute
TTS_VOICE = "en"

# ── Camera ───────────────────────────────────────────────────
CAMERA_RESOLUTION = (1280, 720)
CAMERA_FORMAT = "RGB888"

# ── Object Categories (Indian Roads Detection model) ─────────
CLASS_CATEGORIES = {
    "person": [0],
    "vehicles": [1, 2, 3, 4, 5, 6, 7, 8, 9, 17, 18],
    "animals": [10, 11, 12, 13, 14],
    "infrastructure": [15, 16, 19, 20, 21, 22, 29, 30],
    "hazards": [23],
    "nature": [24, 25, 35],
    "buildings": [26, 27, 33],
    "emergency": [9],
    "traffic": [19, 28, 32],
}
