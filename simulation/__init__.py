"""
simulation — O.A.S.I.S. simulation framework for development and testing.

Layer 0 (Hardware primitives — no external runtime deps beyond stdlib):

    from simulation.layer0.sensor import MockSensor, MockSensorArray
    from simulation.layer0.gpio   import MockGPIO
    from simulation.layer0.i2c    import MockI2C
    from simulation.layer0.spi    import MockSPI
    from simulation.layer0.camera import MockCamera
    from simulation.layer0.audio  import MockMicrophone, MockSpeaker

Layer 1 (Protocol simulation — requires paho-mqtt, websockets):

    from simulation.layer1.mqtt        import MQTTPublisher
    from simulation.layer1.ocp         import OCPBuilder
    from simulation.layer1.dap2_client import DAP2Client

Layer 2 (Software behavior — requires flask; optional LLM/memory deps):

    from simulation.layer2.ha_mock     import HomeAssistantMock
    from simulation.layer2.llm_mock    import LLMMock
    from simulation.layer2.memory_mock import MemoryMock

Top-level convenience imports (Layer 0 only — safe for all environments):
"""

from simulation.layer0.sensor import MockSensor, MockSensorArray
from simulation.layer0.gpio   import MockGPIO
from simulation.layer0.i2c    import MockI2C
from simulation.layer0.spi    import MockSPI
from simulation.layer0.camera import MockCamera
from simulation.layer0.audio  import MockMicrophone, MockSpeaker

__all__ = [
    "MockSensor",
    "MockSensorArray",
    "MockGPIO",
    "MockI2C",
    "MockSPI",
    "MockCamera",
    "MockMicrophone",
    "MockSpeaker",
]
