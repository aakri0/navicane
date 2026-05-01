"""
navicane.modules.sensor_fusion — Alert arbitration and cooldown management.

Prevents alert flooding by enforcing per-source cooldown timers.
"""

import time
import logging

from src.config.settings import DETECTION_COOLDOWN_S, ELEVATION_COOLDOWN_S

logger = logging.getLogger(__name__)


class AlertManager:
    """Manages per-source cooldowns to prevent alert flooding."""

    def __init__(self):
        self._last_alert: dict[str, float] = {}
        self._cooldowns: dict[str, float] = {
            "ultrasonic": DETECTION_COOLDOWN_S,
            "camera": DETECTION_COOLDOWN_S,
            "elevation": ELEVATION_COOLDOWN_S,
            "fall": 0.0,  # fall always fires immediately
            "gps": 30.0,
        }

    def should_alert(self, source: str) -> bool:
        """Check whether enough time has passed for this source to alert again."""
        now = time.time()
        cooldown = self._cooldowns.get(source, DETECTION_COOLDOWN_S)
        last = self._last_alert.get(source, 0.0)

        if (now - last) > cooldown:
            self._last_alert[source] = now
            return True
        return False

    def reset(self, source: str):
        """Reset the cooldown for a specific source."""
        self._last_alert[source] = 0.0
