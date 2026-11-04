"""Intel GPUs through Level Zero Sysman (zes*): temperature, power (energy counter) and fan speed.

Windows (ze_loader.dll, installed with the Intel driver) and Linux (libze_loader.so.1). Layouts and values are
from the official headers, include/ze_api.h and include/zes_api.h at oneapi-src/level-zero v1.32.0:

    zes_power_energy_counter_t.energy     "monotonic energy counter in microjoules"
    zes_power_energy_counter_t.timestamp  "microsecond timestamp", only for deltas within one structure
    ZES_TEMP_SENSORS_GLOBAL = 0, ZES_TEMP_SENSORS_GPU = 1, ZES_FAN_SPEED_UNITS_RPM = 0
    ZES_STRUCTURE_TYPE_DEVICE_PROPERTIES = 0x1, ZE_STRUCTURE_TYPE_DEVICE_PROPERTIES = 0x3,
    ZES_STRUCTURE_TYPE_TEMP_PROPERTIES = 0x14, ZES_STRUCTURE_TYPE_POWER_PROPERTIES = 0xd

This reaches the sensors through Intel's own driver interface, independently of the Windows D3DKMT path, which is
what makes it a cross-check on the primary temperature.
"""
import ctypes as C
import sys

from simulation.live.gpu.base import LiveGpuSource

ZE_RESULT_SUCCESS = 0
ZES_STRUCTURE_TYPE_DEVICE_PROPERTIES = 0x1
ZE_STRUCTURE_TYPE_DEVICE_PROPERTIES = 0x3
ZES_STRUCTURE_TYPE_POWER_PROPERTIES = 0xD
ZES_STRUCTURE_TYPE_TEMP_PROPERTIES = 0x14
ZES_TEMP_SENSORS_GLOBAL, ZES_TEMP_SENSORS_GPU = 0, 1
ZES_FAN_SPEED_UNITS_RPM = 0
ze_bool_t = C.c_uint8


class ze_device_uuid_t(C.Structure):
    _fields_ = [("id", C.c_uint8 * 16)]


class ze_device_properties_t(C.Structure):
    _fields_ = [("stype", C.c_uint32), ("pNext", C.c_void_p), ("type", C.c_uint32), ("vendorId", C.c_uint32),
                ("deviceId", C.c_uint32), ("flags", C.c_uint32), ("subdeviceId", C.c_uint32),
                ("coreClockRate", C.c_uint32), ("maxMemAllocSize", C.c_uint64), ("maxHardwareContexts", C.c_uint32),
                ("maxCommandQueuePriority", C.c_uint32), ("numThreadsPerEU", C.c_uint32),
                ("physicalEUSimdWidth", C.c_uint32), ("numEUsPerSubslice", C.c_uint32),
                ("numSubslicesPerSlice", C.c_uint32), ("numSlices", C.c_uint32), ("timerResolution", C.c_uint64),
                ("timestampValidBits", C.c_uint32), ("kernelTimestampValidBits", C.c_uint32),
                ("uuid", ze_device_uuid_t), ("name", C.c_char * 256)]


class zes_device_properties_t(C.Structure):
    _fields_ = [("stype", C.c_uint32), ("pNext", C.c_void_p), ("core", ze_device_properties_t),
                ("numSubdevices", C.c_uint32), ("serialNumber", C.c_char * 64), ("boardNumber", C.c_char * 64),
                ("brandName", C.c_char * 64), ("modelName", C.c_char * 64), ("vendorName", C.c_char * 64),
                ("driverVersion", C.c_char * 64)]


class zes_temp_properties_t(C.Structure):
    _fields_ = [("stype", C.c_uint32), ("pNext", C.c_void_p), ("type", C.c_uint32), ("onSubdevice", ze_bool_t),
                ("subdeviceId", C.c_uint32), ("maxTemperature", C.c_double), ("isCriticalTempSupported", ze_bool_t),
                ("isThreshold1Supported", ze_bool_t), ("isThreshold2Supported", ze_bool_t)]


class zes_power_properties_t(C.Structure):
    _fields_ = [("stype", C.c_uint32), ("pNext", C.c_void_p), ("onSubdevice", ze_bool_t), ("subdeviceId", C.c_uint32),
                ("canControl", ze_bool_t), ("isEnergyThresholdSupported", ze_bool_t), ("defaultLimit", C.c_int32),
                ("minLimit", C.c_int32), ("maxLimit", C.c_int32)]


class zes_power_energy_counter_t(C.Structure):
    _fields_ = [("energy", C.c_uint64), ("timestamp", C.c_uint64)]


def _load():
    names = ["ze_loader.dll"] if sys.platform == "win32" else ["libze_loader.so.1", "libze_loader.so"]
    for n in names:
        try:
            return C.CDLL(n)
        except OSError:
            continue
    return None


