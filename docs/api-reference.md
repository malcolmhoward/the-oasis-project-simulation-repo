# API Reference

Class and method documentation for the simulation framework. Each layer's section is added alongside its implementation.

## HAL (Hardware Abstraction Layer) — Interface Contracts

### `simulation.hal.device`

| Interface | Methods | Description |
|-----------|---------|-------------|
| `SensorInterface` | `read()`, `calibrate(**kwargs)`, `activate()`, `deactivate()`, `reset()` | Sensor that produces periodic readings as a string-keyed map |
| `SensorArrayInterface` | `add_sensor(name, type)`, `remove_sensor(name)`, `read_all()`, `read_sensor(name)`, `list_sensors()` | Named collection of sensors |
| `GPIOInterface` | `setmode(mode)`, `getmode()`, `setup(pin, mode, ...)`, `output(pin, value)`, `input(pin)`, `cleanup(pin)` | GPIO (General-Purpose Input/Output) pin control |
| `I2CInterface` | `write_byte_data(addr, reg, val)`, `read_byte_data(addr, reg)`, `write_i2c_block_data(...)`, `read_i2c_block_data(...)`, `write_byte(addr, val)`, `read_byte(addr)`, `close()` | I2C (Inter-Integrated Circuit) bus |
| `SPIInterface` | `transfer(data)`, `read(length)`, `write(data)`, `close()` | SPI (Serial Peripheral Interface) bus |
| `CameraInterface` | `capture()`, `set_resolution(w, h)`, `set_fps(fps)`, `get_properties()`, `release()` | Video capture device |
| `MicrophoneInterface` | `start()`, `stop()`, `read()` | Audio input (returns PCM byte array) |
| `SpeakerInterface` | `start()`, `stop()`, `write(data)` | Audio output (accepts PCM byte array) |

### `simulation.hal.provider`

| Class | Methods | Description |
|-------|---------|-------------|
| `Provider(initial, on_swap)` | `swap(new_impl)`, `implementation`, `implementation_type` | Runtime hot-swap wrapper; forwards all attribute access to the active implementation. Thread-safe. |

---

## Device Layer — `simulation.layer0`

### `MockSensor(SensorInterface)`

Generates time-varying sensor values matching O.A.S.I.S. MQTT message schemas.

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `name` | string | `"sensor"` | Sensor identifier |
| `sensor_type` | string | `"generic"` | Type: `"motion"`, `"gps"`, `"environmental"`, `"temperature"`, `"humidity"`, `"pressure"` |
| `update_interval` | float | `0.0` | Minimum seconds between reads |

| Method | Returns | Description |
|--------|---------|-------------|
| `read()` | string-keyed map | Sensor reading; schema depends on `sensor_type` |
| `calibrate(**kwargs)` | None | Override base values (e.g., `heading=180.0`) |
| `activate()` / `deactivate()` | None | Enable/disable the sensor |
| `reset()` | None | Reset reading count and timer |

### `MockSensorArray(SensorArrayInterface)`

Named collection of `MockSensor` instances.

| Method | Returns | Description |
|--------|---------|-------------|
| `add_sensor(name, sensor_type)` | `MockSensor` | Create and register a sensor |
| `remove_sensor(name)` | None | Remove by name |
| `read_all()` | map of name → reading | Read all sensors |
| `read_sensor(name)` | string-keyed map | Read one sensor |
| `list_sensors()` | list of strings | All registered names |

### `MockGPIO(GPIOInterface)`

RPi.GPIO-compatible class-method API.

| Constant | Value | Description |
|----------|-------|-------------|
| `BCM` | `"BCM"` | Broadcom SOC channel numbering |
| `BOARD` | `"BOARD"` | Physical pin numbering |
| `IN` / `OUT` | `"in"` / `"out"` | Pin directions |
| `HIGH` / `LOW` | `1` / `0` | Pin values |

