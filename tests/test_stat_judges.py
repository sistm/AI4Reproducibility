"""Tests for the statistical-validity judges (tools/orchestrator/stat_judges.py).

Evidence is passed in, so these run with an injected fake backend and no repo,
network, or model. One test ties STAT_CHECKS to cqv_checklist.yaml so the two
cannot drift (the YAML is the source of truth, conventions §8).
"""

from __future__ import annotations

import json
from pathlib import Path

import yaml

from tools.orchestrator.llm import LLMResponse
from tools.orchestrator.stat_judges import (
    STAT_CHECKS,
    run_stat_judge,
    run_stat_judges,
)

_REPO_ROOT = Path(__file__).resolve().parents[1]


class _Recorder:
    """Fake backend returning a fixed verdict and counting calls."""

    def __init__(self, payload):
        self.payload = payload
        self.calls = 0

    def __call__(self, model, messages, tools):
        self.calls += 1
        text = self.payload if isinstance(self.payload, str) else json.dumps(self.payload)
        return LLMResponse(text=text)


def _check(item_id):
    return next(c for c in STAT_CHECKS if c.item_id == item_id)


def test_there_are_sixteen_checks():
    assert len(STAT_CHECKS) == 16


def test_checks_match_yaml_source_of_truth():
    data = yaml.safe_load((_REPO_ROOT / "cqv_checklist.yaml").read_text())
    # Judges span stat, data, perf, sec, doc, test, dep categories — not stat only
    yaml_llm = {
        item["id"]: item
        for item in data["items"]
        if item.get("check_type") == "llm"
    }
    impl_ids = {c.item_id for c in STAT_CHECKS}
    assert impl_ids == set(yaml_llm), (
        f"Missing from STAT_CHECKS: {set(yaml_llm) - impl_ids}\n"
        f"Extra in STAT_CHECKS: {impl_ids - set(yaml_llm)}"
    )
    for c in STAT_CHECKS:
        item = yaml_llm[c.item_id]
        assert c.tool_id == item["tool_id"]
        assert c.severity == item["severity"]
        assert item["check_type"] == "llm"


def test_pass_verdict_normalised():
    fake = _Recorder({"verdict": "pass", "confidence": "high", "rationale": "checked"})
    out = run_stat_judge(_check("cqv-stat-test-assumptions"), "shapiro.test(x)", complete_fn=fake)
    assert out["verdict"] == "pass"
    assert out["severity"] == "major"
    assert out["tool_id"] == "judge_test_assumptions"
    assert fake.calls == 1


def test_empty_evidence_is_not_applicable_without_a_call():
    fake = _Recorder({"verdict": "fail"})
    out = run_stat_judge(_check("cqv-stat-no-data-leakage"), "   ", complete_fn=fake)
    assert out["verdict"] == "not_applicable"
    assert fake.calls == 0  # no model call when there is nothing to judge


def test_needs_kbe_check_runs_on_kbe_alone():
    fake = _Recorder({"verdict": "fail", "rationale": "convenience sample"})
    out = run_stat_judge(
        _check("cqv-stat-representative-sampling"),
        "",  # no code evidence
        kbe_context="Target population: all ICU patients; sampling: convenience.",
        complete_fn=fake,
    )
    assert fake.calls == 1
    assert out["verdict"] == "fail"


def test_code_only_check_ignores_kbe_context():
    fake = _Recorder({"verdict": "fail"})
    # test-assumptions does not use KBE; with empty code it must be N/A, no call.
    out = run_stat_judge(
        _check("cqv-stat-test-assumptions"),
        "",
        kbe_context="some paper context",
        complete_fn=fake,
    )
    assert out["verdict"] == "not_applicable"
    assert fake.calls == 0


def test_unparseable_response_is_unverified():
    fake = _Recorder("not json at all")
    out = run_stat_judge(_check("cqv-stat-ci-coverage"), "confint(model)", complete_fn=fake)
    assert out["verdict"] == "unverified"


def test_unknown_verdict_value_coerced_to_unverified():
    fake = _Recorder({"verdict": "definitely-bad", "confidence": "ultra"})
    out = run_stat_judge(_check("cqv-stat-ci-coverage"), "confint(model)", complete_fn=fake)
    assert out["verdict"] == "unverified"
    assert out["confidence"] == "low"


def test_backend_exception_is_unverified_not_raised():
    def exploding(model, messages, tools):
        raise RuntimeError("model exploded")

    out = run_stat_judge(_check("cqv-stat-model-diagnostics"), "plot(model)", complete_fn=exploding)
    assert out["verdict"] == "unverified"
    assert "model exploded" in out["rationale"]


def test_run_all_returns_one_per_check():
    fake = _Recorder({"verdict": "pass"})
    evidence = {c.item_id: "t.test(a, b)" for c in STAT_CHECKS}
    results = run_stat_judges(evidence, kbe_context="ctx", complete_fn=fake)
    assert len(results) == len(STAT_CHECKS)
    assert {r["item_id"] for r in results} == {c.item_id for c in STAT_CHECKS}


