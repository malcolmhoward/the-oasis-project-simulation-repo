"""Intel GPUs on Windows through the Intel Graphics Control Library (ControlLib.dll, installed with the driver;
the interface Intel's own Arc software uses): temperature and power (energy counter).

Layouts and values are from include/igcl_api.h and Samples/Telemetry_Samples/Sample_TelemetryAPP.cpp in
intel/drivers.gpu.control-library:

    ctl_power_energy_counter_t.energy     "monotonic energy counter in microjoules"
    ctl_power_energy_counter_t.timestamp  "microsecond timestamp", only for deltas within one structure
    CTL_TEMP_SENSORS_GLOBAL = 0, CTL_TEMP_SENSORS_GPU = 1; CTL_DEVICE_TYPE_GRAPHICS = 1
    CTL_IMPL_VERSION = (1 << 16) | 1; adapter properties Version = 2 with pDeviceID -> LUID, as in the sample

This path reaches the sensors through Intel's control interface, independently of D3DKMT.
"""
import ctypes as C
import sys

from simulation.live.gpu.base import LiveGpuSource

CTL_RESULT_SUCCESS = 0
CTL_IMPL_VERSION = (1 << 16) | 1
CTL_INIT_FLAG_USE_LEVEL_ZERO = 1
CTL_DEVICE_TYPE_GRAPHICS = 1
CTL_TEMP_SENSORS_GLOBAL, CTL_TEMP_SENSORS_GPU = 0, 1


class ctl_application_id_t(C.Structure):
    _fields_ = [("Data1", C.c_uint32), ("Data2", C.c_uint16), ("Data3", C.c_uint16), ("Data4", C.c_uint8 * 8)]


class ctl_init_args_t(C.Structure):
    _fields_ = [("Size", C.c_uint32), ("Version", C.c_uint8), ("AppVersion", C.c_uint32), ("flags", C.c_uint32),
                ("SupportedVersion", C.c_uint32), ("ApplicationUID", ctl_application_id_t)]


class ctl_firmware_version_t(C.Structure):
    _fields_ = [("major_version", C.c_uint64), ("minor_version", C.c_uint64), ("build_number", C.c_uint64)]


class ctl_adapter_bdf_t(C.Structure):
    _fields_ = [("bus", C.c_uint8), ("device", C.c_uint8), ("function", C.c_uint8)]


class ctl_device_adapter_properties_t(C.Structure):
    _fields_ = [("Size", C.c_uint32), ("Version", C.c_uint8), ("pDeviceID", C.c_void_p), ("device_id_size", C.c_uint32),
                ("device_type", C.c_uint32), ("supported_subfunction_flags", C.c_uint32),
                ("driver_version", C.c_uint64), ("firmware_version", ctl_firmware_version_t),
                ("pci_vendor_id", C.c_uint32), ("pci_device_id", C.c_uint32), ("rev_id", C.c_uint32),
                ("num_eus_per_sub_slice", C.c_uint32), ("num_sub_slices_per_slice", C.c_uint32),
                ("num_slices", C.c_uint32), ("name", C.c_char * 100), ("graphics_adapter_properties", C.c_uint32),
                ("Frequency", C.c_uint32), ("pci_subsys_id", C.c_uint16), ("pci_subsys_vendor_id", C.c_uint16),
                ("adapter_bdf", ctl_adapter_bdf_t), ("num_xe_cores", C.c_uint32), ("reserved", C.c_char * 108)]


class ctl_temp_properties_t(C.Structure):
    _fields_ = [("Size", C.c_uint32), ("Version", C.c_uint8), ("type", C.c_uint32), ("maxTemperature", C.c_double)]


class ctl_power_energy_counter_t(C.Structure):
    _fields_ = [("Size", C.c_uint32), ("Version", C.c_uint8), ("energy", C.c_uint64), ("timestamp", C.c_uint64)]


class LUID(C.Structure):
    _fields_ = [("LowPart", C.c_uint32), ("HighPart", C.c_int32)]


def _handles(fn, parent):
    n = C.c_uint32(0)
    if fn(parent, C.byref(n), None) != CTL_RESULT_SUCCESS or not n.value:
        return []
    arr = (C.c_void_p * n.value)()
    if fn(parent, C.byref(n), arr) != CTL_RESULT_SUCCESS:
        return []
    return [C.c_void_p(arr[i]) for i in range(n.value)]


