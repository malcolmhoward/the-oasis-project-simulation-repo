"""
Layer 0: I2C bus simulator.

Register-array-backed: each device address gets a 256-byte register bank.
No external runtime dependencies.
"""

import logging
from typing import Dict, List

logger = logging.getLogger(__name__)


from simulation.hal.device import I2CInterface


class MockI2C(I2CInterface):
    """
    Mock I2C (Inter-Integrated Circuit) bus that simulates register read/write
    operations.

    Implements :class:`~simulation.hal.device.I2CInterface`.

    Each device address is backed by a 256-byte register array.
    Unwritten registers return 0x00.

    Example::

        bus = MockI2C(bus_number=1)
        bus.write_byte_data(0x68, 0x6B, 0x00)   # wake MPU-6050
        whoami = bus.read_byte_data(0x68, 0x75)  # read WHO_AM_I register
    """

    def __init__(self, bus_number: int = 1):
        self.bus_number = bus_number
        self.devices: Dict[int, bytearray] = {}
        logger.info("MockI2C bus %d initialized", bus_number)

    def _ensure_device(self, addr: int):
        if addr not in self.devices:
            self.devices[addr] = bytearray(256)

    def write_byte_data(self, addr: int, register: int, value: int):
        """Write one byte to a device register."""
        self._ensure_device(addr)
        self.devices[addr][register] = value & 0xFF
        logger.debug("I2C write: addr=0x%02X reg=0x%02X val=0x%02X", addr, register, value)

    def read_byte_data(self, addr: int, register: int) -> int:
        """Read one byte from a device register."""
        self._ensure_device(addr)
        value = self.devices[addr][register]
        logger.debug("I2C read:  addr=0x%02X reg=0x%02X val=0x%02X", addr, register, value)
        return value

    def write_i2c_block_data(self, addr: int, register: int, data: List[int]):
        """Write a block of bytes starting at register."""
        self._ensure_device(addr)
        for i, byte in enumerate(data):
            self.devices[addr][(register + i) & 0xFF] = byte & 0xFF
        logger.debug("I2C block write: addr=0x%02X reg=0x%02X len=%d", addr, register, len(data))

    def read_i2c_block_data(self, addr: int, register: int, length: int) -> List[int]:
        """Read a block of bytes starting at register."""
        self._ensure_device(addr)
        data = [self.devices[addr][(register + i) & 0xFF] for i in range(length)]
        logger.debug("I2C block read:  addr=0x%02X reg=0x%02X len=%d", addr, register, length)
        return data

    def write_byte(self, addr: int, value: int):
        """Write a single byte (no register address)."""
        self._ensure_device(addr)
        self.devices[addr][0] = value & 0xFF

    def read_byte(self, addr: int) -> int:
        """Read a single byte (no register address)."""
        self._ensure_device(addr)
        return self.devices[addr][0]

    def close(self):
        """Release the bus (no-op in simulation)."""
        logger.info("MockI2C bus %d closed", self.bus_number)

    def __repr__(self):
        return f"MockI2C(bus_number={self.bus_number}, devices={[hex(a) for a in self.devices]})"
