"""
Tests for the CQV static-check tools.

Each implemented check is run against two fixture repositories:

  - ``clean_repo``: a minimal R + Python project that should pass everything.
  - ``dirty_repo``: a project that should trip nearly every check.

Stubs are exercised separately to confirm they return ``not_implemented``.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from tools.cqv_agent.static_checks import REGISTRY, list_static_checks, run_static_check

HERE = Path(__file__).resolve().parent
FIXTURES = HERE / "fixtures" / "static_checks"
CLEAN = FIXTURES / "clean_repo"
DIRTY = FIXTURES / "dirty_repo"


# ---------------------------------------------------------------------------
# Dispatch behaviour
# ---------------------------------------------------------------------------

def test_registry_covers_yaml_static_checks():
    """Every tool_id in either YAML with check_type=static must be in the registry."""
    import yaml

    repo_root = HERE.parent
    expected: set[str] = set()
    for yml in ("checklist.yaml", "cqv_checklist.yaml"):
        data = yaml.safe_load((repo_root / yml).read_text())
        for item in data["items"]:
            if item["check_type"] == "static":
                expected.add(item["tool_id"])

    missing = expected - REGISTRY.keys()
    assert not missing, f"Static checks declared in YAML but missing from registry: {sorted(missing)}"


def test_unknown_check_raises():
    with pytest.raises(ValueError, match="Unknown static check"):
        run_static_check("check_definitely_not_real", CLEAN)


def test_list_static_checks_reports_implementation_status():
    info = list_static_checks()
    assert "check_absolute_paths" in info
    assert info["check_absolute_paths"]["implemented"] is True
    assert info["check_set_seed_scope"]["implemented"] is True   # patch 0071
    assert info["check_parse_success"]["implemented"] is False   # still stubbed


# ---------------------------------------------------------------------------
# Clean repo: everything should pass (or warn benignly)
# ---------------------------------------------------------------------------

CLEAN_EXPECTED_PASS = [
    "check_readme_present",
    "check_sessioninfo_block",
    "check_python_requirements",
    "check_version_pinning",
    "check_environment_tooling",
    "check_main_entry_point",
    "check_test_directory_present",
    "check_file_naming_hygiene",
    "check_archive_layout",
    "check_output_naming_convention",
    "check_absolute_paths",
    "check_path_helpers",
    "check_no_workspace_clear",
    "check_no_auto_install",
    "check_no_eval_parse",
    "check_no_system_calls",
    "check_no_hardcoded_secrets",
    "check_no_attach",
    "check_no_arbitrary_downloads",
    "check_no_unsafe_deserialization",
    # patch 0071 — regex-tractable R heuristics
    "check_set_seed_scope",
    "check_imports_complete",
    "check_function_docs_present",
    "check_no_unbounded_loops",
    "check_global_state_mutation",
]


@pytest.mark.parametrize("tool_id", CLEAN_EXPECTED_PASS)
def test_clean_repo_passes(tool_id: str):
    result = run_static_check(tool_id, CLEAN)
    assert result["status"] in ("pass", "warning"), (
        f"{tool_id}: expected pass/warning on clean repo, got {result['status']}; "
        f"summary={result['summary']}"
    )


# ---------------------------------------------------------------------------
# Dirty repo: each check should fire on its corresponding pattern
# ---------------------------------------------------------------------------

DIRTY_EXPECTED_FAIL = {
    "check_readme_present":            ("fail",),
    "check_sessioninfo_block":         ("fail",),
    "check_main_entry_point":          ("fail",),
    "check_test_directory_present":    ("fail",),
    "check_version_pinning":           ("fail",),
    "check_file_naming_hygiene":       ("fail",),
    "check_absolute_paths":            ("fail",),
    "check_no_workspace_clear":        ("warning",),
    "check_no_auto_install":           ("fail",),
    "check_no_eval_parse":             ("fail",),
    "check_no_system_calls":           ("fail",),
    "check_no_hardcoded_secrets":      ("fail",),
    "check_no_attach":                 ("fail",),
    "check_no_unsafe_deserialization": ("warning",),
    "check_archive_layout":            ("warning",),
}


@pytest.mark.parametrize("tool_id,expected_statuses", list(DIRTY_EXPECTED_FAIL.items()))
def test_dirty_repo_fails(tool_id: str, expected_statuses: tuple[str, ...]):
    result = run_static_check(tool_id, DIRTY)
    assert result["status"] in expected_statuses, (
        f"{tool_id}: expected one of {expected_statuses} on dirty repo, "
        f"got {result['status']}; summary={result['summary']}"
    )
    # Failing checks should produce evidence so the agent can cite it.
    if result["status"] in ("fail", "warning"):
        assert result["evidence"] or result["metadata"], (
            f"{tool_id} reported {result['status']} but produced no evidence"
        )


# ---------------------------------------------------------------------------
# Stubs return not_implemented (not exceptions)
# ---------------------------------------------------------------------------

STUBBED_CHECKS = [
    "check_parse_success",
    "check_undefined_references",
    "check_function_signatures",
    "check_duplicate_code_blocks",
    "check_dead_code",
    "check_growing_vectors",
    "check_loop_invariants",
    "check_error_handling_coverage",
]


@pytest.mark.parametrize("tool_id", STUBBED_CHECKS)
def test_stubs_return_not_implemented(tool_id: str):
    result = run_static_check(tool_id, CLEAN)
    assert result["status"] == "not_implemented"
    assert "reason" in result["metadata"]


# ---------------------------------------------------------------------------
# patch 0071 — r_heuristics: ~3 tests per check
# ---------------------------------------------------------------------------

# check_set_seed_scope -------------------------------------------------------

def test_set_seed_scope_pass_seed_before_rng(tmp_path):
    (tmp_path / "a.R").write_text("set.seed(42)\nx <- runif(10)\n")
    r = run_static_check("check_set_seed_scope", tmp_path)
    assert r["status"] == "pass"


def test_set_seed_scope_fail_rng_before_seed(tmp_path):
    (tmp_path / "a.R").write_text("x <- runif(10)\nset.seed(42)\n")
    r = run_static_check("check_set_seed_scope", tmp_path)
    assert r["status"] == "fail"
    assert r["evidence"][0]["line"] == 1


def test_set_seed_scope_fail_no_seed_at_all(tmp_path):
    (tmp_path / "a.R").write_text("x <- rnorm(100)\n")
    r = run_static_check("check_set_seed_scope", tmp_path)
    assert r["status"] == "fail"


def test_set_seed_scope_pass_no_rng_calls(tmp_path):
    (tmp_path / "a.R").write_text("x <- 1 + 1\n")
    r = run_static_check("check_set_seed_scope", tmp_path)
    assert r["status"] == "pass"


# check_imports_complete -----------------------------------------------------

def test_imports_complete_pass_declared(tmp_path):
    (tmp_path / "a.R").write_text("library(dplyr)\nx <- dplyr::filter(df, x > 0)\n")
    r = run_static_check("check_imports_complete", tmp_path)
    assert r["status"] == "pass"


def test_imports_complete_fail_undeclared(tmp_path):
    (tmp_path / "a.R").write_text("x <- dplyr::filter(df, x > 0)\n")
    r = run_static_check("check_imports_complete", tmp_path)
    assert r["status"] == "fail"
    assert any("dplyr" in e["note"] for e in r["evidence"])


def test_imports_complete_pass_no_namespace_uses(tmp_path):
    (tmp_path / "a.R").write_text("x <- 1\n")
    r = run_static_check("check_imports_complete", tmp_path)
    assert r["status"] == "pass"


# check_function_docs_present ------------------------------------------------

def test_function_docs_pass_comment_present(tmp_path):
    (tmp_path / "a.R").write_text(
        "# Compute the square of x.\nfoo <- function(x) x^2\n"
    )
    r = run_static_check("check_function_docs_present", tmp_path)
    assert r["status"] == "pass"


def test_function_docs_fail_no_comment(tmp_path):
    (tmp_path / "a.R").write_text("foo <- function(x) x^2\n")
    r = run_static_check("check_function_docs_present", tmp_path)
    assert r["status"] == "fail"
    assert r["evidence"][0]["line"] == 1


def test_function_docs_fail_function_at_top_of_file(tmp_path):
    """No preceding line at all — must not crash, must fail."""
    (tmp_path / "a.R").write_text("foo <- function(x) {\n  x\n}\n")
    r = run_static_check("check_function_docs_present", tmp_path)
    assert r["status"] == "fail"


def test_function_docs_pass_no_functions(tmp_path):
    (tmp_path / "a.R").write_text("x <- 1\n")
    r = run_static_check("check_function_docs_present", tmp_path)
    assert r["status"] == "pass"


# check_no_unbounded_loops ---------------------------------------------------

def test_unbounded_loops_pass_while_true_with_break(tmp_path):
    (tmp_path / "a.R").write_text(
        "i <- 0\nwhile (TRUE) {\n  i <- i + 1\n  if (i > 10) break\n}\n"
    )
    r = run_static_check("check_no_unbounded_loops", tmp_path)
    assert r["status"] == "pass"


def test_unbounded_loops_fail_while_true_no_break(tmp_path):
    (tmp_path / "a.R").write_text("while (TRUE) {\n  x <- 1\n}\n")
    r = run_static_check("check_no_unbounded_loops", tmp_path)
    assert r["status"] == "fail"
    assert r["evidence"][0]["line"] == 1


def test_unbounded_loops_fail_repeat_no_break(tmp_path):
    (tmp_path / "a.R").write_text("repeat {\n  x <- x + 1\n}\n")
    r = run_static_check("check_no_unbounded_loops", tmp_path)
    assert r["status"] == "fail"


def test_unbounded_loops_pass_no_loops(tmp_path):
    (tmp_path / "a.R").write_text("for (i in 1:10) { x <- i }\n")
    r = run_static_check("check_no_unbounded_loops", tmp_path)
    assert r["status"] == "pass"


# check_global_state_mutation ------------------------------------------------

def test_global_state_pass_superassign_inside_function(tmp_path):
    (tmp_path / "a.R").write_text(
        "counter <- 0\n"
        "increment <- function() {\n"
        "  counter <<- counter + 1\n"
        "}\n"
    )
    r = run_static_check("check_global_state_mutation", tmp_path)
    assert r["status"] == "pass"


def test_global_state_fail_toplevel_superassign(tmp_path):
    (tmp_path / "a.R").write_text("x <<- 42\n")
    r = run_static_check("check_global_state_mutation", tmp_path)
    assert r["status"] == "fail"
    assert r["evidence"][0]["line"] == 1


def test_global_state_pass_no_superassign(tmp_path):
    (tmp_path / "a.R").write_text("x <- 1\ny <- x + 2\n")
    r = run_static_check("check_global_state_mutation", tmp_path)
    assert r["status"] == "pass"
