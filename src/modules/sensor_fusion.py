"""
navicane.modules.sensor_fusion — Priority-ordered event arbitration.

Central alert manager that:
  1. Assigns a severity level to every alert source.
  2. Enforces per-source cooldown timers.
  3. Suppresses lower-priority alerts while a higher-priority alert
     is still active (e.g. fall trumps obstacle detection).
  4. Provides a unified dispatch() method that selects the right
     feedback action (buzz, vibrate, speak, or combination).

Satisfies Issue #18: Implement sensor fusion and event arbitration logic.
"""

import time
import logging
import threading

from src.config.settings import DETECTION_COOLDOWN_S, ELEVATION_COOLDOWN_S

logger = logging.getLogger(__name__)


# ── Alert priorities (higher number = higher priority) ───────
PRIORITY = {
    "fall":       100,    # highest — user may be injured
    "emergency":   90,    # ambulance / police detected
    "elevation":   70,    # step / slope / terrain change
    "ultrasonic":  60,    # proximity obstacle
    "camera":      50,    # detected object via YOLO
    "gps":         10,    # location announcement (lowest)
}

DEFAULT_COOLDOWNS = {
    "fall":       0.0,    # always fire immediately
    "emergency":  5.0,
    "elevation":  ELEVATION_COOLDOWN_S,
    "ultrasonic": DETECTION_COOLDOWN_S,
    "camera":     DETECTION_COOLDOWN_S,
    "gps":        30.0,
}


class AlertEvent:
    """Represents a single alert event produced by a sensor module.

    Attributes:
        source:   Sensor source key (e.g. "ultrasonic", "fall").
        message:  Human-readable text for TTS.
        priority: Numeric priority (auto-looked-up from PRIORITY dict).
        action:   Feedback action — one of "buzz", "vibrate", "speak",
                  "buzz+speak", "vibrate+speak".
        timestamp: When the event was created.
    """

    def __init__(
        self,
        source: str,
        message: str,
        action: str = "speak",
    ):
        self.source = source
        self.message = message
        self.priority = PRIORITY.get(source, 0)
        self.action = action
        self.timestamp = time.time()

    def __repr__(self):
        return (
            f"AlertEvent(source={self.source!r}, priority={self.priority}, "
            f"action={self.action!r}, msg={self.message[:40]!r})"
        )


class AlertManager:
    """Manages per-source cooldowns and priority-based suppression.

    Thread-safe: all public methods can be called from any thread.

    Usage::

        mgr = AlertManager()

        # Sensor loop produces events:
        event = AlertEvent("ultrasonic", "Obstacle at 50 centimetres", "buzz+speak")

        if mgr.should_alert(event):
            mgr.dispatch(event)
    """

    def __init__(self):
        self._last_alert: dict[str, float] = {}
        self._cooldowns: dict[str, float] = dict(DEFAULT_COOLDOWNS)
        self._active_priority: int = 0
        self._active_until: float = 0.0
        self._lock = threading.Lock()

    # ── Cooldown management ──────────────────────────────────

    def should_alert(self, event: AlertEvent) -> bool:
        """Determine if an event should fire based on cooldown and priority.

        Rules:
          1. A source in cooldown is suppressed.
          2. A lower-priority event is suppressed while a higher-priority
             event is still "active" (within its cooldown window).
          3. Equal or higher priority events always pass.

        Side-effect: updates the last-alert timestamp if returning True.

        Args:
            event: The candidate AlertEvent.

        Returns:
            True if the alert should be dispatched.
        """
        with self._lock:
            now = time.time()

            # Check per-source cooldown
            cooldown = self._cooldowns.get(event.source, DETECTION_COOLDOWN_S)
            last = self._last_alert.get(event.source, 0.0)
            if (now - last) < cooldown:
                return False

            # Check priority suppression
            if now < self._active_until and event.priority < self._active_priority:
                logger.debug(
                    "Suppressed %s (priority %d < active %d)",
                    event.source, event.priority, self._active_priority,
                )
                return False

            # Accept the alert
            self._last_alert[event.source] = now
            self._active_priority = event.priority
            self._active_until = now + cooldown
            return True

    def reset(self, source: str):
        """Reset the cooldown timer for a specific source.

        Args:
            source: Source key to reset.
        """
        with self._lock:
            self._last_alert[source] = 0.0

    def reset_all(self):
        """Reset all cooldown timers."""
        with self._lock:
            self._last_alert.clear()
            self._active_priority = 0
            self._active_until = 0.0

    # ── Dispatch ─────────────────────────────────────────────

    def dispatch(self, event: AlertEvent):
        """Execute the feedback action(s) for an accepted event.

        Imports the feedback module lazily to avoid circular imports.
        Runs all I/O (buzz, speak) in a background thread so the
        sensor loop is never blocked.

        Args:
            event: The AlertEvent to dispatch.
        """
        def _worker():
            from src.modules import feedback

            logger.info("ALERT [%s] p=%d → %s", event.source, event.priority, event.message[:60])

            if event.action == "buzz":
                feedback.buzz()
            elif event.action == "vibrate":
                feedback.vibrate()
            elif event.action == "speak":
                feedback.speak(event.message, blocking=True)
            elif event.action == "buzz+speak":
                feedback.buzz()
                time.sleep(0.5)  # let buzzer finish before speaking
                feedback.speak_cached(event.message)
            elif event.action == "vibrate+speak":
                feedback.vibrate()
                time.sleep(0.8)
                feedback.speak_cached(event.message)
            else:
                feedback.speak(event.message, blocking=True)

        threading.Thread(target=_worker, daemon=True).start()
