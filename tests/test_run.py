"""Tests for the top-level pipeline orchestrator (tools/orchestrator/run.py).

These exercise the real chain with injected fakes (no LiteLLM, no PDF backend)
AND the REAL bash pre/post-flight scripts via subprocess, so the end-to-end
test proves what unit asserts cannot: that ``validate_review.sh`` actually
exits 0 on a healthy run (verification discipline, HANDOFF §5). Tests that need
bash skip cleanly where it is unavailable.
"""

from __future__ import annotations

import json
import shutil

import pytest

from tools.orchestrator.llm import LLMResponse
from tools.orchestrator.run import run_pipeline

_KBE_FIELDS = (
    "paper_title",
    "structured_knowledge",
    "identified_assumptions",
    "statistical_methods",
    "data_generation_processes",
    "reproducibility_gaps",
)

needs_bash = pytest.mark.skipif(
    shutil.which("bash") is None, reason="bash required for pre/post-flight scripts"
)


def _fake_backend(model, messages, tools):
    """One fake answering every stage's calls by inspecting the prompt.

    KBE issues one sectioned call per field (the prompt embeds the JSON shape
    ``{"<field>": ...}``); CQV and Review issue a single final-answer call each.
    Returning a response with no tool_calls terminates run_agent immediately.

    Detection must key on tokens unique to each *request*: the Review prompts
    embed the upstream CQV JSON (which mentions ``repository_audit``), so CQV is
    matched only by ``"as your final message"``, which appears solely in the CQV
    request itself.
    """
    u = messages[-1]["content"]

    # KBE sectioned calls: detect the field from the requested JSON shape. The
    # shape token "{\"<field>\"" never appears in embedded upstream JSON, where
    # those keys are preceded by ", " rather than "{".
    for field in _KBE_FIELDS:
        if '{"' + field + '"' in u:
            value: object = "A Reproducible Biostat Paper" if field == "paper_title" else []
            return LLMResponse(text=json.dumps({field: value}))

    # CQV final answer (token unique to the CQV request prompt).
    if "as your final message" in u:
        return LLMResponse(
            text=json.dumps(
                {
                    "status": "success",
                    "repository_audit": {"files_seen": 1},
                    "code_method_alignment": "consistent",
                    "dependency_validation": "declared",
                    "execution_readiness": "ready",
                    "reproducibility_blockers": [],
                    "partial_data": None,
                    "notes": "Fake CQV audit.",
                }
            )
        )

    # Review risk-matrix core.
    if '"risk_score"' in u and "Return ONLY" in u:
        return LLMResponse(
            text=json.dumps(
                {
                    "risk_score": 30,
                    "risk_level": "MEDIUM",
                    "verdict": "MINOR REVISION",
                    "issues": {"critical": [], "major": [], "minor": [], "suggestions": []},
                    "required_changes": [],
                }
            )
        )

    # Review markdown sections. Satisfies the per-section validators added in
    # patch 0036 (>= _MIN_MD_CHARS, plus a heading + verdict token + [PASS]
    # token to clear all three structural-marker checks at once).
    return LLMResponse(
        text=(
            "# Report\n\n"
            "Verdict: **MINOR REVISION**\n\n"
            "## Checklist\n"
            "- [x] **[PASS]** bj-01-readme — README present.\n\n"
            "This fake synthesis body exists only to clear the minimum-length "
            "threshold and carry each markdown file's structural marker so the "
            "end-to-end test reflects a well-formed pipeline run.\n"
        )
    )


def _fake_extract(_pdf_path):
    # >= _MIN_TEXT_CHARS (500) so KBE proceeds past the short-text guard.
    return "Reproducible biostatistics manuscript. " * 40


def _seed_inputs(root, title, *, with_pdf=True, with_asset=True):
    """Create the input layout a real run expects before pre-flight runs."""
    base = root / "ai4r" / title / "input"
    (base / "assets").mkdir(parents=True, exist_ok=True)
    if with_pdf:
        (base / "paper.pdf").write_bytes(b"%PDF-1.4 fake bytes for the fixture\n")
    if with_asset:
        (base / "assets" / "analysis.R").write_text("set.seed(1)\nx <- rnorm(10)\n")


