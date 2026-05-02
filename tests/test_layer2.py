"""Tests for Layer 2 — platform simulation (Home Assistant, LLM, Memory/RAG)."""

from __future__ import annotations

import json
import time
import urllib.request

import pytest

# ---------------------------------------------------------------------------
# Home Assistant mock
# ---------------------------------------------------------------------------

from simulation.layer2.ha_mock import HomeAssistantMock


def _find_free_port() -> int:
    import socket
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("", 0))
        return s.getsockname()[1]


class TestHomeAssistantDirect:
    """Test HomeAssistantMock via direct HAL interface (no HTTP)."""

    def test_default_entities(self):
        ha = HomeAssistantMock()
        states = ha.get_states()
        assert len(states) == 3
        ids = {s["entity_id"] for s in states}
        assert "light.kitchen_lights" in ids
        assert "light.bedroom_lights" in ids
        assert "climate.living_room_thermostat" in ids

    def test_get_state_found(self):
        ha = HomeAssistantMock()
        state = ha.get_state("light.kitchen_lights")
        assert state is not None
        assert state["state"] == "off"
        assert state["attributes"]["friendly_name"] == "Kitchen Lights"

    def test_get_state_not_found(self):
        ha = HomeAssistantMock()
        assert ha.get_state("light.nonexistent") is None

    def test_turn_on(self):
        ha = HomeAssistantMock()
        ha.call_service("light", "turn_on", {"entity_id": "light.kitchen_lights"})
        state = ha.get_state("light.kitchen_lights")
        assert state["state"] == "on"
        assert state["attributes"]["brightness"] == 255

    def test_turn_on_with_brightness(self):
        ha = HomeAssistantMock()
        ha.call_service("light", "turn_on", {"entity_id": "light.kitchen_lights", "brightness": 128})
        state = ha.get_state("light.kitchen_lights")
        assert state["state"] == "on"
        assert state["attributes"]["brightness"] == 128

    def test_turn_off(self):
        ha = HomeAssistantMock()
        ha.call_service("light", "turn_on", {"entity_id": "light.kitchen_lights"})
        ha.call_service("light", "turn_off", {"entity_id": "light.kitchen_lights"})
        state = ha.get_state("light.kitchen_lights")
        assert state["state"] == "off"
        assert state["attributes"]["brightness"] == 0

    def test_toggle(self):
        ha = HomeAssistantMock()
        ha.call_service("light", "toggle", {"entity_id": "light.kitchen_lights"})
        assert ha.get_state("light.kitchen_lights")["state"] == "on"
        ha.call_service("light", "toggle", {"entity_id": "light.kitchen_lights"})
        assert ha.get_state("light.kitchen_lights")["state"] == "off"

    def test_set_temperature(self):
        ha = HomeAssistantMock()
        ha.call_service("climate", "set_temperature", {
            "entity_id": "climate.living_room_thermostat",
            "temperature": 24.0,
        })
        state = ha.get_state("climate.living_room_thermostat")
        assert state["attributes"]["temperature"] == 24.0

    def test_service_log(self):
        ha = HomeAssistantMock()
        ha.call_service("light", "turn_on", {"entity_id": "light.kitchen_lights"})
        ha.call_service("light", "turn_off", {"entity_id": "light.kitchen_lights"})
        assert len(ha.service_log) == 2
        assert ha.service_log[0]["service"] == "turn_on"
        assert ha.service_log[1]["service"] == "turn_off"

    def test_custom_entities(self):
        entities = [{"entity_id": "switch.fan", "state": "off", "attributes": {"friendly_name": "Fan"}}]
        ha = HomeAssistantMock(entities=entities)
        assert len(ha.get_states()) == 1
        assert ha.get_state("switch.fan")["attributes"]["friendly_name"] == "Fan"

    def test_unknown_entity_service_call(self):
        ha = HomeAssistantMock()
        ha.call_service("light", "turn_on", {"entity_id": "light.nonexistent"})
        assert len(ha.service_log) == 1  # logged but no state change


class TestHomeAssistantHTTP:
    """Test HomeAssistantMock via HTTP (Flask server)."""

    @pytest.fixture
    def ha_server(self):
        port = _find_free_port()
        ha = HomeAssistantMock(port=port)
        ha.start()
        time.sleep(0.1)  # allow server to start
        yield ha, port
        ha.stop()

    def _request(self, port, path, method="GET", data=None, token="mock-ha-token"):
        url = f"http://localhost:{port}{path}"
        body = json.dumps(data).encode() if data else None
        req = urllib.request.Request(url, data=body, method=method)
        req.add_header("Authorization", f"Bearer {token}")
        if data:
            req.add_header("Content-Type", "application/json")
        try:
            with urllib.request.urlopen(req) as resp:
                return json.loads(resp.read()), resp.status
        except urllib.error.HTTPError as e:
            return json.loads(e.read()), e.code

    def test_get_states(self, ha_server):
        _, port = ha_server
        data, status = self._request(port, "/api/states")
        assert status == 200
        assert len(data) == 3

    def test_get_single_state(self, ha_server):
        _, port = ha_server
        data, status = self._request(port, "/api/states/light.kitchen_lights")
        assert status == 200
        assert data["entity_id"] == "light.kitchen_lights"

    def test_404_on_missing_entity(self, ha_server):
        _, port = ha_server
        data, status = self._request(port, "/api/states/light.nonexistent")
        assert status == 404

    def test_service_call_via_http(self, ha_server):
        ha, port = ha_server
        data, status = self._request(port, "/api/services/light/turn_on",
                                     method="POST",
                                     data={"entity_id": "light.kitchen_lights"})
        assert status == 200
        assert ha.get_state("light.kitchen_lights")["state"] == "on"

    def test_unauthorized(self, ha_server):
        _, port = ha_server
        data, status = self._request(port, "/api/states", token="wrong-token")
        assert status == 401


# ---------------------------------------------------------------------------
# LLM mock
# ---------------------------------------------------------------------------

from simulation.layer2.llm_mock import LLMMock


class TestLLMMock:
    """Test LLMMock keyword-to-response and tool-call mapping."""

    def test_default_response(self):
        llm = LLMMock()
        assert "not sure" in llm.complete("random gibberish")

    def test_custom_default(self):
        llm = LLMMock(default_response="Unknown command.")
        assert llm.complete("anything") == "Unknown command."

    def test_add_rule_match(self):
        llm = LLMMock()
        llm.add_rule("weather", "It's sunny and 72 degrees.")
        assert llm.complete("what's the weather?") == "It's sunny and 72 degrees."

    def test_rule_case_insensitive(self):
        llm = LLMMock()
        llm.add_rule("HELLO", "Hi there!")
        assert llm.complete("hello world") == "Hi there!"

    def test_first_rule_wins(self):
        llm = LLMMock()
        llm.add_rule("lights", "First rule.")
        llm.add_rule("lights", "Second rule.")
        assert llm.complete("turn on the lights") == "First rule."

    def test_no_match_returns_default(self):
        llm = LLMMock()
        llm.add_rule("weather", "Sunny.")
        assert "not sure" in llm.complete("tell me a joke")

    def test_stream_produces_deltas(self):
        llm = LLMMock()
        llm.add_rule("test", "Hello world from LLM.")
        deltas = list(llm.stream("test prompt"))
        assert len(deltas) > 1
        assert "".join(deltas) == "Hello world from LLM."

    def test_tool_call_match(self):
        llm = LLMMock()
        llm.add_tool_rule("turn on", tool="homeassistant", args={"action": "turn_on"})
        result = llm.tool_call("turn on the lights")
        assert result is not None
        assert result["tool"] == "homeassistant"
        assert result["args"]["action"] == "turn_on"

    def test_tool_call_no_match(self):
        llm = LLMMock()
        llm.add_tool_rule("turn on", tool="homeassistant", args={})
        assert llm.tool_call("what's the weather?") is None

    def test_tool_call_returns_copy(self):
        llm = LLMMock()
        llm.add_tool_rule("test", tool="t", args={"k": "v"})
        r1 = llm.tool_call("test")
        r2 = llm.tool_call("test")
        assert r1 is not r2  # independent copies

    def test_multiple_tool_rules(self):
        llm = LLMMock()
        llm.add_tool_rule("lights on", tool="ha", args={"action": "turn_on"})
        llm.add_tool_rule("lights off", tool="ha", args={"action": "turn_off"})
        on = llm.tool_call("lights on please")
        off = llm.tool_call("lights off please")
        assert on["args"]["action"] == "turn_on"
        assert off["args"]["action"] == "turn_off"


# ---------------------------------------------------------------------------
# Memory / RAG mock
# ---------------------------------------------------------------------------

from simulation.layer2.memory_mock import MemoryMock


class TestMemoryMock:
    """Test MemoryMock SQLite-backed fact store."""

    def test_store_and_count(self):
        mem = MemoryMock()
        assert mem.count() == 0
        mem.store("The sky is blue.")
        assert mem.count() == 1

    def test_store_returns_id(self):
        mem = MemoryMock()
        fact_id = mem.store("Fact one.")
        assert isinstance(fact_id, str)
        assert len(fact_id) == 36  # UUID4

    def test_retrieve_by_keyword(self):
        mem = MemoryMock()
        mem.store("The kitchen lights are Philips Hue bulbs.")
        mem.store("The bedroom has blackout curtains.")
        results = mem.retrieve("kitchen lights")
        assert len(results) >= 1
        assert "kitchen" in results[0]["text"].lower()
        assert results[0]["score"] > 0

    def test_retrieve_returns_score(self):
        mem = MemoryMock()
        mem.store("The kitchen lights are smart bulbs.")
        results = mem.retrieve("kitchen lights")
        assert "score" in results[0]
        assert 0 < results[0]["score"] <= 1.0

    def test_retrieve_top_k(self):
        mem = MemoryMock()
        for i in range(10):
            mem.store(f"Fact number {i} about lights.")
        results = mem.retrieve("lights", top_k=3)
        assert len(results) == 3

    def test_retrieve_no_match(self):
        mem = MemoryMock()
        mem.store("The sky is blue.")
        results = mem.retrieve("quantum physics")
        assert len(results) == 0

    def test_retrieve_empty_query(self):
        mem = MemoryMock()
        mem.store("Something.")
        assert mem.retrieve("") == []

    def test_delete(self):
        mem = MemoryMock()
        fact_id = mem.store("Temporary fact.")
        assert mem.count() == 1
        assert mem.delete(fact_id) is True
        assert mem.count() == 0

    def test_delete_nonexistent(self):
        mem = MemoryMock()
        assert mem.delete("nonexistent-id") is False

    def test_metadata_stored_and_retrieved(self):
        mem = MemoryMock()
        mem.store("Kitchen has smart lights.", metadata={"room": "kitchen", "type": "lights"})
        results = mem.retrieve("kitchen lights")
        assert "metadata" in results[0]
        assert results[0]["metadata"]["room"] == "kitchen"

    def test_multiple_stores_independent(self):
        mem = MemoryMock()
        id1 = mem.store("Fact one.")
        id2 = mem.store("Fact two.")
        assert id1 != id2
        assert mem.count() == 2
