"""NVIDIA GPUs through NVML (nvml.dll on Windows, libnvidia-ml.so.1 on Linux), installed with the NVIDIA driver.

Reads temperature, board power, utilization and memory. NVML reports fan speed as a percentage of maximum, not
RPM, so fan_rpm stays empty. Uses only long-standing NVML entry points.

NOT YET TESTED ON NVIDIA HARDWARE: the development machine has no NVIDIA GPU. Before relying on it, run
`python -m metrics_helper --list` on an NVIDIA system and compare with nvidia-smi.
"""
import ctypes as C
import os
import sys

from simulation.live.gpu.base import LiveGpuSource

NVML_SUCCESS = 0
NVML_TEMPERATURE_GPU = 0


class nvmlPciInfo_t(C.Structure):              # nvmlDeviceGetPciInfo_v3
    _fields_ = [("busIdLegacy", C.c_char * 16), ("domain", C.c_uint), ("bus", C.c_uint), ("device", C.c_uint),
                ("pciDeviceId", C.c_uint),      # (device id << 16) | vendor id
                ("pciSubSystemId", C.c_uint), ("busId", C.c_char * 32)]


class nvmlUtilization_t(C.Structure):
    _fields_ = [("gpu", C.c_uint), ("memory", C.c_uint)]


class nvmlMemory_t(C.Structure):
    _fields_ = [("total", C.c_ulonglong), ("free", C.c_ulonglong), ("used", C.c_ulonglong)]


def _load():
    if sys.platform == "win32":
        candidates = ["nvml.dll", os.path.join(os.environ.get("ProgramFiles", r"C:\Program Files"),
                                                "NVIDIA Corporation", "NVSMI", "nvml.dll")]
    else:
        candidates = ["libnvidia-ml.so.1", "libnvidia-ml.so"]
    for n in candidates:
        try:
            return C.CDLL(n)
        except OSError:
            continue
    return None


class NvmlDevice(LiveGpuSource):
    provider = "nvml"

    def __init__(self, lib, handle, name):
        self.lib, self.handle, self.name = lib, handle, name

    def capabilities(self):
        return {"temp_c": True, "power_w": True, "fan_rpm": False, "util_pct": True, "mem_used_mb": True}

    def read(self):
        r, v = {}, C.c_uint()
        if self.lib.nvmlDeviceGetTemperature(self.handle, NVML_TEMPERATURE_GPU, C.byref(v)) == NVML_SUCCESS:
            r["temp_c"] = float(v.value)
        if self.lib.nvmlDeviceGetPowerUsage(self.handle, C.byref(v)) == NVML_SUCCESS:
            r["power_w"] = v.value / 1000.0                                   # milliwatts
        u = nvmlUtilization_t()
        if self.lib.nvmlDeviceGetUtilizationRates(self.handle, C.byref(u)) == NVML_SUCCESS:
            r["util_pct"] = float(u.gpu)
        m = nvmlMemory_t()
        if self.lib.nvmlDeviceGetMemoryInfo(self.handle, C.byref(m)) == NVML_SUCCESS:
            r["mem_used_mb"] = m.used / 2 ** 20
        return r


def devices():
    lib = _load()
    if lib is None or lib.nvmlInit_v2() != NVML_SUCCESS:
        return []
    n = C.c_uint()
    if lib.nvmlDeviceGetCount_v2(C.byref(n)) != NVML_SUCCESS:
        return []
    out = []
    for i in range(n.value):
        h = C.c_void_p()
        if lib.nvmlDeviceGetHandleByIndex_v2(i, C.byref(h)) != NVML_SUCCESS:
            continue
        buf = C.create_string_buffer(96)
        lib.nvmlDeviceGetName(h, buf, 96)
        pci = nvmlPciInfo_t()
        ids = None
        if lib.nvmlDeviceGetPciInfo_v3(h, C.byref(pci)) == NVML_SUCCESS:
            ids = (pci.pciDeviceId & 0xFFFF, pci.pciDeviceId >> 16)
        name = buf.value.decode("utf-8", "replace")
        out.append((name, ids, lambda hh=h, nn=name: NvmlDevice(lib, hh, nn)))
    return out
