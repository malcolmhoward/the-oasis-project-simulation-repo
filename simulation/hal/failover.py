"""
FailoverProvider — a Provider that picks its implementation from a ranked list and fails over on its own.

Provider (provider.py) swaps when a caller says so. FailoverProvider adds the policy for when the caller has
several candidate implementations of one interface, ranked by preference, and wants the best one that is
currently working: real hardware first, then another real source, then a simulation.

Each tick, the caller gives it the value every candidate produced (null when a candidate produced nothing).
FailoverProvider returns the active candidate's value. After ``fail_after`` consecutive ticks without a value
from the active candidate, it swaps to the best-ranked candidate that did produce one. It never swaps back on its
own, so a flaky source cannot make it flap; call ``swap()`` to return deliberately.

Two FailoverProviders can be made mutually exclusive with ``exclude``: the second never activates the first's
current implementation. That gives two independent sources for one quantity, for cross-checking.

Swaps go through Provider.swap(), so ``on_swap(old, new)`` works as usual, including
``SimulationStatus.create_swap_handler()``. The reason for the most recent automatic swap is kept in
``last_swap_reason``.

Example::

    from simulation.hal.failover import FailoverProvider

    temp = FailoverProvider([os_source, vendor_source, mock_source], on_swap=status.create_swap_handler("gpu.temp"))
    readings = {c: c.read().get("temp_c") for c in (os_source, vendor_source, mock_source)}
    value = temp.observe(readings)
"""

from __future__ import annotations

from typing import Any, Callable, Hashable, List, Mapping, Optional

from simulation.hal.provider import Provider


class FailoverProvider(Provider):
    """Provider over ranked candidates with automatic failover.

    Parameters
    ----------
    candidates : list
        Implementations in preference order.  May be empty (then ``implementation`` is None).
    on_swap : callable, optional
        ``on_swap(old, new)``, as for Provider.
    fail_after : int
        Consecutive ticks without a value before failing over.  Default 3.
    exclude : FailoverProvider, optional
        Another provider whose current implementation this one must never activate.
    name : str, optional
        Label for this provider (for logs and status), e.g. ``"gpu.temp"``.
    """

    def __init__(
        self,
        candidates: List[Any],
        on_swap: Optional[Callable[[Any, Any], None]] = None,
        fail_after: int = 3,
        exclude: Optional["FailoverProvider"] = None,
        name: str = "",
    ) -> None:
        self._candidates = list(candidates)
        self._exclude = exclude
        self._fail_after = fail_after
        self._misses = 0
        self.name = name
        self.last_swap_reason: Optional[str] = None
        eligible = self._eligible()
        super().__init__(eligible[0] if eligible else None, on_swap=on_swap)

    @property
    def candidates(self) -> List[Any]:
        return list(self._candidates)

    def _eligible(self) -> List[Any]:
        banned = self._exclude.implementation if self._exclude is not None else None
        return [c for c in self._candidates if c is not banned]

    def observe(self, values: Mapping[Hashable, Any]) -> Any:
        """Return the active candidate's value for this tick, failing over if it has missed ``fail_after`` ticks.

        ``values`` maps candidates to the value each produced this tick; a missing key or null means none.
        """
        active = self.implementation
        if active is None:
            return None
        value = values.get(active)
        if value is not None:
            self._misses = 0
            return value
        self._misses += 1
        if self._misses >= self._fail_after:
            for c in self._eligible():
                if c is not active and values.get(c) is not None:
                    self.last_swap_reason = f"no value from {self.label(active)} for {self._misses} ticks"
                    self._misses = 0
                    self.swap(c)
                    return values[c]
        return None

    @staticmethod
    def label(impl: Any) -> str:
        """A short name for an implementation: its ``provider`` attribute if it has one, else its class name."""
        return getattr(impl, "provider", "") or type(impl).__name__
