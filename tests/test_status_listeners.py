"""Tests for MQTT-based SimulationStatus listeners."""

from __future__ import annotations

import json
from unittest.mock import MagicMock

import pytest

from simulation.hal.status import SimulationStatus, StatusChange, StatusEvent
from simulation.layer0.camera import MockCamera
from simulation.layer0.sensor import MockSensor
from simulation.hal.provider import Provider
from simulation.layer1.status_listeners import (
    MQTTBroadcastListener,
    TTSNotificationListener,
    AudioAlertListener,
    WebUIStatusListener,
)


def _make_mock_client() -> MagicMock:
    client = MagicMock()
    client.publish = MagicMock()
    return client


def _make_swap_event(
    was_simulated: bool = True,
    is_simulated: bool = False,
    interface: str = "camera",
) -> StatusEvent:
    return StatusEvent(
        change=StatusChange.SWAPPED,
        interface=interface,
        implementation="RealCamera" if not is_simulated else "MockCamera",
        previous_implementation="MockCamera" if was_simulated else "RealCamera",
        is_simulated=is_simulated,
        was_simulated=was_simulated,
    )


class TestMQTTBroadcastListener:
    """MQTTBroadcastListener publishes all events to echo/status."""

    def test_publishes_on_register(self):
        client = _make_mock_client()
        listener = MQTTBroadcastListener(client)
        tracker = SimulationStatus("test")
        tracker.add_listener(listener)
        tracker.register("camera", MockCamera())

        client.publish.assert_called()
        call = client.publish.call_args
        assert call.args[0] == "echo/status"
        payload = json.loads(call.kwargs["payload"])
        assert payload["change"] == "registered"
        assert payload["interface"] == "camera"
        assert payload["is_simulated"] is True

    def test_publishes_on_swap(self):
        client = _make_mock_client()
        listener = MQTTBroadcastListener(client)
        event = _make_swap_event()
        listener(event)

        client.publish.assert_called_once()
        payload = json.loads(client.publish.call_args.kwargs["payload"])
        assert payload["change"] == "swapped"
        assert payload["is_simulated"] is False

    def test_retained_message(self):
        client = _make_mock_client()
        listener = MQTTBroadcastListener(client)
        listener(_make_swap_event())
        assert client.publish.call_args.kwargs["retain"] is True

    def test_custom_topic(self):
        client = _make_mock_client()
        listener = MQTTBroadcastListener(client, topic="custom/status")
        listener(_make_swap_event())
        assert client.publish.call_args.args[0] == "custom/status"


class TestTTSNotificationListener:
    """TTSNotificationListener announces mode changes via D.A.W.N. TTS."""

    def test_announces_mode_change(self):
        client = _make_mock_client()
        listener = TTSNotificationListener(client)
        event = _make_swap_event(was_simulated=True, is_simulated=False)
        listener(event)

        client.publish.assert_called_once()
        call = client.publish.call_args
        assert call.args[0] == "dawn"
        payload = json.loads(call.kwargs["payload"])
        assert payload["action"] == "speak"
        assert "live" in payload["value"]
        assert "camera" in payload["value"]

    def test_silent_on_same_mode_swap(self):
        client = _make_mock_client()
        listener = TTSNotificationListener(client)
        event = _make_swap_event(was_simulated=True, is_simulated=True)
        listener(event)
        client.publish.assert_not_called()

    def test_silent_on_register(self):
        client = _make_mock_client()
        listener = TTSNotificationListener(client)
        event = StatusEvent(
            change=StatusChange.REGISTERED,
            interface="camera",
            implementation="MockCamera",
            previous_implementation=None,
            is_simulated=True,
            was_simulated=None,
        )
        listener(event)
        client.publish.assert_not_called()

    def test_announces_degradation(self):
        """Live → simulated (hardware disconnected) triggers TTS."""
        client = _make_mock_client()
        listener = TTSNotificationListener(client)
        event = _make_swap_event(was_simulated=False, is_simulated=True)
        listener(event)

        payload = json.loads(client.publish.call_args.kwargs["payload"])
        assert "simulated" in payload["value"]


