"""Tests for Layer 1 — protocol simulation (MQTT helpers, OCP peers, DAP2 client)."""

from __future__ import annotations

import asyncio
import json
import time
from unittest.mock import MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# MQTT topic helpers
# ---------------------------------------------------------------------------

from simulation.layer1.mqtt import TopicBuilder, MessageSerializer


class TestTopicBuilder:
    """TopicBuilder constructs MQTT topic strings per OCP conventions."""

    def test_status_topic_mirage(self):
        tb = TopicBuilder("mirage")
        assert tb.status() == "hud/status"

    def test_status_topic_dawn(self):
        tb = TopicBuilder("dawn")
        assert tb.status() == "dawn/status"

    def test_status_topic_unknown_component(self):
        tb = TopicBuilder("custom")
        assert tb.status() == "custom/status"

    def test_discovery_with_capability(self):
        tb = TopicBuilder("mirage")
        assert tb.discovery("map") == "hud/discovery/map"

    def test_discovery_wildcard(self):
        tb = TopicBuilder("mirage")
        assert tb.discovery() == "hud/discovery/#"

    def test_command_topic(self):
        tb = TopicBuilder("dawn")
        assert tb.command() == "dawn"

    def test_command_topic_mirage(self):
        tb = TopicBuilder("mirage")
        assert tb.command() == "hud"

    def test_broadcast(self):
        tb = TopicBuilder("mirage")
        assert tb.broadcast() == "oasis/broadcast"

    def test_peer_status(self):
        tb = TopicBuilder("mirage")
        assert tb.peer_status("echo-sim-1") == "oasis/echo-sim-1/status"

    def test_sim_discovery(self):
        tb = TopicBuilder("mirage")
        assert tb.sim_discovery() == "echo/discovery/simulates"

    def test_case_insensitive(self):
        tb = TopicBuilder("MIRAGE")
        assert tb.status() == "hud/status"

    def test_all_known_components(self):
        expected = {
            "mirage": "hud",
            "dawn": "dawn",
            "aura": "aura",
            "spark": "spark",
            "stat": "stat",
            "beacon": "beacon",
            "genesis": "genesis",
            "scope": "scope",
        }
        for comp, base in expected.items():
            tb = TopicBuilder(comp)
            assert tb.base == base, f"TopicBuilder({comp!r}).base != {base!r}"


class TestMessageSerializer:
    """MessageSerializer produces valid OCP JSON messages."""

    def test_status_online(self):
        ms = MessageSerializer("mirage")
        raw = ms.status_online(version="2.1.0", capabilities=["detect"])
        msg = json.loads(raw)
        assert msg["device"] == "mirage"
        assert msg["msg_type"] == "status"
        assert msg["status"] == "online"
        assert msg["version"] == "2.1.0"
        assert msg["capabilities"] == ["detect"]
        assert msg["timestamp"] > 0

    def test_status_offline(self):
        ms = MessageSerializer("dawn")
        raw = ms.status_offline()
        msg = json.loads(raw)
        assert msg["device"] == "dawn"
        assert msg["status"] == "offline"
        assert msg["timestamp"] == 0

    def test_discovery(self):
        ms = MessageSerializer("mirage")
        raw = ms.discovery(["armor_display", "detect", "map"])
        msg = json.loads(raw)
        assert msg["device"] == "mirage"
        assert msg["msg_type"] == "discovery"
        assert msg["elements"] == ["armor_display", "detect", "map"]
        assert msg["timestamp"] > 0

    def test_command(self):
        ms = MessageSerializer("viewing")
        raw = ms.command(action="look", value="describe what you see", request_id="dawn_42")
        msg = json.loads(raw)
        assert msg["device"] == "viewing"
        assert msg["action"] == "look"
        assert msg["value"] == "describe what you see"
        assert msg["request_id"] == "dawn_42"

    def test_command_no_request_id(self):
        ms = MessageSerializer("dawn")
        raw = ms.command(action="speak", value="hello")
        msg = json.loads(raw)
        assert "request_id" not in msg

    def test_command_extra_fields(self):
        ms = MessageSerializer("dawn")
        raw = ms.command(action="speak", value="hello", priority="high")
        msg = json.loads(raw)
        assert msg["priority"] == "high"

    def test_response(self):
        ms = MessageSerializer("mirage")
        raw = ms.response(
            action="completed",
            value="/tmp/screenshot.jpg",
            request_id="dawn_42",
            checksum="abc123",
        )
        msg = json.loads(raw)
        assert msg["device"] == "mirage"
        assert msg["action"] == "completed"
        assert msg["status"] == "success"
        assert msg["request_id"] == "dawn_42"
        assert msg["checksum"] == "abc123"
        assert msg["timestamp"] > 0

    def test_response_no_request_id(self):
        ms = MessageSerializer("dawn")
        raw = ms.response(action="completed", value="done")
        msg = json.loads(raw)
        assert "request_id" not in msg

    def test_status_online_no_capabilities(self):
        ms = MessageSerializer("stat")
        raw = ms.status_online(version="1.0")
        msg = json.loads(raw)
        assert "capabilities" not in msg

    def test_case_insensitive_device(self):
        ms = MessageSerializer("MIRAGE")
        raw = ms.status_online()
        msg = json.loads(raw)
        assert msg["device"] == "mirage"


