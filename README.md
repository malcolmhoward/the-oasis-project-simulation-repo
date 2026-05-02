# O.A.S.I.S. Simulation Framework

Software simulators for O.A.S.I.S. hardware, protocols, and services — develop and test without physical hardware or live external service dependencies.

## Why This Project?

O.A.S.I.S. is a distributed system that spans NVIDIA Jetsons, Raspberry Pis, custom sensor arrays, and specialized software services. Without simulation, a contributor needs physical hardware or running infrastructure just to test their code. That is a steep barrier for an open-source project whose mission includes accessibility.

The simulation framework removes that barrier. Every hardware interface and every external service dependency has a drop-in mock that runs on any 2 GB machine with Python or Docker. The goal is simple: **no contributor should be blocked by hardware they do not own**.

## Description

The simulation framework provides drop-in replacements for the physical and software dependencies that O.A.S.I.S. components require at runtime:

| Layer | What it simulates | Dependencies |
|-------|------------------|--------------|
| **Device** (`layer0`) | Hardware primitives — sensors, GPIO, I2C, SPI, camera, audio | None (stdlib only) |
| **Network** (`layer1`) | Communication protocols — MQTT, DAP2 WebSocket, OCP messages | `paho-mqtt`, `websockets` |
| **Platform** (`layer2`) | External software services — Home Assistant, LLM, memory/RAG | `flask` |

Each layer is independent. If you only need sensor simulation, install the Device layer — no broker, no Flask, no network required.

> **Layer naming note**: Device / Network / Platform are provisional names pending ecosystem review. Internal package directories use `layer0/`, `layer1/`, `layer2/`.

## Who Is This For

O.A.S.I.S. is designed to run on specialized hardware — NVIDIA Jetson,
Raspberry Pi, custom sensor arrays. But the ideas behind it should not
require hardware ownership as a prerequisite for contribution.

The simulation framework lets you develop and test against the full O.A.S.I.S.
software stack on a standard laptop, a modest desktop, a Chromebook, or a
Windows or macOS machine. **No Jetson required. No GPU required. No external
services required.**

O.A.S.I.S. components have two distinct categories of dependency that can
block contributors:

- **Hardware dependencies** — GPIO, I2C, cameras, sensors, microphones
- **Software service dependencies** — a local LLM (which requires Jetson-class
  CPU or GPU for real inference), Home Assistant, real-time ASR, and a
  memory/RAG system

The simulation framework addresses both. The Device layer replaces hardware
for any component (M.I.R.A.G.E., A.U.R.A., S.P.A.R.K., S.T.A.T.). The
Platform layer replaces software services — using in-process Flask and SQLite
mocks that carry no compute or memory floor. A developer on any platform can
exercise the full O.A.S.I.S. software stack without any of those dependencies
running. D.A.W.N. benefits the most (it uses all three layers), but every
component has mock coverage.

There are two ways to use the simulation framework:

- **Python only** — install the simulation package with `pip` and develop
  against it directly. Works on Linux, macOS, Windows (WSL2), and Chrome OS
  (Crostini).
- **Pre-built Docker image** — load a pre-built image and run it with
  `docker compose up`. Works on Linux, **Windows (Docker Desktop)**, and
  **macOS (Docker Desktop)** — no Linux required on the host. The container
  is a self-contained Linux environment; `docker-compose` handles all
  OS-specific differences.

### Minimum hardware

| Access path | RAM | GPU | Host OS | Notes |
|-------------|:---:|:---:|---------|-------|
| Python simulation | 2 GB | Not required | Linux, macOS, Windows (WSL2), Chrome OS (Crostini) | Suitable for classroom use |
| Docker image | 2 GB | Not required | **Linux, Windows, macOS** — any OS with Docker | Full simulation stack; no build required on recipient machine |
| Build locally | 8 GB | Not required | Linux (Debian/Ubuntu recommended) | Only needed for C/C++ source development |
| Full target | 8 GB+ | Jetson GPU | Linux (JetPack) | Local LLM and real-time ASR viable |

