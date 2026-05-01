"""
navicane.modules.elevation — Elevation / terrain change detection.

Combines ultrasonic distance history with gyroscope data to detect
steps, slopes, and uneven terrain.
"""

import logging
from src.config.settings import ELEVATION_THRESHOLDS

logger = logging.getLogger(__name__)


class ElevationDetector:
    """Stateful detector that tracks distance history for one sensor."""

    def __init__(self, max_history: int = 10):
        self._history: list[float] = []
        self._prev_distance: float | None = None
        self._max_history = max_history

    def update(
        self, current_distance: float, gx: float, gy: float, gz: float
    ) -> tuple[str | None, str | None]:
        """Analyse a new reading.

        Returns:
            (elevation_type, alert_type) — both None if nothing detected.
        """
        elevation_type = None
        alert_type = None

        self._history.append(current_distance)
        if len(self._history) > self._max_history:
            self._history.pop(0)

        if self._prev_distance is not None and len(self._history) >= 3:
            vertical_change = abs(current_distance - self._prev_distance)

            if vertical_change >= ELEVATION_THRESHOLDS["small_step"]:
                elevation_type = "Small step or drop detected"
                alert_type = "short_buzzer"

            if vertical_change >= ELEVATION_THRESHOLDS["large_step"]:
                elevation_type = "Large step or drop detected"
                alert_type = "vibration_voice"

            if len(self._history) >= 3:
                recent = [
                    abs(self._history[i] - self._history[i - 1])
                    for i in range(1, len(self._history))
                ]
                if any(
                    c >= ELEVATION_THRESHOLDS["uneven_terrain"]
                    for c in recent[-3:]
                ):
                    if elevation_type is None:
                        elevation_type = "Uneven terrain detected"
                        alert_type = "mild_vibration"

        if abs(gy) >= ELEVATION_THRESHOLDS["steep_slope"]:
            elevation_type = "Steep slope detected"
            alert_type = "voice_alert"

        self._prev_distance = current_distance
        return elevation_type, alert_type
