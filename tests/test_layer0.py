"""
Layer 0 sanity checks.

These tests verify that all Layer 0 simulators:
  - Import without errors
  - Return the expected dict keys
  - Behave correctly under basic operations

No external dependencies are required to run these tests.
"""

import pytest
from simulation.layer0.sensor import MockSensor, MockSensorArray
from simulation.layer0.gpio   import MockGPIO
from simulation.layer0.i2c    import MockI2C
from simulation.layer0.spi    import MockSPI
from simulation.layer0.camera import MockCamera
from simulation.layer0.audio  import MockMicrophone, MockSpeaker


# ------------------------------------------------------------------
# MockSensor
# ------------------------------------------------------------------

class TestMockSensorMotion:
    def setup_method(self):
        self.sensor = MockSensor("imu", sensor_type="motion")

    def test_read_returns_dict(self):
        data = self.sensor.read()
        assert isinstance(data, dict)

    def test_motion_has_required_keys(self):
        data = self.sensor.read()
        for key in ("device", "format", "heading", "pitch", "roll"):
            assert key in data, f"Missing key: {key}"

    def test_motion_device_name(self):
        assert self.sensor.read()["device"] == "Motion"

    def test_motion_format_name(self):
        assert self.sensor.read()["format"] == "Orientation"

    def test_heading_range(self):
        for _ in range(10):
            h = self.sensor.read()["heading"]
            assert 0 <= h < 360, f"Heading out of range: {h}"

    def test_quaternion_fields(self):
        data = self.sensor.read()
        for key in ("w", "x", "y", "z"):
            assert key in data


class TestMockSensorGPS:
    def setup_method(self):
        self.sensor = MockSensor("gps", sensor_type="gps")

    def test_gps_has_required_keys(self):
        data = self.sensor.read()
        for key in ("device", "time", "date", "fix", "latitude", "longitude",
                    "latitudeDegrees", "longitudeDegrees", "lat", "lon",
                    "speed", "altitude", "satellites"):
            assert key in data, f"Missing key: {key}"

    def test_gps_device_name(self):
        assert self.sensor.read()["device"] == "GPS"

    def test_fix_is_integer(self):
        assert isinstance(self.sensor.read()["fix"], int)


class TestMockSensorEnvironmental:
    def setup_method(self):
        self.sensor = MockSensor("enviro", sensor_type="environmental")

    def test_enviro_has_required_keys(self):
        data = self.sensor.read()
        for key in ("device", "temp", "humidity", "air_quality",
                    "tvoc_ppb", "eco2_ppm", "co2_ppm", "heat_index_c", "dew_point"):
            assert key in data, f"Missing key: {key}"

    def test_enviro_device_name(self):
        assert self.sensor.read()["device"] == "Enviro"

    def test_humidity_range(self):
        for _ in range(10):
            h = self.sensor.read()["humidity"]
            assert 0 <= h <= 100, f"Humidity out of range: {h}"


class TestMockSensorArray:
    def test_add_and_read_all(self):
        arr = MockSensorArray()
        arr.add_sensor("imu",    "motion")
        arr.add_sensor("enviro", "environmental")
        results = arr.read_all()
        assert "imu" in results
        assert "enviro" in results

    def test_remove_sensor(self):
        arr = MockSensorArray()
        arr.add_sensor("imu", "motion")
        arr.remove_sensor("imu")
        assert "imu" not in arr.read_all()


# ------------------------------------------------------------------
# MockGPIO
# ------------------------------------------------------------------

class TestMockGPIO:
    def setup_method(self):
        MockGPIO.cleanup()

    def test_setmode_bcm(self):
        MockGPIO.setmode(MockGPIO.BCM)
        assert MockGPIO.getmode() == MockGPIO.BCM

    def test_setup_and_output(self):
        MockGPIO.setmode(MockGPIO.BCM)
        MockGPIO.setup(17, MockGPIO.OUT)
        MockGPIO.output(17, MockGPIO.HIGH)
        assert MockGPIO.input(17) == MockGPIO.HIGH

    def test_input_default_low(self):
        MockGPIO.setmode(MockGPIO.BCM)
        MockGPIO.setup(18, MockGPIO.OUT)
        assert MockGPIO.input(18) == MockGPIO.LOW

    def test_cleanup_clears_pins(self):
        MockGPIO.setmode(MockGPIO.BCM)
        MockGPIO.setup(17, MockGPIO.OUT)
        MockGPIO.cleanup()
        assert MockGPIO.get_all_pins() == {}

    def test_invalid_mode_raises(self):
        with pytest.raises(ValueError):
            MockGPIO.setmode("INVALID")


