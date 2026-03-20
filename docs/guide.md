# E.C.H.O. — O.A.S.I.S. Simulation Framework

> **Naming note**: E.C.H.O. is a working name pending Kris Kersey's selection. See ADR-0007 in S.C.O.P.E. for the naming convention and candidate table.

## Overview

E.C.H.O. provides drop-in replacements for the hardware, protocols, and services that O.A.S.I.S. components depend on at runtime. It enables development and testing on any 4 GB device with Python or Docker — no Jetson, no GPU, and no external services required.

The framework is organized into three independent layers:

| Layer | Directory | What It Simulates | Dependencies |
|-------|-----------|-------------------|--------------|
| **Device** | `simulation/layer0/` | Hardware primitives: sensors, GPIO, I2C, SPI, camera, audio | None (stdlib only) |
| **Network** | `simulation/layer1/` | Protocol participation: OCP peers, DAP2 satellites, MQTT helpers | `paho-mqtt`, `websockets` |
| **Platform** | `simulation/layer2/` | Software behavior: Home Assistant API, LLM responses, Memory/RAG | `flask` |

Each layer is independent. If you only need sensor simulation, install the Device layer — no broker, no Flask, no network required.

The framework also follows a language-independent HAL design: Python mock implementations serve D.A.W.N. and S.C.O.P.E., while C HAL headers and mock implementations (future phases) serve M.I.R.A.G.E., A.U.R.A., and S.P.A.R.K.

## Software Dependencies

### Device Layer (Layer 0)
No external dependencies. Uses only the Python standard library.

### Network Layer (Layer 1)
| Package | Version | Purpose |
|---------|---------|---------|
| `paho-mqtt` | >=1.6.1 | MQTT client for OCP peer simulation |
| `websockets` | >=11.0 | WebSocket client for DAP2 satellite mock |

### Platform Layer (Layer 2)
| Package | Version | Purpose |
|---------|---------|---------|
| `flask` | >=3.0 | HTTP server for Home Assistant REST API mock |

### Development
| Package | Version | Purpose |
|---------|---------|---------|
| `pytest` | >=7.0 | Test runner |
| `pytest-cov` | any | Coverage reporting |

## Installation

### Python Virtual Environment (Recommended)

```bash
# Clone the repo (or add as submodule)
git clone https://github.com/malcolmhoward/the-oasis-project-simulation-repo.git
cd the-oasis-project-simulation-repo

# Create and activate virtual environment
python -m venv .venv

# Linux/macOS
source .venv/bin/activate

# Windows
.venv\Scripts\activate

# Install Device layer only (no external deps)
pip install -e .

# Install with Network layer
pip install -e ".[layer1]"

# Install all layers + dev tools
pip install -e ".[all,dev]"
```

### As a Git Submodule (Component Repos)

Component repos import E.C.H.O. as a git submodule for test and demo use:

```bash
# From your component repo root
git submodule add https://github.com/malcolmhoward/the-oasis-project-simulation-repo.git simulation
pip install -e "./simulation[all]"
```

### Docker

See `docs/DOCKER.md` for containerized development setup.

## Usage

### Device Layer — MockSensor

```python
from simulation.layer0.sensor import MockSensor

# Create a sensor with default noise
sensor = MockSensor()

# Read a single sample
data = sensor.read()
print(data["heading"])    # degrees, 0-360
print(data["pitch"])      # degrees
print(data["latitude"])   # GPS latitude
print(data["temperature"])# Celsius

# Read with a specific sensor type
gps = MockSensor(sensor_type="gps")
print(gps.read())
```

### Device Layer — MockGPIO

```python
from simulation.layer0.gpio import MockGPIO

MockGPIO.setmode(MockGPIO.BCM)
MockGPIO.setup(18, MockGPIO.OUT)
MockGPIO.output(18, MockGPIO.HIGH)
state = MockGPIO.input(18)  # Returns 1
MockGPIO.cleanup()
```

### Device Layer — MockI2C / MockSPI

