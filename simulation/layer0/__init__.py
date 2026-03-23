"""Layer 0: Hardware primitive simulators (no external runtime dependencies)."""

from simulation.layer0.sensor import MockSensor, MockSensorArray
from simulation.layer0.gpio   import MockGPIO
from simulation.layer0.i2c    import MockI2C
from simulation.layer0.spi    import MockSPI
from simulation.layer0.camera import MockCamera
from simulation.layer0.audio  import MockMicrophone, MockSpeaker

__all__ = [
    "MockSensor", "MockSensorArray",
    "MockGPIO",
    "MockI2C",
    "MockSPI",
    "MockCamera",
    "MockMicrophone", "MockSpeaker",
]
