"""Python orchestration layer for the AI4Reproducibility pipeline.

This package is the in-progress, provider-agnostic replacement for the Kilo
Code slash-command workflow (see LOGIC.md §7): a driver that calls LLMs via
LiteLLM with per-stage system prompts and per-stage models.

Importing this package does NOT require LiteLLM (or any agent runtime
dependency such as PyMuPDF). The LiteLLM backend and the tool registry are
imported lazily, only when a real run actually needs them. This keeps the
agent loop unit-testable with an injected fake backend, and lets CI exercise
the orchestration logic without provider credentials or heavy dependencies.
"""
