"""
HAL (Hardware Abstraction Layer) — interface contracts for the simulation framework.

Each module defines ABCs (Abstract Base Classes) that both Python mock
implementations and future C HAL headers must conform to.  The dependency
flows one way: implementation layers (layer0, layer1, layer2) import from
hal, never the reverse.

Language note:
    These interfaces are defined as Python ABCs, but the docstrings describe
    parameters and return values in language-neutral terms (e.g., "integer",
    "byte array", "string-keyed map") so that C HAL headers can be derived
    directly from the same descriptions in Phase 2.  No separate IDL
    (Interface Definition Language) or specification format is needed — the
    ABCs are the single source of truth.

Modules:
    device   — Sensor, GPIO, I2C, SPI, Camera, Audio interfaces (Layer 0)
    network  — MQTT, OCP, DAP2 interfaces (Layer 1)
    platform — Home Assistant, LLM, Memory interfaces (Layer 2)
"""
