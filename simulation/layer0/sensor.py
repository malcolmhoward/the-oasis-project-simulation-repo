"""
Layer 0: Sensor value generators for O.A.S.I.S. simulation.

Provides sensor data matching the field names and formats expected by O.A.S.I.S. components.
No external runtime dependencies beyond the standard library and numpy.

Sensor types and their MQTT device names:
  "motion"       -> device: "Motion", format: "Orientation" (heading/pitch/roll + quaternion)
  "gps"          -> device: "GPS" (time/date/fix/latitude/longitude/speed/altitude/satellites)
  "environmental"-> device: "Enviro" (temp/humidity/air_quality/tvoc_ppb/eco2_ppm/co2_ppm/heat_index_c/dew_point)
"""

import math
import time
import random
import logging
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)


from simulation.hal.device import SensorInterface, SensorArrayInterface


class MockSensor(SensorInterface):
    """
    Generic mock sensor that generates time-varying values.

    Implements :class:`~simulation.hal.device.SensorInterface`.

    Sensor type selects which fields are produced. Use ``sensor_type`` matching the
    O.A.S.I.S. MQTT device type your component expects (e.g. "motion", "gps",
    "environmental", "temperature", "humidity").

    Example::

        sensor = MockSensor("imu", sensor_type="motion")
        reading = sensor.read()
        # {"device": "Motion", "format": "Orientation", "heading": 45.2, ...}
    """

    def __init__(
        self,
        name: str = "sensor",
        sensor_type: str = "generic",
        update_interval: float = 0.0,
    ):
        self.name = name
        self.sensor_type = sensor_type
        self.update_interval = update_interval
        self.reading_count = 0
        self.last_reading_time: float = 0.0
        self.is_active = True

        # Adjustable base values (set via calibrate())
        self._base_temperature: float = 22.5
        self._base_humidity: float = 65.0
        self._base_pressure: float = 1013.25
        self._base_heading: float = 0.0      # degrees, 0-360
        self._base_pitch: float = 0.0        # degrees
        self._base_roll: float = 0.0         # degrees
        self._base_lat: float = 33.7490      # Atlanta, GA
        self._base_lon: float = -84.3880

        # Phase offset for sine-wave variation (gives each sensor a unique starting point)
        self._phase = random.uniform(0, 2 * math.pi)

        logger.info("MockSensor '%s' initialized (type: %s)", name, sensor_type)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def read(self) -> Dict[str, Any]:
        """Return a sensor reading dict. Blocks until update_interval has elapsed."""
        if not self.is_active:
            raise RuntimeError(f"Sensor '{self.name}' is not active")

        now = time.time()
        elapsed_since_last = now - self.last_reading_time
        if elapsed_since_last < self.update_interval:
            time.sleep(self.update_interval - elapsed_since_last)
            now = time.time()

        self.reading_count += 1
        self.last_reading_time = now

        readers = {
            "motion":        self._read_motion,
            "gps":           self._read_gps,
            "environmental": self._read_environmental,
            "temperature":   self._read_temperature,
            "humidity":      self._read_humidity,
            "pressure":      self._read_pressure,
        }
        reader = readers.get(self.sensor_type, self._read_generic)
        return reader(now)

    def calibrate(self, **kwargs):
        """Override base values used for simulated readings."""
        for key, value in kwargs.items():
            attr = f"_base_{key}"
            if hasattr(self, attr):
                setattr(self, attr, value)
                logger.info("Calibrated %s.%s = %s", self.name, key, value)

    def activate(self):
        self.is_active = True

    def deactivate(self):
        self.is_active = False

    def reset(self):
        self.reading_count = 0
        self.last_reading_time = 0.0

    def __repr__(self):
        return f"MockSensor(name={self.name!r}, type={self.sensor_type!r})"

    # ------------------------------------------------------------------
    # Sensor-specific readers — output matches O.A.S.I.S. MQTT schemas
    # ------------------------------------------------------------------

    def _sine(self, t: float, period: float = 60.0, amplitude: float = 1.0) -> float:
        """Smooth sine-wave variation with this sensor's phase offset."""
        return amplitude * math.sin(2 * math.pi * t / period + self._phase)

    def _read_motion(self, t: float) -> Dict[str, Any]:
        """
        Output matches MIRAGE command_processing.c Motion/Orientation schema::

            {"device": "Motion", "format": "Orientation",
             "heading": 45.2, "pitch": -2.1, "roll": 3.5}

        Also includes quaternion fields for full OCP compliance.
        """
        heading = (self._base_heading + self._sine(t, period=120, amplitude=45)) % 360
        pitch   = self._base_pitch + self._sine(t, period=30,  amplitude=5)
        roll    = self._base_roll  + self._sine(t, period=20,  amplitude=3)

        # Euler → quaternion (approximate, small-angle is fine for simulation)
        h_r = math.radians(heading / 2)
        p_r = math.radians(pitch   / 2)
        r_r = math.radians(roll    / 2)
        return {
            "device": "Motion",
            "format": "Orientation",
            "heading": round(heading, 2),
            "pitch":   round(pitch,   2),
            "roll":    round(roll,    2),
            # Quaternion (w, x, y, z) — OCP extended fields
            "w": round(math.cos(h_r) * math.cos(p_r) * math.cos(r_r)
                       + math.sin(h_r) * math.sin(p_r) * math.sin(r_r), 4),
            "x": round(math.cos(h_r) * math.cos(p_r) * math.sin(r_r)
                       - math.sin(h_r) * math.sin(p_r) * math.cos(r_r), 4),
            "y": round(math.cos(h_r) * math.sin(p_r) * math.cos(r_r)
                       + math.sin(h_r) * math.cos(p_r) * math.sin(r_r), 4),
            "z": round(math.sin(h_r) * math.cos(p_r) * math.cos(r_r)
                       - math.cos(h_r) * math.sin(p_r) * math.sin(r_r), 4),
        }

    def _read_gps(self, t: float) -> Dict[str, Any]:
        """
        Output matches MIRAGE command_processing.c GPS schema::

            {"device": "GPS", "time": "12:30:00", "date": "2026-03-07",
             "fix": 1, "latitude": 37.77, "latitudeDegrees": 37.77, "lat": "N",
             "longitude": -122.42, "longitudeDegrees": -122.42, "lon": "W",
             "speed": 0.0, "angle": 0.0, "altitude": 50.0, "satellites": 8}
        """
        from datetime import datetime, timezone
        now_dt = datetime.now(timezone.utc)
        lat = self._base_lat + self._sine(t, period=300, amplitude=0.001)
        lon = self._base_lon + self._sine(t, period=240, amplitude=0.001)
        return {
            "device":           "GPS",
            "time":             now_dt.strftime("%H:%M:%S"),
            "date":             now_dt.strftime("%Y-%m-%d"),
            "fix":              1,
            "quality":          1,
            "latitude":         round(lat, 6),
            "latitudeDegrees":  round(lat, 6),
            "lat":              "N" if lat >= 0 else "S",
            "longitude":        round(lon, 6),
            "longitudeDegrees": round(lon, 6),
            "lon":              "W" if lon < 0 else "E",
            "speed":            round(max(0, self._sine(t, period=90, amplitude=0.5)), 2),
            "angle":            round((self._base_heading + self._sine(t, period=120, amplitude=45)) % 360, 1),
            "altitude":         round(320 + self._sine(t, period=60, amplitude=2), 1),
            "satellites":       8,
        }

    def _read_environmental(self, t: float) -> Dict[str, Any]:
        """
        Output matches MIRAGE command_processing.c Enviro schema::

            {"device": "Enviro", "temp": 22.5, "humidity": 65.0,
             "air_quality": 85.0, "tvoc_ppb": 12.0, "eco2_ppm": 400.0,
             "co2_ppm": 415.0, "heat_index_c": 24.0, "dew_point": 14.5}
        """
        temp     = self._base_temperature + self._sine(t, period=120, amplitude=2)
        humidity = max(10, min(100, self._base_humidity + self._sine(t, period=90, amplitude=5)))
        # Approximate heat index (Steadman formula, simplified)
        hi = temp + 0.33 * (humidity / 100 * 6.105 * math.exp(17.27 * temp / (237.7 + temp))) - 4.0
        # Approximate dew point (Magnus formula)
        dp = (243.04 * (math.log(humidity / 100) + 17.625 * temp / (243.04 + temp))
              / (17.625 - math.log(humidity / 100) - 17.625 * temp / (243.04 + temp)))
        tvoc  = max(0, 10 + self._sine(t, period=45, amplitude=8))
        eco2  = max(400, 400 + self._sine(t, period=60, amplitude=50))
        co2   = eco2 + random.uniform(5, 20)
        aq    = max(0, min(100, 85 + self._sine(t, period=180, amplitude=10)))
        return {
            "device":      "Enviro",
            "temp":        round(temp, 1),
            "humidity":    round(humidity, 1),
            "air_quality": round(aq, 1),
            "tvoc_ppb":    round(tvoc, 1),
            "eco2_ppm":    round(eco2, 1),
            "co2_ppm":     round(co2, 1),
            "heat_index_c": round(hi, 1),
            "dew_point":   round(dp, 1),
        }

    def _read_temperature(self, t: float) -> Dict[str, Any]:
        return {
            "temperature": round(self._base_temperature + self._sine(t, period=120, amplitude=2), 1),
            "unit": "celsius",
        }

    def _read_humidity(self, t: float) -> Dict[str, Any]:
        return {
            "humidity": round(max(0, min(100,
                self._base_humidity + self._sine(t, period=90, amplitude=5))), 1),
            "unit": "percent",
        }

    def _read_pressure(self, t: float) -> Dict[str, Any]:
        return {
            "pressure": round(self._base_pressure + self._sine(t, period=180, amplitude=5), 2),
            "unit": "hPa",
        }

    def _read_generic(self, t: float) -> Dict[str, Any]:
        return {
            "value":  round(50 + self._sine(t, period=60, amplitude=25), 2),
            "status": "ok",
        }


