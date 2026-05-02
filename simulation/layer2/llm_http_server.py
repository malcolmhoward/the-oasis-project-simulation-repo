"""
OpenAI-compatible HTTP server wrapper for LLMMock.

Exposes the LLMMock as an HTTP endpoint that speaks the OpenAI
``/v1/chat/completions`` API format.  D.A.W.N.'s local LLM provider
auto-detects this as a "generic OpenAI-compatible" endpoint, so no
D.A.W.N. code changes are needed — just point ``[llm.local] endpoint``
at the mock server's URL.

Also supports ``/v1/models`` for model listing and tool calling
(function calling) responses.

Example::

    from simulation.layer2.llm_mock import LLMMock
    from simulation.layer2.llm_http_server import LLMHTTPServer

    llm = LLMMock()
    llm.add_rule("weather", "It's sunny and 72 degrees.")
    llm.add_tool_rule("turn on", tool="homeassistant",
        args={"action": "turn_on", "entity_id": "light.kitchen_lights"})

    server = LLMHTTPServer(llm, port=8080)
    server.start()
    # D.A.W.N. connects to http://localhost:8080/v1/chat/completions
    server.stop()
"""

from __future__ import annotations

import json
import threading
import time
import uuid
from typing import Any

try:
    from flask import Flask, jsonify, request, Response
except ImportError as exc:
    raise ImportError(
        "Layer 2 requires flask.  Install with:  "
        'pip install "oasis-simulation[layer2]"'
    ) from exc

from simulation.layer2.llm_mock import LLMMock


class LLMHTTPServer:
    """OpenAI-compatible HTTP server backed by an LLMMock instance.

    Parameters
    ----------
    llm : LLMMock
        The mock LLM instance that handles prompt → response mapping.
    host : str
        Bind address (default ``"0.0.0.0"``).
    port : int
        Bind port (default ``8080``).
    model_name : str
        Model name returned in API responses (default ``"echo-mock"``).
    """

    def __init__(
        self,
        llm: LLMMock,
        host: str = "0.0.0.0",
        port: int = 8080,
        model_name: str = "echo-mock",
    ) -> None:
        self.llm = llm
        self.host = host
        self.port = port
        self.model_name = model_name
        self._app = self._create_app()
        self._thread: threading.Thread | None = None
        self._server: Any = None

    def start(self) -> None:
        """Start the mock LLM server in a background thread."""
        from werkzeug.serving import make_server

        self._server = make_server(self.host, self.port, self._app)
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        """Stop the mock LLM server."""
        if self._server is not None:
            self._server.shutdown()
            self._server = None
        if self._thread is not None:
            self._thread.join(timeout=5)
            self._thread = None

    def _create_app(self) -> Flask:
        app = Flask(__name__)
        app.config["TESTING"] = True

        @app.route("/v1/chat/completions", methods=["POST"])
        def chat_completions() -> Any:
            data = request.get_json(silent=True) or {}
            messages = data.get("messages", [])
            stream = data.get("stream", False)

            # Extract the last user message as the prompt
            prompt = ""
            for msg in reversed(messages):
                if msg.get("role") == "user":
                    content = msg.get("content", "")
                    if isinstance(content, list):
                        # Multi-modal: extract text parts
                        prompt = " ".join(
                            p.get("text", "") for p in content
                            if isinstance(p, dict) and p.get("type") == "text"
                        )
                    else:
                        prompt = content
                    break

            # Check for tool call first
            tool_result = self.llm.tool_call(prompt)
            if tool_result is not None:
                return self._tool_call_response(tool_result, data)

            # Regular text response
            response_text = self.llm.complete(prompt)

            if stream:
                return self._streaming_response(response_text, data)
            else:
                return self._complete_response(response_text, data)

        @app.route("/v1/models", methods=["GET"])
        def list_models() -> Any:
            return jsonify({
                "object": "list",
                "data": [{
                    "id": self.model_name,
                    "object": "model",
                    "created": int(time.time()),
                    "owned_by": "echo-simulation",
                }],
            })

        return app

    def _complete_response(self, text: str, req_data: dict) -> Any:
        return jsonify({
            "id": f"chatcmpl-{uuid.uuid4().hex[:12]}",
            "object": "chat.completion",
            "created": int(time.time()),
            "model": req_data.get("model", self.model_name),
            "choices": [{
                "index": 0,
                "message": {
                    "role": "assistant",
                    "content": text,
                },
                "finish_reason": "stop",
            }],
            "usage": {
                "prompt_tokens": 10,
                "completion_tokens": len(text.split()),
                "total_tokens": 10 + len(text.split()),
            },
        })

    def _tool_call_response(self, tool_result: dict, req_data: dict) -> Any:
        return jsonify({
            "id": f"chatcmpl-{uuid.uuid4().hex[:12]}",
            "object": "chat.completion",
            "created": int(time.time()),
            "model": req_data.get("model", self.model_name),
            "choices": [{
                "index": 0,
                "message": {
                    "role": "assistant",
                    "content": None,
                    "tool_calls": [{
                        "id": f"call_{uuid.uuid4().hex[:8]}",
                        "type": "function",
                        "function": {
                            "name": tool_result["tool"],
                            "arguments": json.dumps(tool_result.get("args", {})),
                        },
                    }],
                },
                "finish_reason": "tool_calls",
            }],
            "usage": {
                "prompt_tokens": 10,
                "completion_tokens": 5,
                "total_tokens": 15,
            },
        })

    def _streaming_response(self, text: str, req_data: dict) -> Response:
        model = req_data.get("model", self.model_name)
        chat_id = f"chatcmpl-{uuid.uuid4().hex[:12]}"

        def generate():
            # Send chunks word by word
            words = text.split(" ")
            for i, word in enumerate(words):
                delta = word + (" " if i < len(words) - 1 else "")
                chunk = {
                    "id": chat_id,
                    "object": "chat.completion.chunk",
                    "created": int(time.time()),
                    "model": model,
                    "choices": [{
                        "index": 0,
                        "delta": {"content": delta},
                        "finish_reason": None,
                    }],
                }
                yield f"data: {json.dumps(chunk)}\n\n"

            # Send final chunk
            final = {
                "id": chat_id,
                "object": "chat.completion.chunk",
                "created": int(time.time()),
                "model": model,
                "choices": [{
                    "index": 0,
                    "delta": {},
                    "finish_reason": "stop",
                }],
            }
            yield f"data: {json.dumps(final)}\n\n"
            yield "data: [DONE]\n\n"

        return Response(
            generate(),
            mimetype="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )
