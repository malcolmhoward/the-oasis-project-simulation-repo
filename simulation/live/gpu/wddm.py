"""The Windows display-driver path: D3DKMT (temperature, power share, fan) plus PDH (utilization per engine type,
dedicated memory). Works for any WDDM 2.4+ GPU, whatever the vendor. Windows only."""
import sys

from simulation.live.gpu.base import LiveGpuSource


class WddmDevice(LiveGpuSource):
    provider = "windows-wddm"

    def __init__(self, name, luid, pci_ids):
        from simulation.live.gpu import pdh
        self.name, self.luid, self.pci_ids = name, luid, pci_ids
        self.query = pdh.Query([pdh.GPU_ENGINE, pdh.GPU_DEDICATED, pdh.CPU_TOTAL])
        self.cpu_pct = None                                  # system CPU busy %, a by-product of the PDH query

    def capabilities(self):
        from simulation.live.gpu import d3dkmt
        p = d3dkmt.fresh_perfdata(self.luid) or {}
        return {"temp_c": p.get("temp_c") is not None, "power_w": False, "fan_rpm": p.get("fan_rpm") is not None,
                "util_pct": True, "mem_used_mb": True}

    def read(self):
        from simulation.live.gpu import d3dkmt, pdh
        p = d3dkmt.fresh_perfdata(self.luid) or {}           # a new adapter handle every sample
        s = self.query.sample()
        engines = pdh.engine_utilization(s.get(pdh.GPU_ENGINE, []), self.luid)
        mem = pdh.adapter_value(s.get(pdh.GPU_DEDICATED, []), self.luid)
        cpu = s.get(pdh.CPU_TOTAL) or []
        self.cpu_pct = cpu[0][1] if cpu else None
        return {"temp_c": p.get("temp_c"), "fan_rpm": p.get("fan_rpm"),
                "util_pct": max(engines.values()) if engines else None,
                "mem_used_mb": mem / 2 ** 20 if mem is not None else None,
                "extra": {"util_3d": engines.get("3D"), "util_compute": engines.get("Compute"),
                          "power_pct": p.get("power_pct")}}

    def close(self):
        self.query.close()


def devices():
    """[(name, pci ids, open_fn)] for every WDDM adapter; [] off Windows. Adapter handles are closed here: each
    reading opens a fresh one, so a stuck handle cannot freeze values."""
    if sys.platform != "win32":
        return []
    from simulation.live.gpu import d3dkmt
    out = []
    adapters = d3dkmt.enum_adapters()
    try:
        for a in adapters:
            ids = a.pci_ids()
            out.append((a.name, ids, lambda n=a.name, l=a.luid, i=ids: WddmDevice(n, l, i)))
    finally:
        for a in adapters:
            a.close()
    return out
