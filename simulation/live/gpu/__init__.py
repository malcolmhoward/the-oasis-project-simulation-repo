"""
simulation.live.gpu — real GPU telemetry sources implementing GpuTelemetryInterface.

These sit beside the simulated source (simulation.layer0.gpu.MockGpuTelemetry) so a Provider or FailoverProvider
can hold whichever the available hardware supports.  Standard library only (ctypes); each source loads its
vendor library at runtime and reports no devices if it is absent.

| Module      | provider          | GPUs                     | Platforms      | Reads                                    |
|-------------|-------------------|--------------------------|----------------|------------------------------------------|
| wddm        | windows-wddm      | any WDDM 2.4+ GPU        | Windows        | temperature, utilization, memory         |
| igcl        | intel-igcl        | Intel                    | Windows        | temperature, power                       |
| levelzero   | level-zero-sysman | Intel                    | Windows, Linux | temperature, power, fan (driver-dependent)|
| nvml        | nvml              | NVIDIA                   | Windows, Linux | temperature, power, utilization, memory  |
| hwmon       | linux-hwmon       | AMD, Intel, nouveau, ... | Linux          | temperature, power, fan; AMD util, VRAM  |

Verified on an Intel discrete GPU under Windows 11: wddm (temperature, utilization, memory), igcl
(temperature and power), levelzero (fan only on that driver).  nvml and hwmon are written from the documented
interfaces and not yet tested on hardware.

Example::

    from simulation.live.gpu import discover, resolve_pci
    from simulation.live.gpu.hub import GpuTelemetryHub
    sources, report = discover(pci=resolve_pci("RTX 4090"))   # every source that can see this card
    sample = GpuTelemetryHub(sources).sample()           # failover per metric, plus a cross-check temperature

To share telemetry with other components over MQTT without them importing this package, run
``python -m simulation.live.gpu.publish`` (OCP v1.4 GpuTelemetry messages; spec in docs/GPU_TELEMETRY.md).
"""

from typing import Any, Dict, List, Optional, Tuple

from simulation.live.gpu.base import LiveGpuSource

__all__ = ["LiveGpuSource", "discover", "resolve_pci", "SOURCE_MODULES"]

SOURCE_MODULES = ("wddm", "igcl", "levelzero", "nvml", "hwmon")


def _modules(names):
    import importlib
    return [importlib.import_module(f"simulation.live.gpu.{n}") for n in names]


def resolve_pci(match: str, modules=None) -> Optional[Tuple[int, int]]:
    """PCI IDs of the first device, in any source, whose name contains ``match`` (case-insensitive).  Use it to turn
    a friendly name ("RTX 4090", "Arc") into the IDs that discover() matches on."""
    for mod in (modules if modules is not None else _modules(SOURCE_MODULES)):
        try:
            devs = mod.devices()
        except (OSError, AttributeError, ValueError):
            continue
        for n, ids, _ in devs:
            if ids and match and match.lower() in (n or "").lower():
                return tuple(ids)
    return None


def discover(match: str = "", pci: Optional[Tuple[int, int]] = None, modules=None) -> Tuple[List[Any], Dict]:
    """Open each source's device for one GPU.  Returns (sources, report).

    Matching is by PCI (vendor, device) IDs when given, since names differ between sources (Level Zero on Windows
    calls some Intel cards just "Intel(R) Graphics [0x<device id>]"); otherwise by case-insensitive name substring.  Two
    identical cards cannot be told apart this way: the first match is used, and the report lists all matches.
    ``modules`` overrides the source modules (tests pass fakes).
    """
    if modules is None:
        modules = _modules(SOURCE_MODULES)
    found, report = [], {}
    for mod in modules:
        label = mod.__name__.rsplit(".", 1)[-1]
        try:
            devs = mod.devices()
        except (OSError, AttributeError, ValueError) as e:
            report[label] = f"error: {type(e).__name__}: {e}"
            continue
        if pci is not None:
            hits = [(n, ids, op) for n, ids, op in devs if ids == tuple(pci)]
        else:
            hits = [(n, ids, op) for n, ids, op in devs if match and match.lower() in (n or "").lower()]
        report[label] = {"devices": [f"{n} [{ids[0]:04x}:{ids[1]:04x}]" if ids else n for n, ids, _ in devs],
                         "matched": [n for n, _, _ in hits], "matched_by": "pci" if pci is not None else "name"}
        for n, ids, opener in hits[:1]:
            try:
                dev = opener()
                dev.pci_ids = dev.pci_ids or ids
                found.append(dev)
            except (OSError, AttributeError, ValueError) as e:
                report[label]["open_error"] = f"{type(e).__name__}: {e}"
    return found, report
