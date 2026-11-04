"""
GpuTelemetryHub — one GPU's telemetry from several sources, with failover per metric and an independent
cross-check temperature.

Each metric is a :class:`~simulation.hal.failover.FailoverProvider` over the sources that can report it, ranked by
``preference``.  ``temp_alt_c`` is a second temperature provider paired exclusively with ``temp_c``, so it never uses
the same source: a consumer can compare the two to catch a frozen sensor.  Swaps are reported to ``on_swap`` and
tracked in a :class:`~simulation.hal.status.SimulationStatus`.

Works with any GpuTelemetryInterface sources: real ones from ``simulation.live.gpu.discover()``, the simulated
``simulation.layer0.gpu.MockGpuTelemetry``, or a mix.

Example::

    from simulation.live.gpu import discover, resolve_pci
    from simulation.live.gpu.hub import GpuTelemetryHub

    sources, _ = discover(pci=resolve_pci("RTX 4090"))
    hub = GpuTelemetryHub(sources)
    sample = hub.sample()
    sample.values["temp_c"], sample.sources["temp_c"]      # e.g. 61.0, "windows-wddm"
"""

from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Mapping, Optional

from simulation.hal.device import GPU_TELEMETRY_KEYS
from simulation.hal.failover import FailoverProvider
from simulation.hal.status import SimulationStatus

#: Default rank order of sources per metric: OS interfaces first (what Task Manager and similar tools show), then
#: vendor libraries, then simulations.  Consumers may pass their own.
DEFAULT_PREFERENCE: Dict[str, List[str]] = {
    "temp_c": ["windows-wddm", "intel-igcl", "level-zero-sysman", "nvml", "linux-hwmon", "simulated", "simulated-alt"],
    "power_w": ["intel-igcl", "level-zero-sysman", "nvml", "linux-hwmon", "simulated"],
    "fan_rpm": ["windows-wddm", "level-zero-sysman", "linux-hwmon", "simulated"],
    "util_pct": ["windows-wddm", "nvml", "linux-hwmon", "simulated"],
    "mem_used_mb": ["windows-wddm", "nvml", "linux-hwmon", "simulated"],
}

#: Metrics a hub reports: the five interface keys plus the cross-check temperature.
HUB_METRICS = GPU_TELEMETRY_KEYS + ("temp_alt_c",)


@dataclass
class HubSample:
    """One tick: the value of each metric (None when unavailable), the source that produced it, and the raw
    readings of every source (for source-specific extras)."""
    values: Dict[str, Optional[float]]
    sources: Dict[str, Optional[str]]
    readings: Dict[Any, Dict[str, Any]] = field(default_factory=dict)

    def extra(self, metric: str = "util_pct") -> Dict[str, Any]:
        """The ``extra`` map from whichever source is active for ``metric``."""
        for src, reading in self.readings.items():
            if FailoverProvider.label(src) == self.sources.get(metric):
                return reading.get("extra") or {}
        return {}


def label(src: Any) -> Optional[str]:
    return FailoverProvider.label(src) if src is not None else None


class GpuTelemetryHub:
    """Failover providers for one GPU's metrics.

    Parameters
    ----------
    sources : list
        GpuTelemetryInterface implementations for the same GPU.
    preference : dict, optional
        Rank order of ``provider`` names per metric; defaults to DEFAULT_PREFERENCE.
    on_swap : callable, optional
        ``on_swap(metric, old_source, new_source, reason)`` on every automatic swap.
    status : SimulationStatus, optional
        Tracker to register and update; one is created if not given.
    fail_after : int
        Consecutive ticks without a value before failing over.
    """

    def __init__(self, sources: List[Any], preference: Optional[Mapping[str, List[str]]] = None,
                 on_swap: Optional[Callable[[str, Any, Any, Optional[str]], None]] = None,
                 status: Optional[SimulationStatus] = None, fail_after: int = 3) -> None:
        self.sources = list(sources)
        self.preference = dict(preference or DEFAULT_PREFERENCE)
        self.status = status or SimulationStatus("gpu")
        self._on_swap = on_swap
        caps = {s: s.capabilities() for s in self.sources}

        def ranked(metric):
            order = self.preference.get(metric, [])
            cands = [s for s in self.sources if caps[s].get(metric)]
            return sorted(cands, key=lambda s: order.index(s.provider) if s.provider in order else len(order))

        self.providers: Dict[str, FailoverProvider] = {}
        for m in GPU_TELEMETRY_KEYS:
            self.providers[m] = FailoverProvider(ranked(m), on_swap=self._swap_handler(m), fail_after=fail_after,
                                                 name=f"gpu.{m}")
        self.providers["temp_alt_c"] = FailoverProvider(ranked("temp_c"), on_swap=self._swap_handler("temp_alt_c"),
                                                        fail_after=fail_after, exclude=self.providers["temp_c"],
                                                        name="gpu.temp_alt_c")
        for m, p in self.providers.items():
            if p.implementation is not None:
                self.status.register(f"gpu.{m}", p.implementation)

    def _swap_handler(self, metric: str):
        track = self.status.create_swap_handler(f"gpu.{metric}")

        def handler(old, new):
            track(old, new)
            if self._on_swap is not None:
                self._on_swap(metric, old, new, self.providers[metric].last_swap_reason)
        return handler

    def active(self) -> Dict[str, Optional[str]]:
        """The source currently active for each metric (None if no source can report it)."""
        return {m: label(p.implementation) for m, p in self.providers.items()}

    def is_simulated(self) -> bool:
        return self.status.is_any_simulated()

    def sample(self, read_error: Optional[Callable[[Any, Exception], None]] = None) -> HubSample:
        """Read every source once and resolve each metric.  A source whose read raises counts as reporting nothing
        this tick; ``read_error(source, exception)`` is told about it."""
        readings: Dict[Any, Dict[str, Any]] = {}
        for s in self.sources:
            try:
                readings[s] = s.read() or {}
            except (OSError, ValueError, ArithmeticError) as e:
                readings[s] = {}
                if read_error is not None:
                    read_error(s, e)
        values, used = {}, {}
        for m, p in self.providers.items():
            key = "temp_c" if m == "temp_alt_c" else m
            values[m] = p.observe({s: r.get(key) for s, r in readings.items()})
            used[m] = label(p.implementation)
        return HubSample(values, used, readings)

    def close(self) -> None:
        for s in self.sources:
            s.close()
