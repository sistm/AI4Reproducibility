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
    assert info["check_parse_success"]["implemented"] is True    # patch 0092
    assert info["check_loop_invariants"]["implemented"] is False  # still stubbed


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
    # patch 0092 — cross-language heuristics
    "check_parse_success",
    "check_duplicate_code_blocks",
    "check_growing_vectors",
    "check_error_handling_coverage",
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
    "check_undefined_references",
    "check_function_signatures",
    "check_dead_code",
    "check_loop_invariants",
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


# ---------------------------------------------------------------------------
# patch 0070 — dispatch-level: language filtering and result serialisation
# ---------------------------------------------------------------------------

def test_get_applicable_r_only_excludes_python():
    """R-only submission: Python-only checks excluded; R-only and universal included."""
    from tools.cqv_agent.static_checks.dispatch import APPLICABLE_TO, get_applicable_checks

    result = get_applicable_checks({"r"})
    python_only = [c for c, langs in APPLICABLE_TO.items() if langs == ["python"]]
    r_only = [c for c, langs in APPLICABLE_TO.items() if langs == ["r"]]
    universal = [c for c, langs in APPLICABLE_TO.items() if langs == ["*"]]

    for c in python_only:
        assert c not in result, f"Python-only check {c} should be excluded for R-only"
    for c in r_only + universal:
        assert c in result, f"R/universal check {c} should be included for R-only"


def test_get_applicable_python_only_excludes_r():
    """Python-only submission: R-only checks excluded; Python-only and universal included."""
    from tools.cqv_agent.static_checks.dispatch import APPLICABLE_TO, get_applicable_checks

    result = get_applicable_checks({"python"})
    r_only = [c for c, langs in APPLICABLE_TO.items() if langs == ["r"]]
    python_only = [c for c, langs in APPLICABLE_TO.items() if langs == ["python"]]
    universal = [c for c, langs in APPLICABLE_TO.items() if langs == ["*"]]

    for c in r_only:
        assert c not in result, f"R-only check {c} should be excluded for Python-only"
    for c in python_only + universal:
        assert c in result, f"Python/universal check {c} should be included for Python-only"


def test_get_applicable_mixed_includes_all():
    """Mixed R+Python submission: every registered check is applicable."""
    from tools.cqv_agent.static_checks.dispatch import REGISTRY, get_applicable_checks

    result = get_applicable_checks({"r", "python"})
    assert set(result) == set(REGISTRY.keys())


def test_get_applicable_empty_languages_only_universal():
    """Unknown/empty language set: only universal checks included."""
    from tools.cqv_agent.static_checks.dispatch import APPLICABLE_TO, get_applicable_checks

    result = get_applicable_checks(set())
    universal = {c for c, langs in APPLICABLE_TO.items() if langs == ["*"]}
    non_universal = {c for c, langs in APPLICABLE_TO.items() if langs != ["*"]}

    assert universal == set(result)
    for c in non_universal:
        assert c not in result


def test_check_result_to_dict_has_required_keys():
    """CheckResult.to_dict() always returns the five contract keys."""
    from tools.cqv_agent.static_checks._common import CheckResult

    r = CheckResult(
        tool_id="check_absolute_paths",
        status="pass",
        summary="All good.",
        evidence=[{"file": "a.R", "line": 1}],
        metadata={"total": 0},
    )
    d = r.to_dict()
    for key in ("tool_id", "status", "summary", "evidence", "metadata"):
        assert key in d, f"Missing key: {key}"
    assert d["tool_id"] == "check_absolute_paths"
    assert d["status"] == "pass"
    assert d["evidence"] == [{"file": "a.R", "line": 1}]


# ---------------------------------------------------------------------------
# patch 0092 — heuristics_cross_lang: ~3 tests per check
# ---------------------------------------------------------------------------

# check_parse_success --------------------------------------------------------

def test_parse_success_pass_valid_python(tmp_path):
    (tmp_path / "a.py").write_text("x = 1 + 1\n")
    assert run_static_check("check_parse_success", tmp_path)["status"] == "pass"


def test_parse_success_fail_python_syntax_error(tmp_path):
    (tmp_path / "a.py").write_text("def foo(\n  x\n  # unclosed\n")
    r = run_static_check("check_parse_success", tmp_path)
    assert r["status"] == "fail"


def test_parse_success_fail_r_unclosed_brace(tmp_path):
    (tmp_path / "a.R").write_text("foo <- function(x) {\n  x + 1\n# missing closing brace\n")
    r = run_static_check("check_parse_success", tmp_path)
    assert r["status"] == "fail"


