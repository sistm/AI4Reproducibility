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


def test_there_are_seven_checks():
    assert len(STAT_CHECKS) == 7


def test_checks_match_yaml_source_of_truth():
    data = yaml.safe_load((_REPO_ROOT / "cqv_checklist.yaml").read_text())
    yaml_stat = {
        item["id"]: item
        for item in data["items"]
        if item.get("category") == "stat"
    }
    assert {c.item_id for c in STAT_CHECKS} == set(yaml_stat)
    for c in STAT_CHECKS:
        item = yaml_stat[c.item_id]
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
