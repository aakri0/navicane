"""
navicane.modules.camera_detect — YOLOv8 camera detection.

Loads the custom-trained model at import time and provides
capture_and_detect() for per-frame inference.
"""

import logging
from collections import Counter

from picamera2 import Picamera2
from ultralytics import YOLO

from src.config.settings import (
    MODEL_CUSTOM_PATH, MODEL_FALLBACK_PATH,
    CONFIDENCE_THRESHOLD, CAMERA_RESOLUTION, CAMERA_FORMAT,
    CLASS_CATEGORIES,
)

logger = logging.getLogger(__name__)

_model = None
_camera = None


def setup():
    """Load the YOLO model and start the Pi Camera. Call once at startup."""
    global _model, _camera

    # Load model
    try:
        _model = YOLO(MODEL_CUSTOM_PATH)
        logger.info(
            "Custom YOLOv8 model loaded — %d classes: %s",
            len(_model.names), list(_model.names.values()),
        )
    except Exception as e:
        logger.error("Failed to load custom model: %s — falling back", e)
        _model = YOLO(MODEL_FALLBACK_PATH)

    # Start camera
    try:
        _camera = Picamera2()
        _camera.preview_configuration.main.size = CAMERA_RESOLUTION
        _camera.preview_configuration.main.format = CAMERA_FORMAT
        _camera.preview_configuration.align()
        _camera.configure("preview")
        _camera.start()
        logger.info("Camera initialised successfully.")
    except Exception as e:
        logger.error("Camera initialisation failed: %s", e)
        raise


def capture_frame():
    """Capture a single frame from the camera."""
    return _camera.capture_array()


def detect(frame):
    """Run YOLOv8 inference on a frame.

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


def categorise(detected_objects: list[str]) -> dict[str, list[str]]:
    """Group detected object names into semantic categories."""
    categorised = {}
    for obj_name in detected_objects:
        obj_class_id = None
        for cid, cname in _model.names.items():
            if cname == obj_name:
                obj_class_id = cid
                break
        if obj_class_id is not None:
            for category, class_ids in CLASS_CATEGORIES.items():
                if obj_class_id in class_ids:
                    categorised.setdefault(category, []).append(obj_name)
                    break
    return categorised


def build_announcement(detected_objects: list[str], level: str) -> str | None:
    """Build a human-readable announcement string from detections."""
    categorised = categorise(detected_objects)
    if not categorised:
        return None

    parts = []
    for category, objects in categorised.items():
        counts = Counter(objects)
        if len(counts) == 1:
            obj, count = list(counts.items())[0]
            parts.append(f"{count} {obj}" if count == 1 else f"{count} {obj}s")
        else:
            descs = []
            for obj, count in counts.items():
                descs.append(obj if count == 1 else f"{count} {obj}s")
            parts.append(f"{category}: {', '.join(descs)}")

    prefix = "At head level: " if level == "head" else "At ground level: "
    return prefix + f"Detected: {', '.join(parts)}"


def stop():
    """Stop the camera cleanly."""
    if _camera:
        _camera.stop()
        logger.info("Camera stopped.")
