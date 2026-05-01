"""
navicane.modules.feedback — Multi-modal output (buzzer + TTS).

Provides buzz(), vibrate(), and speak() functions for user alerts.
Uses espeak for offline text-to-speech.
"""

import logging
import subprocess
import threading

from gpiozero import OutputDevice

from src.config.settings import (
    BUZZER_PIN, BUZZER_ACTIVE_HIGH,
    TTS_SPEED, TTS_VOICE,
)

logger = logging.getLogger(__name__)

_buzzer = None


def setup():
    """Initialise the buzzer output device. Call once at startup."""
    global _buzzer
    try:
        _buzzer = OutputDevice(
            BUZZER_PIN, active_high=BUZZER_ACTIVE_HIGH, initial_value=True
        )
        logger.info("Buzzer initialised on GPIO%d", BUZZER_PIN)
    except Exception as e:
        logger.warning("Buzzer initialisation failed: %s", e)


def buzz(duration: float = 0.2, repeats: int = 3, gap: float = 0.1):
    """Sound the buzzer in short pulses."""
    import time

    def _worker():
        if not _buzzer:
            return
        for _ in range(repeats):
            _buzzer.on()
            time.sleep(duration)
            _buzzer.off()
            time.sleep(gap)

    threading.Thread(target=_worker, daemon=True).start()


def vibrate(duration: float = 0.3, repeats: int = 2, gap: float = 0.2):
    """Longer buzzer pulses to simulate vibration feedback."""
    import time

    def _worker():
        if not _buzzer:
            return
        for _ in range(repeats):
            _buzzer.on()
            time.sleep(duration)
            _buzzer.off()
            time.sleep(gap)

    threading.Thread(target=_worker, daemon=True).start()


def speak(text: str):
    """Speak text using espeak (fully offline). Non-blocking."""

    def _worker():
        try:
            subprocess.run(
                ["espeak", "-s", str(TTS_SPEED), "-v", TTS_VOICE, text],
                check=True, capture_output=True, timeout=10,
            )
            logger.info("Spoke: %s", text[:50])
        except subprocess.TimeoutExpired:
            logger.error("Speech timeout for: %s", text)
        except FileNotFoundError:
            logger.error("espeak not found. Install with: sudo apt install espeak")
        except Exception as e:
            logger.error("Speech error: %s", e)

    threading.Thread(target=_worker, daemon=True).start()


def silence():
    """Turn off buzzer immediately."""
    if _buzzer:
        _buzzer.off()
