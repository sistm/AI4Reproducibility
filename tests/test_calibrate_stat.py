"""Tests for the stat-judge calibration harness (calibrate_stat.py).

Runs with an injected fake backend and a seeded review, so no model/network.
"""

from __future__ import annotations

import json

from tools.orchestrator.calibrate_stat import format_calibration_report, run_calibration
from tools.orchestrator.llm import LLMResponse


def test_format_shows_verdict_and_evidence():
    evidence = {"cqv-stat-test-assumptions": "2: t.test(a, b)"}
    verdicts = [
        {
            "item_id": "cqv-stat-test-assumptions",
            "tool_id": "judge_test_assumptions",
            "severity": "major",
            "verdict": "fail",
            "confidence": "high",
            "rationale": "no assumption check",
            "evidence_refs": ["analysis.R:2"],
        }
    ]
    report = format_calibration_report(evidence, verdicts)
    assert "cqv-stat-test-assumptions" in report
    assert "FAIL" in report
    assert "t.test(a, b)" in report
    assert "analysis.R:2" in report
    assert "summary: fail=1" in report


def test_format_truncates_long_evidence():
    evidence = {"cqv-stat-test-assumptions": "x" * 5000}
    verdicts = [
        {
            "item_id": "cqv-stat-test-assumptions",
            "tool_id": "judge_test_assumptions",
            "severity": "major",
            "verdict": "unverified",
            "confidence": "low",
            "rationale": "",
            "evidence_refs": [],
        }
    ]
    report = format_calibration_report(evidence, verdicts, max_evidence_chars=100)
    assert "…(truncated)" in report


def test_run_calibration_end_to_end_with_fake(tmp_path):
    assets = tmp_path / "ai4r" / "demo" / "input" / "assets"
    assets.mkdir(parents=True)
    (assets / "a.R").write_text("res <- t.test(g1, g2)\n")

    def fake(model, messages, tools):
        return LLMResponse(
            text=json.dumps({"verdict": "fail", "confidence": "high", "rationale": "no check"})
        )

    report = run_calibration("demo", root=tmp_path, complete_fn=fake)
    assert "cqv-stat-test-assumptions" in report
    assert "FAIL" in report
    # checks with no evidence are reported as not_applicable
    assert "not_applicable" in report.lower() or "not applicable" in report.lower()
