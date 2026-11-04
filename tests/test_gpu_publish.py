"""GpuTelemetryHub, the OCP GpuTelemetry messages and the MQTT publisher (fake client and clock; no broker).

    pytest tests/test_gpu_publish.py -q
"""
import json
import types

from simulation.layer0.gpu import MockGpuTelemetry
from simulation.live.gpu import messages, resolve_pci
from simulation.live.gpu.base import LiveGpuSource
from simulation.live.gpu.hub import DEFAULT_PREFERENCE, GpuTelemetryHub
from simulation.live.gpu.publish import Publisher, connect


class Fake(LiveGpuSource):
    def __init__(self, provider, caps, values=None):
        self.provider, self.name, self.caps, self.values = provider, provider, caps, dict(values or {})

    def capabilities(self):
        return self.caps

    def read(self):
        if self.values.get("raise"):
            raise OSError("driver gone")
        return dict(self.values)


def trio():
    wd = Fake("windows-wddm", {"temp_c": True, "util_pct": True, "mem_used_mb": True},
              {"temp_c": 60.0, "util_pct": 80.0, "mem_used_mb": 2048.0, "extra": {"util_3d": 80.0}})
    ig = Fake("intel-igcl", {"temp_c": True, "power_w": True}, {"temp_c": 59.5, "power_w": 150.0})
    l0 = Fake("level-zero-sysman", {"fan_rpm": True}, {"fan_rpm": 1500.0})
    return wd, ig, l0


# ---- hub ----

def test_hub_ranks_pairs_and_samples():
    wd, ig, l0 = trio()
    hub = GpuTelemetryHub([l0, ig, wd])
    assert hub.active() == {"temp_c": "windows-wddm", "power_w": "intel-igcl", "fan_rpm": "level-zero-sysman",
                            "util_pct": "windows-wddm", "mem_used_mb": "windows-wddm", "temp_alt_c": "intel-igcl"}
    s = hub.sample()
    assert s.values == {"temp_c": 60.0, "power_w": 150.0, "fan_rpm": 1500.0, "util_pct": 80.0, "mem_used_mb": 2048.0,
                        "temp_alt_c": 59.5}
    assert s.extra()["util_3d"] == 80.0 and not hub.is_simulated()
    assert set(DEFAULT_PREFERENCE) == {"temp_c", "power_w", "fan_rpm", "util_pct", "mem_used_mb"}


def test_hub_fails_over_reports_swaps_and_survives_read_errors():
    wd, ig, l0 = trio()
    swaps, errors = [], []
    hub = GpuTelemetryHub([wd, ig, l0], on_swap=lambda *x: swaps.append(x))
    wd.values["raise"] = True
    for _ in range(3):
        hub.sample(read_error=lambda s, e: errors.append(s.provider))
    assert errors == ["windows-wddm"] * 3
    metric, old, new, reason = swaps[0]
    assert (metric, old.provider, new.provider) == ("temp_c", "windows-wddm", "intel-igcl") and "3 ticks" in reason
    assert hub.active()["temp_c"] == "intel-igcl"


def test_hub_with_mocks_is_simulated():
    hub = GpuTelemetryHub([MockGpuTelemetry(), MockGpuTelemetry(provider="simulated-alt")])
    assert hub.is_simulated() and hub.active()["temp_alt_c"] == "simulated-alt"


# ---- messages ----

def test_telemetry_omits_unavailable_values_and_names_sources():
    gpu = messages.gpu_identity("Example GPU", (0x1234, 0x5678))
    m = messages.telemetry("gpu", gpu, {"temp_c": 61.04, "fan_rpm": 1650.4, "power_w": None},
                           {"temp_c": "windows-wddm", "fan_rpm": "level-zero-sysman", "power_w": "intel-igcl"}, False, 7)
    assert m["msg_type"] == "telemetry" and m["type"] == "GpuTelemetry" and m["timestamp"] == 7
    assert m["gpu"] == {"index": 0, "name": "Example GPU", "pci_id": "1234:5678"}
    assert m["temp_c"] == 61.0 and m["fan_rpm"] == 1650 and "power_w" not in m
    assert m["sources"] == {"temp_c": "windows-wddm", "fan_rpm": "level-zero-sysman"} and m["is_simulated"] is False


