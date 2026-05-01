"""
navicane.modules.gps_tracker — Neo-6M GPS module interface.

Reads NMEA sentences from the GPS module over UART (serial),
parses GGA/RMC fixes via pynmea2, and provides:
  - get_position()    → (lat, lon, alt, speed, fix_quality)
  - has_fix()         → whether the GPS has a satellite fix
  - announce()        → speak the current location via TTS
  - distance_to()     → Haversine distance to a target point

Falls back gracefully if the GPS hardware is not connected
(MOCK_HARDWARE mode or missing serial port).

Satisfies Issue #17: Implement GPS location announcement module.
"""

import logging
import math
import threading
import time

from src.config.settings import (
    GPS_SERIAL_PORT, GPS_BAUD_RATE, GPS_ANNOUNCE_INTERVAL_S,
    MOCK_HARDWARE,
)

logger = logging.getLogger(__name__)

# ── GPS state ────────────────────────────────────────────────
_serial = None
_available = False
_thread = None
_running = False

_latitude: float | None = None
_longitude: float | None = None
_altitude: float | None = None    # metres above sea level
_speed_kmh: float | None = None   # ground speed
_fix_quality: int = 0              # 0 = no fix, 1 = GPS, 2 = DGPS
_satellites: int = 0
_last_update: float = 0.0
_lock = threading.Lock()


# ── Setup / teardown ─────────────────────────────────────────

def setup():
    """Open the serial port and start the background NMEA reader thread.

    Call once at startup. Safe to call even when GPS hardware is absent.
    """
    global _serial, _available, _thread, _running

    if MOCK_HARDWARE:
        logger.info("GPS disabled (mock hardware mode)")
        return

    try:
        import serial
        _serial = serial.Serial(
            port=GPS_SERIAL_PORT,
            baudrate=GPS_BAUD_RATE,
            timeout=1.0,
        )
        _available = True
        _running = True
        _thread = threading.Thread(target=_reader_loop, daemon=True)
        _thread.start()
        logger.info(
            "GPS initialised on %s @ %d baud",
            GPS_SERIAL_PORT, GPS_BAUD_RATE,
        )
    except ImportError:
        logger.warning("pyserial not installed — GPS disabled")
        _available = False
    except Exception as e:
        logger.warning("GPS initialisation failed: %s", e)
        _available = False


def stop():
    """Stop the reader thread and close the serial port."""
    global _running
    _running = False
    if _serial and _serial.is_open:
        _serial.close()
        logger.info("GPS serial port closed.")


# ── Background NMEA reader ──────────────────────────────────

def _reader_loop():
    """Continuously read and parse NMEA sentences from the serial port."""
    global _latitude, _longitude, _altitude, _speed_kmh
    global _fix_quality, _satellites, _last_update

    try:
        import pynmea2
    except ImportError:
        logger.error("pynmea2 not installed — GPS parsing disabled")
        return

    while _running and _serial and _serial.is_open:
        try:
            line = _serial.readline().decode("ascii", errors="replace").strip()
            if not line:
                continue

            msg = pynmea2.parse(line)

            with _lock:
                # GGA sentence — position + altitude + fix quality
                if isinstance(msg, pynmea2.types.talker.GGA):
                    if msg.gps_qual and msg.gps_qual > 0:
                        _latitude = msg.latitude
                        _longitude = msg.longitude
                        _altitude = msg.altitude
                        _fix_quality = msg.gps_qual
                        _satellites = msg.num_sats
                        _last_update = time.time()

                # RMC sentence — position + ground speed
                elif isinstance(msg, pynmea2.types.talker.RMC):
                    if msg.status == "A":  # A = active, V = void
                        _latitude = msg.latitude
                        _longitude = msg.longitude
                        _speed_kmh = (
                            msg.spd_over_grnd * 1.852
                            if msg.spd_over_grnd else 0.0
                        )
                        _last_update = time.time()

        except pynmea2.ParseError:
            pass  # malformed sentence — skip silently
        except Exception as e:
            logger.debug("GPS reader error: %s", e)
            time.sleep(0.1)


# ── Public API ───────────────────────────────────────────────

def is_available() -> bool:
    """Return True if GPS hardware was initialised."""
    return _available


def has_fix() -> bool:
    """Return True if the GPS currently has a satellite fix.

    A fix is considered stale after 10 seconds without an update.
    """
    with _lock:
        if _fix_quality == 0 or _latitude is None:
            return False
        return (time.time() - _last_update) < 10.0


def get_position() -> dict:
    """Return the current GPS position as a dictionary.

    Returns:
        dict with keys: latitude, longitude, altitude_m, speed_kmh,
        fix_quality, satellites, has_fix.
        Values are None if no fix is available.
    """
    with _lock:
        return {
            "latitude": _latitude,
            "longitude": _longitude,
            "altitude_m": _altitude,
            "speed_kmh": _speed_kmh,
            "fix_quality": _fix_quality,
            "satellites": _satellites,
            "has_fix": has_fix(),
        }


def format_location() -> str:
    """Return a human-readable location string for TTS.

    Examples:
        "Location: 12 point 97 north, 77 point 59 east, altitude 920 metres"
        "GPS signal not available"
    """
    with _lock:
        if _latitude is None or _fix_quality == 0:
            return "GPS signal not available"

        lat_dir = "north" if _latitude >= 0 else "south"
        lon_dir = "east" if _longitude >= 0 else "west"
        lat_abs = abs(_latitude)
        lon_abs = abs(_longitude)

        parts = [
            f"Location: {lat_abs:.2f} degrees {lat_dir}, "
            f"{lon_abs:.2f} degrees {lon_dir}",
        ]

        if _altitude is not None:
            parts.append(f", altitude {int(_altitude)} metres")

        if _speed_kmh is not None and _speed_kmh > 1.0:
            parts.append(f", speed {int(_speed_kmh)} kilometres per hour")

        return "".join(parts)


def announce():
    """Speak the current GPS location via TTS.

    Imports feedback lazily to avoid circular imports.
    """
    from src.modules.feedback import speak
    text = format_location()
    logger.info("GPS announcement: %s", text)
    speak(text)


# ── Distance calculation ────────────────────────────────────

def distance_to(target_lat: float, target_lon: float) -> float | None:
    """Compute the Haversine distance (in metres) to a target coordinate.

    Args:
        target_lat: Target latitude in decimal degrees.
        target_lon: Target longitude in decimal degrees.

    Returns:
        Distance in metres, or None if no GPS fix.
    """
    with _lock:
        if _latitude is None or _longitude is None:
            return None

    R = 6_371_000  # Earth radius in metres
    phi1 = math.radians(_latitude)
    phi2 = math.radians(target_lat)
    dphi = math.radians(target_lat - _latitude)
    dlam = math.radians(target_lon - _longitude)

    a = (
        math.sin(dphi / 2) ** 2
        + math.cos(phi1) * math.cos(phi2) * math.sin(dlam / 2) ** 2
    )
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
