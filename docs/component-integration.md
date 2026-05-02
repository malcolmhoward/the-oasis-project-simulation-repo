# Component Integration Guide

How each O.A.S.I.S. component imports and uses the E.C.H.O. simulation framework for development and testing.

## Quick Reference

| Component | Layers Used | Primary Mock Classes |
|-----------|-------------|---------------------|
| M.I.R.A.G.E. | Device | `MockSensor` (motion, GPS, environmental), `MockCamera` |
| D.A.W.N. | Device, Network, Platform | `MockSensor`, `DAP2Satellite`, `OCPPeer`, `HomeAssistantMock`, `LLMMock`, `MemoryMock` |
| A.U.R.A. | Device | `MockSensor` (environmental), `MockI2C` |
| S.P.A.R.K. | Device | `MockGPIO`, `MockSPI` |
| S.T.A.T. | Device | `MockSensor` (system metrics, battery) |
| S.C.O.P.E. | Network | `OCPPeer`, `TopicBuilder`, `MessageSerializer` |

---

## M.I.R.A.G.E. — HUD Display

M.I.R.A.G.E. subscribes to MQTT topics and renders sensor data on its HUD. The simulation framework provides the sensor data publishers.

### Installation

```bash
# As a git submodule in the M.I.R.A.G.E. repo
git submodule add https://github.com/malcolmhoward/the-oasis-project-simulation-repo simulation_framework
pip install -e "./simulation_framework"
```

### Usage — Mock Sensor Publisher

```python
import json
import time
import paho.mqtt.client as mqtt
from simulation.layer0.sensor import MockSensor

client = mqtt.Client()
client.connect("localhost", 1883)

imu = MockSensor("imu", sensor_type="motion")
gps = MockSensor("gps", sensor_type="gps")
enviro = MockSensor("enviro", sensor_type="environmental")

while True:
    client.publish("aura", json.dumps(imu.read()))
    client.publish("aura", json.dumps(gps.read()))
    client.publish("aura", json.dumps(enviro.read()))
    time.sleep(1.0)
```

M.I.R.A.G.E. receives these messages on the `aura` topic and displays heading, pitch, roll, GPS coordinates, and environmental data — all from simulated values.

### With Provider (runtime hot-swap)

```python
from simulation.hal.provider import Provider
from simulation.layer0.camera import MockCamera

# Start with mock camera
camera = Provider(MockCamera(device_id=0, width=1920, height=1080))
frame = camera.capture()  # simulated metadata

# USB camera plugged in — swap to real driver
# camera.swap(RealCamera(device_id=0))

# USB camera unplugged — fall back to mock
# camera.swap(MockCamera(device_id=0))
```

### Demo

See [`demos/hud-mock/`](https://github.com/malcolmhoward/mirage/tree/feat/mirage/5-simulation-demo/demos/hud-mock) for a Docker Compose demo with broker + mock publisher + M.I.R.A.G.E. HUD.

---

## D.A.W.N. — AI Voice Assistant

D.A.W.N. uses all three layers. The simulation framework provides mock services that D.A.W.N. connects to via its standard configuration (no code changes needed).

### Service-Level Integration

D.A.W.N. is a C application — it doesn't import Python mocks directly. Instead, the mocks run as HTTP/WebSocket servers that D.A.W.N. connects to:

| D.A.W.N. Config | Mock Service | Port |
|-----------------|-------------|------|
| `[homeassistant] url` | `HomeAssistantMock` (Flask) | 8123 |
| `[llm.local] endpoint` | `LLMHTTPServer` (OpenAI-compatible) | 8080 |
| `[mqtt] broker` | Eclipse Mosquitto | 1883 |

### Configuration (`dawn-simulation.toml`)

```toml
[llm]
type = "local"

[llm.local]
endpoint = "http://mock-llm:8080"
provider = "generic"

[mqtt]
broker = "mqtt-broker"

[homeassistant]
url = "http://mock-ha:8123"
enabled = true

[audio]
enabled = false
```

### Demo

See [`demos/full-mock/`](https://github.com/malcolmhoward/dawn/tree/feat/dawn/9-simulation-demo/demos/full-mock) for a Docker Compose demo with D.A.W.N. + mock services.

---

## A.U.R.A. — Helmet Sensors

A.U.R.A. reads environmental sensors via I2C and publishes to MQTT. The simulation framework replaces the real I2C bus and sensors.

### Usage

```python
from simulation.layer0.i2c import MockI2C
from simulation.layer0.sensor import MockSensor

# Simulate I2C environmental sensor (e.g., BME680)
bus = MockI2C(bus_number=1)
bus.write_byte_data(0x76, 0xD0, 0x61)  # WHO_AM_I for BME680

# Or use MockSensor for higher-level data
enviro = MockSensor("enviro", sensor_type="environmental")
reading = enviro.read()
# {"device": "Enviro", "temp": 22.5, "humidity": 65.0, "co2_ppm": 415.0, ...}
```

---

## S.P.A.R.K. — Armor Actuators

S.P.A.R.K. controls actuators via GPIO and communicates with sensors via SPI.

### Usage

```python
from simulation.layer0.gpio import MockGPIO
from simulation.layer0.spi import MockSPI

# Simulate GPIO pin control (e.g., LED indicator)
MockGPIO.setmode(MockGPIO.BCM)
MockGPIO.setup(18, MockGPIO.OUT)
MockGPIO.output(18, MockGPIO.HIGH)

# Simulate SPI sensor (e.g., accelerometer with custom response)
def accel_response(data):
    if data[0] == 0x0F:  # WHO_AM_I register
        return [0x33] + [0x00] * (len(data) - 1)
    return [0x00] * len(data)

spi = MockSPI(bus=0, device=0, response_handler=accel_response)
device_id = spi.transfer([0x0F, 0x00])  # returns [0x33, 0x00]
```

---

## S.T.A.T. — System Monitor

S.T.A.T. reads system metrics (CPU, memory, temperature, battery) and publishes to MQTT.

### Usage

```python
from simulation.layer0.sensor import MockSensor

# System metrics don't have a dedicated sensor type yet —
# use calibrate() to set base values for generic sensors
system = MockSensor("system", sensor_type="temperature")
system.calibrate(temperature=52.3)  # simulated CPU temperature
reading = system.read()
```

For the MQTT publishing pattern, see the ecosystem demo's [`entrypoint.py`](https://github.com/malcolmhoward/the-oasis-project-meta-repo/tree/feat/scope/40-ecosystem-demo/demos/ecosystem-mock/mock_ecosystem/entrypoint.py) which publishes `SystemMetrics` and `BatteryStatus` on the `stat` topic.

---

## S.C.O.P.E. — Coordination

S.C.O.P.E. coordinates the ecosystem and monitors component health via OCP.

### Usage

```python
import paho.mqtt.client as mqtt
from simulation.layer1.ocp import OCPPeer, Embodiment
from simulation.layer1.mqtt import TopicBuilder, MessageSerializer

client = mqtt.Client()
client.connect("localhost", 1883)
client.loop_start()

# Register as a coordination peer
scope = OCPPeer(
    client=client,
    peer_id="scope-coordination",
    component="scope",
    embodiment=Embodiment.E4,
    capabilities=["coordination", "monitoring"],
)
scope.start()  # publishes status + discovery, starts heartbeat

# Build and publish OCP messages
serializer = MessageSerializer("scope")
client.publish("oasis/broadcast", serializer.command(action="health_check"))
```
