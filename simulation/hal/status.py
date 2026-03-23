"""
SimulationStatus — centralized tracker for which interfaces are running on
simulated vs. real implementations.

Emits events when status changes occur (Provider swaps, startup, shutdown),
enabling multiple notification channels to react:

- Structured logging (always on)
- MQTT broadcast to ``echo/status`` topic
- TTS announcements via D.A.W.N. (``dawn`` MQTT topic)
- Audio alerts via M.I.R.A.G.E. (``hud`` MQTT topic)
- WebUI notifications (via WebSocket or HTTP endpoint)
- HUD visual indicators (consume ``echo/status`` messages)

The tracker is decoupled from notification delivery — it publishes events
through registered listeners. Components register the channels they support.

Language-neutral design note:
    The tracker maintains a string-keyed map of interface names to status
    records. Each record contains: interface name (string), implementation
    type name (string), is_simulated (boolean), and timestamp (float,
    seconds since epoch). A C equivalent would be a struct array with a
    callback function pointer for change notifications.

Example::

    from simulation.hal.status import SimulationStatus, StatusEvent
    from simulation.hal.provider import Provider
    from simulation.layer0.camera import MockCamera

    tracker = SimulationStatus()

    # Register a listener (any callable that accepts a StatusEvent)
    tracker.add_listener(lambda event: print(f"{event.interface}: {event.message}"))

    # Wire a Provider to the tracker
    camera = Provider(
        MockCamera(),
        on_swap=tracker.create_swap_handler("camera"),
    )

    # Swap triggers the listener
    camera.swap(MockCamera(device_id=1))
    # prints: camera: Swapped from MockCamera to MockCamera
"""

from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)


class StatusChange(Enum):
    """Type of simulation status change."""
    REGISTERED = "registered"
    SWAPPED = "swapped"
    UNREGISTERED = "unregistered"


@dataclass
class StatusRecord:
    """Current status of a single interface."""
    interface: str
    implementation: str
    is_simulated: bool
    timestamp: float = field(default_factory=time.time)


@dataclass
class StatusEvent:
    """Event emitted when simulation status changes."""
    change: StatusChange
    interface: str
    implementation: str
    previous_implementation: Optional[str]
    is_simulated: bool
    was_simulated: Optional[bool]
    timestamp: float = field(default_factory=time.time)

    @property
    def message(self) -> str:
        """Human-readable description of the change."""
        if self.change == StatusChange.REGISTERED:
            mode = "simulated" if self.is_simulated else "live"
            return f"{self.interface} registered as {mode} ({self.implementation})"
        elif self.change == StatusChange.SWAPPED:
            old_mode = "simulated" if self.was_simulated else "live"
            new_mode = "simulated" if self.is_simulated else "live"
            if old_mode != new_mode:
                return (f"{self.interface} switched from {old_mode} to {new_mode} "
                        f"({self.previous_implementation} to {self.implementation})")
            return (f"{self.interface} swapped implementation "
                    f"({self.previous_implementation} to {self.implementation})")
        elif self.change == StatusChange.UNREGISTERED:
            return f"{self.interface} unregistered"
        return f"{self.interface}: {self.change.value}"

    def to_dict(self) -> Dict[str, Any]:
        """Serialize to a string-keyed map for MQTT/JSON publishing."""
        return {
            "change": self.change.value,
            "interface": self.interface,
            "implementation": self.implementation,
            "previous_implementation": self.previous_implementation,
            "is_simulated": self.is_simulated,
            "was_simulated": self.was_simulated,
            "timestamp": self.timestamp,
            "message": self.message,
        }


# Type alias for event listeners
StatusListener = Callable[[StatusEvent], None]


def is_mock_implementation(impl: Any) -> bool:
    """Heuristic to determine if an implementation is a mock.

    Returns true if the class name starts with "Mock" or the module path
    contains "simulation.layer". Override by setting a ``_is_simulated``
    attribute on the implementation.
    """
    if hasattr(impl, "_is_simulated"):
        return bool(impl._is_simulated)
    name = type(impl).__name__
    module = type(impl).__module__ or ""
    return name.startswith("Mock") or "simulation.layer" in module