For the full breakdown — including classroom configurations, Docker image
distribution, and component coverage by profile — see the
[Development Environment Guide](https://github.com/malcolmhoward/the-oasis-project-meta-repo/blob/main/getting-started/DEVELOPMENT_ENVIRONMENT.md)
in S.C.O.P.E.

## Quick Start

```bash
# Device layer only (most common — hardware primitives, no extra deps)
pip install -e .

# Device + Network layers (adds protocol simulation)
pip install -e ".[layer1]"

# All layers
pip install -e ".[all]"

# Development (adds pytest)
pip install -e ".[dev]"
```

Or, for Docker/CI without cloning:

```bash
pip install "git+https://github.com/malcolmhoward/the-oasis-project-simulation-repo.git"
```

```python
from simulation.layer0.sensor import MockSensor

sensor = MockSensor("imu", sensor_type="motion")
data = sensor.read()
print(data)
# {"device": "Motion", "format": "Orientation", "heading": 45.2, "pitch": -2.1, "roll": 3.5, ...}
```

### Recommended Alias

`simulation` is the full package name; `sim` is a natural shorthand:

```python
import simulation as sim

imu    = sim.MockSensor("imu",    sensor_type="motion")
gps    = sim.MockSensor("gps",    sensor_type="gps")
enviro = sim.MockSensor("enviro", sensor_type="environmental")
camera = sim.MockCamera(width=1920, height=1080, fps=30)
gpio   = sim.MockGPIO()

# Use just like the real hardware interfaces
reading = imu.read()
frame   = camera.capture()
```

## Documentation

### Device Layer — Hardware Primitives

#### MockSensor

Generates time-varying sensor values matching O.A.S.I.S. MQTT message schemas.

| `sensor_type` | MQTT `device` field | Key output fields |
|---------------|--------------------|--------------------|
| `"motion"` | `"Motion"` | `heading`, `pitch`, `roll`, `w`, `x`, `y`, `z` |
| `"gps"` | `"GPS"` | `latitude`, `longitude`, `altitude`, `satellites`, `fix` |
| `"environmental"` | `"Enviro"` | `temp`, `humidity`, `air_quality`, `tvoc_ppb`, `eco2_ppm`, `co2_ppm` |
| `"temperature"` | *(generic)* | `temperature` |
| `"humidity"` | *(generic)* | `humidity` |

Values vary over time via sine-wave functions — each sensor has a random phase offset so they don't all move in lockstep.

```python
from simulation.layer0.sensor import MockSensor, MockSensorArray

# Single sensor
sensor = MockSensor("imu", sensor_type="motion")
data = sensor.read()

# Adjust simulated base values
sensor.calibrate(heading=180.0, pitch=0.0)

# Multiple sensors
sensors = MockSensorArray()
sensors.add_sensor("imu",    "motion")
sensors.add_sensor("enviro", "environmental")
all_readings = sensors.read_all()
```

#### MockGPIO

API-compatible with `RPi.GPIO` (class-method interface).

```python
from simulation.layer0.gpio import MockGPIO

MockGPIO.setmode(MockGPIO.BCM)
MockGPIO.setup(17, MockGPIO.OUT)
MockGPIO.output(17, MockGPIO.HIGH)
value = MockGPIO.input(17)
MockGPIO.cleanup()
```

#### MockI2C

256-byte register array per device address.

```python
from simulation.layer0.i2c import MockI2C

bus = MockI2C(bus_number=1)
bus.write_byte_data(0x68, 0x6B, 0x00)   # wake MPU-6050
whoami = bus.read_byte_data(0x68, 0x75)
```

#### MockSPI

Loopback by default; supports pluggable response handlers for device-specific behaviour.

```python
from simulation.layer0.spi import MockSPI

with MockSPI(bus=0, device=0) as spi:
    response = spi.transfer([0xD0, 0x00])  # echoed back by default

# Custom device response
def bme280_id(data):
    if data[0] == 0xD0:
        return [0x60, 0x00]  # WHO_AM_I for BME280
    return [0x00] * len(data)

spi = MockSPI(response_handler=bme280_id)
```

#### MockCamera

Returns frame metadata dicts (no actual pixel data needed for most tests).

```python
from simulation.layer0.camera import MockCamera

with MockCamera(device_id=0, width=1920, height=1080, fps=30) as cam:
    frame = cam.capture()
    print(frame["frame_number"], frame["brightness"])
```

#### MockMicrophone / MockSpeaker

```python
from simulation.layer0.audio import MockMicrophone, MockSpeaker

mic = MockMicrophone(sample_rate=16_000, channels=1, chunk_size=1024)
mic.start()
pcm_bytes = mic.read()   # 16-bit signed PCM, little-endian
mic.stop()

speaker = MockSpeaker(sample_rate=16_000)
speaker.start()
speaker.write(pcm_bytes)  # null sink — discards audio
speaker.stop()
```

### Network Layer — Protocol Simulation

Enables testing of O.A.S.I.S. protocol interactions without live hardware:

- **`mqtt.py`** — MQTT topic publisher/subscriber helpers with message serializers
- **`ocp.py`** — OCP (O.A.S.I.S. Communications Protocol) peer registration with E1-E5 embodiment spectrum
- **`dap2_client.py`** — DAP2 satellite WebSocket client (register, query, text-path command injection)
- **`status_listeners.py`** — MQTT broadcast, TTS notification, audio alert, and WebUI status listeners

### Platform Layer — Software Service Simulation

In-process Flask servers and deterministic stubs for external services:

- **`ha_mock.py`** — Home Assistant REST API mock (`/api/states`, `/api/services/...`)
- **`llm_mock.py`** — LLM response simulator (keyword → tool call synthesis, streaming)
- **`llm_http_server.py`** — OpenAI-compatible `/v1/chat/completions` HTTP wrapper around LLMMock
- **`memory_mock.py`** — Memory/RAG stub (SQLite-backed fact store, keyword retrieval)

### OCP Embodiment Spectrum

OCP peers declare an embodiment type indicating their relationship to physical reality:

| Type | Name | Description | Example |
|------|------|-------------|---------|
| E1 | Physical | Real hardware with sensors and actuators | Jetson, Raspberry Pi, Arduino |
| E2 | Remote-Physical | Real hardware, remote operator | Robot driven wirelessly |
| E3 | Digital/Virtual | Game engine avatar, simulation peer | Godot character, E.C.H.O. mock |
| E4 | Software-Only | No body — pure service/infrastructure | LLM routing, session management |
| E5 | Hybrid | Spans multiple types via Provider | Real camera + simulated sensors |

All five types are implemented across O.A.S.I.S. ecosystem branches. The `Embodiment` enum in `simulation/layer1/ocp.py` currently defines E3 (physical) and E4 (software). The full E1-E5 taxonomy is specified in ADR-0003 Amendment 5 in S.C.O.P.E.

### HAL Architecture

All mock classes implement interface contracts defined as ABCs (Abstract Base Classes) in `simulation/hal/`. Two cross-cutting components support runtime flexibility:

- **Provider** (`simulation/hal/provider.py`) — Thread-safe runtime hot-swap wrapper. Component code programs against the HAL interface; the Provider manages which implementation (mock or real) is active and handles transparent swapping. Supports swap callbacks for notification (SimulationStatus, MQTT broadcast, TTS) and graceful degradation when hardware disconnects.

  ```python
  from simulation.hal.provider import Provider
  from simulation.layer0.camera import MockCamera

  camera = Provider(MockCamera())
  frame = camera.capture()       # MockCamera.capture()
  camera.swap(RealCamera())      # hot-swap at runtime
  frame = camera.capture()       # RealCamera.capture()
  camera.swap(MockCamera())      # graceful fallback
  ```

- **SimulationStatus** (`simulation/hal/status.py`) — Per-interface registry tracking whether each dependency is simulated or live. Supports event listeners for mode-change notifications (MQTT broadcast, TTS alerts, WebUI status, structured logging).

### Running Tests

```bash
# Install with dev dependencies first
pip install -e ".[dev]"

# Run all tests
pytest

# Run Device layer tests only
pytest tests/test_layer0.py -v
```

### Integration with Component Repos

This repository is designed for use as a **git submodule** in O.A.S.I.S. component repos:

```bash
# In a component repo
git submodule add https://github.com/malcolmhoward/the-oasis-project-simulation-repo simulation_framework
cd simulation_framework && pip install -e .
```

## Status

| Layer | Status |
|-------|--------|
| Device — Hardware primitives | **Available** |
| Network — Protocol simulation | **Available** |
| Platform — Service simulation | **Available** |

## Contributing

Please see [CONTRIBUTING.md](CONTRIBUTING.md) for the fork-first workflow, branch naming conventions, and code review process.

## License

GPL-3.0. This project is part of the O.A.S.I.S. ecosystem; all O.A.S.I.S. component repositories use the GNU General Public License v3.0. See [LICENSE](LICENSE).

## Security

For security concerns, please open a private issue or contact the maintainers via the [O.A.S.I.S. meta-repository](https://github.com/malcolmhoward/the-oasis-project-meta-repo).