class TestAudioAlertListener:
    """AudioAlertListener sends sound alerts to M.I.R.A.G.E. on mode changes."""

    def test_alert_on_mode_change(self):
        client = _make_mock_client()
        listener = AudioAlertListener(client)
        event = _make_swap_event(was_simulated=True, is_simulated=False)
        listener(event)

        client.publish.assert_called_once()
        call = client.publish.call_args
        assert call.args[0] == "hud"
        payload = json.loads(call.kwargs["payload"])
        assert payload["action"] == "audio"
        assert payload["value"] == "sim_status_change"

    def test_silent_on_same_mode(self):
        client = _make_mock_client()
        listener = AudioAlertListener(client)
        event = _make_swap_event(was_simulated=True, is_simulated=True)
        listener(event)
        client.publish.assert_not_called()

    def test_custom_sound(self):
        client = _make_mock_client()
        listener = AudioAlertListener(client, alert_sound="warning_beep")
        listener(_make_swap_event())
        payload = json.loads(client.publish.call_args.kwargs["payload"])
        assert payload["value"] == "warning_beep"


class TestWebUIStatusListener:
    """WebUIStatusListener publishes events for D.A.W.N.'s WebUI."""

    def test_publishes_all_events(self):
        client = _make_mock_client()
        listener = WebUIStatusListener(client)
        event = _make_swap_event()
        listener(event)

        client.publish.assert_called_once()
        payload = json.loads(client.publish.call_args.kwargs["payload"])
        assert payload["type"] == "simulation_status"
        assert payload["payload"]["interface"] == "camera"

    def test_includes_registration_events(self):
        client = _make_mock_client()
        listener = WebUIStatusListener(client)
        event = StatusEvent(
            change=StatusChange.REGISTERED,
            interface="sensor",
            implementation="MockSensor",
            previous_implementation=None,
            is_simulated=True,
            was_simulated=None,
        )
        listener(event)
        client.publish.assert_called_once()


class TestFullIntegration:
    """End-to-end: Provider → SimulationStatus → MQTT listeners."""

    def test_provider_swap_triggers_all_listeners(self):
        client = _make_mock_client()
        tracker = SimulationStatus("mirage")

        broadcast = MQTTBroadcastListener(client)
        tts = TTSNotificationListener(client)
        audio = AudioAlertListener(client)
        webui = WebUIStatusListener(client)

        tracker.add_listener(broadcast)
        tracker.add_listener(tts)
        tracker.add_listener(audio)
        tracker.add_listener(webui)

        # Create provider with tracker integration
        handler = tracker.create_swap_handler("camera")
        mock_cam = MockCamera()
        camera = Provider(mock_cam, on_swap=handler)
        tracker.register("camera", mock_cam)

        client.publish.reset_mock()

        # Simulate real camera connected (mode change: simulated → live)
        class RealCamera:
            _is_simulated = False
            def capture(self): return {}
            def set_resolution(self, w, h): pass
            def set_fps(self, f): pass
            def get_properties(self): return {}
            def release(self): pass

        camera.swap(RealCamera())

        # All 4 listeners should have published
        # broadcast (echo/status) + tts (dawn) + audio (hud) + webui (echo/status/webui)
        topics = [call.args[0] for call in client.publish.call_args_list]
        assert "echo/status" in topics
        assert "dawn" in topics
        assert "hud" in topics
        assert "echo/status/webui" in topics

    def test_graceful_degradation_notifications(self):
        """Camera disconnect → fall back to mock → all channels notified."""
        client = _make_mock_client()
        tracker = SimulationStatus("mirage")

        tts = TTSNotificationListener(client)
        tracker.add_listener(tts)

        handler = tracker.create_swap_handler("camera")

        class RealCamera:
            _is_simulated = False
            def capture(self): return {}
            def set_resolution(self, w, h): pass
            def set_fps(self, f): pass
            def get_properties(self): return {}
            def release(self): pass

        camera = Provider(RealCamera(), on_swap=handler)
        tracker.register("camera", RealCamera())

        client.publish.reset_mock()

        # Camera disconnected — fall back to mock
        camera.swap(MockCamera())

        # TTS should announce the degradation
        client.publish.assert_called()
        payload = json.loads(client.publish.call_args.kwargs["payload"])
        assert "simulated" in payload["value"]
        assert payload["action"] == "speak"