```python
from simulation.layer0.i2c import MockI2C
from simulation.layer0.spi import MockSPI

# I2C: 256-byte register array per device address
bus = MockI2C(bus_number=1)
bus.write_byte_data(0x68, 0x00, 0xFF)
val = bus.read_byte_data(0x68, 0x00)  # Returns 0xFF

# SPI: loopback by default, pluggable response handlers
spi = MockSPI()
spi.open(0, 0)
response = spi.xfer2([0x01, 0x02, 0x03])
```

### Device Layer — MockCamera / MockAudio

```python
from simulation.layer0.camera import MockCamera
from simulation.layer0.audio import MockMicrophone, MockSpeaker

# Camera: returns frame metadata dicts (no pixel data needed)
cam = MockCamera()
cam.start()
frame = cam.capture()
print(frame["width"], frame["height"], frame["timestamp"])
cam.stop()

# Audio: synthetic PCM frames / null sink
mic = MockMicrophone()
mic.start()
audio_data = mic.read()
mic.stop()

speaker = MockSpeaker()
speaker.play(audio_data)  # Null sink — no actual output
```

## Communication

E.C.H.O.'s Network layer (Layer 1) simulates the MQTT and WebSocket protocols used across O.A.S.I.S.:

### MQTT Topics (OCP)

| Topic Pattern | Purpose | Layer |
|---------------|---------|-------|
| `oasis/<peer_id>/status` | OCP peer status and keepalive | Network |
| `echo/discovery/simulates` | Simulated peer discovery | Network |
| `aura` | Environmental sensor telemetry | Used by component demos |
| `stat` | System metrics and battery status | Used by component demos |

> **Note**: Component-specific MQTT schemas (e.g., M.I.R.A.G.E.'s exact JSON format for `aura` topic payloads) live in component demo directories, not in E.C.H.O. itself. E.C.H.O. provides topic builders and serializers; components own their schemas.

### DAP2 WebSocket

The DAP2 satellite mock supports:
- `satellite_register` — WebSocket registration
- Text-path command injection
- Synthetic `state`, `stream_delta`, `stream_end` responses

## Troubleshooting

### Import Errors

**`ModuleNotFoundError: No module named 'simulation'`**
Ensure you installed the package in editable mode: `pip install -e .` from the repo root.

**`ModuleNotFoundError: No module named 'paho'`**
You are using a Network layer class but only installed the base package. Install with: `pip install -e ".[layer1]"`

**`ModuleNotFoundError: No module named 'flask'`**
You are using a Platform layer class but only installed base or Layer 1. Install with: `pip install -e ".[all]"`

### Test Failures

**`pytest: command not found`**
Install dev dependencies: `pip install -e ".[all,dev]"`

**Layer 0 tests should always pass with no external dependencies.** If a Layer 0 test fails, it indicates a real bug — file an issue.

### Submodule Issues

**`fatal: not a git repository` when running from a component repo**
Ensure the submodule is initialized: `git submodule update --init`

## Related Components

| Component | Relationship |
|-----------|-------------|
| [M.I.R.A.G.E.](https://github.com/The-OASIS-Project/mirage) | Uses Device layer (IMU, GPS, environmental sensors, camera) for HUD development without hardware |
| [D.A.W.N.](https://github.com/The-OASIS-Project/dawn) | Uses all three layers for full intent-processing pipeline testing |
| [A.U.R.A.](https://github.com/The-OASIS-Project/aura) | Uses Device layer (environmental sensors, I2C) |
| [S.P.A.R.K.](https://github.com/The-OASIS-Project/spark) | Uses Device layer (GPIO, SPI) |
| [S.T.A.T.](https://github.com/The-OASIS-Project/stat) | Uses Device layer (system metrics, battery) |
| [S.C.O.P.E.](https://github.com/malcolmhoward/the-oasis-project-meta-repo) | Uses Network layer (OCP peer mocks, MQTT helpers) for coordination testing |
