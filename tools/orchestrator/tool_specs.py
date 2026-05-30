"""Build OpenAI-format tool specs from the pipeline tool registry.

A stage exposes to its model only the subset of tools it is allowed to call
(KBE gets the PDF tools, CQV gets the inspection tools, ...). This module turns
the registry's ``{name: {"description", "args"}}`` shape into the ``tools=[...]``
JSON-schema list that the completion seam (``llm.py``) hands to the model.

The transformation is pure and registry-free (:func:`build_specs`), so it is
unit-testable without the registry's runtime dependencies; :func:`registry_specs`
is a thin wrapper that lazily reads the live registry.

Limitation (v1): the registry records only an argument's name and a one-line
description, not its type, so every argument is presented to the model as a
required string. That is correct for the path-string tools KBE and CQV use.
Tools with structured arguments (e.g. the ER tools' dependency lists) will need
explicit per-tool schemas before being exposed to a model.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence

from tools.orchestrator.llm import ToolSpec


def _spec_from_entry(name: str, description: str, args: Mapping[str, str]) -> ToolSpec:
    """Build one OpenAI function spec from a registry entry."""
    properties = {arg: {"type": "string", "description": desc} for arg, desc in args.items()}
    return {
        "type": "function",
        "function": {
            "name": name,
            "description": description,
            "parameters": {
                "type": "object",
                "properties": properties,
                "required": list(args.keys()),
            },
        },
    }


def build_specs(
    registry: Mapping[str, Mapping[str, object]],
    names: Sequence[str] | None = None,
) -> list[ToolSpec]:
    """Convert a ``list_tools()``-shaped mapping into OpenAI tool specs.

    ``registry`` maps tool name -> ``{"description": str, "args": {arg: desc}}``.
    ``names`` optionally restricts (and orders) the output to specific tools;
    an unknown name raises ``KeyError``.
    """
    selected = list(names) if names is not None else list(registry)
    specs: list[ToolSpec] = []
    for name in selected:
        try:
            entry = registry[name]
        except KeyError:
            raise KeyError(f"unknown tool {name!r}; available: {sorted(registry)}") from None
        description = str(entry.get("description", ""))
        args = entry.get("args", {})
        specs.append(_spec_from_entry(name, description, args))
    return specs


def registry_specs(names: Sequence[str] | None = None) -> list[ToolSpec]:
    """Tool specs for the live pipeline registry (lazily imported)."""
    from tools.tools import list_tools

    return build_specs(list_tools(), names)