# ---------------------------------------------------------------------------
# OCP peer simulation
# ---------------------------------------------------------------------------

from simulation.layer1.ocp import OCPPeer, Embodiment


class TestEmbodiment:
    """Embodiment enum represents E3 (physical) and E4 (software)."""

    def test_e3_value(self):
        assert Embodiment.E3.value == "physical"

    def test_e4_value(self):
        assert Embodiment.E4.value == "software"


class TestOCPPeer:
    """OCPPeer publishes OCP status, discovery, and heartbeat over MQTT."""

    def _make_mock_client(self) -> MagicMock:
        client = MagicMock()
        client.publish = MagicMock()
        client.will_set = MagicMock()
        return client

    def test_set_lwt(self):
        client = self._make_mock_client()
        peer = OCPPeer(client=client, peer_id="sim-1", component="mirage")
        peer.set_lwt()
        client.will_set.assert_called_once()
        args, kwargs = client.will_set.call_args
        assert args[0] == "hud/status"
        msg = json.loads(kwargs["payload"])
        assert msg["status"] == "offline"
        assert msg["timestamp"] == 0

    def test_start_publishes_status_and_discovery(self):
        client = self._make_mock_client()
        peer = OCPPeer(
            client=client,
            peer_id="sim-1",
            component="mirage",
            capabilities=["detect", "map"],
            version="1.0.0-sim",
        )
        peer.start()
        try:
            # Should have published: online status, peer status, discovery, sim discovery
            topics = [call.args[0] for call in client.publish.call_args_list]
            assert "hud/status" in topics
            assert "oasis/sim-1/status" in topics
            assert "hud/discovery" in topics
            assert "echo/discovery/simulates" in topics

            # Verify online status content
            for call in client.publish.call_args_list:
                if call.args[0] == "hud/status":
                    msg = json.loads(call.kwargs["payload"])
                    assert msg["status"] == "online"
                    assert msg["version"] == "1.0.0-sim"
                    assert msg["capabilities"] == ["detect", "map"]
                    break
        finally:
            peer.stop()

    def test_start_sets_running(self):
        client = self._make_mock_client()
        peer = OCPPeer(client=client, peer_id="sim-1", component="dawn")
        assert not peer.is_running
        peer.start()
        assert peer.is_running
        peer.stop()
        assert not peer.is_running

    def test_stop_publishes_offline(self):
        client = self._make_mock_client()
        peer = OCPPeer(client=client, peer_id="sim-1", component="dawn")
        peer.start()
        client.publish.reset_mock()
        peer.stop()

        # Offline status should be published
        topics = [call.args[0] for call in client.publish.call_args_list]
        assert "dawn/status" in topics
        for call in client.publish.call_args_list:
            if call.args[0] == "dawn/status":
                msg = json.loads(call.kwargs["payload"])
                assert msg["status"] == "offline"
                assert msg["timestamp"] == 0
                break

    def test_e4_embodiment_in_peer_status(self):
        client = self._make_mock_client()
        peer = OCPPeer(
            client=client,
            peer_id="sim-1",
            component="mirage",
            embodiment=Embodiment.E4,
        )
        peer.start()
        try:
            for call in client.publish.call_args_list:
                if call.args[0] == "oasis/sim-1/status":
                    msg = json.loads(call.kwargs["payload"])
                    assert msg["embodiment"] == "software"
                    assert msg["peer_id"] == "sim-1"
                    break
            else:
                pytest.fail("No peer status message published")
        finally:
            peer.stop()

    def test_e3_embodiment(self):
        client = self._make_mock_client()
        peer = OCPPeer(
            client=client,
            peer_id="hw-1",
            component="mirage",
            embodiment=Embodiment.E3,
        )
        peer.start()
        try:
            for call in client.publish.call_args_list:
                if call.args[0] == "oasis/hw-1/status":
                    msg = json.loads(call.kwargs["payload"])
                    assert msg["embodiment"] == "physical"
                    break
        finally:
            peer.stop()

    def test_no_discovery_without_capabilities(self):
        client = self._make_mock_client()
        peer = OCPPeer(
            client=client,
            peer_id="sim-1",
            component="dawn",
            capabilities=[],
        )
        peer.start()
        try:
            topics = [call.args[0] for call in client.publish.call_args_list]
            assert "dawn/discovery" not in topics
        finally:
            peer.stop()

    def test_sim_discovery_published(self):
        client = self._make_mock_client()
        peer = OCPPeer(
            client=client,
            peer_id="echo-sim",
            component="mirage",
            capabilities=["detect"],
        )
        peer.start()
        try:
            for call in client.publish.call_args_list:
                if call.args[0] == "echo/discovery/simulates":
                    msg = json.loads(call.kwargs["payload"])
                    assert msg["peer_id"] == "echo-sim"
                    assert msg["component"] == "mirage"
                    assert msg["capabilities"] == ["detect"]
                    break
            else:
                pytest.fail("No sim discovery message published")
        finally:
            peer.stop()

    def test_heartbeat_interval_configurable(self):
        client = self._make_mock_client()
        peer = OCPPeer(
            client=client,
            peer_id="sim-1",
            component="dawn",
            heartbeat_interval=5.0,
        )
        assert peer.heartbeat_interval == 5.0

    def test_default_version(self):
        client = self._make_mock_client()
        peer = OCPPeer(client=client, peer_id="sim-1", component="dawn")
        assert peer.version == "0.0.0-sim"


