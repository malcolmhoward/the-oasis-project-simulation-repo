"""
Publish one GPU's telemetry over MQTT as OCP v1.4 GpuTelemetry messages (spec: docs/GPU_TELEMETRY.md).

    python -m simulation.live.gpu.publish --broker localhost --adapter "RTX 4090"
    python -m simulation.live.gpu.publish --broker localhost:1883 --pci 10de:2684 --device gpu-lab-2
    python -m simulation.live.gpu.publish --broker localhost --simulate --load 80      # simulated GPU, same messages

Topics (``--device``, default ``gpu``): ``<device>/telemetry`` every ``--interval`` seconds, ``<device>/status``
(online on connect, a heartbeat every 30 s, offline on exit, and a Last Will and Testament for crashes), and
``<device>/events`` when a metric's source changes.  Consumers in any language subscribe to these and need no
library.  Nothing about the host is published unless you put it in ``--device``.

Requires paho-mqtt (``pip install "oasis-simulation[layer1]"``).  Broker credentials, if any, come from the
MQTT_USERNAME and MQTT_PASSWORD environment variables, never the command line.
"""

import argparse
import json
import os
import sys
import time
from typing import Any, Callable, Dict, List, Optional

from simulation.live.gpu import messages
from simulation.live.gpu.hub import GpuTelemetryHub

VERSION = "1.0.0"
HEARTBEAT_S = 30.0


class Publisher:
    """The publish loop, given a connected MQTT client (paho-compatible: ``publish(topic, payload, qos, retain)``).
    Separate from connecting, so tests can pass a fake client."""

    def __init__(self, client: Any, device: str, hub: GpuTelemetryHub, gpu: Dict[str, Any], interval: float = 2.0,
                 heartbeat: float = HEARTBEAT_S, clock: Callable[[], float] = time.monotonic,
                 sleep: Callable[[float], None] = time.sleep, now_ms: Callable[[], int] = lambda: int(time.time() * 1000),
                 before_sample: Optional[Callable[[], None]] = None) -> None:
        self.client, self.device, self.hub, self.gpu = client, device, hub, gpu
        self.interval, self.heartbeat, self.clock, self.sleep, self.now_ms = interval, heartbeat, clock, sleep, now_ms
        self.before_sample = before_sample
        self.topics = messages.topics(device)
        self.capabilities = sorted(m for m, s in hub.active().items() if s)

    def _send(self, topic: str, msg: Dict[str, Any], qos: int = 0, retain: bool = False) -> None:
        self.client.publish(topic, json.dumps(msg), qos=qos, retain=retain)

    def online(self) -> None:
        self._send(self.topics["status"], messages.status(self.device, True, self.now_ms(), VERSION, self.capabilities),
                   qos=1, retain=True)

    def offline(self) -> None:
        self._send(self.topics["status"], messages.status(self.device, False, self.now_ms(), VERSION), qos=1,
                   retain=True)

    def swapped(self, metric: str, old: Any, new: Any, reason: Optional[str]) -> None:
        from simulation.live.gpu.hub import label
        self._send(self.topics["events"], messages.source_swapped(self.device, self.gpu, metric, label(old), label(new),
                                                                  reason, self.hub.is_simulated(), self.now_ms()), qos=1)

    def tick(self) -> Dict[str, Any]:
        if self.before_sample is not None:
            self.before_sample()
        s = self.hub.sample()
        msg = messages.telemetry(self.device, self.gpu, s.values, s.sources, self.hub.is_simulated(), self.now_ms())
        self._send(self.topics["telemetry"], msg)
        return msg

    def run(self, duration: float = 0.0) -> None:
        self.online()
        start = self.clock()
        next_beat, next_tick = start + self.heartbeat, start
        try:
            while not duration or self.clock() - start < duration:
                now = self.clock()
                if now >= next_tick:
                    self.tick()
                    next_tick += self.interval
                if now >= next_beat:
                    self.online()
                    next_beat += self.heartbeat
                self.sleep(max(0.0, min(next_tick, next_beat) - self.clock()))
        finally:
            self.offline()


