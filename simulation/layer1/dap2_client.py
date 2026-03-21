"""
DAP2 satellite mock — a simulated Tier 1 satellite that connects to a DAWN
daemon via WebSocket, registers, sends queries, and receives streaming responses.

Can also run as a **standalone mock daemon** (via :class:`DAP2MockDaemon`) for
testing without a real DAWN instance.

Satellite example::

    import asyncio
    from simulation.layer1.dap2_client import DAP2Satellite

    async def main():
        sat = DAP2Satellite(
            uri="ws://localhost:3000",
            name="Kitchen Assistant",
            location="kitchen",
        )
        await sat.connect()
        response = await sat.query("turn on the kitchen lights")
        print(response)  # full assembled response text
        await sat.disconnect()

    asyncio.run(main())

Mock daemon example::

    import asyncio
    from simulation.layer1.dap2_client import DAP2MockDaemon

    async def main():
        daemon = DAP2MockDaemon(host="localhost", port=3000)
        await daemon.start()
        # ... satellites can now connect ...
        await daemon.stop()

    asyncio.run(main())
"""

from __future__ import annotations

import asyncio
import json
import uuid
from dataclasses import dataclass, field
from typing import Any, Callable

try:
    import websockets
    from websockets import connect as ws_connect, serve as ws_serve
except ImportError as exc:
    raise ImportError(
        "Layer 1 requires websockets.  Install with:  "
        'pip install "oasis-sim[layer1]"'
    ) from exc


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass
class SatelliteInfo:
    """Registration payload for a DAP2 satellite."""

    uuid: str = field(default_factory=lambda: str(uuid.uuid4()))
    name: str = "Mock Satellite"
    location: str = "simulation"
    tier: int = 1
    capabilities: dict[str, bool] = field(
        default_factory=lambda: {
            "local_asr": True,
            "local_tts": True,
            "wake_word": True,
        }
    )


@dataclass
class StreamResponse:
    """Assembled response from a streaming DAP2 exchange."""

    stream_id: int
    text: str
    reason: str  # "complete", "error", "cancelled"
    states: list[dict[str, Any]] = field(default_factory=list)


from simulation.hal.network import DAP2SatelliteInterface, DAP2DaemonInterface


# ---------------------------------------------------------------------------
# DAP2 Satellite (client)
# ---------------------------------------------------------------------------


class DAP2Satellite(DAP2SatelliteInterface):
    """Simulated Tier 1 DAP2 (Dawn Audio Protocol 2.0) satellite that connects to a D.A.W.N. daemon.

    Parameters
    ----------
    uri : str
        WebSocket URI of the DAWN daemon (e.g., ``"ws://localhost:3000"``).
    name : str
        Human-readable satellite name.
    location : str
        Room or location identifier.
    info : SatelliteInfo | None
        Full registration info.  If ``None``, built from *name* and *location*.
    ping_interval : float
        Seconds between keepalive pings (default 10).
    """

    def __init__(
        self,
        uri: str = "ws://localhost:3000",
        name: str = "Mock Satellite",
        location: str = "simulation",
        info: SatelliteInfo | None = None,
        ping_interval: float = 10.0,
    ) -> None:
        self.uri = uri
        self.info = info or SatelliteInfo(name=name, location=location)
        self.ping_interval = ping_interval

        self._ws: Any = None
        self._session_id: int | None = None
        self._reconnect_secret: str | None = None
        self._ping_task: asyncio.Task[None] | None = None
        self._registered = False

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def connect(self) -> dict[str, Any]:
        """Connect and register with the daemon.  Returns the registration ack payload."""
        self._ws = await ws_connect(self.uri)
        ack = await self._register()
        self._ping_task = asyncio.create_task(self._ping_loop())
        return ack

    async def disconnect(self) -> None:
        """Gracefully disconnect."""
        if self._ping_task is not None:
            self._ping_task.cancel()
            try:
                await self._ping_task
            except asyncio.CancelledError:
                pass
            self._ping_task = None
        if self._ws is not None:
            await self._ws.close()
            self._ws = None
        self._registered = False

    @property
    def is_connected(self) -> bool:
        return self._ws is not None and self._registered

    # ------------------------------------------------------------------
    # Messaging
    # ------------------------------------------------------------------

    async def query(self, text: str) -> StreamResponse:
        """Send a text query and collect the full streaming response."""
        if not self.is_connected:
            raise RuntimeError("Not connected — call connect() first")
        await self._send({
            "type": "satellite_query",
            "payload": {"text": text},
        })
        return await self._collect_stream()

    async def send_raw(self, message: dict[str, Any]) -> None:
        """Send an arbitrary JSON message."""
        await self._send(message)

    async def recv_raw(self) -> dict[str, Any]:
        """Receive and parse a single JSON message."""
        return await self._recv()

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    async def _register(self) -> dict[str, Any]:
        await self._send({
            "type": "satellite_register",
            "payload": {
                "uuid": self.info.uuid,
                "name": self.info.name,
                "location": self.info.location,
                "tier": self.info.tier,
                "capabilities": self.info.capabilities,
            },
        })
        ack = await self._recv()
        if ack.get("type") != "satellite_register_ack":
            raise RuntimeError(f"Expected register_ack, got: {ack}")
        payload = ack.get("payload", {})
        if not payload.get("success", False):
            raise RuntimeError(f"Registration failed: {payload.get('message', 'unknown')}")
        self._session_id = payload.get("session_id")
        self._reconnect_secret = payload.get("reconnect_secret")
        self._registered = True
        return payload

    async def _collect_stream(self) -> StreamResponse:
        """Read messages until ``stream_end``, assembling deltas."""
        text_parts: list[str] = []
        states: list[dict[str, Any]] = []
        stream_id = 0

        while True:
            msg = await self._recv()
            msg_type = msg.get("type", "")
            payload = msg.get("payload", {})

            if msg_type == "state":
                states.append(payload)
            elif msg_type == "stream_start":
                stream_id = payload.get("stream_id", 0)
            elif msg_type == "stream_delta":
                text_parts.append(payload.get("delta", ""))
            elif msg_type == "stream_end":
                return StreamResponse(
                    stream_id=stream_id,
                    text="".join(text_parts),
                    reason=payload.get("reason", "complete"),
                    states=states,
                )
            elif msg_type == "error":
                return StreamResponse(
                    stream_id=stream_id,
                    text="".join(text_parts),
                    reason="error",
                    states=states,
                )

    async def _ping_loop(self) -> None:
        try:
            while True:
                await asyncio.sleep(self.ping_interval)
                await self._send({"type": "satellite_ping"})
                # Consume the pong (non-blocking drain)
                try:
                    msg = await asyncio.wait_for(self._recv(), timeout=5.0)
                    # Silently discard pong
                except asyncio.TimeoutError:
                    pass
        except asyncio.CancelledError:
            raise

    async def _send(self, data: dict[str, Any]) -> None:
        await self._ws.send(json.dumps(data))

    async def _recv(self) -> dict[str, Any]:
        raw = await self._ws.recv()
        return json.loads(raw)


