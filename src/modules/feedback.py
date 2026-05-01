"""
navicane.modules.feedback — Multi-modal output (buzzer + vibration + TTS).

Provides:
  - buzz()      — short rapid pulses (proximity alert)
  - vibrate()   — longer pulses simulating vibration motor
  - speak()     — offline TTS via espeak (non-blocking)
  - speak_cached() — play a pre-generated WAV for latency-critical alerts
  - precache_phrases() — generate WAV files at startup for common phrases
  - silence()   — immediately kill buzzer + audio

Uses espeak for offline text-to-speech and aplay for cached WAV playback.
Audio cache is stored under AUDIO_CACHE_DIR and survives container restarts.

Satisfies Issue #15: Implement multi-modal feedback module.
"""

import hashlib
import logging
import os
import subprocess
import threading
import time

from gpiozero import OutputDevice

from src.config.settings import (
    BUZZER_PIN, BUZZER_ACTIVE_HIGH,
    TTS_SPEED, TTS_VOICE,
    AUDIO_CACHE_DIR, CACHED_PHRASES,
)

logger = logging.getLogger(__name__)

_buzzer = None
_speak_lock = threading.Lock()     # serialise TTS output
_audio_process = None              # track the running speech process


# ── Setup ────────────────────────────────────────────────────

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


# ── Buzzer patterns ──────────────────────────────────────────

def buzz(duration: float = 0.2, repeats: int = 3, gap: float = 0.1):
    """Sound the buzzer in short rapid pulses (proximity warning).

    Args:
        duration: On-time per pulse in seconds.
        repeats:  Number of pulses.
        gap:      Off-time between pulses in seconds.
    """
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
    """Longer buzzer pulses to simulate vibration motor feedback.

    Uses the same buzzer hardware with different timing to feel
    distinct from short proximity beeps.

    Args:
        duration: On-time per pulse in seconds.
        repeats:  Number of pulses.
        gap:      Off-time between pulses in seconds.
    """
    def _worker():
        if not _buzzer:
            return
        for _ in range(repeats):
            _buzzer.on()
            time.sleep(duration)
            _buzzer.off()
            time.sleep(gap)

    threading.Thread(target=_worker, daemon=True).start()


def buzz_pattern(pattern: list[tuple[float, float]]):
    """Play an arbitrary buzz pattern.

    Args:
        pattern: List of (on_seconds, off_seconds) tuples.
                 Example: [(0.1, 0.05), (0.3, 0.1)] = short-long.
    """
    def _worker():
        if not _buzzer:
            return
        for on_t, off_t in pattern:
            _buzzer.on()
            time.sleep(on_t)
            _buzzer.off()
            time.sleep(off_t)

    threading.Thread(target=_worker, daemon=True).start()


# ── Text-to-speech ───────────────────────────────────────────

def speak(text: str, blocking: bool = False):
    """Speak text using espeak (fully offline).

    Args:
        text:     The string to speak.
        blocking: If True, wait until speech completes before returning.
    """
    def _worker():
        global _audio_process
        with _speak_lock:
            try:
                _audio_process = subprocess.Popen(
                    ["espeak", "-s", str(TTS_SPEED), "-v", TTS_VOICE, text],
                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                )
                _audio_process.wait(timeout=15)
                logger.info("Spoke: %s", text[:60])
            except subprocess.TimeoutExpired:
                if _audio_process:
                    _audio_process.kill()
                logger.error("Speech timeout for: %s", text)
            except FileNotFoundError:
                logger.error("espeak not found. Install: sudo apt install espeak")
            except Exception as e:
                logger.error("Speech error: %s", e)
            finally:
                _audio_process = None

    if blocking:
        _worker()
    else:
        threading.Thread(target=_worker, daemon=True).start()


# ── Audio caching (pre-generated WAV files) ──────────────────

def _phrase_hash(text: str) -> str:
    """Return a short hash for the phrase to use as a filename."""
    return hashlib.md5(text.encode()).hexdigest()[:12]


def _cache_path(text: str) -> str:
    """Return the full path to the cached WAV file for a phrase."""
    return os.path.join(AUDIO_CACHE_DIR, f"{_phrase_hash(text)}.wav")


def precache_phrases(phrases: list[str] | None = None):
    """Pre-generate WAV files for common phrases at startup.

    Uses `espeak --stdout` to pipe PCM audio directly to a WAV file.
    Skips phrases that are already cached.

    Args:
        phrases: List of strings to cache.  Defaults to CACHED_PHRASES
                 from settings.
    """
    if phrases is None:
        phrases = CACHED_PHRASES

    os.makedirs(AUDIO_CACHE_DIR, exist_ok=True)
    cached, skipped = 0, 0

    for phrase in phrases:
        wav_path = _cache_path(phrase)
        if os.path.exists(wav_path) and os.path.getsize(wav_path) > 0:
            skipped += 1
            continue

        try:
            subprocess.run(
                [
                    "espeak", "-s", str(TTS_SPEED), "-v", TTS_VOICE,
                    "--stdout", phrase,
                ],
                stdout=open(wav_path, "wb"),
                stderr=subprocess.DEVNULL,
                check=True, timeout=10,
            )
            cached += 1
        except (subprocess.CalledProcessError, FileNotFoundError) as e:
            logger.warning("Failed to cache phrase '%s': %s", phrase[:30], e)

    logger.info(
        "Audio cache: %d generated, %d already cached, %d total phrases",
        cached, skipped, len(phrases),
    )


def speak_cached(text: str):
    """Play a pre-cached phrase. Falls back to live espeak if not cached.

    This is ~10× faster than live synthesis for common alerts.

    Args:
        text: The exact phrase that was previously cached.
    """
    wav_path = _cache_path(text)

    if os.path.exists(wav_path) and os.path.getsize(wav_path) > 0:
        def _worker():
            global _audio_process
            with _speak_lock:
                try:
                    _audio_process = subprocess.Popen(
                        ["aplay", "-q", wav_path],
                        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                    )
                    _audio_process.wait(timeout=10)
                except FileNotFoundError:
                    logger.warning("aplay not found, falling back to espeak")
                    speak(text, blocking=True)
                except subprocess.TimeoutExpired:
                    if _audio_process:
                        _audio_process.kill()
                except Exception as e:
                    logger.error("Cached playback error: %s", e)
                finally:
                    _audio_process = None

        threading.Thread(target=_worker, daemon=True).start()
    else:
        speak(text)


# ── Control ──────────────────────────────────────────────────

def silence():
    """Immediately silence all output — kill buzzer and any running audio."""
    if _buzzer:
        _buzzer.off()
    if _audio_process and _audio_process.poll() is None:
        _audio_process.kill()
        logger.info("Audio process killed by silence()")