def test_parse_success_fail_r_negative_depth(tmp_path):
    (tmp_path / "a.R").write_text("x <- 1\n}\n")  # extra closing brace
    r = run_static_check("check_parse_success", tmp_path)
    assert r["status"] == "fail"


def test_parse_success_pass_empty_repo(tmp_path):
    assert run_static_check("check_parse_success", tmp_path)["status"] == "pass"


# check_duplicate_code_blocks ------------------------------------------------

def test_duplicate_blocks_pass_no_duplicates(tmp_path):
    (tmp_path / "a.R").write_text("\n".join(
        [f"line_{i} <- i * {i} + some_value" for i in range(20)]
    ))
    assert run_static_check("check_duplicate_code_blocks", tmp_path)["status"] == "pass"


def test_duplicate_blocks_fail_copied_block(tmp_path):
    block = "\n".join(
        [f"result_{i} <- compute_thing(x_{i}, param_{i})" for i in range(6)]
    )
    filler = "\n".join([f"x_{i} <- {i}" for i in range(20)])  # 20-line gap satisfies _MIN_SEPARATION
    (tmp_path / "a.R").write_text(block + "\n\n" + filler + "\n\n" + block + "\n")
    r = run_static_check("check_duplicate_code_blocks", tmp_path)
    assert r["status"] == "fail"


def test_duplicate_blocks_fail_across_files(tmp_path):
    block = "\n".join(
        [f"process_item_{i} <- function(x_{i}) x_{i} * weight_{i}" for i in range(6)]
    )
    (tmp_path / "a.R").write_text(block + "\n")
    (tmp_path / "b.R").write_text(block + "\n")
    r = run_static_check("check_duplicate_code_blocks", tmp_path)
    assert r["status"] == "fail"


# check_growing_vectors ------------------------------------------------------

def test_growing_vectors_pass_no_loop_growth(tmp_path):
    (tmp_path / "a.R").write_text(
        "results <- vector('list', 100)\n"
        "for (i in seq_along(items)) { results[[i]] <- process(items[[i]]) }\n"
    )
    assert run_static_check("check_growing_vectors", tmp_path)["status"] == "pass"


def test_growing_vectors_fail_c_in_loop(tmp_path):
    (tmp_path / "a.R").write_text(
        "out <- c()\n"
        "for (i in 1:100) {\n"
        "  out <- c(out, compute(i))\n"
        "}\n"
    )
    r = run_static_check("check_growing_vectors", tmp_path)
    assert r["status"] == "fail"
    assert r["evidence"][0]["line"] == 3


def test_growing_vectors_fail_append_in_while(tmp_path):
    (tmp_path / "a.R").write_text(
        "results <- list()\n"
        "while (condition) {\n"
        "  results <- append(results, new_item)\n"
        "}\n"
    )
    r = run_static_check("check_growing_vectors", tmp_path)
    assert r["status"] == "fail"


def test_growing_vectors_pass_no_r_files(tmp_path):
    (tmp_path / "a.py").write_text("x = []\nfor i in range(10):\n    x.append(i)\n")
    assert run_static_check("check_growing_vectors", tmp_path)["status"] == "pass"


# check_error_handling_coverage ----------------------------------------------

def test_error_handling_pass_trycatch_present(tmp_path):
    (tmp_path / "a.R").write_text(
        "result <- tryCatch(\n"
        "  download.file(url, dest),\n"
        "  error = function(e) NULL\n"
        ")\n"
    )
    assert run_static_check("check_error_handling_coverage", tmp_path)["status"] == "pass"


def test_error_handling_fail_network_without_handler(tmp_path):
    (tmp_path / "a.R").write_text(
        "download.file('https://example.com/data.csv', 'data.csv')\n"
        "dat <- read.csv('data.csv')\n"
    )
    r = run_static_check("check_error_handling_coverage", tmp_path)
    assert r["status"] == "fail"
    assert r["evidence"][0]["line"] == 1


def test_error_handling_pass_no_network_calls(tmp_path):
    (tmp_path / "a.R").write_text(
        "dat <- read.csv('local_data.csv')\n"
        "result <- lm(y ~ x, data = dat)\n"
    )
    assert run_static_check("check_error_handling_coverage", tmp_path)["status"] == "pass"


def test_error_handling_fail_python_requests_no_try(tmp_path):
    (tmp_path / "a.py").write_text(
        "import requests\n"
        "r = requests.get('https://api.example.com/data')\n"
        "data = r.json()\n"
    )
    r = run_static_check("check_error_handling_coverage", tmp_path)
    assert r["status"] == "fail"
