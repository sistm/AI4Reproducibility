"""Tests for OpenAI tool-spec generation (tools/orchestrator/tool_specs.py).

The pure transform is tested against a hand-made registry, so it needs none of
the registry's runtime dependencies. A final test exercises the live registry;
it guards the import defensively so it skips (rather than errors) if the
registry can't be imported in some environment, but in practice the registry
imports without heavy dependencies, so it runs in CI too.
"""

from __future__ import annotations

import pytest

from tools.orchestrator.tool_specs import build_specs

FAKE_REGISTRY = {
    "list_files": {
        "description": "List all files in a directory recursively.",
        "args": {"directory": "Directory to explore"},
    },
    "read_file": {
        "description": "Read a file and return its content.",
        "args": {"filepath": "Path to the file"},
    },
    "list_static_checks": {
        "description": "List all CQV static checks and their implementation status.",
        "args": {},
    },
}


def test_build_all_returns_one_spec_per_tool():
    specs = build_specs(FAKE_REGISTRY)
    assert [s["function"]["name"] for s in specs] == list(FAKE_REGISTRY)


def test_spec_shape_is_openai_function_format():
    spec = build_specs(FAKE_REGISTRY, ["list_files"])[0]
    assert spec["type"] == "function"
    fn = spec["function"]
    assert fn["name"] == "list_files"
    assert fn["description"] == "List all files in a directory recursively."
    params = fn["parameters"]
    assert params["type"] == "object"
    assert params["properties"] == {
        "directory": {"type": "string", "description": "Directory to explore"}
    }
    assert params["required"] == ["directory"]


def test_names_filters_and_orders():
    specs = build_specs(FAKE_REGISTRY, ["read_file", "list_files"])
    assert [s["function"]["name"] for s in specs] == ["read_file", "list_files"]


def test_empty_args_gives_empty_object_schema():
    spec = build_specs(FAKE_REGISTRY, ["list_static_checks"])[0]
    params = spec["function"]["parameters"]
    assert params["properties"] == {}
    assert params["required"] == []


def test_unknown_name_raises():
    with pytest.raises(KeyError):
        build_specs(FAKE_REGISTRY, ["does_not_exist"])


def test_registry_specs_against_live_registry():
    # Exercises the live registry; skips (rather than errors) if it can't be
    # imported here, e.g. an optional tool dependency is missing.
    pytest.importorskip("tools.tools")
    from tools.orchestrator.tool_specs import registry_specs

    specs = registry_specs(["list_files", "read_file"])
    assert [s["function"]["name"] for s in specs] == ["list_files", "read_file"]
    for spec in specs:
        assert spec["type"] == "function"
        assert spec["function"]["parameters"]["type"] == "object"