# ---------------------------------------------------------------------------
# DAP2 satellite and mock daemon
# ---------------------------------------------------------------------------

from simulation.layer1.dap2_client import (
    DAP2Satellite,
    DAP2MockDaemon,
    SatelliteInfo,
    StreamResponse,
)


class TestSatelliteInfo:
    """SatelliteInfo data class defaults."""

    def test_defaults(self):
        info = SatelliteInfo()
        assert info.name == "Mock Satellite"
        assert info.location == "simulation"
        assert info.tier == 1
        assert info.capabilities["local_asr"] is True
        assert len(info.uuid) == 36  # UUID4 format

    def test_custom_values(self):
        info = SatelliteInfo(name="Kitchen", location="kitchen", tier=2)
        assert info.name == "Kitchen"
        assert info.location == "kitchen"
        assert info.tier == 2


class TestStreamResponse:
    """StreamResponse data class."""

    def test_fields(self):
        sr = StreamResponse(stream_id=1, text="hello world", reason="complete")
        assert sr.stream_id == 1
        assert sr.text == "hello world"
        assert sr.reason == "complete"
        assert sr.states == []


def _find_free_port() -> int:
    """Find an available TCP port for testing."""
    import socket
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("", 0))
        return s.getsockname()[1]


class TestDAP2Integration:
    """Integration tests: DAP2MockDaemon + DAP2Satellite end-to-end."""

    @pytest.fixture
    def port(self):
        return _find_free_port()

    @pytest.mark.asyncio
    async def test_register_and_query(self, port):
        """Satellite registers with mock daemon and sends a query."""
        daemon = DAP2MockDaemon(host="localhost", port=port)
        await daemon.start()
        try:
            sat = DAP2Satellite(uri=f"ws://localhost:{port}", name="Test Sat", location="lab")
            ack = await sat.connect()
            assert ack["success"] is True
            assert "session_id" in ack
            assert sat.is_connected

            response = await sat.query("turn on the lights")
            assert isinstance(response, StreamResponse)
            assert "turn on the lights" in response.text
            assert response.reason == "complete"

            await sat.disconnect()
            assert not sat.is_connected
        finally:
            await daemon.stop()

    @pytest.mark.asyncio
    async def test_custom_query_handler(self, port):
        """Mock daemon uses custom query handler for responses."""
        def handler(text: str) -> str:
            if "lights" in text:
                return "I'll turn on the lights. They should be on now."
            return "I don't understand."

        daemon = DAP2MockDaemon(host="localhost", port=port, query_handler=handler)
        await daemon.start()
        try:
            sat = DAP2Satellite(uri=f"ws://localhost:{port}")
            await sat.connect()

            r1 = await sat.query("turn on the lights")
            assert "turn on the lights" in r1.text
            assert "should be on now" in r1.text

            r2 = await sat.query("do something random")
            assert "I don't understand" in r2.text

            await sat.disconnect()
        finally:
            await daemon.stop()

    @pytest.mark.asyncio
    async def test_async_query_handler(self, port):
        """Mock daemon supports async query handlers."""
        async def handler(text: str) -> str:
            await asyncio.sleep(0.01)  # simulate processing
            return f"Processed: {text}"

        daemon = DAP2MockDaemon(host="localhost", port=port, query_handler=handler)
        await daemon.start()
        try:
            sat = DAP2Satellite(uri=f"ws://localhost:{port}")
            await sat.connect()

            response = await sat.query("test async")
            assert response.text == "Processed: test async "

            await sat.disconnect()
        finally:
            await daemon.stop()

    @pytest.mark.asyncio
    async def test_state_messages_captured(self, port):
        """Satellite captures state messages (thinking, etc.) during query."""
        daemon = DAP2MockDaemon(host="localhost", port=port)
        await daemon.start()
        try:
            sat = DAP2Satellite(uri=f"ws://localhost:{port}")
            await sat.connect()

            response = await sat.query("hello")
            # Daemon sends a "thinking" state before the stream
            assert len(response.states) >= 1
            assert response.states[0]["state"] == "thinking"

            await sat.disconnect()
        finally:
            await daemon.stop()

    @pytest.mark.asyncio
    async def test_multiple_queries(self, port):
        """Satellite can send multiple queries on the same connection."""
        daemon = DAP2MockDaemon(host="localhost", port=port)
        await daemon.start()
        try:
            sat = DAP2Satellite(uri=f"ws://localhost:{port}")
            await sat.connect()

            r1 = await sat.query("first")
            r2 = await sat.query("second")
            assert "first" in r1.text
            assert "second" in r2.text
            # Stream IDs should increment
            assert r2.stream_id > r1.stream_id

            await sat.disconnect()
        finally:
            await daemon.stop()

    @pytest.mark.asyncio
    async def test_query_before_connect_raises(self):
        """Querying without connecting raises RuntimeError."""
        sat = DAP2Satellite(uri="ws://localhost:9999")
        with pytest.raises(RuntimeError, match="Not connected"):
            await sat.query("hello")

    @pytest.mark.asyncio
    async def test_satellite_info_used_in_registration(self, port):
        """Custom SatelliteInfo is used in the registration payload."""
        daemon = DAP2MockDaemon(host="localhost", port=port)
        await daemon.start()
        try:
            info = SatelliteInfo(name="Custom Sat", location="garage", tier=1)
            sat = DAP2Satellite(uri=f"ws://localhost:{port}", info=info)
            ack = await sat.connect()
            assert "Custom Sat" in ack["message"]

            await sat.disconnect()
        finally:
            await daemon.stop()

    @pytest.mark.asyncio
    async def test_reconnect_secret_stored(self, port):
        """Satellite stores the reconnect secret from registration ack."""
        daemon = DAP2MockDaemon(host="localhost", port=port)
        await daemon.start()
        try:
            sat = DAP2Satellite(uri=f"ws://localhost:{port}")
            await sat.connect()
            assert sat._reconnect_secret is not None
            assert sat._session_id is not None

            await sat.disconnect()
        finally:
            await daemon.stop()

    @pytest.mark.asyncio
    async def test_disconnect_idempotent(self, port):
        """Calling disconnect multiple times does not raise."""
        daemon = DAP2MockDaemon(host="localhost", port=port)
        await daemon.start()
        try:
            sat = DAP2Satellite(uri=f"ws://localhost:{port}")
            await sat.connect()
            await sat.disconnect()
            await sat.disconnect()  # should not raise
        finally:
            await daemon.stop()

    @pytest.mark.asyncio
    async def test_multiple_satellites(self, port):
        """Multiple satellites can connect to the same daemon."""
        daemon = DAP2MockDaemon(host="localhost", port=port)
        await daemon.start()
        try:
            sat1 = DAP2Satellite(uri=f"ws://localhost:{port}", name="Sat 1")
            sat2 = DAP2Satellite(uri=f"ws://localhost:{port}", name="Sat 2")
            ack1 = await sat1.connect()
            ack2 = await sat2.connect()
            # Each gets a unique session ID
            assert ack1["session_id"] != ack2["session_id"]

            r1 = await sat1.query("from sat1")
            r2 = await sat2.query("from sat2")
            assert "sat1" in r1.text
            assert "sat2" in r2.text

            await sat1.disconnect()
            await sat2.disconnect()
        finally:
            await daemon.stop()
