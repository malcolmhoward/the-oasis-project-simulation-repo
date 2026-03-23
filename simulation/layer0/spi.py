"""
Layer 0: SPI bus simulator.

Loopback simulation by default; supports pluggable response handlers.
No external runtime dependencies.
"""

import logging
from typing import Callable, List, Optional

logger = logging.getLogger(__name__)


from simulation.hal.device import SPIInterface


class MockSPI(SPIInterface):
    """
    Mock SPI (Serial Peripheral Interface) that simulates SPI communication.

    Implements :class:`~simulation.hal.device.SPIInterface`.

    Default behaviour is loopback (echoes sent bytes back).
    Provide a ``response_handler`` callable to simulate device-specific responses.

    Example::

        spi = MockSPI(bus=0, device=0)
        response = spi.transfer([0x01, 0x02, 0x03])
        spi.close()

    Custom response::

        def my_device(data):
            if data[0] == 0xD0:        # read ID register
                return [0x60] + [0] * (len(data) - 1)
            return [0x00] * len(data)

        spi = MockSPI(bus=0, device=0, response_handler=my_device)
    """

    MODE_0 = 0  # CPOL=0, CPHA=0
    MODE_1 = 1  # CPOL=0, CPHA=1
    MODE_2 = 2  # CPOL=1, CPHA=0
    MODE_3 = 3  # CPOL=1, CPHA=1

    def __init__(
        self,
        bus: int = 0,
        device: int = 0,
        max_speed_hz: int = 500_000,
        mode: int = 0,
        bits_per_word: int = 8,
        response_handler: Optional[Callable[[List[int]], List[int]]] = None,
    ):
        self.bus            = bus
        self.device         = device
        self.max_speed_hz   = max_speed_hz
        self.mode           = mode
        self.bits_per_word  = bits_per_word
        self._response_handler = response_handler
        self.is_open        = True
        self.transfer_count = 0
        logger.info("MockSPI initialized (bus %d, device %d, %d Hz, mode %d)",
                    bus, device, max_speed_hz, mode)

    def transfer(self, data: List[int]) -> List[int]:
        """Transfer data; return simulated response (loopback by default)."""
        if not self.is_open:
            raise RuntimeError("SPI device is not open")
        self.transfer_count += 1
        if self._response_handler:
            response = self._response_handler(data)
        else:
            # Simple loopback — echo back
            response = list(data)
        logger.debug("SPI transfer #%d: tx=%s rx=%s",
                     self.transfer_count,
                     [hex(x) for x in data],
                     [hex(x) for x in response])
        return response

    def read(self, length: int) -> List[int]:
        """Read ``length`` bytes (sends zeros)."""
        return self.transfer([0x00] * length)

    def write(self, data: List[int]):
        """Write data (discard response)."""
        self.transfer(data)

    def set_speed(self, speed_hz: int):
        self.max_speed_hz = speed_hz

    def set_mode(self, mode: int):
        if mode not in (0, 1, 2, 3):
            raise ValueError("SPI mode must be 0-3")
        self.mode = mode

    def close(self):
        self.is_open = False
        logger.info("MockSPI closed (bus %d, device %d, %d transfers)",
                    self.bus, self.device, self.transfer_count)

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()

    def __repr__(self):
        return (f"MockSPI(bus={self.bus}, device={self.device}, "
                f"{self.max_speed_hz}Hz, mode={self.mode})")
