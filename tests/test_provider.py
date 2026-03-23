"""Tests for the Provider — runtime hot-swap wrapper for HAL interfaces."""

from __future__ import annotations

import threading

import pytest

from simulation.hal.provider import Provider
from simulation.layer0.camera import MockCamera
from simulation.layer0.sensor import MockSensor
from simulation.layer0.gpio import MockGPIO


class TestProviderBasic:
    """Provider wraps an implementation and forwards attribute access."""

    def test_forwards_method_calls(self):
        sensor = MockSensor("imu", sensor_type="motion")
        provider = Provider(sensor)
        data = provider.read()
        assert "heading" in data

    def test_forwards_properties(self):
        sensor = MockSensor("imu", sensor_type="motion")
        provider = Provider(sensor)
        assert provider.name == "imu"
        assert provider.sensor_type == "motion"

    def test_implementation_property(self):
        sensor = MockSensor("imu")
        provider = Provider(sensor)
        assert provider.implementation is sensor

    def test_implementation_type(self):
        sensor = MockSensor("imu")
        provider = Provider(sensor)
        assert provider.implementation_type is MockSensor

    def test_repr(self):
        sensor = MockSensor("imu", sensor_type="motion")
        provider = Provider(sensor)
        assert "Provider" in repr(provider)
        assert "MockSensor" in repr(provider)


class TestProviderSwap:
    """Provider.swap() replaces the active implementation at runtime."""

    def test_swap_changes_implementation(self):
        cam1 = MockCamera(device_id=0, width=640, height=480)
        cam2 = MockCamera(device_id=1, width=1920, height=1080)
        provider = Provider(cam1)
        assert provider.width == 640

        old = provider.swap(cam2)
        assert old is cam1
        assert provider.width == 1920
        assert provider.implementation is cam2

    def test_swap_returns_old_implementation(self):
        sensor1 = MockSensor("a")
        sensor2 = MockSensor("b")
        provider = Provider(sensor1)
        old = provider.swap(sensor2)
        assert old is sensor1

    def test_swap_callback_called(self):
        calls = []

        def on_swap(old, new):
            calls.append((type(old).__name__, type(new).__name__))

        cam1 = MockCamera(device_id=0)
        cam2 = MockCamera(device_id=1)
        provider = Provider(cam1, on_swap=on_swap)
        provider.swap(cam2)

        assert len(calls) == 1
        assert calls[0] == ("MockCamera", "MockCamera")

    def test_swap_callback_receives_correct_instances(self):
        received = {}

        def on_swap(old, new):
            received["old"] = old
            received["new"] = new

        sensor1 = MockSensor("a")
        sensor2 = MockSensor("b")
        provider = Provider(sensor1, on_swap=on_swap)
        provider.swap(sensor2)

        assert received["old"] is sensor1
        assert received["new"] is sensor2

    def test_multiple_swaps(self):
        s1 = MockSensor("a")
        s2 = MockSensor("b")
        s3 = MockSensor("c")
        provider = Provider(s1)

        provider.swap(s2)
        assert provider.name == "b"

        provider.swap(s3)
        assert provider.name == "c"

    def test_swap_back_to_mock(self):
        """Simulate graceful degradation: real → mock fallback."""
        mock = MockCamera(device_id=0, width=640, height=480)
        real = MockCamera(device_id=1, width=1920, height=1080)  # stand-in for real camera

        provider = Provider(mock)
        assert provider.width == 640

        # "Real camera connected"
        provider.swap(real)
        assert provider.width == 1920

        # "Real camera disconnected — fall back to mock"
        provider.swap(mock)
        assert provider.width == 640

    def test_no_callback_when_none(self):
        """swap() works without a callback."""
        provider = Provider(MockSensor("a"))
        provider.swap(MockSensor("b"))
        assert provider.name == "b"


class TestProviderThreadSafety:
    """Provider is safe to use from multiple threads."""

    def test_concurrent_reads(self):
        sensor = MockSensor("imu", sensor_type="motion")
        provider = Provider(sensor)
        results = []
        errors = []

        def read_loop():
            try:
                for _ in range(50):
                    data = provider.read()
                    results.append(data)
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=read_loop) for _ in range(4)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(errors) == 0
        assert len(results) == 200

    def test_concurrent_swap_and_read(self):
        """Swap and read simultaneously without crashing."""
        mock1 = MockSensor("a", sensor_type="motion")
        mock2 = MockSensor("b", sensor_type="gps")
        provider = Provider(mock1)
        errors = []

        def swap_loop():
            try:
                for i in range(50):
                    if i % 2 == 0:
                        provider.swap(mock2)
                    else:
                        provider.swap(mock1)
            except Exception as e:
                errors.append(e)

        def read_loop():
            try:
                for _ in range(50):
                    provider.read()
            except Exception as e:
                errors.append(e)

        t1 = threading.Thread(target=swap_loop)
        t2 = threading.Thread(target=read_loop)
        t1.start()
        t2.start()
        t1.join()
        t2.join()

        assert len(errors) == 0


class TestProviderGracefulDegradation:
    """Demonstrate the graceful degradation pattern from ADR-0003 Amendment 4."""

    def test_camera_hotplug_scenario(self):
        """USB camera plugged in → swap to real; unplugged → fall back to mock."""
        swap_log = []

        def on_swap(old, new):
            swap_log.append(f"{type(old).__name__}→{type(new).__name__}")

        mock_cam = MockCamera(device_id=0, width=640, height=480)
        provider = Provider(mock_cam, on_swap=on_swap)

        # Initial state: mock camera
        frame = provider.capture()
        assert frame["width"] == 640

        # Event: USB camera connected
        real_cam = MockCamera(device_id=1, width=1920, height=1080)  # stand-in
        provider.swap(real_cam)
        frame = provider.capture()
        assert frame["width"] == 1920

        # Event: USB camera disconnected
        provider.swap(mock_cam)
        frame = provider.capture()
        assert frame["width"] == 640

        assert swap_log == ["MockCamera→MockCamera", "MockCamera→MockCamera"]

    def test_sensor_failover_scenario(self):
        """Real sensor fails → fall back to mock sensor transparently."""
        mock_sensor = MockSensor("imu", sensor_type="motion")
        provider = Provider(mock_sensor)

        # Component reads sensor — doesn't care if it's real or mock
        data = provider.read()
        assert "heading" in data
        assert "pitch" in data
        assert "roll" in data
