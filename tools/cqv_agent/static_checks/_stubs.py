"""
Stubs for static checks that genuinely require a language parser.

Each returns a valid ``CheckResult`` with ``status="not_implemented"`` so the
CQV agent emits a well-formed ``cqv_output.json`` and Review marks the item
Unverified.

When implementing, move the function to the appropriate module and update
``dispatch.py``.

Implemented and removed (patch 0071): check_set_seed_scope,
check_imports_complete, check_function_docs_present, check_no_unbounded_loops,
check_global_state_mutation → r_heuristics.py.

Implemented and removed (patch 0092): check_parse_success,
check_duplicate_code_blocks, check_growing_vectors,
check_error_handling_coverage → heuristics_cross_lang.py.

Remaining four require a symbol table or CFG; preferred path is tree-sitter-r
(Python bindings, no R install required).
"""

from __future__ import annotations

from pathlib import Path

from ._common import CheckResult


def _stub(tool_id: str, reason: str) -> CheckResult:
    return CheckResult(
        tool_id=tool_id,
        status="not_implemented",
        summary=f"Static check '{tool_id}' is not yet implemented. Reason: {reason}",
        evidence=[],
        metadata={"reason": reason},
    )


def check_undefined_references(repo_path: Path, **_: object) -> CheckResult:
    return _stub(
        "check_undefined_references",
        "Requires symbol-table construction (tree-sitter-r for R, ast for Python).",
    )


def check_function_signatures(repo_path: Path, **_: object) -> CheckResult:
    return _stub(
        "check_function_signatures",
        "Requires per-package signature DB or live import resolution.",
    )


def check_dead_code(repo_path: Path, **_: object) -> CheckResult:
    return _stub(
        "check_dead_code",
        "Requires control-flow graph construction.",
    )


def check_loop_invariants(repo_path: Path, **_: object) -> CheckResult:
    return _stub(
        "check_loop_invariants",
        "Requires data-flow analysis across loop iterations.",
    )
