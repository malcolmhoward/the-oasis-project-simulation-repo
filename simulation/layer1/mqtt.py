"""
MQTT topic helpers — builders and serializers for O.A.S.I.S. message schemas.

Provides convenience functions for constructing MQTT topics and serializing
messages that follow the OCP (OASIS Communications Protocol) conventions.
Component-specific payload schemas (e.g., MIRAGE's exact JSON format for the
``aura`` topic) live in component demos, not here.

Example::

    from simulation.layer1.mqtt import TopicBuilder, MessageSerializer

    tb = TopicBuilder("mirage")
    tb.status()          # "hud/status"
    tb.discovery("map")  # "hud/discovery/map"

    ms = MessageSerializer("mirage")
    ms.status_online(version="2.1.0", capabilities=["armor_display", "detect"])
    ms.discovery(elements=["armor_display", "detect", "map", "info"])
"""

from __future__ import annotations

import json
import time
from typing import Any

# Mapping from component names to their OCP topic base.
# Some components use abbreviated topic names per OCP convention.
_TOPIC_BASE: dict[str, str] = {
    "mirage": "hud",
    "dawn": "dawn",
    "aura": "aura",
    "spark": "spark",
    "stat": "stat",
    "beacon": "beacon",
    "genesis": "genesis",
    "scope": "scope",
}


from simulation.hal.network import TopicBuilderInterface, MessageSerializerInterface


class TopicBuilder(TopicBuilderInterface):
    """Build MQTT (Message Queuing Telemetry Transport) topic strings for an O.A.S.I.S. component.

    Parameters
    ----------
    component : str
        Component name (e.g., ``"mirage"``, ``"dawn"``).  Looked up in the
        OCP topic-base mapping; falls back to the component name itself.
    """

    def __init__(self, component: str) -> None:
        self.component = component.lower()
        self.base = _TOPIC_BASE.get(self.component, self.component)

    def status(self) -> str:
        """Component status topic (e.g., ``hud/status``)."""
        return f"{self.base}/status"

    def discovery(self, capability: str | None = None) -> str:
        """Discovery topic, optionally scoped to a capability.

        ``hud/discovery/#`` or ``hud/discovery/map``.
        """
        if capability:
            return f"{self.base}/discovery/{capability}"
        return f"{self.base}/discovery/#"

    def command(self) -> str:
        """Primary command topic (e.g., ``hud``, ``dawn``)."""
        return self.base

    def broadcast(self) -> str:
        """System-wide broadcast topic."""
        return "oasis/broadcast"

    def peer_status(self, peer_id: str) -> str:
        """Per-peer status topic for OCP embodiment (e.g., ``oasis/<peer_id>/status``)."""
        return f"oasis/{peer_id}/status"

    def sim_discovery(self) -> str:
        """Simulation discovery topic for simulated peers."""
        return "echo/discovery/simulates"


class MessageSerializer(MessageSerializerInterface):
    """Serialize O.A.S.I.S. OCP (OASIS Communications Protocol) messages to JSON strings.

    Parameters
    ----------
    device : str
        Device/component name included in message payloads.
    """

    def __init__(self, device: str) -> None:
        self.device = device.lower()

    def status_online(
        self,
        version: str = "0.0.0",
        capabilities: list[str] | None = None,
    ) -> str:
        """Serialize an online status message (retained, heartbeat every 30s)."""
        return self._status("online", version, capabilities)

    def status_offline(self) -> str:
        """Serialize an offline status message (timestamp=0 for LWT)."""
        return json.dumps({
            "device": self.device,
            "msg_type": "status",
            "status": "offline",
            "timestamp": 0,
        })

    def discovery(self, elements: list[str]) -> str:
        """Serialize a discovery message (retained)."""
        return json.dumps({
            "device": self.device,
            "msg_type": "discovery",
            "timestamp": int(time.time()),
            "elements": elements,
        })

    def command(
        self,
        action: str,
        value: str = "",
        request_id: str | None = None,
        **extra: Any,
    ) -> str:
        """Serialize a command/request message."""
        msg: dict[str, Any] = {
            "device": self.device,
            "action": action,
            "value": value,
        }
        if request_id:
            msg["request_id"] = request_id
        msg.update(extra)
        return json.dumps(msg)

    def response(
        self,
        action: str = "completed",
        value: str = "",
        request_id: str | None = None,
        status: str = "success",
        **extra: Any,
    ) -> str:
        """Serialize a command response message."""
        msg: dict[str, Any] = {
            "device": self.device,
            "action": action,
            "value": value,
            "status": status,
            "timestamp": int(time.time()),
        }
        if request_id:
            msg["request_id"] = request_id
        msg.update(extra)
        return json.dumps(msg)

    def _status(
        self,
        status: str,
        version: str,
        capabilities: list[str] | None,
    ) -> str:
        msg: dict[str, Any] = {
            "device": self.device,
            "msg_type": "status",
            "status": status,
            "timestamp": int(time.time()),
            "version": version,
        }
        if capabilities:
            msg["capabilities"] = capabilities
        return json.dumps(msg)
