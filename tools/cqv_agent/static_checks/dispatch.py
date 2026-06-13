"""
Static-check dispatcher.

The CQV agent calls a single entry point — ``run_static_check(tool_id,
repo_path)`` — and the dispatcher routes to the appropriate implementation.

Adding a new check:
    1. Implement it in the right module (file_inventory, path_checks,
       danger_patterns, or a new module).
    2. Import it here.
    3. Register it in REGISTRY.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any

from ._common import CheckResult

# Stubs (AST-requiring; deferred to Phase 3 / tree-sitter-r)
from .check_r_ast import (
    check_dead_code,
    check_function_signatures,
    check_loop_invariants,
    check_undefined_references,
)
from .danger_patterns import (
    check_no_arbitrary_downloads,
    check_no_attach,
    check_no_auto_install,
    check_no_eval_parse,
    check_no_hardcoded_secrets,
    check_no_system_calls,
    check_no_unsafe_deserialization,
    check_no_workspace_clear,
)

# Implemented
from .file_inventory import (
    check_archive_layout,
    check_environment_tooling,
    check_file_naming_hygiene,
    check_main_entry_point,
    check_output_naming_convention,
    check_python_requirements,
    check_readme_present,
    check_sessioninfo_block,
    check_test_directory_present,
    check_version_pinning,
)

# Cross-language heuristics implementable without tree-sitter (patch 0092)
from .heuristics_cross_lang import (
    check_duplicate_code_blocks,
    check_error_handling_coverage,
    check_growing_vectors,
    check_parse_success,
)
from .path_checks import (
    check_absolute_paths,
    check_path_helpers,
)

# Regex-tractable R heuristics (patch 0071)
from .r_heuristics import (
    check_function_docs_present,
    check_global_state_mutation,
    check_imports_complete,
    check_no_unbounded_loops,
    check_set_seed_scope,
)

CheckFn = Callable[..., CheckResult]


REGISTRY: dict[str, CheckFn] = {
    # File inventory ----------------------------------------------------------
    "check_readme_present":              check_readme_present,
    "check_sessioninfo_block":           check_sessioninfo_block,
    "check_python_requirements":         check_python_requirements,
    "check_version_pinning":             check_version_pinning,
    "check_environment_tooling":         check_environment_tooling,
    "check_main_entry_point":            check_main_entry_point,
    "check_test_directory_present":      check_test_directory_present,
    "check_file_naming_hygiene":         check_file_naming_hygiene,
    "check_archive_layout":              check_archive_layout,
    "check_output_naming_convention":    check_output_naming_convention,
    # Path checks -------------------------------------------------------------
    "check_absolute_paths":              check_absolute_paths,
    "check_path_helpers":                check_path_helpers,
    # Danger patterns ---------------------------------------------------------
    "check_no_workspace_clear":          check_no_workspace_clear,
    "check_no_auto_install":             check_no_auto_install,
    "check_no_eval_parse":               check_no_eval_parse,
    "check_no_system_calls":             check_no_system_calls,
    "check_no_hardcoded_secrets":        check_no_hardcoded_secrets,
    "check_no_attach":                   check_no_attach,
    "check_no_arbitrary_downloads":      check_no_arbitrary_downloads,
    "check_no_unsafe_deserialization":   check_no_unsafe_deserialization,
    # Stubs (not implemented yet) --------------------------------------------
    "check_set_seed_scope":              check_set_seed_scope,
    "check_parse_success":               check_parse_success,
    "check_undefined_references":        check_undefined_references,
    "check_function_signatures":         check_function_signatures,
    "check_imports_complete":            check_imports_complete,
    "check_duplicate_code_blocks":       check_duplicate_code_blocks,
    "check_dead_code":                   check_dead_code,
    "check_global_state_mutation":       check_global_state_mutation,
    "check_growing_vectors":             check_growing_vectors,
    "check_loop_invariants":             check_loop_invariants,
    "check_no_unbounded_loops":          check_no_unbounded_loops,
    "check_error_handling_coverage":     check_error_handling_coverage,
    "check_function_docs_present":       check_function_docs_present,
}


def run_static_check(tool_id: str, repo_path: str | Path, **kwargs: Any) -> dict:
    """Dispatch entry point. Returns a JSON-serialisable dict.

    Args:
        tool_id:   Name of the static check (e.g. "check_absolute_paths").
        repo_path: Path to the extracted repository under inspection.
        **kwargs:  Forwarded to the check implementation.

    Returns:
        Dict with keys ``tool_id``, ``status``, ``summary``, ``evidence``,
        ``metadata`` — see ``CheckResult.to_dict()``.

    Raises:
        ValueError: if ``tool_id`` is unknown.
    """
    impl = REGISTRY.get(tool_id)
    if impl is None:
        raise ValueError(f"Unknown static check: {tool_id!r}")
    result = impl(Path(repo_path), **kwargs)
    return result.to_dict()


def list_static_checks() -> dict[str, dict]:
    """Introspection: per-check (status, implementation module, applicable_to)."""
    out: dict[str, dict] = {}
    for tool_id, fn in REGISTRY.items():
        module = fn.__module__.rsplit(".", 1)[-1]
        out[tool_id] = {
            "implemented": module != "_stubs",
            "module": module,
            "applicable_to": APPLICABLE_TO.get(tool_id, ["*"]),
        }
    return out


# ---------------------------------------------------------------------------
# Language applicability (patch 0070)
# ---------------------------------------------------------------------------
# Each entry lists the languages a check is meaningful for:
#   ["*"]              — always applicable (file-/directory-level checks)
#   ["r"]              — R-only patterns
#   ["python"]         — Python-only patterns
#   ["r", "python"]    — checks that inspect both R and Python source

APPLICABLE_TO: dict[str, list[str]] = {
    # Universal (file-/directory-level)
    "check_readme_present":              ["*"],
    "check_environment_tooling":         ["*"],
    "check_main_entry_point":            ["*"],
    "check_test_directory_present":      ["*"],
    "check_file_naming_hygiene":         ["*"],
    "check_archive_layout":              ["*"],
    "check_output_naming_convention":    ["*"],
    # R + Python source-level
    "check_absolute_paths":              ["r", "python"],
    "check_path_helpers":                ["r", "python"],
    "check_version_pinning":             ["r", "python"],
    "check_no_auto_install":             ["r", "python"],
    "check_no_eval_parse":               ["r", "python"],
    "check_no_system_calls":             ["r", "python"],
    "check_no_hardcoded_secrets":        ["r", "python"],
    "check_no_arbitrary_downloads":      ["r", "python"],
    "check_no_unsafe_deserialization":   ["r", "python"],
    "check_parse_success":               ["r", "python"],
    "check_undefined_references":        ["r", "python"],
    "check_function_signatures":         ["r", "python"],
    "check_duplicate_code_blocks":       ["r", "python"],
    "check_dead_code":                   ["r", "python"],
    "check_loop_invariants":             ["r", "python"],
    "check_error_handling_coverage":     ["r", "python"],
    # R-only
    "check_sessioninfo_block":           ["r"],
    "check_no_workspace_clear":          ["r"],
    "check_no_attach":                   ["r"],
    "check_set_seed_scope":              ["r"],
    "check_imports_complete":            ["r"],
    "check_function_docs_present":       ["r"],
    "check_no_unbounded_loops":          ["r"],
    "check_global_state_mutation":       ["r"],
    "check_growing_vectors":             ["r"],
    # Python-only
    "check_python_requirements":         ["python"],
}


def get_applicable_checks(detected_languages: set[str]) -> list[str]:
    """Return check IDs applicable for the given set of detected languages.

    Universal checks (``["*"]``) are always included.  Language-specific
    checks are included only when the matching language appears in
    ``detected_languages``.
    """
    applicable: list[str] = []
    for check_id in REGISTRY:
        langs = APPLICABLE_TO.get(check_id, ["*"])
        if langs == ["*"] or any(lang in detected_languages for lang in langs):
            applicable.append(check_id)
    return applicable
