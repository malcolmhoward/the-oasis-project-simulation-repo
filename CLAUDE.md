# CLAUDE.md - LLM Integration Guide

## Project Overview

**E.C.H.O.** (working name) is the O.A.S.I.S. simulation framework — drop-in replacements for the hardware, protocols, and services that O.A.S.I.S. components depend on at runtime. It enables development and testing on any 2 GB device with Python or Docker, without specialized hardware, GPUs, or external services.

The framework follows a language-independent HAL design, serving both Python components (D.A.W.N., S.C.O.P.E.) and C components (M.I.R.A.G.E., A.U.R.A., S.P.A.R.K.).

> **Naming note**: E.C.H.O. is a working name pending Kris Kersey's selection. See ADR-0007 in S.C.O.P.E. for the naming convention and candidate table.

## Architecture

### Three Simulation Layers

| Layer | Directory | Stability | What It Simulates | Dependencies |
|-------|-----------|-----------|-------------------|--------------|
| **Device** | `simulation/layer0/` | STABLE | Hardware primitives: sensors, GPIO, I2C, SPI, camera, audio | None (stdlib only) |
| **Network** | `simulation/layer1/` | STABLE | Protocol participation: OCP peers, DAP2 satellites, MQTT helpers | `paho-mqtt`, `websockets` |
| **Platform** | `simulation/layer2/` | VERSIONED | Software behavior: Home Assistant API, LLM responses, Memory/RAG | `flask` |

Layer stability is enforced structurally — a breaking change in the Platform layer does not affect the Device or Network layers.

> **Layer naming note**: Device / Network / Platform are provisional names pending ecosystem review. Internal package directories use `layer0/`, `layer1/`, `layer2/`.

### Language-Independent HAL

| Phase | Deliverable | Components Served |
|-------|-------------|-------------------|
| 1 | Python mock implementations (all three layers) | D.A.W.N., S.C.O.P.E. |
| 2 | C HAL headers (interface definitions matching real hardware APIs) | M.I.R.A.G.E., A.U.R.A., S.P.A.R.K. |
| 3 | C mock implementations (link against HAL headers) | M.I.R.A.G.E., A.U.R.A., S.P.A.R.K. |
| 4 | Integration harness (unified test infrastructure) | All components |

## Key Files

| File | Purpose |
|------|---------|
| `simulation/__init__.py` | Package root; Layer 0 convenience imports |
| `simulation/layer0/sensor.py` | MockSensor (motion/GPS/environmental), MockSensorArray |
| `simulation/layer0/gpio.py` | MockGPIO (RPi.GPIO-compatible class-method API) |
| `simulation/layer0/i2c.py` | MockI2C (256-byte register array per device address) |
| `simulation/layer0/spi.py` | MockSPI (loopback; pluggable response handlers) |
| `simulation/layer0/camera.py` | MockCamera (frame metadata dict; no pixel data) |
| `simulation/layer0/audio.py` | MockMicrophone (synthetic PCM), MockSpeaker (null sink) |
| `simulation/layer1/mqtt.py` | MQTT topic publisher/subscriber helpers |
| `simulation/layer1/ocp.py` | OCP peer registration with E1-E5 embodiment spectrum |
| `simulation/layer1/dap2_client.py` | DAP2 satellite WebSocket client |
| `simulation/layer1/status_listeners.py` | MQTT broadcast, TTS, audio alert, WebUI status listeners |
| `simulation/layer2/ha_mock.py` | Home Assistant REST API mock (Flask) |
| `simulation/layer2/llm_mock.py` | LLM response simulator (keyword-to-tool-call, streaming) |
| `simulation/layer2/llm_http_server.py` | OpenAI-compatible `/v1/chat/completions` HTTP wrapper |
| `simulation/layer2/memory_mock.py` | Memory/RAG stub (SQLite-backed, keyword retrieval) |
| `simulation/hal/provider.py` | Runtime hot-swap Provider (thread-safe) |
| `simulation/hal/status.py` | SimulationStatus tracker (per-interface registry, event listeners) |
| `tests/test_layer0.py` | Device layer test suite |
| `tests/test_layer1.py` | Network layer test suite |
| `tests/test_layer2.py` | Platform layer test suite |
| `tests/test_provider.py` | Provider hot-swap test suite |
| `tests/test_status.py` | SimulationStatus test suite |
| `tests/test_status_listeners.py` | Status listeners test suite |
| `pyproject.toml` | Build config; optional dep groups per layer |

## Commands

```bash
# Install (Device layer only — no external deps)
pip install -e .

# Install with Network layer
pip install -e ".[layer1]"

# Install with all layers
pip install -e ".[all]"

# Install with dev tools
pip install -e ".[all,dev]"

# Run tests
pytest tests/

# Run tests with coverage
pytest tests/ --cov=simulation
```