class SimulationStatus:
    """Centralized tracker for simulation vs. real implementation status.

    Thread-safe. Maintains a registry of interface names and their current
    status. Emits events to registered listeners on every status change.

    Parameters
    ----------
    name : str
        Identifier for this tracker instance (e.g., component name).
    """

    def __init__(self, name: str = "default") -> None:
        self.name = name
        self._interfaces: Dict[str, StatusRecord] = {}
        self._listeners: List[StatusListener] = []
        self._lock = threading.RLock()

        # Always log events
        self.add_listener(self._log_listener)

    # ------------------------------------------------------------------
    # Interface registration
    # ------------------------------------------------------------------

    def register(self, interface: str, implementation: Any) -> None:
        """Register an interface with its current implementation.

        Emits a REGISTERED event to all listeners.
        """
        simulated = is_mock_implementation(implementation)
        record = StatusRecord(
            interface=interface,
            implementation=type(implementation).__name__,
            is_simulated=simulated,
        )
        event = StatusEvent(
            change=StatusChange.REGISTERED,
            interface=interface,
            implementation=record.implementation,
            previous_implementation=None,
            is_simulated=simulated,
            was_simulated=None,
        )
        with self._lock:
            self._interfaces[interface] = record
            self._emit(event)

    def unregister(self, interface: str) -> None:
        """Remove an interface from the tracker.

        Emits an UNREGISTERED event if the interface was tracked.
        """
        with self._lock:
            record = self._interfaces.pop(interface, None)
            if record:
                self._emit(StatusEvent(
                    change=StatusChange.UNREGISTERED,
                    interface=interface,
                    implementation=record.implementation,
                    previous_implementation=None,
                    is_simulated=record.is_simulated,
                    was_simulated=None,
                ))

    # ------------------------------------------------------------------
    # Provider integration
    # ------------------------------------------------------------------

    def create_swap_handler(self, interface: str) -> Callable:
        """Create an ``on_swap`` callback for a Provider.

        Returns a callable suitable for ``Provider(impl, on_swap=handler)``.
        The handler updates the tracker and emits a SWAPPED event.

        Parameters
        ----------
        interface : str
            The interface name to track (e.g., "camera", "sensor.imu").
        """
        def handler(old_impl: Any, new_impl: Any) -> None:
            old_simulated = is_mock_implementation(old_impl)
            new_simulated = is_mock_implementation(new_impl)
            record = StatusRecord(
                interface=interface,
                implementation=type(new_impl).__name__,
                is_simulated=new_simulated,
            )
            event = StatusEvent(
                change=StatusChange.SWAPPED,
                interface=interface,
                implementation=type(new_impl).__name__,
                previous_implementation=type(old_impl).__name__,
                is_simulated=new_simulated,
                was_simulated=old_simulated,
            )
            with self._lock:
                self._interfaces[interface] = record
                self._emit(event)

        return handler

    # ------------------------------------------------------------------
    # Status queries
    # ------------------------------------------------------------------

    def get_status(self, interface: str) -> Optional[StatusRecord]:
        """Get the current status of a single interface."""
        with self._lock:
            return self._interfaces.get(interface)

    def get_all(self) -> Dict[str, StatusRecord]:
        """Get all tracked interfaces and their status."""
        with self._lock:
            return dict(self._interfaces)

    def is_any_simulated(self) -> bool:
        """True if any tracked interface is running on a simulated implementation."""
        with self._lock:
            return any(r.is_simulated for r in self._interfaces.values())

    def is_all_simulated(self) -> bool:
        """True if all tracked interfaces are running on simulated implementations."""
        with self._lock:
            return bool(self._interfaces) and all(
                r.is_simulated for r in self._interfaces.values()
            )

    def summary(self) -> Dict[str, Any]:
        """Return a summary map suitable for JSON serialization or display.

        Returns a string-keyed map with: tracker name (string), total
        interfaces (integer), simulated count (integer), live count
        (integer), and per-interface details.
        """
        with self._lock:
            records = dict(self._interfaces)
        simulated = sum(1 for r in records.values() if r.is_simulated)
        return {
            "tracker": self.name,
            "total": len(records),
            "simulated": simulated,
            "live": len(records) - simulated,
            "interfaces": {
                name: {
                    "implementation": r.implementation,
                    "is_simulated": r.is_simulated,
                    "timestamp": r.timestamp,
                }
                for name, r in records.items()
            },
        }

    # ------------------------------------------------------------------
    # Listeners
    # ------------------------------------------------------------------

    def add_listener(self, listener: StatusListener) -> None:
        """Register a listener that receives StatusEvent objects."""
        with self._lock:
            self._listeners.append(listener)

    def remove_listener(self, listener: StatusListener) -> None:
        """Remove a previously registered listener."""
        with self._lock:
            self._listeners = [l for l in self._listeners if l is not listener]

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _emit(self, event: StatusEvent) -> None:
        """Emit an event to all registered listeners. Called under lock."""
        for listener in self._listeners:
            try:
                listener(event)
            except Exception:
                logger.exception("SimulationStatus listener error for event: %s", event.message)

    @staticmethod
    def _log_listener(event: StatusEvent) -> None:
        """Default listener that logs all events."""
        if event.change == StatusChange.SWAPPED:
            if event.was_simulated != event.is_simulated:
                logger.warning("SIMULATION STATUS: %s", event.message)
            else:
                logger.info("SIMULATION STATUS: %s", event.message)
        else:
            logger.info("SIMULATION STATUS: %s", event.message)
