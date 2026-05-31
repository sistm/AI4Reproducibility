"""Tests for the Review stage runner (tools/orchestrator/review.py).

Seeds upstream kbe/cqv JSONs on disk and injects a fake completion backend that
answers the risk-core call and each markdown call by inspecting the prompt. No
LiteLLM, no network.
"""

from __future__ import annotations

import json
from pathlib import Path

from tools.orchestrator.llm import LLMResponse
from tools.orchestrator.review import _MD_OUTPUTS, run_review

# The 10 top-level keys validate_review.sh requires in risk_matrix.json.
REQUIRED_KEYS = {
    "paper_id", "paper_title", "assessed_at", "assessment_status", "risk_score",
    "risk_level", "verdict", "issues", "required_changes", "upstream_status",
}

GOOD_CORE = json.dumps(
    {
        "risk_score": 40,
        "risk_level": "MEDIUM",
        "verdict": "MINOR REVISION",
        "issues": {"critical": [], "major": [{"id": "M1", "description": "x", "evidence": "cqv/repo_analysis.md"}], "minor": [], "suggestions": []},
        "required_changes": [{"id": "R1", "description": "fix", "addresses": ["M1"], "done": False}],
    }
)


def _seed(root: Path, title: str, kbe: dict | None, cqv: dict | None) -> None:
    base = root / "ai4r" / title
    if kbe is not None:
        (base / "kbe").mkdir(parents=True, exist_ok=True)
        (base / "kbe" / "kbe_output.json").write_text(json.dumps(kbe))
    if cqv is not None:
        (base / "cqv").mkdir(parents=True, exist_ok=True)
        (base / "cqv" / "cqv_output.json").write_text(json.dumps(cqv))


def _backend(core: str = GOOD_CORE, md: str = "# report\n"):
    def b(model, messages, tools):
        u = messages[-1]["content"]
        if '"risk_score"' in u and "Return ONLY" in u:
            return LLMResponse(text=core)
        return LLMResponse(text=md)

    return b


def _raises(model, messages, tools):
    raise RuntimeError("gateway down")


def _rm(root: Path, title: str) -> dict:
    return json.loads((root / "ai4r" / title / "review" / "risk_matrix.json").read_text())


def _files_exist(root: Path, title: str) -> bool:
    rdir = root / "ai4r" / title / "review"
    return (rdir / "risk_matrix.json").is_file() and all((rdir / n).is_file() for n in _MD_OUTPUTS)


def test_complete_success(tmp_path):
    _seed(tmp_path, "p", {"status": "success", "paper_title": "A Title"}, {"status": "success"})
    rm = run_review("p", root=tmp_path, complete_fn=_backend())
    assert rm["assessment_status"] == "complete"
    assert rm["verdict"] == "MINOR REVISION"
    assert rm["paper_id"] == "p"
    assert rm["paper_title"] == "A Title"
    assert REQUIRED_KEYS <= set(_rm(tmp_path, "p"))
    assert _files_exist(tmp_path, "p")


def test_partial_when_upstream_degraded(tmp_path):
    _seed(tmp_path, "p", {"status": "partial", "paper_title": "T"}, {"status": "success"})
    rm = run_review("p", root=tmp_path, complete_fn=_backend())
    assert rm["assessment_status"] == "partial"
    assert rm["upstream_status"]["kbe"]["status"] == "partial"
    assert rm["verdict"] in {"ACCEPT", "MINOR REVISION", "MAJOR REVISION", "REJECT"}


def test_all_upstream_failed_is_deterministic_no_model(tmp_path):
    _seed(tmp_path, "p",
          {"status": "failed", "failure_mode": "pdf_unreadable", "paper_title": None},
          {"status": "failed", "failure_mode": "assets_directory_empty"})
    # backend raises: proves the failed path does NOT call the model
    rm = run_review("p", root=tmp_path, complete_fn=_raises)
    assert rm["assessment_status"] == "failed"
    assert rm["verdict"] == "UNABLE_TO_ASSESS"
    assert rm["failure_mode"] == "all_upstream_failed"
    assert rm["risk_score"] is None and rm["risk_level"] is None
    assert rm["upstream_status"]["kbe"]["failure_mode"] == "pdf_unreadable"
    assert _files_exist(tmp_path, "p")


def test_missing_upstream_files_treated_as_failed(tmp_path):
    (tmp_path / "ai4r" / "p").mkdir(parents=True)  # no kbe/cqv files
    rm = run_review("p", root=tmp_path, complete_fn=_raises)
    assert rm["assessment_status"] == "failed"
    assert rm["upstream_status"]["kbe"]["status"] == "missing"


def test_risk_core_transport_failure_is_failed_but_writes_files(tmp_path):
    _seed(tmp_path, "p", {"status": "success", "paper_title": "T"}, {"status": "success"})
    rm = run_review("p", root=tmp_path, complete_fn=_raises)
    assert rm["assessment_status"] == "failed"
    assert rm["failure_mode"] == "risk_matrix_schema_error"
    assert _files_exist(tmp_path, "p")


def test_invalid_verdict_is_coerced(tmp_path):
    _seed(tmp_path, "p", {"status": "success", "paper_title": "T"}, {"status": "success"})
    bad = json.dumps({"risk_score": 10, "risk_level": "LOW", "verdict": "LGTM", "issues": {}, "required_changes": []})
    rm = run_review("p", root=tmp_path, complete_fn=_backend(core=bad))
    assert rm["verdict"] in {"ACCEPT", "MINOR REVISION", "MAJOR REVISION", "REJECT"}
    assert set(rm["issues"]) == {"critical", "major", "minor", "suggestions"}


def test_risk_level_derived_from_score_when_missing(tmp_path):
    _seed(tmp_path, "p", {"status": "success", "paper_title": "T"}, {"status": "success"})
    core = json.dumps({"risk_score": 80, "verdict": "REJECT", "issues": {}, "required_changes": []})
    rm = run_review("p", root=tmp_path, complete_fn=_backend(core=core))
    assert rm["risk_level"] == "CRITICAL"  # 80 -> CRITICAL


def test_markdown_failure_is_placeholdered_not_fatal(tmp_path):
    _seed(tmp_path, "p", {"status": "success", "paper_title": "T"}, {"status": "success"})

    def flaky(model, messages, tools):
        u = messages[-1]["content"]
        if '"risk_score"' in u:
            return LLMResponse(text=GOOD_CORE)
        raise RuntimeError("md boom")  # all markdown calls fail

    rm = run_review("p", root=tmp_path, complete_fn=flaky)
    assert rm["assessment_status"] == "complete"  # verdict stands
    assert _files_exist(tmp_path, "p")
    fr = (tmp_path / "ai4r" / "p" / "review" / "final_review.md").read_text()
    assert "Generation failed" in fr


def test_paper_title_copied_from_kbe_null(tmp_path):
    _seed(tmp_path, "p", {"status": "success", "paper_title": None}, {"status": "success"})
    rm = run_review("p", root=tmp_path, complete_fn=_backend())
    assert rm["paper_title"] is None


def test_non_kebab_title_rejected(tmp_path):
    rm = run_review("Not Kebab", root=tmp_path, complete_fn=_backend())
    assert rm["assessment_status"] == "failed"
    assert REQUIRED_KEYS <= set(rm)


def test_log_written(tmp_path):
    _seed(tmp_path, "p", {"status": "success", "paper_title": "T"}, {"status": "success"})
    run_review("p", root=tmp_path, complete_fn=_backend())
    log = (tmp_path / "ai4r" / "p" / "logs" / "workflow.log").read_text()
    assert "REVIEW assessment_status=complete" in log