def test_status_lwt_and_event_follow_ocp_v1_4():
    assert messages.last_will("gpu") == {"device": "gpu", "msg_type": "status", "status": "offline", "timestamp": 0}
    on = messages.status("gpu", True, 5, "1.0.0", ["temp_c"])
    assert on == {"device": "gpu", "msg_type": "status", "status": "online", "timestamp": 5, "version": "1.0.0",
                  "capabilities": ["temp_c"]}
    ev = messages.source_swapped("gpu", {"index": 0}, "temp_c", "a", "b", "why", True, 9)
    assert ev["msg_type"] == "event" and ev["event"] == "source_swapped" and ev["to"] == "b" and ev["is_simulated"]
    assert messages.topics("gpu-lab-2") == {"telemetry": "gpu-lab-2/telemetry", "status": "gpu-lab-2/status",
                                            "events": "gpu-lab-2/events"}


# ---- publisher ----

class FakeClient:
    def __init__(self, client_id=""):
        self.client_id, self.sent, self.will, self.auth, self.connected = client_id, [], None, None, None

    def publish(self, topic, payload, qos=0, retain=False):
        self.sent.append((topic, json.loads(payload), qos, retain))

    def will_set(self, topic, payload, qos=0, retain=False):
        self.will = (topic, json.loads(payload), qos, retain)

    def username_pw_set(self, user, password):
        self.auth = (user, password)

    def connect(self, host, port):
        self.connected = (host, port)

    def loop_start(self):
        pass


class Clock:
    def __init__(self):
        self.t = 0.0

    def __call__(self):
        return self.t

    def sleep(self, s):
        self.t += max(s, 0.01)


def test_publisher_online_telemetry_heartbeat_and_offline():
    wd, ig, l0 = trio()
    client, clock = FakeClient(), Clock()
    hub = GpuTelemetryHub([wd, ig, l0])
    p = Publisher(client, "gpu", hub, {"index": 0}, interval=2.0, heartbeat=30.0, clock=clock, sleep=clock.sleep,
                  now_ms=lambda: int(clock.t * 1000))
    p.run(duration=61.0)
    status = [m for t, m, q, r in client.sent if t == "gpu/status"]
    tele = [m for t, m, q, r in client.sent if t == "gpu/telemetry"]
    assert status[0]["status"] == "online" and status[-1]["status"] == "offline"
    assert len([s for s in status if s["status"] == "online"]) == 3        # connect, 30 s, 60 s
    assert all(r and q == 1 for t, m, q, r in client.sent if t == "gpu/status")
    assert 30 <= len(tele) <= 32 and tele[0]["temp_alt_c"] == 59.5
    assert status[0]["capabilities"] == ["fan_rpm", "mem_used_mb", "power_w", "temp_alt_c", "temp_c", "util_pct"]


def test_publisher_emits_a_swap_event_when_a_source_fails():
    wd, ig, l0 = trio()
    client, clock = FakeClient(), Clock()
    holder = {}
    hub = GpuTelemetryHub([wd, ig, l0], on_swap=lambda m, o, n, r: holder["p"].swapped(m, o, n, r))
    holder["p"] = Publisher(client, "gpu", hub, {"index": 0}, clock=clock, sleep=clock.sleep, now_ms=lambda: 1)
    wd.values["temp_c"] = None
    for _ in range(3):
        holder["p"].tick()
    ev = [m for t, m, q, r in client.sent if t == "gpu/events"]
    assert ev and ev[0]["metric"] == "temp_c" and ev[0]["from"] == "windows-wddm" and ev[0]["to"] == "intel-igcl"


def test_connect_sets_the_last_will_before_connecting_and_reads_credentials_from_env(monkeypatch):
    monkeypatch.setenv("MQTT_USERNAME", "u")
    monkeypatch.setenv("MQTT_PASSWORD", "p")
    made = []
    client = connect("broker.local:1884", "gpu", client_factory=lambda cid: made.append(FakeClient(cid)) or made[-1])
    assert client.will == ("gpu/status", messages.last_will("gpu"), 1, True)
    assert client.auth == ("u", "p") and client.connected == ("broker.local", 1884)


def test_resolve_pci_finds_a_device_by_name_in_any_source():
    mod = types.ModuleType("fake")
    mod.devices = lambda: [("Basic Render", None, None), ("Example GPU Pro", (0x1234, 0x5678), None)]
    assert resolve_pci("gpu pro", modules=[mod]) == (0x1234, 0x5678)
    assert resolve_pci("nothing", modules=[mod]) is None
