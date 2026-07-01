"""Offline benchmark harness (not part of the served app).

Runs representative topics through the provider waterfall's candidates
(Gemini-free vs. Ollama-local on the 3060-laptop baseline) and records cost,
wall-clock time, note quality, formula accuracy, and sustained throughput. The
output decides the default bulk provider (docs/architecture.md). Re-run when models
change.
"""