# ---------------------------------------------------------------------------
# MTP rubric regression tests (anti-FP for threshold-based correction)
# ---------------------------------------------------------------------------

def test_mtp_rubric_mentions_threshold_approach():
    """Rubric must explicitly accept Delta.* threshold variables as a valid MTP
    correction so the model cannot anchor solely on p.adjust()."""
    check = _check("cqv-stat-multiple-testing")
    assert "threshold" in check.rubric.lower()
    assert "delta." in check.rubric.lower() or "Delta." in check.rubric
    assert "p.adjust() is absent" in check.rubric or "p.adjust() absent" in check.rubric


def test_mtp_rubric_has_explicit_do_not_fail_guard():
    """The explicit 'Do NOT fail solely because p.adjust() is absent' guard must
    be present to prevent the false positive seen in the smoke-test paper."""
    check = _check("cqv-stat-multiple-testing")
    assert "do not fail" in check.rubric.lower()


def test_mtp_threshold_evidence_reaches_model():
    """With Delta.Bonf evidence the judge is invoked — not short-circuited as N/A."""
    evidence = (
        "Delta.Bonf = alpha / m\n"
        "Delta.Holm = alpha / (m:1)\n"
        "Delta.BH   = alpha * (1:m) / m\n"
        "R.BH = sum(p.sort <= Delta.BH)\n"
    )
    fake = _Recorder({"verdict": "pass", "confidence": "high",
                      "rationale": "threshold-based MTP present"})
    out = run_stat_judge(_check("cqv-stat-multiple-testing"), evidence, complete_fn=fake)
    assert fake.calls == 1, "Model must be called when threshold-based evidence is present"
    assert out["verdict"] == "pass"


# ---------------------------------------------------------------------------
# no_post_hoc rubric regression tests (patch 0095)
# ---------------------------------------------------------------------------

def test_no_post_hoc_rubric_requires_all_three_conditions():
    """FAIL requires undisclosed + absent from Methods + affects inference.
    The rubric must not flag disclosed additions."""
    check = _check("cqv-stat-no-post-hoc")
    rubric = check.rubric.lower()
    assert "all three" in rubric or "all of the following" in rubric or "(a)" in rubric


def test_no_post_hoc_rubric_exempts_reviewer_requested():
    """Reviewer-requested additions must be explicitly listed as DO NOT FAIL."""
    check = _check("cqv-stat-no-post-hoc")
    assert "reviewer" in check.rubric.lower()
    assert "do not fail" in check.rubric.lower()


def test_no_post_hoc_rubric_exempts_sensitivity_analyses():
    """Sensitivity analyses must be explicitly exempted."""
    check = _check("cqv-stat-no-post-hoc")
    assert "sensitivity" in check.rubric.lower()


def test_no_post_hoc_rubric_exempts_bayesian_posteriors():
    """DP/Gibbs/MCMC posterior computations must be explicitly exempted —
    this is the specific pattern that caused the false positive on bimj_202400278."""
    check = _check("cqv-stat-no-post-hoc")
    rubric = check.rubric.lower()
    assert any(kw in rubric for kw in ("gibbs", "mcmc", "bayesian", "dp"))


def test_no_post_hoc_rubric_clarifies_no_preregistration_required():
    """Biometrical Journal doesn't require pre-registration; the rubric must
    not penalise absence of a registered protocol."""
    check = _check("cqv-stat-no-post-hoc")
    rubric = check.rubric.lower()
    assert "pre-registration" in rubric or "preregistration" in rubric or "biometrical" in rubric


def test_no_post_hoc_reviewer_evidence_calls_model():
    """When evidence includes 'added in response to reviewer' language the judge
    is invoked — not short-circuited — and must not automatically fail."""
    evidence = (
        "# Section 4.1 — Posterior-of-M analysis\n"
        "# Added in response to reviewer comment requesting a DP sensitivity check.\n"
        "dp_gibbs <- function(p_vals, alpha=0.05, n_iter=10000) {\n"
        "  # Gibbs sampler for DP-MTP\n"
        "}\n"
    )
    fake = _Recorder({"verdict": "pass", "confidence": "high",
                      "rationale": "reviewer-requested sensitivity analysis, disclosed"})
    out = run_stat_judge(_check("cqv-stat-no-post-hoc"), evidence, complete_fn=fake)
    assert fake.calls == 1
    assert out["verdict"] == "pass"


# ---------------------------------------------------------------------------
# patch 0099 — 9 new LLM judges (rubric smoke tests)
# ---------------------------------------------------------------------------

