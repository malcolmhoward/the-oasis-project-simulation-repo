"""Tests for SimulationStatus — centralized simulation vs. real tracking."""

from __future__ import annotations

import json

import pytest

from simulation.hal.status import (
    SimulationStatus,
    StatusChange,
    StatusEvent,
    StatusRecord,
    is_mock_implementation,
)
from simulation.hal.provider import Provider
from simulation.layer0.camera import MockCamera
from simulation.layer0.sensor import MockSensor


class TestIsMockImplementation:
    """is_mock_implementation() heuristic detection."""

    def test_mock_class_detected(self):
        assert is_mock_implementation(MockCamera()) is True

    def test_mock_sensor_detected(self):
        assert is_mock_implementation(MockSensor("imu")) is True

    def test_non_mock_by_name(self):
        class RealCamera:
            pass
        assert is_mock_implementation(RealCamera()) is False

    def test_override_attribute(self):
        class CustomImpl:
            _is_simulated = True
        assert is_mock_implementation(CustomImpl()) is True

    def test_override_attribute_false(self):
        class MockLike:
            _is_simulated = False
        assert is_mock_implementation(MockLike()) is False


class TestStatusEvent:
    """StatusEvent message generation and serialization."""

    def test_registered_message(self):
        event = StatusEvent(
            change=StatusChange.REGISTERED,
            interface="camera",
            implementation="MockCamera",
            previous_implementation=None,
            is_simulated=True,
            was_simulated=None,
        )
        assert "registered" in event.message
        assert "simulated" in event.message
        assert "camera" in event.message

    def test_swapped_mode_change_message(self):
        event = StatusEvent(
            change=StatusChange.SWAPPED,
            interface="camera",
            implementation="RealCamera",
            previous_implementation="MockCamera",
            is_simulated=False,
            was_simulated=True,
        )
        assert "switched" in event.message
        assert "simulated" in event.message
        assert "live" in event.message

    def test_swapped_same_mode_message(self):
        event = StatusEvent(
            change=StatusChange.SWAPPED,
            interface="camera",
            implementation="MockCameraV2",
            previous_implementation="MockCamera",
            is_simulated=True,
            was_simulated=True,
        )
        assert "swapped implementation" in event.message

    def test_to_dict(self):
        event = StatusEvent(
            change=StatusChange.REGISTERED,
            interface="sensor.imu",
            implementation="MockSensor",
            previous_implementation=None,
            is_simulated=True,
            was_simulated=None,
        )
        d = event.to_dict()
        assert d["change"] == "registered"
        assert d["interface"] == "sensor.imu"
        assert d["is_simulated"] is True
        assert "message" in d
        # Verify it's JSON serializable
        json.dumps(d)


class TestSimulationStatus:
    """SimulationStatus tracker core functionality."""

    def test_register_interface(self):
        tracker = SimulationStatus("test")
        tracker.register("camera", MockCamera())
        status = tracker.get_status("camera")
        assert status is not None
        assert status.is_simulated is True
        assert status.implementation == "MockCamera"

    def test_register_emits_event(self):
        events = []
        tracker = SimulationStatus("test")
        tracker.add_listener(lambda e: events.append(e))
        tracker.register("camera", MockCamera())
        assert len(events) == 1
        assert events[0].change == StatusChange.REGISTERED

    def test_unregister(self):
        tracker = SimulationStatus("test")
        tracker.register("camera", MockCamera())
        tracker.unregister("camera")
        assert tracker.get_status("camera") is None

    def test_unregister_emits_event(self):
        events = []
        tracker = SimulationStatus("test")
        tracker.add_listener(lambda e: events.append(e))
        tracker.register("camera", MockCamera())
        tracker.unregister("camera")
        assert events[-1].change == StatusChange.UNREGISTERED

    def test_get_all(self):
        tracker = SimulationStatus("test")
        tracker.register("camera", MockCamera())
        tracker.register("sensor", MockSensor("imu"))
        all_status = tracker.get_all()
        assert len(all_status) == 2
        assert "camera" in all_status
        assert "sensor" in all_status

    def test_is_any_simulated(self):
        tracker = SimulationStatus("test")
        tracker.register("camera", MockCamera())
        assert tracker.is_any_simulated() is True

    def test_is_all_simulated(self):
        tracker = SimulationStatus("test")
        tracker.register("camera", MockCamera())
        tracker.register("sensor", MockSensor("imu"))
        assert tracker.is_all_simulated() is True

    def test_summary(self):
        tracker = SimulationStatus("mirage")
        tracker.register("camera", MockCamera())
        tracker.register("sensor", MockSensor("imu"))
        s = tracker.summary()
        assert s["tracker"] == "mirage"
        assert s["total"] == 2
        assert s["simulated"] == 2
        assert s["live"] == 0
        assert "camera" in s["interfaces"]
        # Verify JSON serializable
        json.dumps(s)


class TestProviderIntegration:
    """SimulationStatus integrated with Provider via create_swap_handler."""

    def test_swap_handler_emits_event(self):
        events = []
        tracker = SimulationStatus("test")
        tracker.add_listener(lambda e: events.append(e))

        handler = tracker.create_swap_handler("camera")
        camera = Provider(MockCamera(), on_swap=handler)
        tracker.register("camera", camera.implementation)

        # Swap to a different mock
        camera.swap(MockCamera(device_id=1))

        swap_events = [e for e in events if e.change == StatusChange.SWAPPED]
        assert len(swap_events) == 1
        assert swap_events[0].interface == "camera"

    def test_swap_handler_updates_tracker(self):
        tracker = SimulationStatus("test")
        handler = tracker.create_swap_handler("camera")
        camera = Provider(MockCamera(device_id=0, width=640), on_swap=handler)
        tracker.register("camera", camera.implementation)

        camera.swap(MockCamera(device_id=1, width=1920))
        status = tracker.get_status("camera")
        assert status.implementation == "MockCamera"

    def test_mode_change_detection(self):
        """Detect when an interface switches between simulated and live."""
        events = []
        tracker = SimulationStatus("test")
        tracker.add_listener(lambda e: events.append(e))

        handler = tracker.create_swap_handler("camera")
        camera = Provider(MockCamera(), on_swap=handler)
        tracker.register("camera", camera.implementation)

        # Simulate "real camera connected" — use a non-Mock class
        class RealCamera:
            _is_simulated = False
            def capture(self): return {}
            def set_resolution(self, w, h): pass
            def set_fps(self, f): pass
            def get_properties(self): return {}
            def release(self): pass

        camera.swap(RealCamera())
        swap_event = [e for e in events if e.change == StatusChange.SWAPPED][0]
        assert swap_event.was_simulated is True
        assert swap_event.is_simulated is False
        assert "switched" in swap_event.message
        assert "live" in swap_event.message

    def test_graceful_degradation_scenario(self):
        """Full hot-plug scenario: mock → real → mock (camera disconnect)."""
        events = []
        tracker = SimulationStatus("mirage")
        tracker.add_listener(lambda e: events.append(e))

        handler = tracker.create_swap_handler("camera")
        mock_cam = MockCamera(device_id=0)
        camera = Provider(mock_cam, on_swap=handler)
        tracker.register("camera", mock_cam)

        # Real camera connected
        class RealCamera:
            _is_simulated = False
            def capture(self): return {}
            def set_resolution(self, w, h): pass
            def set_fps(self, f): pass
            def get_properties(self): return {}
            def release(self): pass

        camera.swap(RealCamera())
        assert not tracker.is_all_simulated()

        # Real camera disconnected — fall back to mock
        camera.swap(mock_cam)
        assert tracker.is_all_simulated()

        # Verify event sequence
        swap_events = [e for e in events if e.change == StatusChange.SWAPPED]
        assert len(swap_events) == 2
        assert swap_events[0].message.count("live") > 0  # mock → real
        assert swap_events[1].message.count("simulated") > 0  # real → mock

    def test_multiple_interfaces(self):
        """Track multiple interfaces independently."""
        tracker = SimulationStatus("mirage")

        cam_handler = tracker.create_swap_handler("camera")
        sensor_handler = tracker.create_swap_handler("sensor.imu")

        camera = Provider(MockCamera(), on_swap=cam_handler)
        sensor = Provider(MockSensor("imu", sensor_type="motion"), on_swap=sensor_handler)

        tracker.register("camera", camera.implementation)
        tracker.register("sensor.imu", sensor.implementation)

        assert tracker.is_all_simulated()
        s = tracker.summary()
        assert s["simulated"] == 2
        assert s["live"] == 0


class TestNotificationChannels:
    """Verify that multiple listeners can be registered for different channels."""

    def test_multiple_listeners(self):
        log_events = []
        mqtt_events = []

        tracker = SimulationStatus("test")
        tracker.add_listener(lambda e: log_events.append(e.message))
        tracker.add_listener(lambda e: mqtt_events.append(e.to_dict()))

        tracker.register("camera", MockCamera())

        assert len(log_events) == 1
        assert len(mqtt_events) == 1
        assert isinstance(mqtt_events[0], dict)

    def test_remove_listener(self):
        events = []
        listener = lambda e: events.append(e)

        tracker = SimulationStatus("test")
        tracker.add_listener(listener)
        tracker.register("a", MockCamera())
        assert len(events) == 1

        tracker.remove_listener(listener)
        tracker.register("b", MockSensor("x"))
        assert len(events) == 1  # no new events

    def test_listener_error_does_not_break_others(self):
        """A failing listener should not prevent other listeners from firing."""
        good_events = []

        def bad_listener(event):
            raise RuntimeError("intentional error")

        tracker = SimulationStatus("test")
        tracker.add_listener(bad_listener)
        tracker.add_listener(lambda e: good_events.append(e))

        tracker.register("camera", MockCamera())
        assert len(good_events) == 1  # good listener still received the event
