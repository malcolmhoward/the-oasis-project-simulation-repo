"""
MQTT-based listeners for SimulationStatus events.

These listeners bridge the SimulationStatus tracker (HAL layer) to the
O.A.S.I.S. MQTT network, enabling all components to react to simulation
status changes through their existing notification channels.

Listeners:
    MQTTBroadcastListener — publishes status events to ``echo/status`` (retained)
    TTSNotificationListener — publishes human-readable announcements to the
        ``dawn`` topic for D.A.W.N. TTS (text-to-speech) output
    AudioAlertListener — publishes audio commands to the ``hud`` topic for
        M.I.R.A.G.E. sound alerts on mode changes

Example::

    import paho.mqtt.client as mqtt
    from simulation.hal.status import SimulationStatus
    from simulation.layer1.status_listeners import (
        MQTTBroadcastListener,
        TTSNotificationListener,
        AudioAlertListener,
    )

    client = mqtt.Client()
    client.connect("localhost", 1883)
    client.loop_start()

    tracker = SimulationStatus("mirage")
    tracker.add_listener(MQTTBroadcastListener(client))
    tracker.add_listener(TTSNotificationListener(client))
    tracker.add_listener(AudioAlertListener(client))
"""

from __future__ import annotations

import json
import time
from typing import Any

try:
    import paho.mqtt.client as mqtt
except ImportError as exc:
    raise ImportError(
        "Layer 1 requires paho-mqtt.  Install with:  "
        'pip install "oasis-simulation[layer1]"'
    ) from exc

from simulation.hal.status import StatusChange, StatusEvent


class MQTTBroadcastListener:
    """Publishes all status events to ``echo/status`` as retained JSON messages.

    Any component on the MQTT network can subscribe to ``echo/status`` to
    track which interfaces across the ecosystem are simulated vs. real.

    Parameters
    ----------
    client : paho.mqtt.client.Client
        A connected MQTT client.
    topic : str
        Topic to publish to (default ``"echo/status"``).
    qos : int
        MQTT QoS level (default 1).
    """

    def __init__(
        self,
        client: mqtt.Client,
        topic: str = "echo/status",
        qos: int = 1,
    ) -> None:
        self.client = client
        self.topic = topic
        self.qos = qos

    def __call__(self, event: StatusEvent) -> None:
        payload = json.dumps(event.to_dict())
        self.client.publish(self.topic, payload=payload, qos=self.qos, retain=True)


class TTSNotificationListener:
    """Publishes human-readable status announcements to D.A.W.N. for TTS output.

    Only triggers on mode changes (simulated to live, or live to simulated) —
    same-mode swaps and registrations are silent to avoid notification fatigue.

    The message is published to the ``dawn`` topic in D.A.W.N.'s OCP command
    format, requesting text-to-speech output.

    Parameters
    ----------
    client : paho.mqtt.client.Client
        A connected MQTT client.
    topic : str
        Topic for D.A.W.N. TTS commands (default ``"dawn"``).
    """

    def __init__(
        self,
        client: mqtt.Client,
        topic: str = "dawn",
    ) -> None:
        self.client = client
        self.topic = topic

    def __call__(self, event: StatusEvent) -> None:
        # Only announce mode changes (simulated ↔ live)
        if event.change != StatusChange.SWAPPED:
            return
        if event.was_simulated == event.is_simulated:
            return

        self.client.publish(
            self.topic,
            payload=json.dumps({
                "device": "simulation",
                "action": "speak",
                "value": event.message,
                "timestamp": int(time.time()),
            }),
            qos=1,
        )


class AudioAlertListener:
    """Publishes audio alert commands to M.I.R.A.G.E. on mode changes.

    Triggers a notification sound on the HUD when an interface switches
    between simulated and live mode.

    Parameters
    ----------
    client : paho.mqtt.client.Client
        A connected MQTT client.
    topic : str
        Topic for M.I.R.A.G.E. audio commands (default ``"hud"``).
    alert_sound : str
        Sound file name for the alert (default ``"sim_status_change"``).
    """

    def __init__(
        self,
        client: mqtt.Client,
        topic: str = "hud",
        alert_sound: str = "sim_status_change",
    ) -> None:
        self.client = client
        self.topic = topic
        self.alert_sound = alert_sound

    def __call__(self, event: StatusEvent) -> None:
        # Only alert on mode changes
        if event.change != StatusChange.SWAPPED:
            return
        if event.was_simulated == event.is_simulated:
            return

        self.client.publish(
            self.topic,
            payload=json.dumps({
                "device": "simulation",
                "action": "audio",
                "value": self.alert_sound,
                "timestamp": int(time.time()),
            }),
            qos=1,
        )


class WebUIStatusListener:
    """Publishes status events for D.A.W.N.'s WebUI to consume.

    Publishes to a dedicated topic that the WebUI can subscribe to
    for displaying simulation status in the interface.

    Parameters
    ----------
    client : paho.mqtt.client.Client
        A connected MQTT client.
    topic : str
        Topic for WebUI status updates (default ``"echo/status/webui"``).
    """

    def __init__(
        self,
        client: mqtt.Client,
        topic: str = "echo/status/webui",
    ) -> None:
        self.client = client
        self.topic = topic

    def __call__(self, event: StatusEvent) -> None:
        self.client.publish(
            self.topic,
            payload=json.dumps({
                "type": "simulation_status",
                "payload": event.to_dict(),
            }),
            qos=1,
        )
