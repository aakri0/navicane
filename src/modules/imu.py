"""
navicane.modules.imu — MPU-6050 gyroscope / accelerometer interface.

Reads raw gyroscope data over I2C via smbus2.
"""

import logging
import smbus2

from src.config.settings import (
    MPU6050_ADDR, MPU6050_PWR_MGMT_1,
    MPU6050_GYRO_XOUT_H, MPU6050_GYRO_YOUT_H, MPU6050_GYRO_ZOUT_H,
)

logger = logging.getLogger(__name__)

_bus = None
_available = False


def setup():
    """Wake the MPU-6050 and prepare I2C bus. Call once at startup."""
    global _bus, _available
    try:
        _bus = smbus2.SMBus(1)
        _bus.write_byte_data(MPU6050_ADDR, MPU6050_PWR_MGMT_1, 0)
        _available = True
        logger.info("MPU-6050 gyroscope initialised successfully.")
    except Exception as e:
        logger.warning("Gyroscope initialisation failed: %s", e)
        _available = False


def is_available() -> bool:
    return _available


def _read_raw(addr: int) -> int:
    """Read a 16-bit signed value from two consecutive registers."""
    try:
        high = _bus.read_byte_data(MPU6050_ADDR, addr)
        low = _bus.read_byte_data(MPU6050_ADDR, addr + 1)
        value = (high << 8) | low
        if value > 32768:
            value -= 65536
        return value
    except Exception as e:
        logger.error("Error reading gyroscope register 0x%02X: %s", addr, e)
        return 0


def get_gyro_data() -> tuple[float, float, float]:
    """Return (gx, gy, gz) in degrees/sec. Returns (0,0,0) if unavailable."""
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
