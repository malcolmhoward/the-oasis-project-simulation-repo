"""
LLM (Large Language Model) response mock — keyword-to-tool-call mapping with
streaming delta support.

No actual model weights are loaded.  Responses are determined by a configurable
keyword map: if the prompt contains a keyword, the corresponding response or
tool call is returned.  This enables deterministic testing of D.A.W.N.'s
intent-processing pipeline without GPU, API keys, or network access.

This works on the same principle as voice assistant "skills" (e.g., Amazon
Alexa Skills or Google Actions): you define recognized input patterns that
map to specific actions, and the mock matches user input against those
patterns deterministically.  See ``docs/guide.md`` for a detailed comparison.

Example::

    from simulation.layer2.llm_mock import LLMMock

    llm = LLMMock()
    llm.add_rule("lights", response="I'll turn on the lights for you.")
    llm.add_tool_rule("lights on", tool="homeassistant", args={"action": "turn_on", "entity_id": "light.kitchen_lights"})

    print(llm.complete("turn on the lights"))
    # "I'll turn on the lights for you."

    print(llm.tool_call("lights on please"))
    # {"tool": "homeassistant", "args": {"action": "turn_on", "entity_id": "light.kitchen_lights"}}
"""

from __future__ import annotations

from typing import Any, Dict, Iterator, List, Optional

from simulation.hal.platform import LLMInterface


class LLMMock(LLMInterface):
    """Keyword-driven LLM (Large Language Model) mock.

    Implements :class:`~simulation.hal.platform.LLMInterface`.

    Responses are matched by scanning the prompt for keywords.  Rules are
    evaluated in insertion order; the first match wins.  If no rule matches,
    the default response is returned.

    Parameters
    ----------
    default_response : str
        Response returned when no keyword rule matches.
    """

    def __init__(self, default_response: str = "I'm not sure how to help with that.") -> None:
        self.default_response = default_response
        self._response_rules: list[tuple[str, str]] = []
        self._tool_rules: list[tuple[str, dict[str, Any]]] = []

    def add_rule(self, keyword: str, response: str) -> None:
        """Add a keyword-to-response rule.

        keyword: string to search for in the prompt (case-insensitive).
        response: string to return when the keyword is found.
        """
        self._response_rules.append((keyword.lower(), response))

    def add_tool_rule(self, keyword: str, tool: str, args: Dict[str, Any] | None = None) -> None:
        """Add a keyword-to-tool-call rule.

        keyword: string to search for in the prompt (case-insensitive).
        tool: string tool name.
        args: string-keyed map of tool arguments.
        """
        self._tool_rules.append((keyword.lower(), {"tool": tool, "args": args or {}}))

    # ------------------------------------------------------------------
    # LLMInterface implementation
    # ------------------------------------------------------------------

    def complete(self, prompt: str, **kwargs: Any) -> str:
        """Return a complete response string for the given prompt string.

        Scans response rules in order; returns the first matching response,
        or the default response if no rule matches.
        """
        prompt_lower = prompt.lower()
        for keyword, response in self._response_rules:
            if keyword in prompt_lower:
                return response
        return self.default_response

    def stream(self, prompt: str, **kwargs: Any) -> Iterator[str]:
        """Return an iterator of response delta strings.

        Splits the complete response into word-level deltas to simulate
        token-by-token streaming.
        """
        full_response = self.complete(prompt, **kwargs)
        words = full_response.split(" ")
        for i, word in enumerate(words):
            yield word + (" " if i < len(words) - 1 else "")

    def tool_call(self, prompt: str, **kwargs: Any) -> Optional[Dict[str, Any]]:
        """Return a tool call map if the prompt triggers one, else None.

        Scans tool rules in order; returns the first match.  Tool rules are
        checked before response rules — if both match, the tool call takes
        precedence.
        """
        prompt_lower = prompt.lower()
        for keyword, call in self._tool_rules:
            if keyword in prompt_lower:
                return dict(call)
        return None
