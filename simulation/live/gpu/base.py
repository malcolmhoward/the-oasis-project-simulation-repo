"""Base class for real GPU telemetry sources."""
from typing import Any, Dict

from simulation.hal.device import GpuTelemetryInterface


class LiveGpuSource(GpuTelemetryInterface):
    """A real (not simulated) GPU telemetry source.

    ``_is_simulated = False`` is set explicitly, so SimulationStatus classifies these as real regardless of module
    path or class name (see simulation.hal.status.is_mock_implementation).
    """

    _is_simulated = False
    provider = "?"

    def capabilities(self) -> Dict[str, bool]:
        return {}

    def read(self) -> Dict[str, Any]:
        return {}
