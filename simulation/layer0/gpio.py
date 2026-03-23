"""
Layer 0: GPIO pin simulator.

API-compatible with RPi.GPIO (class-method interface).
No external runtime dependencies.
"""

import logging
from typing import Dict, Optional

logger = logging.getLogger(__name__)


from simulation.hal.device import GPIOInterface


class MockGPIO(GPIOInterface):
    """
    Mock GPIO (General-Purpose Input/Output) interface that mirrors the
    RPi.GPIO class-method API.

    Implements :class:`~simulation.hal.device.GPIOInterface` via class methods
    for RPi.GPIO drop-in compatibility.

    Example::

        MockGPIO.setmode(MockGPIO.BCM)
        MockGPIO.setup(17, MockGPIO.OUT)
        MockGPIO.output(17, MockGPIO.HIGH)
        value = MockGPIO.input(17)
        MockGPIO.cleanup()
    """

    # Pin numbering modes
    BCM   = "BCM"
    BOARD = "BOARD"

    # Pin values
    LOW  = 0
    HIGH = 1

    # Pin directions
    IN  = "in"
    OUT = "out"

    # Pull resistor modes
    PUD_OFF  = 0
    PUD_DOWN = 1
    PUD_UP   = 2

    # Edge detection
    RISING  = "rising"
    FALLING = "falling"
    BOTH    = "both"

    # Class-level state (mirrors RPi.GPIO module-level globals)
    _mode: Optional[str] = None
    _pins: Dict[int, Dict] = {}
    _warnings: bool = True

    @classmethod
    def setmode(cls, mode: str):
        if mode not in (cls.BCM, cls.BOARD):
            raise ValueError("Mode must be BCM or BOARD")
        cls._mode = mode
        logger.debug("GPIO mode set to %s", mode)

    @classmethod
    def getmode(cls) -> Optional[str]:
        return cls._mode

    @classmethod
    def setwarnings(cls, enabled: bool):
        cls._warnings = enabled

    @classmethod
    def setup(cls, pin: int, mode: str, pull_up_down: int = PUD_OFF,
              initial: Optional[int] = None):
        if cls._mode is None:
            raise RuntimeError("Call setmode() before setup()")
        if mode not in (cls.IN, cls.OUT):
            raise ValueError("Mode must be IN or OUT")
        cls._pins[pin] = {
            "mode":          mode,
            "value":         initial if initial is not None else cls.LOW,
            "pull":          pull_up_down,
            "edge_callback": None,
            "edge_type":     None,
        }
        logger.debug("GPIO pin %d configured as %s", pin, mode.upper())

    @classmethod
    def output(cls, pin: int, value: int):
        if pin not in cls._pins:
            raise RuntimeError(f"Pin {pin} not set up")
        if cls._pins[pin]["mode"] != cls.OUT:
            raise RuntimeError(f"Pin {pin} is not configured as output")
        old = cls._pins[pin]["value"]
        cls._pins[pin]["value"] = value
        logger.debug("GPIO pin %d -> %d", pin, value)
        # Trigger edge detection
        cb = cls._pins[pin].get("edge_callback")
        if cb and old != value:
            cb(pin)

    @classmethod
    def input(cls, pin: int) -> int:
        if pin not in cls._pins:
            raise RuntimeError(f"Pin {pin} not set up")
        return cls._pins[pin]["value"]

    @classmethod
    def add_event_detect(cls, pin: int, edge: str, callback=None, bouncetime: int = 0):
        if pin not in cls._pins:
            raise RuntimeError(f"Pin {pin} not set up")
        cls._pins[pin]["edge_callback"] = callback
        cls._pins[pin]["edge_type"]     = edge

    @classmethod
    def remove_event_detect(cls, pin: int):
        if pin in cls._pins:
            cls._pins[pin]["edge_callback"] = None

    @classmethod
    def cleanup(cls, pin: Optional[int] = None):
        if pin is None:
            cls._pins.clear()
            cls._mode = None
            logger.debug("All GPIO pins cleaned up")
        elif pin in cls._pins:
            del cls._pins[pin]
            logger.debug("GPIO pin %d cleaned up", pin)

    @classmethod
    def get_pin_state(cls, pin: int) -> Optional[Dict]:
        return cls._pins.get(pin)

    @classmethod
    def get_all_pins(cls) -> Dict:
        return dict(cls._pins)
