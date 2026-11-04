"""
Layer 0: Simulated GPU telemetry for O.A.S.I.S. simulation.

MockGpuTelemetry implements :class:`~simulation.hal.device.GpuTelemetryInterface` with a simple thermal model:
temperature relaxes toward ambient plus a load-dependent rise with a time constant, and power, fan speed and
memory follow the load.  Faults can be injected at runtime to test how a consumer handles a failing sensor.
No external dependencies.

Real implementations of the same interface are in ``simulation.live.gpu``.

Example::

    from simulation.layer0.gpu import MockGpuTelemetry

    gpu = MockGpuTelemetry()
    gpu.set_load(85.0)                 # percent
    reading = gpu.read()               # {"temp_c": ..., "power_w": ..., "fan_rpm": ..., "util_pct": 85.0, ...}
    gpu.inject(freeze_temp=True)       # the temperature sensor sticks at its current value
    gpu.clear_faults()

Faults (keyword arguments to inject()):

    freeze_temp=True     temperature stops changing (a stuck sensor)
    drop_temp=True       temperature reads as missing
    temp_offset_c=30.0   temperature reads 30 °C high
    drop_all=True        every value reads as missing (a dead source)
"""

import math
import time
from typing import Any, Callable, Dict, Optional

from simulation.hal.device import GpuTelemetryInterface

FAULTS = ("freeze_temp", "drop_temp", "temp_offset_c", "drop_all")


class MockGpuTelemetry(GpuTelemetryInterface):
    """Simulated GPU telemetry source.

    Parameters
    ----------
    name : str
        Device name to report.
    provider : str
        Source identifier to report; give a second instance a different one (e.g. ``"simulated-alt"``) to model an
        independent second sensor.
    ambient_c, rise_c, tau_s : float
        Idle temperature, temperature rise at 100% load, and thermal time constant in seconds.
    clock : callable, optional
        Monotonic time source in seconds; defaults to ``time.monotonic``.  Tests pass a fake clock.
    """

    def __init__(
        self,
        name: str = "Simulated GPU",
        provider: str = "simulated",
        ambient_c: float = 40.0,
        rise_c: float = 35.0,
        tau_s: float = 20.0,
        clock: Optional[Callable[[], float]] = None,
    ) -> None:
        self.name, self.provider, self.pci_ids = name, provider, None
        self.ambient_c, self.rise_c, self.tau_s = ambient_c, rise_c, tau_s
        self._clock = clock or time.monotonic
        self._load = 2.0
        self._temp = ambient_c
        self._last_t: Optional[float] = None
        self._frozen: Optional[float] = None
        self._faults: Dict[str, Any] = {}

    def set_load(self, util_pct: float) -> None:
        """Set the simulated utilization, 0-100.  Temperature follows with the thermal time constant."""
        self._load = max(0.0, min(100.0, float(util_pct)))

    def inject(self, **faults: Any) -> None:
        """Add or change faults (see module docstring).  Unknown names raise ValueError."""
        unknown = set(faults) - set(FAULTS)
        if unknown:
            raise ValueError(f"unknown fault(s): {', '.join(sorted(unknown))}")
        self._faults.update(faults)

    def clear_faults(self) -> None:
        self._faults.clear()
        self._frozen = None

    def capabilities(self) -> Dict[str, bool]:
        return {k: True for k in ("temp_c", "power_w", "fan_rpm", "util_pct", "mem_used_mb")}

    def read(self) -> Dict[str, Any]:
        now = self._clock()
        target = self.ambient_c + self.rise_c * self._load / 100.0
        if self._last_t is not None:
            self._temp = target + (self._temp - target) * math.exp(-(now - self._last_t) / self.tau_s)
        self._last_t = now
        f = self._faults
        if f.get("drop_all"):
            return {}
        if f.get("freeze_temp"):
            self._frozen = self._frozen if self._frozen is not None else round(self._temp)
            temp = self._frozen
        else:
            self._frozen = None
            temp = round(self._temp, 1) + float(f.get("temp_offset_c", 0.0))
        load = self._load
        return {"temp_c": None if f.get("drop_temp") else temp, "power_w": 30.0 + 2.5 * load,
                "fan_rpm": 900.0 + 15.0 * load, "util_pct": load, "mem_used_mb": 400.0 + 200.0 * load}
