"""
navicane.modules.imu — MPU-6050 gyroscope / accelerometer interface.

Reads raw gyroscope AND accelerometer data over I2C via smbus2.
Provides fall detection by monitoring for a free-fall event (< 0.5 g)
followed by an impact event (> 2.5 g) within a 500 ms window.

Satisfies Issue #14: Implement MPU-6050 fall detection module.
"""

import math
import time
import logging
import smbus2

from src.config.settings import (
    MPU6050_ADDR, MPU6050_PWR_MGMT_1,
    MPU6050_GYRO_XOUT_H, MPU6050_GYRO_YOUT_H, MPU6050_GYRO_ZOUT_H,
    MPU6050_ACCEL_XOUT_H, MPU6050_ACCEL_YOUT_H, MPU6050_ACCEL_ZOUT_H,
    MPU6050_ACCEL_SCALE,
    FALL_FREEFALL_THRESHOLD_G, FALL_IMPACT_THRESHOLD_G, FALL_WINDOW_MS,
)

logger = logging.getLogger(__name__)

_bus = None
_available = False

# ── Fall detection state ─────────────────────────────────────
_freefall_time: float | None = None   # timestamp of last free-fall event


def setup():
    """Wake the MPU-6050 and prepare I2C bus. Call once at startup."""
    global _bus, _available
    try:
        _bus = smbus2.SMBus(1)
        # Wake up MPU-6050 by writing 0x00 to register 0x6B
        _bus.write_byte_data(MPU6050_ADDR, MPU6050_PWR_MGMT_1, 0)
        _available = True
        logger.info("MPU-6050 gyroscope + accelerometer initialised successfully.")
    except Exception as e:
        logger.warning("MPU-6050 initialisation failed: %s", e)
        _available = False


def is_available() -> bool:
    """Return True if the MPU-6050 was successfully initialised."""
    return _available


# ── Low-level register access ────────────────────────────────

def _read_raw(addr: int) -> int:
    """Read a 16-bit signed value from two consecutive registers.

    Args:
        addr: Start register address (high byte).

    Returns:
        Signed 16-bit integer, or 0 on error.
    """
    try:
        high = _bus.read_byte_data(MPU6050_ADDR, addr)
        low = _bus.read_byte_data(MPU6050_ADDR, addr + 1)
        value = (high << 8) | low
        if value > 32768:
            value -= 65536
        return value
    except Exception as e:
        logger.error("Error reading register 0x%02X: %s", addr, e)
        return 0


# ── Gyroscope ────────────────────────────────────────────────

def get_gyro_data() -> tuple[float, float, float]:
    """Return (gx, gy, gz) in degrees/sec.

    Returns:
        Tuple of gyroscope readings. (0, 0, 0) if sensor is unavailable.
    """
    if not _available:
        return 0.0, 0.0, 0.0
    try:
        gx = _read_raw(MPU6050_GYRO_XOUT_H) / 131.0
        gy = _read_raw(MPU6050_GYRO_YOUT_H) / 131.0
        gz = _read_raw(MPU6050_GYRO_ZOUT_H) / 131.0
        return gx, gy, gz
    except Exception as e:
        logger.error("Error getting gyroscope data: %s", e)
        return 0.0, 0.0, 0.0


# ── Accelerometer ────────────────────────────────────────────

def read_accel() -> tuple[float, float, float]:
    """Read accelerometer and return (ax, ay, az) in g units.

    The MPU-6050 default range is ±2 g with a scale factor of 16384 LSB/g.

    Returns:
        Tuple of accelerometer readings in g. (0, 0, 0) if unavailable.
    """
    if not _available:
        return 0.0, 0.0, 0.0
    try:
        ax = _read_raw(MPU6050_ACCEL_XOUT_H) / MPU6050_ACCEL_SCALE
        ay = _read_raw(MPU6050_ACCEL_YOUT_H) / MPU6050_ACCEL_SCALE
        az = _read_raw(MPU6050_ACCEL_ZOUT_H) / MPU6050_ACCEL_SCALE
        return ax, ay, az
    except Exception as e:
        logger.error("Error getting accelerometer data: %s", e)
        return 0.0, 0.0, 0.0


def accel_magnitude() -> float:
    """Compute the magnitude of the accelerometer vector: √(ax² + ay² + az²).

    At rest the value should be ≈ 1.0 g.

    Returns:
        Magnitude in g, or 0.0 if sensor is unavailable.
    """
    ax, ay, az = read_accel()
    return math.sqrt(ax * ax + ay * ay + az * az)


# ── Fall detection ───────────────────────────────────────────

def is_fall() -> bool:
    """Detect a fall event using the two-phase algorithm.

    Phase 1 — Free-fall: magnitude drops below FALL_FREEFALL_THRESHOLD_G.
    Phase 2 — Impact:    magnitude exceeds FALL_IMPACT_THRESHOLD_G.

    Both events must occur within FALL_WINDOW_MS milliseconds for a
    positive fall detection.

    This function is designed to be called on every sensor polling cycle
    (typically 20–50 Hz). It maintains internal state between calls.

    Returns:
        True if a fall was just detected, False otherwise.

    Raises:
        RuntimeError: If setup() has not been called.
    """
    global _freefall_time

    if not _available:
        return False

    mag = accel_magnitude()
    now = time.time()

    # Phase 1: detect free-fall
    if mag < FALL_FREEFALL_THRESHOLD_G:
        if _freefall_time is None:
            _freefall_time = now
            logger.debug("Free-fall detected (mag=%.2f g)", mag)

    # Phase 2: detect impact after free-fall
    if mag > FALL_IMPACT_THRESHOLD_G and _freefall_time is not None:
        elapsed_ms = (now - _freefall_time) * 1000.0
        _freefall_time = None  # reset regardless

        if elapsed_ms <= FALL_WINDOW_MS:
            logger.warning(
                "FALL DETECTED — free-fall → impact in %.0f ms (mag=%.2f g)",
                elapsed_ms, mag,
            )
            return True
        else:
            logger.debug(
                "Impact after free-fall ignored — %.0f ms > %d ms window",
                elapsed_ms, FALL_WINDOW_MS,
            )

    # Expire stale free-fall events
    if _freefall_time is not None:
        elapsed_ms = (now - _freefall_time) * 1000.0
        if elapsed_ms > FALL_WINDOW_MS * 2:
            _freefall_time = None

    return False