@needs_bash
def test_full_chain_passes_validator(tmp_path):
    title = "healthy-run"
    _seed_inputs(tmp_path, title)
    summary = run_pipeline(
        title, root=tmp_path, complete_fn=_fake_backend, extract_fn=_fake_extract
    )

    assert summary["ok"] is True  # the real validate_review.sh exited 0
    assert summary["steps"]["prepare"]["exit_code"] == 0
    assert summary["steps"]["kbe"]["status"] == "success"
    assert summary["steps"]["cqv"]["status"] == "success"
    assert summary["steps"]["er"]["status"] == "skipped"
    assert summary["steps"]["review"]["assessment_status"] == "complete"
    assert summary["steps"]["validate"]["exit_code"] == 0

    # Every contract file the gate requires exists.
    base = tmp_path / "ai4r" / title
    for rel in (
        "kbe/kbe_output.json",
        "cqv/cqv_output.json",
        "er/er_output.json",
        "review/risk_matrix.json",
        "review/final_review.md",
        "review/checklist.md",
        "review/exhaustive_audit_report.md",
    ):
        assert (base / rel).is_file(), rel


@needs_bash
def test_er_stub_is_skipped_and_minimal(tmp_path):
    title = "er-stub"
    _seed_inputs(tmp_path, title)
    run_pipeline(title, root=tmp_path, complete_fn=_fake_backend, extract_fn=_fake_extract)
    er = json.loads((tmp_path / "ai4r" / title / "er" / "er_output.json").read_text())
    assert er["status"] == "skipped"
    assert er["paper_id"] == title


@needs_bash
def test_degraded_run_still_passes_gate(tmp_path):
    # No asset files -> CQV fails (assets_directory_empty), but the chain still
    # produces a complete, well-formed artifact set, so the gate passes.
    title = "degraded-run"
    _seed_inputs(tmp_path, title, with_asset=False)
    summary = run_pipeline(
        title, root=tmp_path, complete_fn=_fake_backend, extract_fn=_fake_extract
    )
    assert summary["steps"]["cqv"]["status"] == "failed"
    assert summary["steps"]["review"]["assessment_status"] == "partial"
    assert summary["ok"] is True  # gate checks file/key presence, not health


@needs_bash
def test_missing_pdf_hard_stops_at_prepare(tmp_path):
    title = "no-pdf"
    _seed_inputs(tmp_path, title, with_pdf=False)
    summary = run_pipeline(
        title, root=tmp_path, complete_fn=_fake_backend, extract_fn=_fake_extract
    )
    assert summary["ok"] is False
    assert summary["failed_at"] == "prepare"
    assert "kbe" not in summary["steps"]  # nothing downstream ran
    assert not (tmp_path / "ai4r" / title / "kbe" / "kbe_output.json").exists()


@needs_bash
def test_non_kebab_title_rejected_by_prepare(tmp_path):
    summary = run_pipeline(
        "Not Kebab", root=tmp_path, complete_fn=_fake_backend, extract_fn=_fake_extract
    )
    assert summary["ok"] is False
    assert summary["failed_at"] == "prepare"


def test_skipping_scripts_still_writes_er_stub(tmp_path):
    # No bash needed: with pre/post-flight off, the pure-Python chain still runs
    # and the ER stub is written so Review has well-formed upstream.
    title = "no-scripts"
    _seed_inputs(tmp_path, title)
    summary = run_pipeline(
        title,
        root=tmp_path,
        complete_fn=_fake_backend,
        extract_fn=_fake_extract,
        run_prepare=False,
        run_validate=False,
    )
    assert summary["ok"] is None  # gate skipped -> no pass/fail claim
    assert "prepare" not in summary["steps"]
    er = json.loads((tmp_path / "ai4r" / title / "er" / "er_output.json").read_text())
    assert er["status"] == "skipped"
    assert summary["steps"]["review"]["assessment_status"] == "complete"


@needs_bash
def test_main_exit_code(tmp_path, monkeypatch):
    from tools.orchestrator import run as run_mod

    title = "cli-exit"
    _seed_inputs(tmp_path, title)

    real = run_mod.run_pipeline

    def with_fakes(rt, **kw):
        kw.setdefault("complete_fn", _fake_backend)
        kw.setdefault("extract_fn", _fake_extract)
        return real(rt, **kw)

    monkeypatch.setattr(run_mod, "run_pipeline", with_fakes)
    assert run_mod.main([title, "--root", str(tmp_path)]) == 0