class IgclDevice(LiveGpuSource):
    provider = "intel-igcl"

    def __init__(self, lib, handle, name):
        self.lib, self.handle, self.name = lib, handle, name
        self.temp = self._pick_temp()
        self.power = self._pick_power()
        self._last_energy = None

    def _pick_temp(self):
        best = {}
        for h in _handles(self.lib.ctlEnumTemperatureSensors, self.handle):
            p = ctl_temp_properties_t(Size=C.sizeof(ctl_temp_properties_t))
            t = C.c_double()
            if self.lib.ctlTemperatureGetProperties(h, C.byref(p)) == CTL_RESULT_SUCCESS \
                    and self.lib.ctlTemperatureGetState(h, C.byref(t)) == CTL_RESULT_SUCCESS and t.value > 0:
                best.setdefault(p.type, h)
        return best.get(CTL_TEMP_SENSORS_GPU) or best.get(CTL_TEMP_SENSORS_GLOBAL)

    def _pick_power(self):
        for h in _handles(self.lib.ctlEnumPowerDomains, self.handle):
            e = ctl_power_energy_counter_t(Size=C.sizeof(ctl_power_energy_counter_t))
            if self.lib.ctlPowerGetEnergyCounter(h, C.byref(e)) == CTL_RESULT_SUCCESS:
                return h
        return None

    def capabilities(self):
        return {"temp_c": self.temp is not None, "power_w": self.power is not None}

    def read(self):
        r = {}
        if self.temp is not None:
            t = C.c_double()
            if self.lib.ctlTemperatureGetState(self.temp, C.byref(t)) == CTL_RESULT_SUCCESS and t.value > 0:
                r["temp_c"] = t.value
        if self.power is not None:
            e = ctl_power_energy_counter_t(Size=C.sizeof(ctl_power_energy_counter_t))
            if self.lib.ctlPowerGetEnergyCounter(self.power, C.byref(e)) == CTL_RESULT_SUCCESS:
                if self._last_energy and e.timestamp > self._last_energy[1]:
                    r["power_w"] = (e.energy - self._last_energy[0]) / (e.timestamp - self._last_energy[1])
                self._last_energy = (e.energy, e.timestamp)
        return r


_api = None


def devices():
    """[(name, (pci vendor, pci device), open_fn)] for Intel graphics adapters; [] off Windows or without IGCL.
    Also records each adapter's LUID in device_luids for exact matching against D3DKMT."""
    global _api
    if sys.platform != "win32":
        return []
    try:
        lib = C.CDLL("ControlLib.dll")
    except OSError:
        return []
    for fn in ("ctlInit", "ctlEnumerateDevices", "ctlGetDeviceProperties", "ctlEnumTemperatureSensors",
               "ctlTemperatureGetProperties", "ctlTemperatureGetState", "ctlEnumPowerDomains",
               "ctlPowerGetEnergyCounter"):
        getattr(lib, fn).restype = C.c_uint32
    if _api is None:
        args = ctl_init_args_t(Size=C.sizeof(ctl_init_args_t), Version=0, AppVersion=CTL_IMPL_VERSION,
                               flags=CTL_INIT_FLAG_USE_LEVEL_ZERO)
        api = C.c_void_p()
        if lib.ctlInit(C.byref(args), C.byref(api)) != CTL_RESULT_SUCCESS:
            return []
        _api = api
    out = []
    for h in _handles(lib.ctlEnumerateDevices, _api):
        luid = LUID()
        p = ctl_device_adapter_properties_t(Size=C.sizeof(ctl_device_adapter_properties_t), Version=2,
                                            pDeviceID=C.cast(C.pointer(luid), C.c_void_p), device_id_size=C.sizeof(LUID))
        if lib.ctlGetDeviceProperties(h, C.byref(p)) != CTL_RESULT_SUCCESS or p.device_type != CTL_DEVICE_TYPE_GRAPHICS:
            continue
        name = p.name.decode("utf-8", "replace").strip()
        device_luids[name] = f"luid_0x{luid.HighPart & 0xFFFFFFFF:08x}_0x{luid.LowPart:08x}"
        out.append((name, (p.pci_vendor_id, p.pci_device_id), lambda hh=h, nn=name: IgclDevice(lib, hh, nn)))
    return out


device_luids = {}
