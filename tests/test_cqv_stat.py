"""Integration tests for the CQV statistical-validity layer (cqv.py + stat_*)."""

from __future__ import annotations

import json
from pathlib import Path

from tools.orchestrator.cqv import run_cqv
from tools.orchestrator.llm import LLMResponse


def _seed(root: Path, title: str, code: str) -> None:
    assets = root / "ai4r" / title / "input" / "assets"
    assets.mkdir(parents=True, exist_ok=True)
    (assets / "analysis.R").write_text(code)


def _seed_kbe(root: Path, title: str, payload: dict) -> None:
    kbe = root / "ai4r" / title / "kbe"
    kbe.mkdir(parents=True, exist_ok=True)
    (kbe / "kbe_output.json").write_text(json.dumps(payload))


def _backend(*, audit: dict, verdict: dict):
    """Fake: judge calls (judge system frame) get ``verdict``; else the audit."""

    def fn(model, messages, tools):
        system = messages[0]["content"]
        if "statistical-methodology reviewer" in system:
            return LLMResponse(text=json.dumps(verdict))
        return LLMResponse(text=json.dumps(audit))

    return fn


def _read(root, title):
    return json.loads((root / "ai4r" / title / "cqv" / "cqv_output.json").read_text())


def test_stat_layer_attached_and_fail_promoted_to_blocker(tmp_path):
    # A repo with a parametric test and no assumption check -> the judge fails it.
    _seed(tmp_path, "leaky", "df <- read.csv('d.csv')\nt.test(df$a, df$b)\n")
    fail = {
        "verdict": "fail",
        "confidence": "high",
        "rationale": "t.test with no shapiro.test or Welch correction.",
        "evidence_refs": ["analysis.R:2"],
    }
    out = run_cqv(
        "leaky",
        root=tmp_path,
        complete_fn=_backend(audit={"notes": "ok"}, verdict=fail),
    )
    assert out["status"] == "success"
    sv = out["statistical_validity"]
    assert len(sv) == 7
    # the test-assumptions judge ran (had evidence) and failed
    ta = next(v for v in sv if v["item_id"] == "cqv-stat-test-assumptions")
    assert ta["verdict"] == "fail"
    # a major-severity fail is promoted to a blocker
    ids = [b["id"] for b in out["reproducibility_blockers"]]
    assert "STAT-cqv-stat-test-assumptions" in ids
    # persisted to disk
    assert "statistical_validity" in _read(tmp_path, "leaky")


def test_pass_verdict_adds_no_blocker(tmp_path):
    _seed(tmp_path, "clean", "shapiro.test(x)\nt.test(a, b, var.equal = FALSE)\n")
    ok = {"verdict": "pass", "confidence": "high", "rationale": "assumptions checked"}
    out = run_cqv(
        "clean", root=tmp_path, complete_fn=_backend(audit={"notes": "ok"}, verdict=ok)
    )
    assert out["reproducibility_blockers"] == []
    assert any(v["verdict"] == "pass" for v in out["statistical_validity"])


def test_kbe_context_drives_sampling_judge(tmp_path):
    # No sampling code, but KBE describes the population -> the needs_kbe judge runs.
    _seed(tmp_path, "sampled", "x <- 1\n")
    _seed_kbe(
        tmp_path,
        "sampled",
        {"paper_title": "T", "structured_knowledge": ["population: all ICU patients"]},
    )
    fail = {"verdict": "fail", "rationale": "convenience sample vs claimed population"}
    out = run_cqv(
        "sampled", root=tmp_path, complete_fn=_backend(audit={"notes": "ok"}, verdict=fail)
    )
    samp = next(
        v for v in out["statistical_validity"] if v["item_id"] == "cqv-stat-representative-sampling"
    )
    assert samp["verdict"] == "fail"
    assert "STAT-cqv-stat-representative-sampling" in [b["id"] for b in out["reproducibility_blockers"]]


def test_failed_audit_skips_stat_layer(tmp_path):
    # empty assets -> hard failure before the audit; stat layer must not run.
    (tmp_path / "ai4r" / "empty" / "input" / "assets").mkdir(parents=True)
    out = run_cqv("empty", root=tmp_path, complete_fn=_backend(audit={}, verdict={}))
    assert out["status"] == "failed"
    assert "statistical_validity" not in out
