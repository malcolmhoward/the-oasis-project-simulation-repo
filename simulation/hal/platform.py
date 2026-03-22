"""
Platform layer interface contracts — external service abstractions.

These ABCs (Abstract Base Classes) define the API that both Python mock
implementations (Layer 2) and future service test harnesses must conform to.

Docstrings use language-neutral descriptions so alternative implementations
(e.g., C service stubs) can be derived from the same definitions.

- HomeAssistantInterface: Home Assistant REST API for smart home control,
  used by D.A.W.N.'s tool execution pipeline
- LLMInterface: LLM (Large Language Model) inference for natural language
  processing, used by D.A.W.N.'s intent pipeline
- MemoryInterface: RAG (Retrieval-Augmented Generation) memory store for
  fact storage and retrieval, used by D.A.W.N.'s context system
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, AsyncIterator, Dict, List, Optional


# ---------------------------------------------------------------------------
# Home Assistant
# ---------------------------------------------------------------------------


class HomeAssistantInterface(ABC):
    """Interface for a Home Assistant REST API server.

    Implementations must support entity state queries and service calls
    with bearer token authentication.
    """

    @abstractmethod
    def start(self) -> None:
        """Start the server."""
        ...

    @abstractmethod
    def stop(self) -> None:
        """Stop the server."""
        ...

    @abstractmethod
    def get_states(self) -> List[Dict[str, Any]]:
        """Return all entity states as an array of string-keyed maps.

        Each map contains at minimum: ``entity_id`` (string), ``state`` (string),
        ``attributes`` (string-keyed map), ``last_changed`` (string, ISO 8601).
        """
        ...

    @abstractmethod
    def get_state(self, entity_id: str) -> Optional[Dict[str, Any]]:
        """Return a single entity state as a string-keyed map, or null/None if not found.

        entity_id: string (e.g., "light.kitchen_lights").
        """
        ...

    @abstractmethod
    def call_service(self, domain: str, service: str,
                     data: Dict[str, Any]) -> None:
        """Call a service with the given data.

        domain: string (e.g., "light"), service: string (e.g., "turn_on"),
        data: string-keyed map of service parameters (e.g., {"entity_id": "light.kitchen_lights"}).
        """
        ...


# ---------------------------------------------------------------------------
# LLM (Large Language Model)
# ---------------------------------------------------------------------------


class LLMInterface(ABC):
    """Interface for an LLM (Large Language Model) inference service.

    Implementations must support both synchronous (full response) and
    streaming (delta-by-delta) response modes.
    """

    @abstractmethod
    def complete(self, prompt: str, **kwargs: Any) -> str:
        """Return a complete response string for the given prompt string."""
        ...

    @abstractmethod
    def stream(self, prompt: str, **kwargs: Any) -> Any:
        """Return an iterable of response delta strings for the given prompt string.

        Each delta is a string fragment; concatenating all deltas produces the
        full response.
        """
        ...

    @abstractmethod
    def tool_call(self, prompt: str, **kwargs: Any) -> Optional[Dict[str, Any]]:
        """Return a tool call as a string-keyed map if the prompt triggers one, else null/None.

        Tool call map format::

            {
                "tool": "<tool_name>",     (string)
                "args": {"arg": "value"}   (string-keyed map)
            }
        """
        ...


# ---------------------------------------------------------------------------
# Memory / RAG (Retrieval-Augmented Generation)
# ---------------------------------------------------------------------------


class MemoryInterface(ABC):
    """Interface for a fact store with keyword-based retrieval.

    Implementations must support storing facts with metadata and
    retrieving them by keyword search or semantic similarity.
    """

    @abstractmethod
    def store(self, text: str, metadata: Optional[Dict[str, Any]] = None) -> str:
        """Store a fact string with optional string-keyed metadata map.

        Returns a unique string identifier for the stored entry.
        """
        ...

    @abstractmethod
    def retrieve(self, query: str, top_k: int = 5) -> List[Dict[str, Any]]:
        """Retrieve the most relevant facts for a query string.

        top_k: integer maximum number of results.  Returns an array of
        string-keyed maps, each containing at minimum ``"text"`` (string)
        and ``"score"`` (float, 0.0 to 1.0).
        """
        ...

    @abstractmethod
    def delete(self, fact_id: str) -> bool:
        """Delete a fact by string identifier.  Returns boolean (true if found and deleted)."""
        ...

    @abstractmethod
    def count(self) -> int:
        """Return the total number of stored facts as an integer."""
        ...