def test_na_handling_rubric_requires_na_rm():
    check = _check("cqv-data-na-handling")
    rubric = check.rubric.lower()
    assert "na.rm" in rubric
    assert "do not fail" in rubric       # explicit guards present
    assert "simulation" in rubric        # simulation data guard
    assert "unverified" in rubric        # ambiguous-origin guard


def test_na_handling_not_applicable_on_no_evidence():
    out = run_stat_judge(_check("cqv-data-na-handling"), "")
    assert out["verdict"] == "not_applicable"


def test_na_handling_calls_model_on_aggregation_code():
    evidence = "result <- mean(x)\ntotal <- sum(values)\n"
    fake = _Recorder({"verdict": "fail", "confidence": "high",
                      "rationale": "mean() called without na.rm=TRUE"})
    out = run_stat_judge(_check("cqv-data-na-handling"), evidence, complete_fn=fake)
    assert fake.calls == 1
    assert out["verdict"] == "fail"


def test_type_handling_rubric_not_fail_on_absence_alone():
    check = _check("cqv-data-explicit-types")
    rubric = check.rubric.lower()
    assert "do not fail" in rubric or "not fail merely" in rubric


def test_type_handling_not_applicable_on_no_evidence():
    out = run_stat_judge(_check("cqv-data-explicit-types"), "")
    assert out["verdict"] == "not_applicable"


def test_dataframe_mutation_rubric_exempts_dplyr():
    check = _check("cqv-data-no-unexpected-mutation")
    assert "dplyr" in check.rubric.lower()
    assert "not_applicable" in check.rubric.lower() or "mark not_applicable" in check.rubric.lower()


def test_dataframe_mutation_not_applicable_on_no_evidence():
    out = run_stat_judge(_check("cqv-data-no-unexpected-mutation"), "")
    assert out["verdict"] == "not_applicable"


def test_object_copying_is_suggestion_severity():
    assert _check("cqv-perf-no-redundant-copies").severity == "suggestion"


def test_object_copying_not_applicable_on_no_evidence():
    out = run_stat_judge(_check("cqv-perf-no-redundant-copies"), "")
    assert out["verdict"] == "not_applicable"


def test_path_sanitization_rubric_exempts_hardcoded():
    check = _check("cqv-sec-path-sanitization")
    rubric = check.rubric.lower()
    assert "hardcoded" in rubric or "not_applicable" in rubric


def test_path_sanitization_not_applicable_on_no_evidence():
    out = run_stat_judge(_check("cqv-sec-path-sanitization"), "")
    assert out["verdict"] == "not_applicable"


def test_docstring_quality_not_applicable_when_no_docs():
    check = _check("cqv-doc-docstring-format")
    rubric = check.rubric.lower()
    assert "not_applicable" in rubric
    # No evidence → not_applicable
    out = run_stat_judge(check, "")
    assert out["verdict"] == "not_applicable"


def test_edge_case_coverage_is_suggestion():
    assert _check("cqv-test-edge-cases").severity == "suggestion"


def test_edge_case_coverage_not_applicable_without_tests():
    out = run_stat_judge(_check("cqv-test-edge-cases"), "")
    assert out["verdict"] == "not_applicable"


def test_integration_test_not_applicable_without_tests():
    out = run_stat_judge(_check("cqv-test-integration"), "")
    assert out["verdict"] == "not_applicable"


def test_deprecated_packages_rubric_names_known_cases():
    check = _check("cqv-dep-no-deprecated")
    rubric = check.rubric.lower()
    assert "rgdal" in rubric or "rgeos" in rubric or "sp" in rubric


def test_deprecated_packages_not_applicable_on_no_evidence():
    out = run_stat_judge(_check("cqv-dep-no-deprecated"), "")
    assert out["verdict"] == "not_applicable"


def test_all_16_judges_registered():
    from tools.orchestrator.stat_judges import STAT_CHECKS
    tool_ids = {c.tool_id for c in STAT_CHECKS}
    expected = {
        "judge_test_assumptions", "judge_multiple_testing_correction",
        "judge_data_leakage", "judge_ci_construction",
        "judge_sampling_representativeness", "judge_no_post_hoc_adjustment",
        "judge_model_diagnostics",
        "judge_na_handling", "judge_type_handling", "judge_dataframe_mutation",
        "judge_object_copying", "judge_path_sanitization", "judge_docstring_quality",
        "judge_edge_case_coverage", "judge_integration_test_coverage",
        "judge_deprecated_packages",
    }
    assert tool_ids == expected, f"Missing: {expected - tool_ids}, Extra: {tool_ids - expected}"


def test_all_16_item_ids_have_evidence_patterns():
    from tools.orchestrator.stat_evidence import PATTERNS
    from tools.orchestrator.stat_judges import STAT_CHECKS
    for check in STAT_CHECKS:
        assert check.item_id in PATTERNS, (
            f"{check.item_id} has no evidence patterns in stat_evidence.PATTERNS"
        )
