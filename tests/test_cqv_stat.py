"""Integration tests for the CQV statistical-validity layer (cqv.py + stat_*)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

import tools.orchestrator.cqv as cqv
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


# ---------------------------------------------------------------------------
# Evidence rehydration (precise quotes from disk, not model-escaped)
# ---------------------------------------------------------------------------

def _audit_backend(audit: dict):
    """Fake: the main audit call returns `audit`; no stat code present."""
    def fn(model, messages, tools):
        return LLMResponse(text=json.dumps(audit))
    return fn


def test_evidence_rehydrated_with_verbatim_source_line(tmp_path):
    code = ('main.path <- file.path("/Users/x")\n'
            'setwd(file.path(main.path, "code"))\n')
    _seed(tmp_path, "rehy", code)  # writes input/assets/analysis.R
    audit = {
        "status": "partial",
        "repository_audit": {
            "issues": [
                {"id": "abs-path", "evidence": [{"file": "analysis.R", "line": 2}]}
            ]
        },
        "reproducibility_blockers": [],
    }
    out = run_cqv("rehy", root=tmp_path, complete_fn=_audit_backend(audit))
    ev = out["repository_audit"]["issues"][0]["evidence"][0]
    assert ev["snippet"] == 'setwd(file.path(main.path, "code"))'  # exact, quotes intact


def test_bad_file_or_line_reference_is_skipped_not_crashed(tmp_path):
    _seed(tmp_path, "badref", "x <- 1\n")
    audit = {
        "status": "partial",
        "repository_audit": {"e": [
            {"file": "nope.R", "line": 1},
            {"file": "analysis.R", "line": 999},
        ]},
        "reproducibility_blockers": [],
    }
    out = run_cqv("badref", root=tmp_path, complete_fn=_audit_backend(audit))
    for e in out["repository_audit"]["e"]:
        assert "snippet" not in e  # unresolved refs left untouched, no crash


def test_path_traversal_reference_rejected(tmp_path):
    _seed(tmp_path, "trav", "x <- 1\n")
    audit = {"status": "partial",
             "repository_audit": {"e": [{"file": "../../etc/passwd", "line": 1}]},
             "reproducibility_blockers": []}
    out = run_cqv("trav", root=tmp_path, complete_fn=_audit_backend(audit))
    assert "snippet" not in out["repository_audit"]["e"][0]


# ---------------------------------------------------------------------------
# Parse-failure repair reprompt (recover a good audit from one bad comma)
# ---------------------------------------------------------------------------

def _repairing_backend(bad_text: str, good: dict):
    """Audit call returns invalid JSON; the repair reprompt returns valid JSON."""
    def fn(model, messages, tools):
        if "repair malformed JSON" in messages[0]["content"]:
            return LLMResponse(text=json.dumps(good))
        return LLMResponse(text=bad_text)
    return fn


def test_invalid_json_recovered_by_repair_reprompt(tmp_path, monkeypatch):
    monkeypatch.setattr(cqv, "_repair_json_deterministic", lambda text: None)
    _seed(tmp_path, "repair", "x <- 1\n")
    bad = '{"status": "partial", "notes": "audit" "execution_readiness": "ready"}'  # missing comma
    good = {"status": "partial", "execution_readiness": "ready",
            "reproducibility_blockers": [], "notes": "recovered audit"}
    out = run_cqv("repair", root=tmp_path, complete_fn=_repairing_backend(bad, good))
    assert out["status"] == "partial"
    assert out["failure_mode"] != "output_parse_failed" if "failure_mode" in out else True
    assert "recovered audit" in out["notes"]
    assert out["execution_readiness"] == "ready"


def test_unrecoverable_json_falls_back_and_keeps_full_raw(tmp_path, monkeypatch):
    monkeypatch.setattr(cqv, "_repair_json_deterministic", lambda text: None)
    _seed(tmp_path, "unrec", "x <- 1\n")
    bad = '{"status": "partial" "broken'  # malformed; repair also fails

    def always_bad(model, messages, tools):
        return LLMResponse(text=bad)  # repair call also returns junk

    out = run_cqv("unrec", root=tmp_path, complete_fn=always_bad)
    assert out["failure_mode"] == "output_parse_failed"
    assert out["status"] == "partial"
    assert bad in out["notes"]  # full raw output preserved, not truncated away


# ---------------------------------------------------------------------------
# Deterministic repair salvage (0028) — recovers structurally-malformed JSON
# ---------------------------------------------------------------------------

def test_deterministic_repair_recovers_simple_delimiter_error(tmp_path):
    pytest.importorskip("json_repair")
    _seed(tmp_path, "detrep", "x <- 1\n")
    bad = '{"status": "partial", "execution_readiness": "ready" "reproducibility_blockers": []}'

    def backend(model, messages, tools):
        return LLMResponse(text=bad)

    out = run_cqv("detrep", root=tmp_path, complete_fn=backend)
    assert out["failure_mode"] == "output_recovered_by_repair"
    assert "deterministic" in out["notes"]
    assert out["execution_readiness"] == "ready"  # field recovered faithfully


def test_repaired_output_is_flagged_and_keeps_raw_for_verification(tmp_path):
    # Repair is best-effort and can drop content; the audit must never present a
    # salvaged result without the marker AND the raw bytes for verification.
    pytest.importorskip("json_repair")
    _seed(tmp_path, "detraw", "x <- 1\n")
    bad = (
        '{"status": "partial", "execution_readiness": {"blockers": '
        '[{"id": "R-2", "evidence": {"file": "a.R", "line": 20}, '
        '{"file": "a.R", "line": 150}]}]}}'  # nested object/array confusion
    )

    def backend(model, messages, tools):
        return LLMResponse(text=bad)

    out = run_cqv("detraw", root=tmp_path, complete_fn=backend)
    assert out["failure_mode"] == "output_recovered_by_repair"
    assert out["raw_model_output"] == bad  # raw retained even though repair guessed


def test_reprompt_used_when_deterministic_repair_unavailable(tmp_path, monkeypatch):
    monkeypatch.setattr(cqv, "_repair_json_deterministic", lambda text: None)
    _seed(tmp_path, "fallback", "x <- 1\n")
    bad = '{"status": "partial" "execution_readiness": "ready"}'
    good = {"status": "partial", "execution_readiness": "ready",
            "reproducibility_blockers": [], "notes": "via reprompt"}

    def backend(model, messages, tools):
        if "repair malformed JSON" in messages[0]["content"]:
            return LLMResponse(text=json.dumps(good))
        return LLMResponse(text=bad)

    out = run_cqv("fallback", root=tmp_path, complete_fn=backend)
    assert out["failure_mode"] == "output_recovered_by_repair"
    assert "reprompt" in out["notes"]


# ---------------------------------------------------------------------------
# Schema tightening (0029) — dedupe duplicated blockers; state the contract
# ---------------------------------------------------------------------------

def test_duplicate_blocker_ids_collapsed(tmp_path):
    _seed(tmp_path, "dedup", "x <- 1\n")
    audit = {
        "status": "partial",
        "reproducibility_blockers": [
            {"id": "bj-14", "severity": "HIGH", "description": "abs path"},
            {"id": "bj-10", "severity": "HIGH", "description": "no seed"},
            {"id": "bj-14", "severity": "HIGH", "description": "abs path (dup)"},
        ],
    }

    def backend(model, messages, tools):
        return LLMResponse(text=json.dumps(audit))

    out = run_cqv("dedup", root=tmp_path, complete_fn=backend)
    ids = [b["id"] for b in out["reproducibility_blockers"]]
    assert ids.count("bj-14") == 1  # duplicate collapsed
    assert "bj-10" in ids
    # first occurrence kept (not the "(dup)" one)
    bj14 = next(b for b in out["reproducibility_blockers"] if b["id"] == "bj-14")
    assert bj14["description"] == "abs path"


def test_blockers_without_id_are_all_kept(tmp_path):
    _seed(tmp_path, "noid", "x <- 1\n")
    audit = {"status": "partial", "reproducibility_blockers": [
        {"severity": "HIGH", "description": "a"}, {"severity": "LOW", "description": "b"}]}

    def backend(model, messages, tools):
        return LLMResponse(text=json.dumps(audit))

    out = run_cqv("noid", root=tmp_path, complete_fn=backend)
    assert len(out["reproducibility_blockers"]) == 2  # no id -> never dropped


def test_prompt_states_evidence_array_and_no_duplication():
    from tools.orchestrator.cqv import _user_prompt
    prompt = _user_prompt(Path("/tmp/assets"), "x")
    assert "must be a JSON array" in prompt.replace("MUST", "must")
    assert "exactly ONCE" in prompt or "exactly once" in prompt.lower()
