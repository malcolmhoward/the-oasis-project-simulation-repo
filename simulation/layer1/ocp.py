"""
OCP peer simulation — simulated peers that register, publish status, and
maintain keepalive on the O.A.S.I.S. MQTT network.

Two embodiment types are supported:

* **E3** — physical hardware peer (real sensors, actuators).
* **E4** — software-only peer (no physical body; used by simulation).

Both follow the same MQTT lifecycle:

1. Set Last Will and Testament (offline status, timestamp=0).
2. Publish online status (retained).
3. Publish discovery message (retained).
4. Heartbeat every ``heartbeat_interval`` seconds (default 30).
5. On shutdown, publish offline status and disconnect.

Example::

    import paho.mqtt.client as mqtt
    from simulation.layer1.ocp import OCPPeer, Embodiment

    client = mqtt.Client()
    client.connect("localhost", 1883)
    client.loop_start()

    peer = OCPPeer(
        client=client,
        peer_id="echo-mirage-sim",
        component="mirage",
        embodiment=Embodiment.E4,
        capabilities=["armor_display", "detect"],
    )
    peer.start()   # publishes online + discovery, starts heartbeat
    # ... do work ...
    peer.stop()    # publishes offline, stops heartbeat
    client.loop_stop()
"""

from __future__ import annotations

import enum
import json
import threading
import time
from typing import Any

try:
    import paho.mqtt.client as mqtt
except ImportError as exc:
    raise ImportError(
        "Layer 1 requires paho-mqtt.  Install with:  "
        'pip install "oasis-sim[layer1]"'
    ) from exc

from simulation.hal.network import OCPPeerInterface
from simulation.layer1.mqtt import TopicBuilder, MessageSerializer


class Embodiment(enum.Enum):
    """OCP embodiment level.

    E3 — physical hardware peer (sensors, actuators, real-world presence).
    E4 — software-only peer (no physical body; simulation or pure-software agent).
    """

    E3 = "physical"
    E4 = "software"


class OCPPeer(OCPPeerInterface):
    """A simulated OCP (OASIS Communications Protocol) peer that publishes status and keepalive over MQTT (Message Queuing Telemetry Transport).

    Parameters
    ----------
    client : paho.mqtt.client.Client
        A connected (and looping) MQTT client.
    peer_id : str
        Unique identifier for this peer (used in topic ``oasis/<peer_id>/status``).
    component : str
        O.A.S.I.S. component name (e.g., ``"mirage"``).
    embodiment : Embodiment
        E3 (physical) or E4 (software-only).
    capabilities : list[str] | None
        List of capabilities advertised in discovery messages.
    version : str
        Version string included in status messages.
    heartbeat_interval : float
        Seconds between heartbeat status publishes (default 30).
    """

    def __init__(
        self,
        client: mqtt.Client,
        peer_id: str,
        component: str,
        embodiment: Embodiment = Embodiment.E4,
        capabilities: list[str] | None = None,
        version: str = "0.0.0-sim",
        heartbeat_interval: float = 30.0,
    ) -> None:
        self.client = client
        self.peer_id = peer_id
        self.component = component
        self.embodiment = embodiment
        self.capabilities = capabilities or []
        self.version = version
        self.heartbeat_interval = heartbeat_interval

        self._topics = TopicBuilder(component)
        self._serializer = MessageSerializer(component)
        self._heartbeat_timer: threading.Timer | None = None
        self._running = False

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def set_lwt(self) -> None:
        """Set the Last Will and Testament before connecting.

        Call this *before* ``client.connect()`` if you want the broker to
        publish an offline message on unexpected disconnect.  If the client
        is already connected, this has no effect until the next reconnect.
        """
        self.client.will_set(
            self._topics.status(),
            payload=self._serializer.status_offline(),
            qos=1,
            retain=True,
        )

    def start(self) -> None:
        """Publish online status and discovery, start heartbeat loop."""
        self._running = True
        self._publish_online()
        self._publish_discovery()
        self._publish_sim_discovery()
        self._schedule_heartbeat()

    def stop(self) -> None:
        """Publish offline status and stop heartbeat."""
        self._running = False
        if self._heartbeat_timer is not None:
            self._heartbeat_timer.cancel()
            self._heartbeat_timer = None
        self._publish_offline()

    @property
    def is_running(self) -> bool:
        return self._running

    # ------------------------------------------------------------------
    # Internal publishing
    # ------------------------------------------------------------------

    def _publish_online(self) -> None:
        self.client.publish(
            self._topics.status(),
            payload=self._serializer.status_online(
                version=self.version,
                capabilities=self.capabilities,
            ),
            qos=1,
            retain=True,
        )
        # Also publish to per-peer topic for E3/E4 tracking
        self.client.publish(
            self._topics.peer_status(self.peer_id),
            payload=json.dumps({
                "peer_id": self.peer_id,
                "component": self.component,
                "embodiment": self.embodiment.value,
                "status": "online",
                "timestamp": int(time.time()),
            }),
            qos=1,
            retain=True,
        )

    def _publish_offline(self) -> None:
        self.client.publish(
            self._topics.status(),
            payload=self._serializer.status_offline(),
            qos=1,
            retain=True,
        )
        self.client.publish(
            self._topics.peer_status(self.peer_id),
            payload=json.dumps({
                "peer_id": self.peer_id,
                "component": self.component,
                "embodiment": self.embodiment.value,
                "status": "offline",
                "timestamp": 0,
            }),
            qos=1,
            retain=True,
        )

    def _publish_discovery(self) -> None:
        if self.capabilities:
            self.client.publish(
                self._topics.discovery(None).replace("/#", ""),
                payload=self._serializer.discovery(self.capabilities),
                qos=1,
                retain=True,
            )

    def _publish_sim_discovery(self) -> None:
        """Publish to ``echo/discovery/simulates`` so other peers know this is simulated."""
        self.client.publish(
            self._topics.sim_discovery(),
            payload=json.dumps({
                "peer_id": self.peer_id,
                "component": self.component,
                "embodiment": self.embodiment.value,
                "capabilities": self.capabilities,
                "timestamp": int(time.time()),
            }),
            qos=1,
            retain=True,
        )

    def _schedule_heartbeat(self) -> None:
        if not self._running:
            return
        self._heartbeat_timer = threading.Timer(
            self.heartbeat_interval,
            self._heartbeat,
        )
        self._heartbeat_timer.daemon = True
        self._heartbeat_timer.start()

    def _heartbeat(self) -> None:
        if not self._running:
            return
        self._publish_online()
        self._schedule_heartbeat()
