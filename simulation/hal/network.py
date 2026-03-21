"""
Network layer interface contracts — protocol participation abstractions.

These ABCs (Abstract Base Classes) define the API that both Python mock
implementations (Layer 1) and future protocol test harnesses must conform to.

- TopicBuilderInterface: MQTT (Message Queuing Telemetry Transport) topic
  construction for OCP (OASIS Communications Protocol) conventions
- MessageSerializerInterface: OCP message serialization to JSON
- OCPPeerInterface: OCP peer lifecycle (status, discovery, heartbeat)
- DAP2SatelliteInterface: DAP2 (Dawn Audio Protocol 2.0) satellite client
- DAP2DaemonInterface: DAP2 mock server for testing without a real D.A.W.N. instance
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional


# ---------------------------------------------------------------------------
# MQTT topic helpers
# ---------------------------------------------------------------------------


class TopicBuilderInterface(ABC):
    """Interface for constructing MQTT topic strings per OCP conventions."""

    @abstractmethod
    def status(self) -> str:
        """Return the component status topic (e.g., ``hud/status``)."""
        ...

    @abstractmethod
    def discovery(self, capability: Optional[str] = None) -> str:
        """Return the discovery topic, optionally scoped to a capability."""
        ...

    @abstractmethod
    def command(self) -> str:
        """Return the primary command topic."""
        ...

    @abstractmethod
    def broadcast(self) -> str:
        """Return the system-wide broadcast topic."""
        ...

    @abstractmethod
    def peer_status(self, peer_id: str) -> str:
        """Return the per-peer status topic for OCP embodiment tracking."""
        ...

    @abstractmethod
    def sim_discovery(self) -> str:
        """Return the simulation discovery topic for simulated peers."""
        ...


class MessageSerializerInterface(ABC):
    """Interface for serializing OCP messages to JSON strings."""

    @abstractmethod
    def status_online(self, version: str = "0.0.0",
                      capabilities: Optional[List[str]] = None) -> str:
        """Serialize an online status message."""
        ...

    @abstractmethod
    def status_offline(self) -> str:
        """Serialize an offline status message (timestamp=0 for LWT)."""
        ...

    @abstractmethod
    def discovery(self, elements: List[str]) -> str:
        """Serialize a discovery message."""
        ...

    @abstractmethod
    def command(self, action: str, value: str = "",
                request_id: Optional[str] = None, **extra: Any) -> str:
        """Serialize a command/request message."""
        ...

    @abstractmethod
    def response(self, action: str = "completed", value: str = "",
                 request_id: Optional[str] = None,
                 status: str = "success", **extra: Any) -> str:
        """Serialize a command response message."""
        ...


# ---------------------------------------------------------------------------
# OCP peer
# ---------------------------------------------------------------------------


class OCPPeerInterface(ABC):
    """Interface for an OCP peer that publishes status and keepalive over MQTT.

    Peers follow the OCP lifecycle:
    1. Set LWT (Last Will and Testament) before connecting
    2. Publish online status (retained)
    3. Publish discovery message (retained)
    4. Heartbeat every N seconds
    5. On shutdown, publish offline status and disconnect
    """

    @abstractmethod
    def set_lwt(self) -> None:
        """Set the MQTT LWT (Last Will and Testament) for offline detection."""
        ...

    @abstractmethod
    def start(self) -> None:
        """Publish online status and discovery, start heartbeat loop."""
        ...

    @abstractmethod
    def stop(self) -> None:
        """Publish offline status and stop heartbeat."""
        ...

    @property
    @abstractmethod
    def is_running(self) -> bool:
        """Whether the peer is actively publishing heartbeats."""
        ...


# ---------------------------------------------------------------------------
# DAP2 satellite and daemon
# ---------------------------------------------------------------------------


class DAP2SatelliteInterface(ABC):
    """Interface for a DAP2 satellite client that connects to a D.A.W.N. daemon."""

    @abstractmethod
    async def connect(self) -> Dict[str, Any]:
        """Connect and register with the daemon.  Returns the registration ack."""
        ...

    @abstractmethod
    async def disconnect(self) -> None:
        """Gracefully disconnect."""
        ...

    @abstractmethod
    async def query(self, text: str) -> Any:
        """Send a text query and collect the full streaming response."""
        ...

    @property
    @abstractmethod
    def is_connected(self) -> bool:
        """Whether the satellite is registered and connected."""
        ...


class DAP2DaemonInterface(ABC):
    """Interface for a DAP2 mock server."""

    @abstractmethod
    async def start(self) -> None:
        """Start accepting satellite connections."""
        ...

    @abstractmethod
    async def stop(self) -> None:
        """Stop the server."""
        ...