def _handles(fn, *args):
    """The zes enumerate pattern: call with count 0, then with an array of that size."""
    n = C.c_uint32(0)
    if fn(*args, C.byref(n), None) != ZE_RESULT_SUCCESS or not n.value:
        return []
    arr = (C.c_void_p * n.value)()
    if fn(*args, C.byref(n), arr) != ZE_RESULT_SUCCESS:
        return []
    return [arr[i] for i in range(n.value)]


class LevelZeroDevice(LiveGpuSource):
    provider = "level-zero-sysman"

    def __init__(self, lib, handle, name):
        # A 64-bit handle must travel as a pointer: a bare Python int is converted to a 32-bit C int and overflows.
        self.lib, self.handle, self.name = lib, C.c_void_p(handle), name
        self.temp = self._pick_temp()
        self.power = self._pick_power()
        self.fans = _handles(lib.zesDeviceEnumFans, self.handle)
        self._last_energy = None

    def _pick_temp(self):
        best = {}
        for h in _handles(self.lib.zesDeviceEnumTemperatureSensors, self.handle):
            p = zes_temp_properties_t(stype=ZES_STRUCTURE_TYPE_TEMP_PROPERTIES)
            if self.lib.zesTemperatureGetProperties(C.c_void_p(h), C.byref(p)) == ZE_RESULT_SUCCESS \
                    and not p.onSubdevice:
                best.setdefault(p.type, h)
        return best.get(ZES_TEMP_SENSORS_GPU) or best.get(ZES_TEMP_SENSORS_GLOBAL)

    def _pick_power(self):
        """A card-level power domain whose energy counter actually works. Listing a domain is not enough: on at least
        one Windows Intel driver both domains list, but the counter returns UNSUPPORTED_FEATURE."""
        for h in _handles(self.lib.zesDeviceEnumPowerDomains, self.handle):
            p = zes_power_properties_t(stype=ZES_STRUCTURE_TYPE_POWER_PROPERTIES)
            e = zes_power_energy_counter_t()
            if self.lib.zesPowerGetProperties(C.c_void_p(h), C.byref(p)) == ZE_RESULT_SUCCESS and not p.onSubdevice \
                    and self.lib.zesPowerGetEnergyCounter(C.c_void_p(h), C.byref(e)) == ZE_RESULT_SUCCESS:
                return h
        return None

    def capabilities(self):
        return {"temp_c": self.temp is not None, "power_w": self.power is not None, "fan_rpm": bool(self.fans)}

    def read(self):
        r = {}
        if self.temp is not None:
            t = C.c_double()
            if self.lib.zesTemperatureGetState(C.c_void_p(self.temp), C.byref(t)) == ZE_RESULT_SUCCESS and t.value > 0:
                r["temp_c"] = t.value
        if self.power is not None:
            e = zes_power_energy_counter_t()
            if self.lib.zesPowerGetEnergyCounter(C.c_void_p(self.power), C.byref(e)) == ZE_RESULT_SUCCESS:
                if self._last_energy and e.timestamp > self._last_energy[1]:
                    # microjoules per microsecond = watts
                    r["power_w"] = (e.energy - self._last_energy[0]) / (e.timestamp - self._last_energy[1])
                self._last_energy = (e.energy, e.timestamp)
        for h in self.fans:
            s = C.c_int32(-1)
            if self.lib.zesFanGetState(C.c_void_p(h), ZES_FAN_SPEED_UNITS_RPM, C.byref(s)) == ZE_RESULT_SUCCESS \
                    and s.value >= 0:
                r["fan_rpm"] = max(r.get("fan_rpm") or 0, s.value)
        return r


def devices():
    """[(name, (pci vendor, pci device), open_fn)] for every Level Zero Sysman device, or [] if absent.
    On Windows the name is generic ("Intel(R) Graphics [0x<device id>]"), so match by PCI IDs."""
    lib = _load()
    if lib is None:
        return []
    for fn in ("zesInit", "zesDriverGet", "zesDeviceGet", "zesDeviceGetProperties", "zesDeviceEnumTemperatureSensors",
               "zesTemperatureGetProperties", "zesTemperatureGetState", "zesDeviceEnumPowerDomains",
               "zesPowerGetProperties", "zesPowerGetEnergyCounter", "zesDeviceEnumFans", "zesFanGetState"):
        getattr(lib, fn).restype = C.c_uint32
    if lib.zesInit(0) != ZE_RESULT_SUCCESS:
        return []
    out = []
    for drv in _handles(lib.zesDriverGet):
        for dev in _handles(lib.zesDeviceGet, C.c_void_p(drv)):
            p = zes_device_properties_t(stype=ZES_STRUCTURE_TYPE_DEVICE_PROPERTIES)
            p.core.stype = ZE_STRUCTURE_TYPE_DEVICE_PROPERTIES
            if lib.zesDeviceGetProperties(C.c_void_p(dev), C.byref(p)) != ZE_RESULT_SUCCESS:
                continue
            name = (p.modelName or p.core.name).decode("utf-8", "replace").strip()
            out.append((name, (p.core.vendorId, p.core.deviceId),
                        lambda d=dev, n=name: LevelZeroDevice(lib, C.c_void_p(d).value, n)))
    return out
