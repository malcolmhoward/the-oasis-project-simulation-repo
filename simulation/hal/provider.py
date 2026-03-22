"""
Provider — manages the active implementation behind a HAL interface and
supports runtime hot-swap between mock and real backends.

The Provider sits above the HAL interfaces. It holds a reference to the
currently active implementation, forwards all attribute access to it, and
supports swapping the backend at runtime without restarting the component.

This enables the three injection modes described in ADR-0003 Amendment 4:

1. **Default injection** — Provider wraps a mock at creation time.
2. **Explicit injection** — Caller passes a specific implementation at creation.
3. **Runtime injection** — Caller calls ``swap()`` after creation to change
   the active backend (e.g., USB camera plugged in → swap MockCamera for
   real camera driver).

The Provider emits optional callbacks on swap events, enabling components
to react to backend changes (e.g., update a status display, log the
transition, notify other components via OCP).

Language-neutral design note:
    The Provider is a thin wrapper with no protocol-specific logic. In Python
    it uses ``__getattr__`` delegation. A C equivalent would be a struct
    holding a function pointer table (the HAL interface) plus a swap function
    that replaces the table pointer.

Example::

    from simulation.hal.provider import Provider
    from simulation.hal.device import CameraInterface
    from simulation.layer0.camera import MockCamera

    # Start with mock
    camera_provider = Provider(MockCamera(device_id=0))

    # Use it — all CameraInterface methods are forwarded
    frame = camera_provider.capture()

    # Later: real camera becomes available
    real_camera = RealCamera(device_id=0)
    camera_provider.swap(real_camera)

    # Subsequent calls go to the real camera
    frame = camera_provider.capture()

    # Camera disconnected — fall back to mock
    camera_provider.swap(MockCamera(device_id=0))

Example with swap callback::

    def on_swap(old_impl, new_impl):
        print(f"Backend changed: {type(old_impl).__name__} → {type(new_impl).__name__}")

    provider = Provider(MockCamera(), on_swap=on_swap)
    provider.swap(RealCamera())
    # prints: Backend changed: MockCamera → RealCamera
"""

from __future__ import annotations

import threading
from typing import Any, Callable, Generic, Optional, TypeVar

T = TypeVar("T")


class Provider(Generic[T]):
    """Runtime-swappable wrapper for any HAL interface implementation.

    Parameters
    ----------
    initial : T
        The initial implementation (typically a mock).
    on_swap : callable, optional
        Callback invoked as ``on_swap(old_implementation, new_implementation)``
        whenever the backend is swapped. Called under the provider's lock,
        so it should be fast and non-blocking.
    """

    def __init__(
        self,
        initial: T,
        on_swap: Optional[Callable[[T, T], None]] = None,
    ) -> None:
        self._impl: T = initial
        self._on_swap = on_swap
        self._lock = threading.RLock()

    @property
    def implementation(self) -> T:
        """The currently active implementation."""
        with self._lock:
            return self._impl

    @property
    def implementation_type(self) -> type:
        """The type of the currently active implementation."""
        with self._lock:
            return type(self._impl)

    def swap(self, new_impl: T) -> T:
        """Replace the active implementation. Returns the old implementation.

        Thread-safe. If an ``on_swap`` callback was provided at creation,
        it is called with (old_implementation, new_implementation) under
        the lock.

        Parameters
        ----------
        new_impl : T
            The new implementation to activate.

        Returns
        -------
        T
            The previous implementation (caller may want to clean it up).
        """
        with self._lock:
            old = self._impl
            self._impl = new_impl
            if self._on_swap is not None:
                self._on_swap(old, new_impl)
            return old

    def __getattr__(self, name: str) -> Any:
        """Forward attribute access to the active implementation.

        This allows the Provider to be used as a drop-in replacement for
        the underlying interface — callers call ``provider.read()`` instead
        of ``provider.implementation.read()``.
        """
        # Avoid infinite recursion for attributes used during __init__
        if name.startswith("_"):
            raise AttributeError(name)
        with self._lock:
            return getattr(self._impl, name)

    def __repr__(self) -> str:
        with self._lock:
            return f"Provider({self._impl!r})"
