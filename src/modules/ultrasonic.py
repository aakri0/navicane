"""
navicane.modules.ultrasonic — Ultrasonic distance measurement.

Wraps two HC-SR04 sensors (top / bottom) via gpiozero.
"""

import logging
from gpiozero import DistanceSensor

from src.config.settings import (
    ULTRASONIC_TOP_TRIGGER, ULTRASONIC_TOP_ECHO,
    ULTRASONIC_BOTTOM_TRIGGER, ULTRASONIC_BOTTOM_ECHO,
)

logger = logging.getLogger(__name__)

_sensor_top = None
_sensor_bottom = None


def setup():
    """Initialise both ultrasonic sensors. Call once at startup."""
    global _sensor_top, _sensor_bottom
    try:
        _sensor_top = DistanceSensor(
            echo=ULTRASONIC_TOP_ECHO, trigger=ULTRASONIC_TOP_TRIGGER
        )
        _sensor_bottom = DistanceSensor(
            echo=ULTRASONIC_BOTTOM_ECHO, trigger=ULTRASONIC_BOTTOM_TRIGGER
        )
        logger.info("Ultrasonic sensors initialised successfully.")
    except Exception as e:
        logger.error("Ultrasonic sensor initialisation failed: %s", e)
        raise


def get_distance_top() -> float:
    """Return distance from top sensor in metres, or inf on error."""
    try:
        return _sensor_top.distance
    except Exception as e:
        logger.error("Top sensor read error: %s", e)
        return float("inf")


def get_distance_bottom() -> float:
    """Return distance from bottom sensor in metres, or inf on error."""
    try:
        return _sensor_bottom.distance
    except Exception as e:
        logger.error("Bottom sensor read error: %s", e)
        return float("inf")