# ------------------------------------------------------------------
# MockI2C
# ------------------------------------------------------------------

class TestMockI2C:
    def setup_method(self):
        self.bus = MockI2C(bus_number=1)

    def test_write_and_read_byte(self):
        self.bus.write_byte_data(0x68, 0x6B, 0xAB)
        assert self.bus.read_byte_data(0x68, 0x6B) == 0xAB

    def test_unwritten_register_returns_zero(self):
        assert self.bus.read_byte_data(0x48, 0x00) == 0x00

    def test_block_write_and_read(self):
        self.bus.write_i2c_block_data(0x68, 0x3B, [0x01, 0x02, 0x03])
        data = self.bus.read_i2c_block_data(0x68, 0x3B, 3)
        assert data == [0x01, 0x02, 0x03]

    def test_multiple_devices_independent(self):
        self.bus.write_byte_data(0x10, 0x00, 0xAA)
        self.bus.write_byte_data(0x20, 0x00, 0xBB)
        assert self.bus.read_byte_data(0x10, 0x00) == 0xAA
        assert self.bus.read_byte_data(0x20, 0x00) == 0xBB


# ------------------------------------------------------------------
# MockSPI
# ------------------------------------------------------------------

class TestMockSPI:
    def test_loopback_default(self):
        with MockSPI(bus=0, device=0) as spi:
            result = spi.transfer([0x01, 0x02, 0x03])
            assert result == [0x01, 0x02, 0x03]

    def test_custom_response_handler(self):
        def handler(data):
            return [0xFF] * len(data)

        spi = MockSPI(response_handler=handler)
        assert spi.transfer([0x00, 0x00]) == [0xFF, 0xFF]
        spi.close()

    def test_closed_raises(self):
        spi = MockSPI()
        spi.close()
        with pytest.raises(RuntimeError):
            spi.transfer([0x01])

    def test_read_returns_zeros_by_default(self):
        with MockSPI() as spi:
            # loopback of zeros is zeros
            result = spi.read(4)
            assert result == [0x00, 0x00, 0x00, 0x00]


# ------------------------------------------------------------------
# MockCamera
# ------------------------------------------------------------------

class TestMockCamera:
    def test_capture_returns_dict(self):
        with MockCamera() as cam:
            frame = cam.capture()
            assert isinstance(frame, dict)

    def test_capture_increments_frame_number(self):
        with MockCamera() as cam:
            f1 = cam.capture()
            f2 = cam.capture()
            assert f2["frame_number"] == f1["frame_number"] + 1

    def test_capture_has_dimensions(self):
        with MockCamera(width=1280, height=720) as cam:
            frame = cam.capture()
            assert frame["width"] == 1280
            assert frame["height"] == 720

    def test_released_camera_raises(self):
        cam = MockCamera()
        cam.release()
        with pytest.raises(RuntimeError):
            cam.capture()


# ------------------------------------------------------------------
# MockMicrophone / MockSpeaker
# ------------------------------------------------------------------

class TestMockMicrophone:
    def test_read_returns_bytes(self):
        mic = MockMicrophone(sample_rate=16_000, chunk_size=512)
        mic.start()
        data = mic.read()
        mic.stop()
        assert isinstance(data, bytes)

    def test_read_length_correct(self):
        mic = MockMicrophone(sample_rate=16_000, channels=1, chunk_size=256)
        mic.start()
        data = mic.read()
        mic.stop()
        # 256 samples * 1 channel * 2 bytes/sample (16-bit)
        assert len(data) == 256 * 1 * 2

    def test_read_without_start_raises(self):
        mic = MockMicrophone()
        with pytest.raises(RuntimeError):
            mic.read()


class TestMockSpeaker:
    def test_write_returns_byte_count(self):
        speaker = MockSpeaker()
        speaker.start()
        n = speaker.write(b"\x00" * 1024)
        speaker.stop()
        assert n == 1024

    def test_write_without_start_raises(self):
        speaker = MockSpeaker()
        with pytest.raises(RuntimeError):
            speaker.write(b"\x00")