## Working with This Codebase

### HAL-First Development Pattern

All mock classes implement interface contracts defined in the HAL (Hardware
Abstraction Layer) at `simulation/hal/`. **The interface should be defined
before its implementation.** Writing implementations first risks implicit
contracts that are harder to maintain across languages — future C HAL headers
(Phase 2) need to derive from the same interface definitions.

```
simulation/hal/device.py     ← defines SensorInterface, GPIOInterface, ...
simulation/layer0/sensor.py  ← MockSensor(SensorInterface)
simulation/layer0/gpio.py    ← MockGPIO(GPIOInterface)
```

This ensures:
- The contract is explicit and reviewable before implementation details
- Both Python mocks and future C HAL headers conform to the same interface
- In git history, the HAL commit precedes the implementation commit

### Adding a New Mock Class

1. **Define the interface** in `simulation/hal/<layer>.py` as an ABC (Abstract
   Base Class) with `@abstractmethod` for each public method
2. **Commit the interface** before writing the implementation
3. Create the mock in `simulation/layer<N>/<module>.py`, inheriting from the
   HAL ABC
4. Add the class to `simulation/layer<N>/__init__.py`
5. If Layer 0: add convenience import to `simulation/__init__.py` and `__all__`
6. Add tests in `tests/test_layer<N>.py`
7. Verify the new class has no imports above its layer's dependency tier

### Layer Dependency Rules

- `hal/` modules must NOT import from any `layer` module
- Layer 0 modules may import from `hal/` only
- Layer 1 modules may import from `hal/` and `layer0/`
- Layer 2 modules may import from `hal/`, `layer0/`, and `layer1/`
- No module may import from component repos (M.I.R.A.G.E., D.A.W.N., etc.)

### Mock Class Design Principles

- Mock classes should **implement a HAL ABC** rather than defining interfaces implicitly — without an explicit interface, future implementations in other languages cannot verify conformance
- Mock classes must be **interface-compatible** with the real drivers they replace
- Each mock should be usable in isolation — no implicit global state

### Injection Modes

The simulation framework supports three injection phases (see ADR-0003 Amendment 4):

| Phase | When | Description |
|-------|------|-------------|
| **Default** | Container/process start | All mocks active; no configuration needed |
| **Explicit** | Container/process start | User declares which deps are real vs. mocked |
| **Runtime** | After launch | Hardware/services appear or disappear; implementations swap transparently |

Runtime injection enables **graceful degradation** — when real hardware disconnects,
the framework falls back to mocks without crashing. When hardware reconnects, it
promotes back to the real driver. This aligns with O.A.S.I.S.'s loose coupling and
OCP component discovery architecture.

Component code programs against the HAL interface. A **Provider** (not part of the
HAL itself) manages which implementation is active and handles swapping. See
ADR-0003 Amendment 4 for the full design.

## O.A.S.I.S. Component Interaction

| Component | Imports From E.C.H.O. | Layers Used |
|-----------|----------------------|-------------|
| M.I.R.A.G.E. | MockSensor (IMU, GPS, environmental), MockCamera | Device |
| D.A.W.N. | MockSensor, DAP2 client, HA mock, LLM mock, Memory mock | Device, Network, Platform |
| A.U.R.A. | MockSensor (environmental), MockI2C | Device |
| S.P.A.R.K. | MockGPIO, MockSPI | Device |
| S.T.A.T. | MockSensor (system metrics, battery) | Device |
| S.C.O.P.E. | OCP peer mocks, MQTT helpers | Network |

## Branch Naming Convention

**Critical**: Branch names must include the GitHub issue number being addressed.

### Format
```
feat/simulation/<issue#>-<short-description>
```

### Before Creating a Branch

1. **Identify the issue** you're working on (check GitHub Issues)
2. **Use that issue's number** in the branch name
3. **Verify** the issue number matches the work being done

### Examples
```bash
# Working on issue #2 "Add CLAUDE.md and governance files"
git checkout -b feat/simulation/2-foundation-files

# Working on issue #5 "Add Device layer"
git checkout -b feat/simulation/5-device-layer
```

### Common Mistake
Do not use arbitrary numbers or copy from another repo's issues. Each repository has its own issue numbering. Always check `gh issue list` or GitHub Issues before creating a branch.

---

*For contribution guidelines, see [CONTRIBUTING.md](CONTRIBUTING.md).*
*For ecosystem coordination, see [S.C.O.P.E.](https://github.com/malcolmhoward/the-oasis-project-meta-repo).*
