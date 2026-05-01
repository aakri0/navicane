"""
navicane.modules.camera_detect — YOLOv8 camera detection.

Loads the custom-trained model and provides detect() for per-frame inference.
Camera (picamera2) is optional — when unavailable the module still loads
the YOLO model for file-based inference.
"""

import logging
from collections import Counter

from ultralytics import YOLO

from src.config.settings import (
    MODEL_CUSTOM_PATH, MODEL_FALLBACK_PATH,
    CONFIDENCE_THRESHOLD, CAMERA_RESOLUTION, CAMERA_FORMAT,
    MOCK_HARDWARE,
)

logger = logging.getLogger(__name__)

_model = None
_camera = None
_Picamera2 = None   # lazily resolved


def setup():
    """Load the YOLO model and (optionally) start the Pi Camera.

    Camera is skipped in mock mode or when picamera2 is not installed.
    The YOLO model is always loaded so file-based inference still works.
    """
    global _model, _camera, _Picamera2

    # ── Load YOLO model ──────────────────────────────────────
    try:
        _model = YOLO(MODEL_CUSTOM_PATH)
        logger.info(
            "Custom YOLOv8 model loaded — %d classes: %s",
            len(_model.names), list(_model.names.values()),
        )
    except Exception as e:
        logger.error("Failed to load custom model: %s — falling back", e)
        _model = YOLO(MODEL_FALLBACK_PATH)

    # ── Start camera (optional) ──────────────────────────────
    if MOCK_HARDWARE:
        logger.info("Camera skipped (mock hardware mode)")
        return

    try:
        from picamera2 import Picamera2
        _Picamera2 = Picamera2
    except ImportError:
        logger.warning("picamera2 not available — camera disabled")
        return

    try:
        _camera = _Picamera2()
        _camera.preview_configuration.main.size = CAMERA_RESOLUTION
        _camera.preview_configuration.main.format = CAMERA_FORMAT
        _camera.preview_configuration.align()
        _camera.configure("preview")
        _camera.start()
        logger.info("Camera initialised successfully.")
    except Exception as e:
        logger.error("Camera initialisation failed: %s", e)
        _camera = None


def has_camera() -> bool:
    """Return True if the camera is available and running."""
    return _camera is not None


def get_model():
    """Return the loaded YOLO model (for external use by main.py)."""
    return _model


def capture_frame():
    """Capture a single frame from the camera.

    Returns:
        numpy array (H, W, 3) or None if camera is unavailable.
    """
    if _camera is None:
        return None
    try:
        return _camera.capture_array()
    except Exception as e:
        logger.error("Frame capture error: %s", e)
        return None


def detect(frame):
    """Run YOLOv8 inference on a frame.

    Args:
        frame: numpy array (H, W, 3).

    Returns:
        results: Raw YOLO results object.
        detected: List of class name strings above the confidence threshold.
    """
    results = _model(frame, conf=CONFIDENCE_THRESHOLD)
    detected = []
    if len(results) > 0 and results[0].boxes is not None:
        for box in results[0].boxes:
            class_id = int(box.cls[0])
            confidence = float(box.conf[0])
            if confidence >= CONFIDENCE_THRESHOLD:
                detected.append(_model.names[class_id])
    return results, detected


def build_announcement(detected_objects: list[str], level: str) -> str | None:
    """Build a human-readable announcement string from detections.

    Groups objects by name and count. Since the custom model has only
    6 classes (Ambulance, Bus, Car, Tempo, Tractor, Truck) we skip
    the category lookup and just list what was seen.

    Args:
        detected_objects: List of class name strings.
        level: "head" or "ground".

    Returns:
        Announcement string, or None if nothing detected.
    """
    if not detected_objects:
        return None

    counts = Counter(detected_objects)
    parts = []
    for obj, count in counts.items():
        parts.append(f"{count} {obj}" if count == 1 else f"{count} {obj}s")

    prefix = "At head level: " if level == "head" else "At ground level: "
    return prefix + f"Detected: {', '.join(parts)}"


def stop():
    """Stop the camera cleanly."""
    if _camera:
        try:
            _camera.stop()
            logger.info("Camera stopped.")
        except Exception as e:
            logger.error("Error stopping camera: %s", e)