def connect(broker: str, device: str, client_factory: Optional[Callable[..., Any]] = None) -> Any:
    """A connected paho client with the OCP Last Will and Testament set on ``<device>/status``."""
    if client_factory is None:
        try:
            import paho.mqtt.client as mqtt
        except ImportError:
            raise SystemExit('publishing needs paho-mqtt: pip install "oasis-simulation[layer1]"')

        def client_factory(client_id):
            try:
                return mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=client_id)
            except AttributeError:                          # paho-mqtt 1.x
                return mqtt.Client(client_id=client_id)
    client = client_factory(f"{device}-{os.getpid()}")
    user = os.environ.get("MQTT_USERNAME")
    if user:
        client.username_pw_set(user, os.environ.get("MQTT_PASSWORD"))
    client.will_set(messages.topics(device)["status"], json.dumps(messages.last_will(device)), qos=1, retain=True)
    host, _, port = broker.partition(":")
    client.connect(host, int(port or 1883))
    client.loop_start()
    return client


def open_sources(adapter: str, pci: Optional[tuple], simulate: bool, load: float):
    """(sources, gpu identity, before_sample hook)."""
    if simulate:
        from simulation.layer0.gpu import MockGpuTelemetry
        a = MockGpuTelemetry(name="Simulated GPU", provider="simulated")
        b = MockGpuTelemetry(name="Simulated GPU (alt sensor)", provider="simulated-alt")
        for g in (a, b):
            g.set_load(load)
        return [a, b], messages.gpu_identity("Simulated GPU", None), None
    from simulation.live.gpu import discover, resolve_pci
    pci = pci or resolve_pci(adapter)
    sources, report = discover(match=adapter, pci=pci)
    if not sources:
        raise SystemExit(f"no telemetry source found for {adapter!r} (pci {pci}): {report}")
    name = next((s.name for s in sources if s.provider == "windows-wddm"), sources[0].name)
    return sources, messages.gpu_identity(name, pci), None


def _pci(text: str) -> tuple:
    v, _, d = text.partition(":")
    return int(v, 16), int(d, 16)


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(prog="python -m simulation.live.gpu.publish", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--broker", default=os.environ.get("MQTT_BROKER"), help="host[:port] (or MQTT_BROKER)")
    ap.add_argument("--device", default="gpu", help="OCP device name and topic prefix (default gpu)")
    ap.add_argument("--adapter", default="", help="substring of the GPU name")
    ap.add_argument("--pci", type=_pci, help="PCI IDs, VENDOR:DEVICE in hex")
    ap.add_argument("--interval", type=float, default=2.0, help="seconds between telemetry messages")
    ap.add_argument("--duration", type=float, default=0.0, help="seconds to run; 0 = until interrupted")
    ap.add_argument("--simulate", action="store_true", help="publish a simulated GPU (is_simulated: true)")
    ap.add_argument("--load", type=float, default=50.0, help="simulated utilization, percent (with --simulate)")
    a = ap.parse_args(argv)
    if not a.broker:
        ap.error("--broker (or MQTT_BROKER) is required")
    if not a.simulate and not (a.adapter or a.pci):
        ap.error("choose the GPU with --adapter or --pci (or use --simulate)")
    sources, gpu, hook = open_sources(a.adapter, a.pci, a.simulate, a.load)
    client = connect(a.broker, a.device)
    pub: Dict[str, Publisher] = {}
    hub = GpuTelemetryHub(sources, on_swap=lambda m, o, n, r: pub["p"].swapped(m, o, n, r))
    pub["p"] = Publisher(client, a.device, hub, gpu, interval=a.interval, before_sample=hook)
    active = hub.active()
    print(f"publishing {gpu.get('name')} to {a.broker} as {a.device}/telemetry; temperature from {active['temp_c']}, "
          f"cross-check from {active['temp_alt_c'] or 'none'}{'; SIMULATED' if hub.is_simulated() else ''}")
    try:
        pub["p"].run(a.duration)
    except KeyboardInterrupt:
        pass
    finally:
        client.loop_stop()
        client.disconnect()
        hub.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
