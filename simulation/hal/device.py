"""
Device layer interface contracts — hardware primitive abstractions.

These ABCs (Abstract Base Classes) define the API that both Python mock
implementations (Layer 0) and future C HAL (Hardware Abstraction Layer)
headers (Phase 2) must conform to.  The interfaces are derived from the
real hardware APIs used by O.A.S.I.S. components:

- SensorInterface: IMU (Inertial Measurement Unit), GPS (Global Positioning
  System), environmental sensors (M.I.R.A.G.E., A.U.R.A., S.T.A.T.)
- GPIOInterface: GPIO (General-Purpose Input/Output) pin control (S.P.A.R.K.)
- I2CInterface: I2C (Inter-Integrated Circuit) bus (A.U.R.A.)
- SPIInterface: SPI (Serial Peripheral Interface) bus (S.P.A.R.K.)
- CameraInterface: Video capture devices (M.I.R.A.G.E.)
- MicrophoneInterface / SpeakerInterface: Audio I/O (D.A.W.N. satellite)

Docstrings use language-neutral descriptions so C HAL headers can be derived
from the same definitions.  Python type annotations are present for static
analysis but are not the authoritative specification — the docstrings are.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Callable, Dict, List, Optional


# ---------------------------------------------------------------------------
# Sensor
# ---------------------------------------------------------------------------


class SensorInterface(ABC):
    """Interface for a sensor that produces periodic readings.

    Implementations must support at minimum: read(), activate(), deactivate().
    A string ``sensor_type`` attribute determines the schema of the returned map.
    """

    @abstractmethod
    def read(self) -> Dict[str, Any]:
        """Return a single sensor reading as a string-keyed map.

        The map keys depend on the sensor type.  Motion readings include
        ``heading`` (float, degrees 0-360), ``pitch`` (float, degrees),
        ``roll`` (float, degrees).  GPS readings include ``latitude`` (float),
        ``longitude`` (float), ``satellites`` (integer).
        """
        ...

    @abstractmethod
    def calibrate(self, **kwargs: Any) -> None:
        """Override base values used for readings.

        Accepts named parameters matching internal base values (e.g.,
        ``temperature=22.5``, ``heading=90.0``).  Unknown names are ignored.
        """
        ...

    @abstractmethod
    def activate(self) -> None:
        """Enable the sensor for reading."""
        ...

    @abstractmethod
    def deactivate(self) -> None:
        """Disable the sensor.  Subsequent read() calls should raise an error."""
        ...

    @abstractmethod
    def reset(self) -> None:
        """Reset internal counters and timers to initial state."""
        ...


class SensorArrayInterface(ABC):
    """Interface for a named collection of sensors."""

    @abstractmethod
    def add_sensor(self, name: str, sensor_type: str = "generic") -> SensorInterface:
        """Create and register a sensor under the given string name.

        Returns the created sensor instance.
        """
        ...

    @abstractmethod
    def remove_sensor(self, name: str) -> None:
        """Remove a sensor by string name.  No error if name is absent."""
        ...

    @abstractmethod
    def read_all(self) -> Dict[str, Dict[str, Any]]:
        """Read all sensors.  Returns a map of name to reading map."""
        ...

    @abstractmethod
    def read_sensor(self, name: str) -> Dict[str, Any]:
        """Read a single sensor by name.  Raises an error if name is absent."""
        ...

    @abstractmethod
    def list_sensors(self) -> List[str]:
        """Return the names of all registered sensors as a list of strings."""
        ...


# ---------------------------------------------------------------------------
# GPIO
# ---------------------------------------------------------------------------


class GPIOInterface(ABC):
    """Interface for GPIO (General-Purpose Input/Output) pin control.

    Modeled after RPi.GPIO (the Raspberry Pi GPIO library).  Implementations
    may use class methods (for RPi.GPIO drop-in compatibility) or instance
    methods — the abstract interface uses instance methods as the
    language-independent baseline.

    Implementing classes should define constants for:
    - Pin numbering modes: ``BCM`` (Broadcom SOC channel), ``BOARD`` (physical pin)
    - Pin directions: ``IN``, ``OUT``
    - Pin values: ``HIGH`` (1), ``LOW`` (0)
    """

    @abstractmethod
    def setmode(self, mode: str) -> None:
        """Set the pin numbering mode.  Accepts a mode string (e.g., "BCM" or "BOARD")."""
        ...

    @abstractmethod
    def getmode(self) -> Optional[str]:
        """Return the current pin numbering mode as a string, or null/None if unset."""
        ...

    @abstractmethod
    def setup(self, pin: int, mode: str, pull_up_down: int = 0,
              initial: Optional[int] = None) -> None:
        """Configure a pin.

        Parameters (language-neutral):
            pin: integer pin number
            mode: string direction ("in" or "out")
            pull_up_down: integer pull resistor mode (0=off, 1=down, 2=up)
            initial: optional integer initial value (0 or 1) for output pins
        """
        ...

    @abstractmethod
    def output(self, pin: int, value: int) -> None:
        """Set an output pin value.  pin: integer, value: integer (0=LOW, 1=HIGH)."""
        ...

    @abstractmethod
    def input(self, pin: int) -> int:
        """Read a pin value.  Returns integer (0 or 1)."""
        ...

    @abstractmethod
    def cleanup(self, pin: Optional[int] = None) -> None:
        """Release one pin (integer) or all pins (null/None)."""
        ...


# ---------------------------------------------------------------------------
# I2C
# ---------------------------------------------------------------------------


class I2CInterface(ABC):
    """Interface for an I2C (Inter-Integrated Circuit) bus with register-addressed devices.

    All addresses and register values are unsigned integers.  Byte values
    are integers in the range 0-255.
    """

    @abstractmethod
    def write_byte_data(self, addr: int, register: int, value: int) -> None:
        """Write one byte (integer 0-255) to a device register.

        addr: integer device address, register: integer register address,
        value: integer byte value.
        """
        ...

    @abstractmethod
    def read_byte_data(self, addr: int, register: int) -> int:
        """Read one byte from a device register.  Returns integer 0-255."""
        ...

    @abstractmethod
    def write_i2c_block_data(self, addr: int, register: int, data: List[int]) -> None:
        """Write an array of bytes starting at the given register.

        data: array of integers (each 0-255).
        """
        ...

    @abstractmethod
    def read_i2c_block_data(self, addr: int, register: int, length: int) -> List[int]:
        """Read an array of bytes starting at the given register.

        length: integer count of bytes to read.  Returns array of integers (each 0-255).
        """
        ...

    @abstractmethod
    def write_byte(self, addr: int, value: int) -> None:
        """Write a single byte with no register address.  value: integer 0-255."""
        ...

    @abstractmethod
    def read_byte(self, addr: int) -> int:
        """Read a single byte with no register address.  Returns integer 0-255."""
        ...

    @abstractmethod
    def close(self) -> None:
        """Release the bus."""
        ...


# ---------------------------------------------------------------------------
# SPI
# ---------------------------------------------------------------------------


class SPIInterface(ABC):
    """Interface for an SPI (Serial Peripheral Interface) bus device.

    All data values are arrays of integers (each 0-255), representing bytes.
    """

    @abstractmethod
    def transfer(self, data: List[int]) -> List[int]:
        """Simultaneously send and receive bytes.

        data: array of integers (each 0-255).  Returns response as an array of
        the same length.
        """
        ...

    @abstractmethod
    def read(self, length: int) -> List[int]:
        """Read bytes by sending zeros.

        length: integer count.  Returns array of integers (each 0-255).
        """
        ...

    @abstractmethod
    def write(self, data: List[int]) -> None:
        """Write bytes, discarding the response.  data: array of integers (each 0-255)."""
        ...

    @abstractmethod
    def close(self) -> None:
        """Release the SPI device."""
        ...


# ---------------------------------------------------------------------------
# Camera
# ---------------------------------------------------------------------------


class CameraInterface(ABC):
    """Interface for a video capture device."""

    @abstractmethod
    def capture(self) -> Dict[str, Any]:
        """Capture a single frame.

        Returns a string-keyed map containing at minimum: ``frame_number``
        (integer), ``timestamp`` (float, seconds since epoch), ``width``
        (integer, pixels), ``height`` (integer, pixels).
        """
        ...

    @abstractmethod
    def set_resolution(self, width: int, height: int) -> None:
        """Change the capture resolution.  width and height: integers in pixels."""
        ...

    @abstractmethod
    def set_fps(self, fps: int) -> None:
        """Change the capture frame rate.  fps: integer frames per second."""
        ...

    @abstractmethod
    def get_properties(self) -> Dict[str, Any]:
        """Return current device properties as a string-keyed map."""
        ...

    @abstractmethod
    def release(self) -> None:
        """Release the camera device."""
        ...


# ---------------------------------------------------------------------------
# Audio
# ---------------------------------------------------------------------------


class MicrophoneInterface(ABC):
    """Interface for an audio input device."""

    @abstractmethod
    def start(self) -> None:
        """Begin capturing audio."""
        ...

    @abstractmethod
    def stop(self) -> None:
        """Stop capturing audio."""
        ...

    @abstractmethod
    def read(self) -> bytes:
        """Return one chunk of PCM (Pulse-Code Modulation) audio data as a byte array.

        Format: 16-bit signed samples, little-endian.  The number of samples
        per chunk is implementation-defined.
        """
        ...


class SpeakerInterface(ABC):
    """Interface for an audio output device (may be a null sink in simulation)."""

    @abstractmethod
    def start(self) -> None:
        """Begin accepting audio for playback."""
        ...

    @abstractmethod
    def stop(self) -> None:
        """Stop playback."""
        ...

    @abstractmethod
    def write(self, data: bytes) -> int:
        """Accept PCM (Pulse-Code Modulation) audio data as a byte array.

        Returns the number of bytes accepted (integer).
        """
        ...
