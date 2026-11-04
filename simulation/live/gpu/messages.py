"""
OCP v1.4 messages for GPU telemetry, as pure functions (no MQTT needed to build or test them).

Spec: docs/GPU_TELEMETRY.md.  Conventions from the OASIS Communications Protocol v1.4 (D.A.W.N.
docs/OASIS_COMMUNICATIONS_PROTOCOL.md): telemetry on ``<device>/telemetry`` with ``msg_type`` and a ``type``
sub-type, presence on ``<device>/status``, unsolicited events on ``<device>/events``; timestamps are Unix
milliseconds; receivers ignore unknown fields; unavailable values are omitted, never zeroed.
"""

from typing import Any, Dict, Mapping, Optional, Sequence

TELEMETRY_TYPE = "GpuTelemetry"
SPEC_VERSION = "1.0"
VALUE_FIELDS = ("temp_c", "temp_alt_c", "power_w", "fan_rpm", "util_pct", "mem_used_mb")


def topics(device: str) -> Dict[str, str]:
    return {"telemetry": f"{device}/telemetry", "status": f"{device}/status", "events": f"{device}/events"}


def _round(v: Optional[float], n: int = 1) -> Optional[float]:
    return None if v is None else round(float(v), n)


def gpu_identity(name: Optional[str], pci_ids: Optional[Sequence[int]], index: int = 0) -> Dict[str, Any]:
    ident: Dict[str, Any] = {"index": index}
    if name:
        ident["name"] = name
    if pci_ids:
        ident["pci_id"] = f"{pci_ids[0]:04x}:{pci_ids[1]:04x}"
    return ident


def telemetry(device: str, gpu: Mapping[str, Any], values: Mapping[str, Optional[float]],
              sources: Mapping[str, Optional[str]], is_simulated: bool, ts_ms: int) -> Dict[str, Any]:
    """A GpuTelemetry message.  Each value is present only if available; ``sources`` names the source of each
    present value."""
    msg: Dict[str, Any] = {"device": device, "msg_type": "telemetry", "type": TELEMETRY_TYPE, "timestamp": ts_ms,
                           "spec_version": SPEC_VERSION, "gpu": dict(gpu), "is_simulated": bool(is_simulated)}
    present = {k: _round(values.get(k), 0 if k in ("fan_rpm", "mem_used_mb") else 1) for k in VALUE_FIELDS
               if values.get(k) is not None}
    msg.update(present)
    msg["sources"] = {k: sources[k] for k in present if sources.get(k)}
    return msg


def status(device: str, online: bool, ts_ms: int, version: Optional[str] = None,
           capabilities: Optional[Sequence[str]] = None) -> Dict[str, Any]:
    """An OCP component status message (presence): online, offline, or a heartbeat (online again)."""
    msg: Dict[str, Any] = {"device": device, "msg_type": "status", "status": "online" if online else "offline",
                           "timestamp": ts_ms}
    if version:
        msg["version"] = version
    if capabilities:
        msg["capabilities"] = list(capabilities)
    return msg


def last_will(device: str) -> Dict[str, Any]:
    """The Last Will and Testament payload: offline with timestamp 0, as OCP v1.4 specifies."""
    return status(device, online=False, ts_ms=0)


def source_swapped(device: str, gpu: Mapping[str, Any], metric: str, old: Optional[str], new: Optional[str],
                   reason: Optional[str], is_simulated: bool, ts_ms: int) -> Dict[str, Any]:
    """An OCP event: the source behind one metric changed."""
    msg: Dict[str, Any] = {"device": device, "msg_type": "event", "event": "source_swapped", "timestamp": ts_ms,
                           "gpu": dict(gpu), "metric": metric, "from": old, "to": new,
                           "is_simulated": bool(is_simulated)}
    if reason:
        msg["reason"] = reason
    return msg