# ---------------------------------------------------------------------------
# DAP2 Mock Daemon (server) — for testing without a real DAWN instance
# ---------------------------------------------------------------------------


class DAP2MockDaemon(DAP2DaemonInterface):
    """A minimal DAP2 (Dawn Audio Protocol 2.0)-compatible WebSocket server for testing.

    Responds to ``satellite_register`` with an ack, echoes queries back
    as a streaming response, and replies to pings with pongs.

    A custom *query_handler* can be provided to generate domain-specific
    responses.

    Parameters
    ----------
    host : str
        Bind address (default ``"localhost"``).
    port : int
        Bind port (default ``3000``).
    query_handler : callable | None
        ``async def handler(text: str) -> str`` that returns the response
        text for a given query.  If ``None``, the default echo handler is
        used.
    """

    def __init__(
        self,
        host: str = "localhost",
        port: int = 3000,
        query_handler: Callable[[str], Any] | None = None,
    ) -> None:
        self.host = host
        self.port = port
        self.query_handler = query_handler or self._default_handler
        self._server: Any = None
        self._next_session_id = 1
        self._next_stream_id = 1

    async def start(self) -> None:
        """Start the mock daemon."""
        self._server = await ws_serve(self._handle_client, self.host, self.port)

    async def stop(self) -> None:
        """Stop the mock daemon."""
        if self._server is not None:
            self._server.close()
            await self._server.wait_closed()
            self._server = None

    async def _handle_client(self, ws: Any) -> None:
        registered = False
        try:
            async for raw in ws:
                msg = json.loads(raw)
                msg_type = msg.get("type", "")

                if msg_type == "satellite_register":
                    session_id = self._next_session_id
                    self._next_session_id += 1
                    await ws.send(json.dumps({
                        "type": "satellite_register_ack",
                        "payload": {
                            "success": True,
                            "session_id": session_id,
                            "reconnect_secret": f"secret-{session_id}",
                            "message": f"Registered as {msg['payload'].get('name', 'unknown')}",
                        },
                    }))
                    registered = True

                elif msg_type == "satellite_query":
                    if not registered:
                        await ws.send(json.dumps({
                            "type": "error",
                            "payload": {
                                "code": "NOT_REGISTERED",
                                "message": "Must register before sending queries",
                            },
                        }))
                        continue

                    text = msg.get("payload", {}).get("text", "")

                    # State: thinking
                    await ws.send(json.dumps({
                        "type": "state",
                        "payload": {"state": "thinking", "detail": "Processing query..."},
                    }))

                    # Generate response
                    if asyncio.iscoroutinefunction(self.query_handler):
                        response_text = await self.query_handler(text)
                    else:
                        response_text = self.query_handler(text)

                    # Stream the response
                    stream_id = self._next_stream_id
                    self._next_stream_id += 1
                    await ws.send(json.dumps({
                        "type": "stream_start",
                        "payload": {"stream_id": stream_id},
                    }))
                    # Split response into sentence-level deltas
                    sentences = [s.strip() + " " for s in response_text.split(". ") if s.strip()]
                    if not sentences:
                        sentences = [response_text]
                    for sentence in sentences:
                        await ws.send(json.dumps({
                            "type": "stream_delta",
                            "payload": {"stream_id": stream_id, "delta": sentence},
                        }))
                    await ws.send(json.dumps({
                        "type": "stream_end",
                        "payload": {"stream_id": stream_id, "reason": "complete"},
                    }))

                elif msg_type == "satellite_ping":
                    import time
                    await ws.send(json.dumps({
                        "type": "satellite_pong",
                        "payload": {"timestamp": int(time.time())},
                    }))

        except websockets.exceptions.ConnectionClosed:
            pass

    @staticmethod
    def _default_handler(text: str) -> str:
        """Default echo handler — returns the query text as the response."""
        return f"Echo: {text}"
