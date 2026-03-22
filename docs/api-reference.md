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