class MockSensorArray(SensorArrayInterface):
    """
    A collection of MockSensor instances for multi-sensor simulations.

    Implements :class:`~simulation.hal.device.SensorArrayInterface`.

    Example::

        sensors = MockSensorArray()
        sensors.add_sensor("imu",   "motion")
        sensors.add_sensor("gps",   "gps")
        sensors.add_sensor("enviro","environmental")
        readings = sensors.read_all()
    """

    def __init__(self):
        self.sensors: Dict[str, MockSensor] = {}

    def add_sensor(self, name: str, sensor_type: str = "generic") -> MockSensor:
        sensor = MockSensor(name=name, sensor_type=sensor_type)
        self.sensors[name] = sensor
        return sensor

    def remove_sensor(self, name: str):
        self.sensors.pop(name, None)

    def read_all(self) -> Dict[str, Dict[str, Any]]:
        return {name: sensor.read() for name, sensor in self.sensors.items()}

    def read_sensor(self, name: str) -> Dict[str, Any]:
        if name not in self.sensors:
            raise KeyError(f"Sensor '{name}' not found")
        return self.sensors[name].read()

    def get_sensor(self, name: str) -> Optional[MockSensor]:
        return self.sensors.get(name)

    def list_sensors(self):
        return list(self.sensors.keys())

    def __repr__(self):
        return f"MockSensorArray(sensors={self.list_sensors()!r})"
