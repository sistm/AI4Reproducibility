"""
Stubs for static checks not yet implemented.

Each stub returns a valid ``CheckResult`` with ``status="not_implemented"``
so the CQV agent can still emit a well-formed ``cqv_output.json`` and the
Review agent can mark the corresponding checklist item as **Unverified**.

When you implement one of these, move the function to the appropriate
module and update the registry in ``dispatch.py``.

Implemented and removed from here (patch 0071): check_set_seed_scope,
check_imports_complete, check_function_docs_present, check_no_unbounded_loops,
check_global_state_mutation → now in r_heuristics.py.
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


# Each of these needs a language parser (Python ast is easy;
# R needs tree-sitter or shelling out to Rscript). Deferred to Phase 3.

def check_parse_success(repo_path: Path, **_: object) -> CheckResult:
    return _stub("check_parse_success",
                 "Requires language-specific parser invocation.")


def check_undefined_references(repo_path: Path, **_: object) -> CheckResult:
    return _stub("check_undefined_references",
                 "Requires symbol-table construction per language.")


def check_function_signatures(repo_path: Path, **_: object) -> CheckResult:
    return _stub("check_function_signatures",
                 "Requires per-package signature DB or live import.")


def check_duplicate_code_blocks(repo_path: Path, **_: object) -> CheckResult:
    return _stub("check_duplicate_code_blocks",
                 "Requires token-level duplicate detection (e.g. CPD).")


def check_dead_code(repo_path: Path, **_: object) -> CheckResult:
    return _stub("check_dead_code",
                 "Requires control-flow graph construction.")


def check_growing_vectors(repo_path: Path, **_: object) -> CheckResult:
    return _stub("check_growing_vectors",
                 "Requires loop-body AST analysis.")


def check_loop_invariants(repo_path: Path, **_: object) -> CheckResult:
    return _stub("check_loop_invariants",
                 "Requires data-flow analysis.")


def check_error_handling_coverage(repo_path: Path, **_: object) -> CheckResult:
    return _stub("check_error_handling_coverage",
                 "Requires AST + a registry of 'risky' operations.")