All methods are class methods: `setmode()`, `getmode()`, `setup()`, `output()`, `input()`, `cleanup()`, `add_event_detect()`, `remove_event_detect()`.

### `MockI2C(I2CInterface)`

256-byte register array per device address.

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `bus_number` | integer | `1` | I2C bus number |

### `MockSPI(SPIInterface)`

Loopback by default; pluggable response handlers.

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `bus` | integer | `0` | SPI bus |
| `device` | integer | `0` | SPI device (chip select) |
| `max_speed_hz` | integer | `500000` | Clock speed |
| `mode` | integer | `0` | SPI mode (0-3) |
| `response_handler` | callable or None | `None` | Custom response: `(data: list[int]) -> list[int]` |

### `MockCamera(CameraInterface)`

Returns frame metadata dicts (no pixel data).

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `device_id` | integer | `0` | Camera device ID |
| `width` | integer | `1920` | Frame width in pixels |
| `height` | integer | `1080` | Frame height in pixels |
| `fps` | integer | `30` | Frames per second |

`capture()` returns: `frame_number`, `timestamp`, `elapsed_time`, `width`, `height`, `device_id`, `fps`, `brightness`, `contrast`, `data`.

### `MockMicrophone(MicrophoneInterface)`

Synthetic sine-wave PCM (Pulse-Code Modulation) audio source.

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `sample_rate` | integer | `16000` | Samples per second |
| `channels` | integer | `1` | Audio channels |
| `chunk_size` | integer | `1024` | Samples per read() call |
| `frequency_hz` | float | `440.0` | Sine wave frequency |
| `amplitude` | float | `0.3` | Signal amplitude (0.0-1.0) |

### `MockSpeaker(SpeakerInterface)`

Null-sink audio output.

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `sample_rate` | integer | `16000` | Samples per second |
| `channels` | integer | `1` | Audio channels |

---

## Network Layer — `simulation.layer1`

### `simulation.hal.network` — Interface Contracts

| Interface | Methods | Description |
|-----------|---------|-------------|
| `TopicBuilderInterface` | `status()`, `discovery(capability)`, `command()`, `broadcast()`, `peer_status(peer_id)`, `sim_discovery()` | MQTT (Message Queuing Telemetry Transport) topic string construction |
| `MessageSerializerInterface` | `status_online(...)`, `status_offline()`, `discovery(elements)`, `command(...)`, `response(...)` | OCP (OASIS Communications Protocol) message serialization to JSON |
| `OCPPeerInterface` | `set_lwt()`, `start()`, `stop()`, `is_running` | OCP peer lifecycle |
| `DAP2SatelliteInterface` | `connect()`, `disconnect()`, `query(text)`, `is_connected` | DAP2 (Dawn Audio Protocol 2.0) satellite client |
| `DAP2DaemonInterface` | `start()`, `stop()` | DAP2 mock server |

### `TopicBuilder(TopicBuilderInterface)`

Builds MQTT topic strings per OCP conventions.

| Parameter | Type | Description |
|-----------|------|-------------|
| `component` | string | Component name (e.g., `"mirage"` → `"hud"`, `"dawn"` → `"dawn"`) |

### `MessageSerializer(MessageSerializerInterface)`

Serializes OCP messages to JSON strings.

| Parameter | Type | Description |
|-----------|------|-------------|
| `device` | string | Device name included in message payloads |

### `OCPPeer(OCPPeerInterface)`

Simulated OCP peer with status, discovery, and heartbeat.

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `client` | paho MQTT client | (required) | Connected MQTT client |
| `peer_id` | string | (required) | Unique peer identifier |
| `component` | string | (required) | O.A.S.I.S. component name |
| `embodiment` | `Embodiment` | `E4` | `Embodiment.E3` (physical) or `Embodiment.E4` (software) |
| `capabilities` | list of strings | `[]` | Advertised in discovery messages |
| `version` | string | `"0.0.0-sim"` | Version in status messages |
| `heartbeat_interval` | float | `30.0` | Seconds between heartbeat publishes |

