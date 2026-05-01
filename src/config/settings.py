"""
navicane — Central configuration and constants.

All hardware pin assignments, detection thresholds, and model paths
are defined here so they can be changed in one place.
"""

import os

# ── Paths ────────────────────────────────────────────────────
BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
MODEL_CUSTOM_PATH = os.path.join(BASE_DIR, "models", "best.pt")
MODEL_FALLBACK_PATH = os.path.join(BASE_DIR, "models", "yolov8n.pt")
LOG_PATH = os.path.join(BASE_DIR, "logs", "blind_stick.log")
AUDIO_CACHE_DIR = os.path.join(BASE_DIR, "audio_cache")

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
