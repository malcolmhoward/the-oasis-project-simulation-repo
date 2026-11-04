# GPU Telemetry Messages (OCP v1.4)

Spec version 1.0. Published by `python -m simulation.live.gpu.publish` (real or simulated GPU). Built by
`simulation/live/gpu/messages.py`.

These messages let any O.A.S.I.S. component read GPU telemetry over MQTT without importing this library, in any
language: subscribe and parse JSON. They follow the OASIS Communications Protocol v1.4 (D.A.W.N.
`docs/OASIS_COMMUNICATIONS_PROTOCOL.md`): `device` and `msg_type` on every message, Unix-millisecond `timestamp`,
receivers ignore unknown fields.

## Topics

`<device>` is the publisher's OCP device name, `gpu` by default. Give each publisher its own name (for example
`gpu-lab-2`) when several share a broker.

| Topic | Message | QoS | Retained | When |
|---|---|---|---|---|
| `<device>/telemetry` | `GpuTelemetry` | 0 | no | every `--interval` seconds (default 2) |
| `<device>/status` | OCP component status | 1 | yes | online on connect, heartbeat every 30 s, offline on exit; Last Will and Testament (offline, timestamp 0) on a crash |
| `<device>/events` | `source_swapped` event | 1 | no | when the source behind a metric changes |

As OCP v1.4 specifies for status, treat the publisher as offline if no status arrives for 90 seconds.

## `GpuTelemetry`

```json
{
  "device": "gpu",
  "msg_type": "telemetry",
  "type": "GpuTelemetry",
  "timestamp": 1800000000000,
  "spec_version": "1.0",
  "gpu": {"index": 0, "name": "Example GPU", "pci_id": "1234:5678"},
  "is_simulated": false,
  "temp_c": 61.0,
  "temp_alt_c": 60.5,
  "power_w": 182.4,
  "fan_rpm": 1650,
  "util_pct": 87.2,
  "mem_used_mb": 20480,
  "sources": {"temp_c": "windows-wddm", "temp_alt_c": "intel-igcl", "power_w": "intel-igcl",
              "fan_rpm": "level-zero-sysman", "util_pct": "windows-wddm", "mem_used_mb": "windows-wddm"}
}
```

| Field | Type | Meaning |
|---|---|---|
| `type` | string | Always `"GpuTelemetry"` |
| `spec_version` | string | This document's version |
| `gpu.index` | integer | Which GPU of this publisher (0 for the first) |
| `gpu.name` | string, optional | Device name as the primary source reports it |
| `gpu.pci_id` | string, optional | PCI vendor and device ID, `vvvv:dddd` in hex: the stable way to identify the model |
| `is_simulated` | boolean | True if any value comes from a simulated source. Never mix these with real readings unknowingly. |
| `temp_c` | number, optional | GPU temperature, °C, from the highest-ranked working source |
| `temp_alt_c` | number, optional | A second temperature from a **different** source, for cross-checking. Absent when no independent second source exists. |
| `power_w` | number, optional | Board power, watts |
| `fan_rpm` | number, optional | Fan speed, revolutions per minute |
| `util_pct` | number, optional | Utilization of the busiest engine, 0–100 |
| `mem_used_mb` | number, optional | Dedicated GPU memory in use, MiB |
| `sources` | object | For each value present, the source that produced it |

**A value the GPU does not report is absent, never zero or substituted.** Consumers must handle every value being
absent.

**Cross-checking.** `temp_c` and `temp_alt_c` reach the sensor through different interfaces. If `temp_c` stays fixed
while `temp_alt_c` moves several degrees, `temp_c` is probably stale. Use the hotter of the two for any limit.

## `source_swapped` event

```json
{
  "device": "gpu",
  "msg_type": "event",
  "event": "source_swapped",
  "timestamp": 1800000000000,
  "gpu": {"index": 0, "name": "Example GPU", "pci_id": "1234:5678"},
  "metric": "temp_c",
  "from": "windows-wddm",
  "to": "intel-igcl",
  "reason": "no value from windows-wddm for 3 ticks",
  "is_simulated": false
}
```

A metric's source changes only when the active one stops reporting (after 3 samples by default). It does not change
back on its own.

## Status

Exactly the OCP v1.4 component status format, with `capabilities` listing the metrics this GPU reports:

```json
{"device": "gpu", "msg_type": "status", "status": "online", "timestamp": 1800000000000, "version": "1.0.0",
 "capabilities": ["fan_rpm", "mem_used_mb", "power_w", "temp_alt_c", "temp_c", "util_pct"]}
```

## Sources

| `sources` value | Interface | GPUs | Platforms |
|---|---|---|---|
| `windows-wddm` | D3DKMT + performance counters (what Task Manager shows) | any WDDM 2.4+ GPU | Windows |
| `intel-igcl` | Intel Graphics Control Library | Intel | Windows |
| `level-zero-sysman` | Level Zero Sysman | Intel | Windows, Linux |
| `nvml` | NVIDIA Management Library | NVIDIA | Windows, Linux |
| `linux-hwmon` | Kernel hwmon sysfs | AMD, Intel, others | Linux |
| `simulated`, `simulated-alt` | `simulation.layer0.gpu.MockGpuTelemetry` | none | any |

What each source reports depends on the driver. `nvml` and `linux-hwmon` are not yet tested on hardware.

## Relationship to S.T.A.T.

S.T.A.T. publishes `SystemMetrics` (CPU, memory, system temperature) on `stat/telemetry`. `GpuTelemetry` is a
separate type on its own topics, so the two never collide, and a consumer such as M.I.R.A.G.E. that does not know
`GpuTelemetry` ignores it.

## Running a publisher

```bash
pip install "oasis-simulation[layer1]"          # paho-mqtt
python -m simulation.live.gpu.publish --broker localhost --adapter "<part of the GPU name>"
python -m simulation.live.gpu.publish --broker localhost --pci <vvvv:dddd> --device gpu-lab-2
python -m simulation.live.gpu.publish --broker localhost --simulate --load 80
```

Broker credentials, if needed, come from `MQTT_USERNAME` and `MQTT_PASSWORD`. Telemetry readings can reveal what
hardware runs where and when it is busy; use a broker you trust.

**Safety-critical consumers** (thermal limits, load shedding) should read the hardware directly with
`simulation.live.gpu`, not over MQTT: delivery is best-effort, and a stalled broker looks like a frozen sensor. If a
safety consumer does use these messages, it must treat a gap in telemetry as "temperature unavailable".
