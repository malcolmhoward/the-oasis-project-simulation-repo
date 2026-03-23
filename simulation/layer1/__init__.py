"""
Layer 1: Protocol simulators (requires paho-mqtt, websockets).

Install extras:
    pip install "oasis-simulation[layer1]"
or:
    pip install paho-mqtt websockets

Modules:
    mqtt         — MQTT topic builders and OCP message serializers
    ocp          — OCP peer simulation (E3/E4 embodiment, status, keepalive)
    dap2_client  — DAP2 satellite mock client and standalone mock daemon
"""
