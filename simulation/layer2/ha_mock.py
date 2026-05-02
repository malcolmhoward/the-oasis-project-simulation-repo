"""
Home Assistant REST API mock — a lightweight Flask app that simulates the HA
API endpoints used by D.A.W.N.'s tool execution pipeline.

Supports:
  - ``GET  /api/states``                — list all entity states
  - ``GET  /api/states/{entity_id}``    — get a single entity state
  - ``POST /api/services/{domain}/{service}`` — call a service (toggle, turn_on, etc.)
  - Bearer token authentication (configurable; default ``mock-ha-token``)

Example::

    from simulation.layer2.ha_mock import HomeAssistantMock

    ha = HomeAssistantMock(port=8123)
    ha.start()          # starts Flask in a background thread
    # ... DAWN can now call http://localhost:8123/api/states ...
    ha.stop()

Or use as an async context manager::

    async with HomeAssistantMock(port=8123) as ha:
        # server running
        pass
"""

from __future__ import annotations

import copy
import threading
import time
from typing import Any

try:
    from flask import Flask, jsonify, request
except ImportError as exc:
    raise ImportError(
        "Layer 2 requires flask.  Install with:  "
        'pip install "oasis-simulation[layer2]"'
    ) from exc


# Default entities matching the meta-issue #30 spec
_DEFAULT_ENTITIES: list[dict[str, Any]] = [
    {
        "entity_id": "light.kitchen_lights",
        "state": "off",
        "attributes": {
            "friendly_name": "Kitchen Lights",
            "brightness": 0,
            "color_mode": "brightness",
            "supported_features": 1,
        },
        "last_changed": "",
        "last_updated": "",
    },
    {
        "entity_id": "light.bedroom_lights",
        "state": "off",
        "attributes": {
            "friendly_name": "Bedroom Lights",
            "brightness": 0,
            "color_mode": "brightness",
            "supported_features": 1,
        },
        "last_changed": "",
        "last_updated": "",
    },
    {
        "entity_id": "climate.living_room_thermostat",
        "state": "heat",
        "attributes": {
            "friendly_name": "Living Room Thermostat",
            "temperature": 21.0,
            "current_temperature": 19.5,
            "hvac_modes": ["off", "heat", "cool", "auto"],
            "min_temp": 7,
            "max_temp": 35,
        },
        "last_changed": "",
        "last_updated": "",
    },
]


from simulation.hal.platform import HomeAssistantInterface


class HomeAssistantMock(HomeAssistantInterface):
    """Simulated Home Assistant REST API server.

    Implements :class:`~simulation.hal.platform.HomeAssistantInterface`.

    Parameters
    ----------
    host : str
        Bind address (default ``"localhost"``).
    port : int
        Bind port (default ``8123``).
    token : str
        Expected bearer token (default ``"mock-ha-token"``).
    entities : list[dict] | None
        Initial entity states.  If ``None``, uses the default set
        (kitchen lights, bedroom lights, living room thermostat).
    """

    def __init__(
        self,
        host: str = "localhost",
        port: int = 8123,
        token: str = "mock-ha-token",
        entities: list[dict[str, Any]] | None = None,
    ) -> None:
        self.host = host
        self.port = port
        self.token = token
        self.entities: dict[str, dict[str, Any]] = {}
        self._service_log: list[dict[str, Any]] = []

        for entity in (entities or copy.deepcopy(_DEFAULT_ENTITIES)):
            eid = entity["entity_id"]
            entity.setdefault("last_changed", self._now())
            entity.setdefault("last_updated", self._now())
            self.entities[eid] = entity

        self._app = self._create_app()
        self._thread: threading.Thread | None = None
        self._server: Any = None

    @property
    def service_log(self) -> list[dict[str, Any]]:
        """List of service calls received (for test assertions)."""
        return list(self._service_log)

    # ------------------------------------------------------------------
    # HAL interface methods (direct access, no HTTP)
    # ------------------------------------------------------------------

    def get_states(self) -> list[dict[str, Any]]:
        """Return all entity states as a list of string-keyed maps."""
        return list(self.entities.values())

    def get_state(self, entity_id: str) -> dict[str, Any] | None:
        """Return a single entity state, or None if not found."""
        return self.entities.get(entity_id)

    def call_service(self, domain: str, service: str,
                     data: dict[str, Any]) -> None:
        """Call a service (e.g., light/turn_on) and update entity state."""
        entity_id = data.get("entity_id")
        self._service_log.append({
            "domain": domain,
            "service": service,
            "data": data,
            "timestamp": self._now(),
        })
        if entity_id and entity_id in self.entities:
            entity = self.entities[entity_id]
            now = self._now()
            if service == "turn_on":
                entity["state"] = "on"
                if "brightness" in data:
                    entity["attributes"]["brightness"] = data["brightness"]
                elif entity["attributes"].get("brightness") == 0:
                    entity["attributes"]["brightness"] = 255
                entity["last_changed"] = now
                entity["last_updated"] = now
            elif service == "turn_off":
                entity["state"] = "off"
                entity["attributes"]["brightness"] = 0
                entity["last_changed"] = now
                entity["last_updated"] = now
            elif service == "toggle":
                new_state = "off" if entity["state"] == "on" else "on"
                entity["state"] = new_state
                if new_state == "on" and entity["attributes"].get("brightness") == 0:
                    entity["attributes"]["brightness"] = 255
                elif new_state == "off":
                    entity["attributes"]["brightness"] = 0
                entity["last_changed"] = now
                entity["last_updated"] = now
            elif service == "set_temperature":
                if "temperature" in data:
                    entity["attributes"]["temperature"] = data["temperature"]
                entity["last_updated"] = now

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def start(self) -> None:
        """Start the mock HA server in a background thread."""
        from werkzeug.serving import make_server

        self._server = make_server(self.host, self.port, self._app)
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        """Stop the mock HA server."""
        if self._server is not None:
            self._server.shutdown()
            self._server = None
        if self._thread is not None:
            self._thread.join(timeout=5)
            self._thread = None

    async def __aenter__(self) -> HomeAssistantMock:
        self.start()
        return self

    async def __aexit__(self, *args: Any) -> None:
        self.stop()

    # ------------------------------------------------------------------
    # Flask app
    # ------------------------------------------------------------------

    def _create_app(self) -> Flask:
        app = Flask(__name__)
        app.config["TESTING"] = True

        @app.before_request
        def _check_auth() -> Any:
            auth = request.headers.get("Authorization", "")
            if auth != f"Bearer {self.token}":
                return jsonify({"message": "Unauthorized"}), 401

        @app.route("/api/states", methods=["GET"])
        def _route_get_states() -> Any:
            return jsonify(self.get_states())

        @app.route("/api/states/<entity_id>", methods=["GET"])
        def _route_get_state(entity_id: str) -> Any:
            entity = self.get_state(entity_id)
            if entity is None:
                return jsonify({"message": f"Entity not found: {entity_id}"}), 404
            return jsonify(entity)

        @app.route("/api/services/<domain>/<service>", methods=["POST"])
        def _route_call_service(domain: str, service: str) -> Any:
            data = request.get_json(silent=True) or {}
            self.call_service(domain, service, data)
            return jsonify([{"entity_id": data.get("entity_id", "unknown")}])

        return app

    @staticmethod
    def _now() -> str:
        return time.strftime("%Y-%m-%dT%H:%M:%S+00:00", time.gmtime())
