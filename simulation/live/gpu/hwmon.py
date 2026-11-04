"""Linux GPUs through the kernel's hwmon sysfs interface: amdgpu, i915, xe, nouveau and other DRM drivers.

    /sys/class/drm/cardN/device/{vendor,device}                    PCI IDs (hex)
    /sys/class/drm/cardN/device/hwmon/hwmonM/name                  driver name (amdgpu, i915, xe, nouveau)
    .../temp*_input (millidegrees C), temp*_label                  temperatures; junction preferred, then edge
    .../power1_average or power1_input (microwatts)                board power, if reported
    .../energy1_input (microjoules)                                energy counter, if power is not reported
    .../fan1_input (RPM)                                           fan speed
    /sys/class/drm/cardN/device/gpu_busy_percent                   AMD utilization
    /sys/class/drm/cardN/device/mem_info_vram_used (bytes)         AMD VRAM in use

No library or privileges needed. `root` exists so tests can point it at a fake tree.
"""
import glob
import os
import time

from simulation.live.gpu.base import LiveGpuSource

ROOT = "/sys/class/drm"
TEMP_PREFERENCE = ("junction", "edge", "gpu", "pkg")


def _read(path, conv=float):
    try:
        with open(path, encoding="ascii") as f:
            return conv(f.read().strip())
    except (OSError, ValueError):
        return None


class HwmonDevice(LiveGpuSource):
    provider = "linux-hwmon"

    def __init__(self, dev_dir, hwmon_dir, name, clock=time.monotonic):
        self.dev_dir, self.hw, self.name, self.clock = dev_dir, hwmon_dir, name, clock
        self.temp_file = self._pick_temp()
        self._last_energy = None

    def _pick_temp(self):
        inputs = sorted(glob.glob(os.path.join(self.hw, "temp*_input")))
        labeled = {}
        for p in inputs:
            label = _read(p.replace("_input", "_label"), str)
            if label:
                labeled[label.lower()] = p
        for want in TEMP_PREFERENCE:
            if want in labeled:
                return labeled[want]
        return inputs[0] if inputs else None

    def capabilities(self):
        return {"temp_c": self.temp_file is not None,
                "power_w": any(os.path.exists(os.path.join(self.hw, f))
                               for f in ("power1_average", "power1_input", "energy1_input")),
                "fan_rpm": os.path.exists(os.path.join(self.hw, "fan1_input")),
                "util_pct": os.path.exists(os.path.join(self.dev_dir, "gpu_busy_percent")),
                "mem_used_mb": os.path.exists(os.path.join(self.dev_dir, "mem_info_vram_used"))}

    def read(self):
        r = {}
        if self.temp_file:
            t = _read(self.temp_file)
            r["temp_c"] = t / 1000.0 if t is not None else None
        for f in ("power1_average", "power1_input"):
            p = _read(os.path.join(self.hw, f))
            if p is not None:
                r["power_w"] = p / 1e6
                break
        else:
            e, now = _read(os.path.join(self.hw, "energy1_input")), self.clock()
            if e is not None:
                if self._last_energy and now > self._last_energy[1]:
                    r["power_w"] = (e - self._last_energy[0]) / 1e6 / (now - self._last_energy[1])
                self._last_energy = (e, now)
        fan = _read(os.path.join(self.hw, "fan1_input"))
        r["fan_rpm"] = fan if fan else None
        r["util_pct"] = _read(os.path.join(self.dev_dir, "gpu_busy_percent"))
        vram = _read(os.path.join(self.dev_dir, "mem_info_vram_used"))
        r["mem_used_mb"] = vram / 2 ** 20 if vram is not None else None
        return r


def devices(root=ROOT):
    out, seen = [], set()
    for card in sorted(glob.glob(os.path.join(root, "card[0-9]*"))):
        if "-" in os.path.basename(card):                   # connectors such as card0-DP-1
            continue
        dev = os.path.realpath(os.path.join(card, "device"))
        if dev in seen:
            continue
        seen.add(dev)
        vendor, device = _read(os.path.join(dev, "vendor"), lambda s: int(s, 16)), \
            _read(os.path.join(dev, "device"), lambda s: int(s, 16))
        for hw in sorted(glob.glob(os.path.join(dev, "hwmon", "hwmon*"))):
            driver = _read(os.path.join(hw, "name"), str) or "hwmon"
            name = f"{driver} {vendor or 0:04x}:{device or 0:04x} ({os.path.basename(card)})"
            ids = (vendor, device) if vendor is not None and device is not None else None
            out.append((name, ids, lambda d=dev, h=hw, n=name: HwmonDevice(d, h, n)))
            break
    return out