### `DAP2Satellite(DAP2SatelliteInterface)`

WebSocket client for DAP2 satellite protocol.

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `uri` | string | `"ws://localhost:3000"` | D.A.W.N. daemon WebSocket URI |
| `name` | string | `"Mock Satellite"` | Satellite display name |
| `location` | string | `"simulation"` | Room or location identifier |
| `ping_interval` | float | `10.0` | Seconds between keepalive pings |

`query(text)` returns a `StreamResponse` with: `stream_id` (integer), `text` (assembled response string), `reason` (string), `states` (list of state maps).

### `DAP2MockDaemon(DAP2DaemonInterface)`

Standalone DAP2 mock server for testing without D.A.W.N.

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `host` | string | `"localhost"` | Bind address |
| `port` | integer | `3000` | Bind port |
| `query_handler` | callable or None | echo handler | `(text: str) -> str` response generator |

---

## Platform Layer — `simulation.layer2`

### `simulation.hal.platform` — Interface Contracts

| Interface | Methods | Description |
|-----------|---------|-------------|
| `HomeAssistantInterface` | `start()`, `stop()`, `get_states()`, `get_state(entity_id)`, `call_service(domain, service, data)` | Home Assistant REST API |
| `LLMInterface` | `complete(prompt)`, `stream(prompt)`, `tool_call(prompt)` | LLM (Large Language Model) inference |
| `MemoryInterface` | `store(text, metadata)`, `retrieve(query, top_k)`, `delete(fact_id)`, `count()` | RAG (Retrieval-Augmented Generation) fact store |

### `HomeAssistantMock(HomeAssistantInterface)`

Flask REST API server simulating Home Assistant.

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `host` | string | `"localhost"` | Bind address |
| `port` | integer | `8123` | Bind port |
| `token` | string | `"mock-ha-token"` | Expected bearer token |
| `entities` | list of maps or None | kitchen lights, bedroom lights, thermostat | Initial entity states |

Supports: `turn_on`, `turn_off`, `toggle`, `set_temperature`. Access via HAL methods (`get_states()`, `call_service()`) or HTTP (`/api/states`, `/api/services/<domain>/<service>`).

### `LLMMock(LLMInterface)`

Keyword-to-response and keyword-to-tool-call mapping. Works like voice assistant skills (Amazon Alexa, Google Assistant) — recognized commands map to specific actions without AI inference.

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `default_response` | string | `"I'm not sure..."` | Response when no rule matches |

| Method | Description |
|--------|-------------|
| `add_rule(keyword, response)` | Map keyword to text response |
| `add_tool_rule(keyword, tool, args)` | Map keyword to tool call |
| `complete(prompt)` | Return matching response string |
| `stream(prompt)` | Return word-level delta iterator |
| `tool_call(prompt)` | Return matching tool call map or None |

### `LLMHTTPServer`

OpenAI-compatible HTTP wrapper for `LLMMock`. D.A.W.N.'s local LLM provider auto-detects this as a "generic OpenAI-compatible" endpoint.

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `llm` | `LLMMock` | (required) | Mock LLM instance |
| `host` | string | `"0.0.0.0"` | Bind address |
| `port` | integer | `8080` | Bind port |
| `model_name` | string | `"echo-mock"` | Model name in API responses |

Endpoints: `POST /v1/chat/completions` (streaming and non-streaming), `GET /v1/models`.

### `MemoryMock(MemoryInterface)`

SQLite-backed fact store with keyword overlap scoring.

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `db_path` | string | `":memory:"` | SQLite path; `":memory:"` for in-memory |

| Method | Returns | Description |
|--------|---------|-------------|
| `store(text, metadata)` | string (UUID) | Store a fact |
| `retrieve(query, top_k)` | list of maps with `text`, `score`, optional `metadata` | Keyword-match retrieval |
| `delete(fact_id)` | boolean | Delete by ID |
| `count()` | integer | Total stored facts |
