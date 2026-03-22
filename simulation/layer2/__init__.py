"""
Layer 2: Software behavior simulators (requires flask; optional LLM/memory deps).

Install extras:
    pip install "oasis-simulation[layer2]"
or:
    pip install flask

Modules:
    ha_mock      — Home Assistant REST API mock (Flask server + direct API)
    llm_mock     — LLM (Large Language Model) keyword-to-response mock
    memory_mock  — RAG (Retrieval-Augmented Generation) SQLite-backed fact store
"""
