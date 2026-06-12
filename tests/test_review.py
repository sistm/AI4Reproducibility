"""Tests for the Review stage runner (tools/orchestrator/review.py).

Seeds upstream kbe/cqv JSONs on disk and injects a fake completion backend that
answers the risk-core call and each markdown call by inspecting the prompt. No
LiteLLM, no network.
"""

from __future__ import annotations

import json
from pathlib import Path

from tools.orchestrator.llm import LLMResponse
from tools.orchestrator.review import (
    _MD_OUTPUTS,
    _SOURCE_CAP,
    _adjudicate_one,
    _build_vision_messages,
    _checklist_prompt,
    _context_blob,
    _load_checklist_rubric,
    _run_visual_adjudications,
    run_review,
)

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


# Default md stub satisfies all three structural validators (heading, verdict
# token, [PASS] checklist token) and clears the _MIN_MD_CHARS threshold.
_GOOD_MD = (
    "# Review report\n\n"
    "Verdict: **MINOR REVISION**\n\n"
    "## Checklist\n"
    "- [x] **[PASS]** bj-01-readme — README is present.\n"
    "- [x] **[PASS]** bj-02-run-instructions — entry point identified.\n\n"
    "Overall this is a placeholder body whose only purpose is to be long enough "
    "to satisfy the per-section minimum-length validator while carrying the "
    "structural markers each markdown file needs.\n"
)


# Default critique response: no_concerns (positive endorsement). Tests that
# need a specific critique payload override via the `critique=` parameter.
_GOOD_CRITIQUE = '{"status": "no_concerns", "concerns": []}'

# Default Synthesiser AUDIT response (patch 0051 Call 1): empty
# addressed_concerns. _normalise_addressed will auto-defer any actionable
# concerns the critique surfaced. Tests that need a substantive audit override
# via the `synth_audit=` parameter.
_GOOD_SYNTH_AUDIT = '{"addressed_concerns": []}'

# Default Synthesiser REVISIONS response (patch 0051 Call 2): no revisions.
# Only called when the audit pass marked at least one concern as
# "incorporated"; for the default audit (empty), this is never reached.
_GOOD_SYNTH_REVISIONS = (
    '{"revised_risk_matrix": null, "revised_markdown_files": null}'
)


def _backend(
    core: str = GOOD_CORE,
    md: str = _GOOD_MD,
    critique: str = _GOOD_CRITIQUE,
    synth_audit: str = _GOOD_SYNTH_AUDIT,
    synth_revisions: str = _GOOD_SYNTH_REVISIONS,
):
    def b(model, messages, tools):
        u = messages[-1]["content"]
        # Synthesis revisions call (Call 2): the only prompt with this tag.
        if "<incorporated_concerns>" in u:
            return LLMResponse(text=synth_revisions)
        # Synthesis audit call (Call 1): has critic_concerns but not
        # incorporated_concerns. Must check AFTER incorporated.
        if "<critic_concerns>" in u:
            return LLMResponse(text=synth_audit)
        # Critic prompt has draft tags but no critic_concerns (it produces them).
        if "<draft_risk_matrix>" in u:
            return LLMResponse(text=critique)
        # Risk-matrix core call.
        if '"risk_score"' in u and "Return ONLY" in u:
            return LLMResponse(text=core)
        # Markdown calls.
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
    assert rm["failure_mode"] == "llm_request_failed"
    assert _files_exist(tmp_path, "p")


def test_risk_core_parse_failure_retains_raw(tmp_path, monkeypatch):
    """Unparseable core AND both repair paths failing -> failed + raw retained."""
    from tools.orchestrator import review as review_mod

    _seed(tmp_path, "p", {"status": "success", "paper_title": "T"}, {"status": "success"})
    garbage = "this is not JSON at all {{{"
    # Disable both repair paths so we hit the final fail+retain branch deterministically.
    monkeypatch.setattr(review_mod, "_repair_json_deterministic", lambda text: None)
    monkeypatch.setattr(
        review_mod, "_repair_json_once",
        lambda bad_text, error, *, model, complete_fn: None,
    )
    rm = run_review("p", root=tmp_path, complete_fn=_backend(core=garbage))
    assert rm["assessment_status"] == "failed"
    assert rm["failure_mode"] == "output_parse_failed"
    assert rm["raw_model_output"] == garbage
    assert _files_exist(tmp_path, "p")
    # The retained raw is also serialised to risk_matrix.json on disk.
    assert _rm(tmp_path, "p")["raw_model_output"] == garbage


def test_risk_core_deterministic_repair_recovers(tmp_path, monkeypatch):
    """A malformed-but-repairable core is salvaged deterministically; raw retained, flagged."""
    from tools.orchestrator import review as review_mod

    _seed(tmp_path, "p", {"status": "success", "paper_title": "T"}, {"status": "success"})
    malformed = '{"risk_score": 30, "risk_level": "MEDIUM", "verdict": "MINOR REVISION"'  # missing closing braces
    repaired = {
        "risk_score": 30, "risk_level": "MEDIUM", "verdict": "MINOR REVISION",
        "issues": {"critical": [], "major": [], "minor": [], "suggestions": []},
        "required_changes": [],
    }
    monkeypatch.setattr(review_mod, "_repair_json_deterministic", lambda text: repaired)
    rm = run_review("p", root=tmp_path, complete_fn=_backend(core=malformed))
    assert rm["assessment_status"] == "complete"  # recovery is non-fatal
    assert rm["failure_mode"] == "output_recovered_by_repair"
    assert rm["verdict"] == "MINOR REVISION"
    assert rm["raw_model_output"] == malformed
    assert "deterministic" in rm["notes"]


def test_risk_core_reprompt_repair_recovers(tmp_path, monkeypatch):
    """Deterministic fails, model reprompt repairs; raw retained, flagged."""
    from tools.orchestrator import review as review_mod

    _seed(tmp_path, "p", {"status": "success", "paper_title": "T"}, {"status": "success"})
    malformed = '{"risk_score": 40, "verdict": "MINOR REVISION" oops'
    # Verdict matches _GOOD_MD's text so reconciliation (patch 0053, Invariant 1)
    # doesn't flag rm/md mismatch — this test exercises the salvage chain only.
    repaired = {
        "risk_score": 40, "risk_level": "MEDIUM", "verdict": "MINOR REVISION",
        "issues": {"critical": [], "major": [], "minor": [], "suggestions": []},
        "required_changes": [],
    }
    monkeypatch.setattr(review_mod, "_repair_json_deterministic", lambda text: None)
    monkeypatch.setattr(
        review_mod, "_repair_json_once",
        lambda bad_text, error, *, model, complete_fn: repaired,
    )
    rm = run_review("p", root=tmp_path, complete_fn=_backend(core=malformed))
    assert rm["assessment_status"] == "complete"
    assert rm["failure_mode"] == "output_recovered_by_repair"
    assert rm["verdict"] == "MINOR REVISION"
    assert rm["raw_model_output"] == malformed
    assert "reprompt" in rm["notes"]


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
    # All md placeholders are too short to pass _validate_md_section -> partial.
    # Verdict still stands (risk_matrix synthesis succeeded), files exist,
    # original generation-failure diagnostic is preserved on disk.
    assert rm["assessment_status"] == "partial"
    assert rm["verdict"] == "MINOR REVISION"
    assert "markdown validation failed" in rm["notes"]
    assert _files_exist(tmp_path, "p")
    fr = (tmp_path / "ai4r" / "p" / "review" / "final_review.md").read_text()
    assert "Generation failed" in fr  # diagnostic kept, not overwritten


def test_md_validation_empty_section_degrades_to_partial(tmp_path):
    """A model returning whitespace for an md call degrades complete -> partial."""
    _seed(tmp_path, "p", {"status": "success", "paper_title": "T"}, {"status": "success"})

    def per_file(model, messages, tools):
        u = messages[-1]["content"]
        if '"risk_score"' in u:
            return LLMResponse(text=GOOD_CORE)
        if "Reproducibility checklist" in u or "Checklist rubric" in u:
            return LLMResponse(text="   \n\n  ")  # empty checklist
        return LLMResponse(text=_GOOD_MD)  # other md files fine

    rm = run_review("p", root=tmp_path, complete_fn=per_file)
    assert rm["assessment_status"] == "partial"
    assert "checklist.md" in rm["notes"]
    assert "too short" in rm["notes"]


def test_md_validation_missing_structural_marker_degrades(tmp_path):
    """A long-but-marker-free section (e.g. final_review.md sans verdict) degrades."""
    _seed(tmp_path, "p", {"status": "success", "paper_title": "T"}, {"status": "success"})
    # 400 chars of prose with no verdict token, no [PASS]/[FAIL], no heading.
    bland = "lorem ipsum " * 40

    def per_file(model, messages, tools):
        u = messages[-1]["content"]
        if '"risk_score"' in u:
            return LLMResponse(text=GOOD_CORE)
        if "Final Review" in u:
            return LLMResponse(text=bland)  # missing verdict token
        return LLMResponse(text=_GOOD_MD)

    rm = run_review("p", root=tmp_path, complete_fn=per_file)
    assert rm["assessment_status"] == "partial"
    assert "final_review.md" in rm["notes"]
    assert "missing verdict token" in rm["notes"]


def test_md_validation_passes_for_well_formed_md(tmp_path):
    """All md sections valid -> assessment_status stays complete, no md note."""
    _seed(tmp_path, "p", {"status": "success", "paper_title": "T"}, {"status": "success"})
    rm = run_review("p", root=tmp_path, complete_fn=_backend())
    assert rm["assessment_status"] == "complete"
    assert "markdown validation failed" not in rm.get("notes", "")


def test_md_validation_preserves_recovery_note(tmp_path, monkeypatch):
    """If risk_matrix was recovered AND md fails, both notes appear."""
    from tools.orchestrator import review as review_mod

    _seed(tmp_path, "p", {"status": "success", "paper_title": "T"}, {"status": "success"})
    malformed = '{"risk_score": 30, "verdict": "REJECT"'  # malformed
    repaired = {
        "risk_score": 30, "risk_level": "MEDIUM", "verdict": "REJECT",
        "issues": {"critical": [], "major": [], "minor": [], "suggestions": []},
        "required_changes": [],
    }
    monkeypatch.setattr(review_mod, "_repair_json_deterministic", lambda text: repaired)

    def per_file(model, messages, tools):
        u = messages[-1]["content"]
        if '"risk_score"' in u:
            return LLMResponse(text=malformed)
        return LLMResponse(text="too short")  # all md fail validation

    rm = run_review("p", root=tmp_path, complete_fn=per_file)
    # md failed -> partial. Recovery note + md note both present.
    assert rm["assessment_status"] == "partial"
    assert "recovered from malformed JSON" in rm["notes"]
    assert "markdown validation failed" in rm["notes"]
    assert rm["raw_model_output"] == malformed


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


# ---------------------------------------------------------------------------
# _context_blob — selective serialisation (patch 0033)
# ---------------------------------------------------------------------------

def test_kbe_bookkeeping_fields_stripped():
    """_KBE_STRIP fields must not appear in the serialised kbe blob."""
    kbe = {
        "paper_id": "p",
        "paper_title": "T",
        "status": "success",
        "structured_knowledge": [{"type": "method", "content": "DP MTP"}],
        "partial_data": {"should": "be stripped"},
        "notes": "internal note",
        "extraction_timestamp": "2026-06-02T00:00:00Z",
    }
    blob = _context_blob(kbe, None, None)
    assert "partial_data" not in blob
    assert "internal note" not in blob
    assert "extraction_timestamp" not in blob
    # Substantive fields must survive
    assert "structured_knowledge" in blob
    assert "DP MTP" in blob


def test_cqv_bookkeeping_fields_stripped():
    """_CQV_STRIP fields must not appear in the serialised cqv blob."""
    cqv = {
        "status": "partial",
        "paper_id": "p",
        "repository_audit": {"code_method_alignment": []},
        "statistical_validity": [{"item_id": "cqv-stat-multiple-testing", "verdict": "fail"}],
        "raw_model_output": "huge raw string",
        "partial_data": {"checks_failed": ["check_absolute_paths"]},
        "notes": "static checks completed",
        "audit_timestamp": "2026-06-02T05:17:45Z",
        "dependency_validation": None,
        "execution_readiness": "unknown",
    }
    blob = _context_blob(None, cqv, None)
    assert "raw_model_output" not in blob
    assert "huge raw string" not in blob
    assert "audit_timestamp" not in blob
    assert "execution_readiness" not in blob
    # Substantive fields must survive
    assert "statistical_validity" in blob
    assert "cqv-stat-multiple-testing" in blob
    assert "repository_audit" in blob


def test_all_stat_judges_visible_after_strip():
    """All 7 stat-validity judges from the smoke-test CQV must be visible."""
    import json as _json

    fixture = Path(__file__).parent / "fixtures" / "smoke_test_cqv.json"
    cqv = _json.loads(fixture.read_text())

    blob = _context_blob(None, cqv, None)
    expected_judges = [
        "cqv-stat-test-assumptions",
        "cqv-stat-multiple-testing",
        "cqv-stat-no-data-leakage",
        "cqv-stat-ci-coverage",
        "cqv-stat-representative-sampling",
        "cqv-stat-no-post-hoc",
        "cqv-stat-model-diagnostics",
    ]
    for judge_id in expected_judges:
        assert judge_id in blob, f"stat judge {judge_id!r} missing from context blob"


def test_source_cap_appends_truncation_marker():
    """When a source exceeds _SOURCE_CAP chars the blob ends with [truncated]."""
    big_kbe = {"paper_id": "p", "data": "x" * (_SOURCE_CAP + 1000)}
    blob = _context_blob(big_kbe, None, None)
    assert "[truncated]" in blob


def test_source_cap_is_not_triggered_on_real_outputs():
    """Real smoke-test KBE and CQV must fit within _SOURCE_CAP after stripping."""
    import json as _json

    fixtures = Path(__file__).parent / "fixtures"
    kbe = _json.loads((fixtures / "smoke_test_kbe.json").read_text())
    cqv = _json.loads((fixtures / "smoke_test_cqv.json").read_text())

    blob = _context_blob(kbe, cqv, None)
    assert "[truncated]" not in blob, (
        "Real smoke-test outputs exceed _SOURCE_CAP after stripping — "
        "either outputs have grown or _SOURCE_CAP needs adjusting"
    )


def test_er_none_omitted_from_blob():
    """When er is None the blob must contain exactly kbe and cqv sections."""
    blob = _context_blob({"status": "success"}, {"status": "partial"}, None)
    assert "er_output:" not in blob
    assert "kbe_output:" in blob
    assert "cqv_output:" in blob


def test_er_present_skipped_compact():
    """Skipped ER output stays compact (no preflight/env internals)."""
    er = {"status": "skipped", "reason": "deferred",
          "preflight": {"very": "verbose"}, "execution_environment": {"r": "4"}}
    blob = _context_blob(None, None, er)
    assert "er_output:" in blob
    assert "preflight" not in blob
    assert "execution_environment" not in blob


def test_er_present_executed_uses_structured_summary():
    """Executed ER uses the structured summary, not raw JSON."""
    er = {
        "status": "success",
        "execution_mode": "full_run",
        "checklist_flags": ["MISSING_REPRODUCED_ARTIFACTS"],
        "run": {"returncode": 0, "timed_out": False, "artifacts": ["fig1.png"]},
        "comparisons": [{
            "artifact": "fig-1", "kind": "figure",
            "status": "no_artifact_produced", "method": "none",
            "detail": "no produced file matched", "needs_visual_review": False,
            "metadata": {},
        }],
    }
    blob = _context_blob(None, None, er)
    assert "er_output:" in blob
    assert "MISSING_REPRODUCED_ARTIFACTS" in blob
    assert "no_artifact_produced" in blob.lower() or "NOT PRODUCED" in blob


def test_er_context_mismatch_flagged_shown():
    er = {
        "status": "success", "execution_mode": "full_run",
        "checklist_flags": [],
        "run": {"returncode": 0, "timed_out": False, "artifacts": ["fig1.png"]},
        "comparisons": [{
            "artifact": "fig-1", "kind": "figure",
            "status": "mismatch_flagged", "method": "phash",
            "detail": "pHash distance 22 > 10",
            "needs_visual_review": True,
            "metadata": {"hamming_distance": 22},
        }],
    }
    blob = _context_blob(None, None, er)
    assert "visual" in blob.lower()
    assert "22" in blob


def test_er_context_pass_shown():
    er = {
        "status": "success", "execution_mode": "full_run",
        "checklist_flags": [],
        "run": {"returncode": 0, "timed_out": False, "artifacts": ["fig1.png"]},
        "comparisons": [{
            "artifact": "fig-1", "kind": "figure",
            "status": "pass", "method": "phash",
            "detail": "pHash distance 2 ≤ 10",
            "needs_visual_review": False,
            "metadata": {"hamming_distance": 2},
        }],
    }
    blob = _context_blob(None, None, er)
    assert "REPRODUCED" in blob


def test_risk_prompt_contains_er_rules():
    from tools.orchestrator.review import _risk_prompt
    prompt = _risk_prompt("ctx", "complete")
    assert "MISSING_RUNTIME_DOCS" in prompt
    assert "mismatch_flagged" in prompt
    assert "no_artifact_produced" in prompt


def test_checklist_prompt_contains_er_rules():
    prompt = _checklist_prompt("ctx", "complete")
    assert "mismatch_flagged" in prompt
    assert "MISSING_REPRODUCED_ARTIFACTS" in prompt


# ---------------------------------------------------------------------------
# _checklist_prompt and _load_checklist_rubric (patch 0034)
# ---------------------------------------------------------------------------

def test_rubric_contains_all_24_item_ids():
    """_load_checklist_rubric must include all 24 item IDs from checklist.yaml."""
    from pathlib import Path as _Path

    import yaml

    with open(_Path(__file__).parent.parent / "checklist.yaml") as f:
        data = yaml.safe_load(f)

    rubric = _load_checklist_rubric()
    for item in data["items"]:
        assert item["id"] in rubric, f"item {item['id']!r} missing from rubric"


def test_checklist_prompt_contains_rubric_and_template():
    """_checklist_prompt must embed the rubric and the template skeleton."""
    context = "kbe_output:\n{}\n\ncqv_output:\n{}"
    prompt = _checklist_prompt(context, "partial")

    # Rubric items: spot-check first, middle, and last
    assert "bj-01-readme" in prompt
    assert "bj-07-no-absolute-paths" in prompt
    assert "audit-verify-tables-match" in prompt

    # Template structural tokens must be present for the model to fill
    assert "[VERDICT]" in prompt
    assert "[AUDIT NOTE]" in prompt
    assert "Required action" in prompt

    # Upstream context must be present
    assert "kbe_output:" in prompt
    assert "assessment_status=partial" in prompt


def test_checklist_prompt_contains_all_24_ids():
    """Every item ID from checklist.yaml must appear in the checklist prompt."""
    from pathlib import Path as _Path

    import yaml

    with open(_Path(__file__).parent.parent / "checklist.yaml") as f:
        data = yaml.safe_load(f)

    prompt = _checklist_prompt("kbe_output:\n{}", "complete")
    missing = [item["id"] for item in data["items"] if item["id"] not in prompt]
    assert missing == [], f"Item IDs missing from checklist prompt: {missing}"


def test_run_review_routes_checklist_to_checklist_prompt(tmp_path):
    """The checklist.md call must receive rubric content; others must not."""
    _seed(tmp_path, "p", {"status": "success", "paper_title": "T"}, {"status": "success"})

    seen: dict[str, str] = {}

    def capturing_backend(model, messages, tools):
        u = messages[-1]["content"]
        if '"risk_score"' in u and "Return ONLY" in u:
            return LLMResponse(text=GOOD_CORE)
        # Identify which markdown call this is by unique content
        if "bj-01-readme" in u:
            seen["checklist"] = u
        else:
            seen.setdefault("other", u)
        return LLMResponse(text="# doc\n")

    run_review("p", root=tmp_path, complete_fn=capturing_backend)

    # Checklist prompt must have received the rubric
    assert "checklist" in seen, "No checklist prompt was captured"
    assert "bj-07-no-absolute-paths" in seen["checklist"]
    assert "audit-verify-tables-match" in seen["checklist"]
    assert "[VERDICT]" in seen["checklist"]

    # Other markdown prompts must NOT contain rubric IDs
    if "other" in seen:
        assert "bj-01-readme" not in seen["other"], (
            "Rubric leaked into a non-checklist markdown prompt"
        )


def test_review_prompts_tag_upstream_as_untrusted():
    """Prompt-injection hardening: all three Review prompts fence upstream JSON."""
    from tools.orchestrator.review import _checklist_prompt, _md_prompt, _risk_prompt

    ctx = '{"paper": "T"}'
    for prompt in (
        _risk_prompt(ctx, "complete"),
        _checklist_prompt(ctx, "complete"),
        _md_prompt("a final review", ctx, "complete"),
    ):
        assert "SECURITY" in prompt
        assert "untrusted" in prompt
        assert "<upstream_outputs" in prompt and "</upstream_outputs>" in prompt


# --- Outer code-fence stripping (patch 0043) ----------------------------------


def test_strip_outer_md_fence_unwraps_markdown_tagged_fence():
    from tools.orchestrator.review import _strip_outer_md_fence

    wrapped = "```markdown\n# Title\n\nBody paragraph.\n```"
    assert _strip_outer_md_fence(wrapped) == "# Title\n\nBody paragraph."


def test_strip_outer_md_fence_unwraps_bare_fence():
    from tools.orchestrator.review import _strip_outer_md_fence

    wrapped = "```\n# Title\n\nBody.\n```"
    assert _strip_outer_md_fence(wrapped) == "# Title\n\nBody."


def test_strip_outer_md_fence_preserves_inner_code_blocks():
    """A document with nested ```r ... ``` blocks must keep them intact."""
    from tools.orchestrator.review import _strip_outer_md_fence

    wrapped = (
        "```markdown\n"
        "# Audit\n\n"
        "Run this:\n\n"
        "```r\n"
        "set.seed(1)\n"
        "x <- rnorm(10)\n"
        "```\n\n"
        "And review the output.\n"
        "```"
    )
    out = _strip_outer_md_fence(wrapped)
    assert out.startswith("# Audit")
    assert "```r\nset.seed(1)" in out
    assert out.endswith("And review the output.")


def test_strip_outer_md_fence_no_fence_is_noop():
    from tools.orchestrator.review import _strip_outer_md_fence

    plain = "# Already clean\n\nBody.\n"
    assert _strip_outer_md_fence(plain) == plain


def test_strip_outer_md_fence_unclosed_fence_is_noop():
    """A fence that opens but never closes is corrupted output; leave it alone."""
    from tools.orchestrator.review import _strip_outer_md_fence

    broken = "```markdown\n# Title\n\nNo closing fence here.\n"
    assert _strip_outer_md_fence(broken) == broken


def test_strip_outer_md_fence_empty_and_none_safe():
    from tools.orchestrator.review import _strip_outer_md_fence

    assert _strip_outer_md_fence("") == ""
    assert _strip_outer_md_fence(None) is None


def test_run_review_strips_outer_fence_from_model_output(tmp_path):
    """End-to-end: a model that fence-wraps its markdown -> file on disk is unwrapped."""
    _seed(tmp_path, "p", {"status": "success", "paper_title": "T"}, {"status": "success"})

    # 200+ char body so it clears _MIN_MD_CHARS after unwrapping. Includes the
    # three structural markers (heading, verdict token, [PASS]) so all three
    # md files pass validation.
    body = (
        "# Review report\n\n"
        "Verdict: **MINOR REVISION**\n\n"
        "## Checklist\n"
        "- [x] **[PASS]** bj-01-readme — README present.\n\n"
        "Padding paragraph that exists solely to clear the minimum-length "
        "threshold while still carrying every structural marker the per-file "
        "validators look for in real review output.\n"
    )
    wrapped = f"```markdown\n{body}```"

    rm = run_review("p", root=tmp_path, complete_fn=_backend(md=wrapped))
    assert rm["assessment_status"] == "complete"
    fr = (tmp_path / "ai4r" / "p" / "review" / "final_review.md").read_text()
    assert not fr.lstrip().startswith("```"), "outer fence was not stripped"
    assert "# Review report" in fr


def test_md_prompt_includes_anti_fence_instruction():
    """Prompt-level belt: tell the model not to wrap in the first place."""
    from tools.orchestrator.review import _checklist_prompt, _md_prompt

    md = _md_prompt("a final review", "{}", "complete")
    cl = _checklist_prompt("{}", "complete")
    for p in (md, cl):
        assert "Do NOT wrap" in p
        assert "```markdown" in p  # explicitly names the fence to avoid


# --- Critic integration (patch 0046) -----------------------------------------


def test_critic_runs_on_success_path_writes_critique_json(tmp_path):
    """Happy path: run_review invokes Critic; critique.json on disk."""
    _seed(tmp_path, "p", {"status": "success", "paper_title": "T"}, {"status": "success"})
    rm = run_review("p", root=tmp_path, complete_fn=_backend())
    assert rm["assessment_status"] == "complete"
    cj_path = tmp_path / "ai4r" / "p" / "review" / "critique.json"
    assert cj_path.is_file()
    cj = json.loads(cj_path.read_text())
    assert cj["status"] == "no_concerns"
    assert cj["paper_id"] == "p"


def test_critic_concerns_are_persisted_but_do_not_change_verdict(tmp_path):
    """0046 contract: Critic surfaces concerns but does not modify rm."""
    _seed(tmp_path, "p", {"status": "success", "paper_title": "T"}, {"status": "success"})
    crit_payload = json.dumps({
        "status": "complete",
        "concerns": [{
            "id": "K1",
            "category": "evidence_gap",
            "severity": "blocking",
            "draft_claim": "Critical: missing data files.",
            "concern": "Evidence cite is too generic.",
            # Ref must point at a file that exists on disk at the moment the
            # Critic runs — patch 0050 filters broken refs and downgrades any
            # blocking concern that loses them all. ``_seed`` writes
            # cqv_output.json.
            "evidence_refs": ["ai4r/p/cqv/cqv_output.json"],
            "suggested_action": "Narrow cite to file:line.",
        }],
    })
    rm = run_review("p", root=tmp_path, complete_fn=_backend(critique=crit_payload))
    # rm itself is unchanged: same verdict as the GOOD_CORE fixture.
    assert rm["verdict"] == "MINOR REVISION"
    assert rm["assessment_status"] == "complete"
    # Critique persisted with the blocking concern intact.
    cj = json.loads((tmp_path / "ai4r" / "p" / "review" / "critique.json").read_text())
    assert cj["status"] == "complete"
    assert len(cj["concerns"]) == 1
    assert cj["concerns"][0]["severity"] == "blocking"


def test_critic_failure_is_noted_but_not_fatal(tmp_path):
    """Critic transport failure -> note in rm, assessment_status unchanged."""
    _seed(tmp_path, "p", {"status": "success", "paper_title": "T"}, {"status": "success"})

    # Backend that succeeds on review calls but raises on the Critic call.
    def selective(model, messages, tools):
        u = messages[-1]["content"]
        if "<draft_risk_matrix>" in u:
            raise RuntimeError("critic gateway down")
        if '"risk_score"' in u and "Return ONLY" in u:
            return LLMResponse(text=GOOD_CORE)
        return LLMResponse(text=_GOOD_MD)

    rm = run_review("p", root=tmp_path, complete_fn=selective)
    assert rm["assessment_status"] == "complete"  # NOT degraded
    assert "critique stage failed" in rm["notes"]
    assert "llm_request_failed" in rm["notes"]
    # critique.json exists with failed status (run_critique always writes)
    cj = json.loads((tmp_path / "ai4r" / "p" / "review" / "critique.json").read_text())
    assert cj["status"] == "failed"
    assert cj["failure_mode"] == "llm_request_failed"


def test_critic_receives_upstream_and_draft(tmp_path):
    """Sanity-check the Critic prompt was actually given upstream + draft."""
    _seed(tmp_path, "p", {"status": "success", "paper_title": "T"}, {"status": "success"})
    seen = {"critique_prompt": None}

    def capture(model, messages, tools):
        u = messages[-1]["content"]
        if "<draft_risk_matrix>" in u:
            seen["critique_prompt"] = u
            return LLMResponse(text='{"status": "no_concerns", "concerns": []}')
        if '"risk_score"' in u and "Return ONLY" in u:
            return LLMResponse(text=GOOD_CORE)
        return LLMResponse(text=_GOOD_MD)

    run_review("p", root=tmp_path, complete_fn=capture)
    p = seen["critique_prompt"]
    assert p is not None
    # Both upstream blocks and all three draft md blocks present in the prompt.
    for tag in ("<upstream_kbe>", "<upstream_cqv>", "<draft_risk_matrix>",
                "<draft_final_review>", "<draft_checklist>",
                "<draft_exhaustive_audit_report>"):
        assert tag in p, f"missing {tag} in critique prompt"


def test_critic_does_not_run_on_all_upstream_failed(tmp_path):
    """Early-exit failure paths skip the Critic; no critique.json written."""
    _seed(tmp_path, "p", {"status": "failed"}, {"status": "failed"})
    rm = run_review("p", root=tmp_path, complete_fn=_backend())
    assert rm["assessment_status"] == "failed"
    assert rm["failure_mode"] == "all_upstream_failed"
    cj_path = tmp_path / "ai4r" / "p" / "review" / "critique.json"
    assert not cj_path.exists()  # Critic skipped on hard-fail


# --- Synthesiser final pass (patch 0047) -------------------------------------


def _critique_with(concerns):
    """Helper: build a critique payload with given concern dicts."""
    return json.dumps({"status": "complete", "concerns": concerns})


_CONCERN_BLOCKING = {
    "id": "K1",
    "category": "evidence_gap",
    "severity": "blocking",
    "draft_claim": "Critical: missing data.",
    "concern": "Evidence too generic.",
    "evidence_refs": ["ai4r/p/cqv/cqv_output.json"],
    "suggested_action": "Cite file:line.",
}
_CONCERN_MATERIAL = {**_CONCERN_BLOCKING, "id": "K2", "severity": "material"}
_CONCERN_ADVISORY = {**_CONCERN_BLOCKING, "id": "K3", "severity": "advisory"}


def test_final_pass_skipped_on_no_concerns(tmp_path):
    """no_concerns critique -> no final pass call -> no addressed_concerns in rm."""
    _seed(tmp_path, "p", {"status": "success", "paper_title": "T"}, {"status": "success"})
    call_count = {"synth": 0}

    def counting(model, messages, tools):
        u = messages[-1]["content"]
        if "<critic_concerns>" in u:
            call_count["synth"] += 1
            return LLMResponse(text=_GOOD_SYNTH_AUDIT)
        if "<draft_risk_matrix>" in u:
            return LLMResponse(text=_GOOD_CRITIQUE)
        if '"risk_score"' in u and "Return ONLY" in u:
            return LLMResponse(text=GOOD_CORE)
        return LLMResponse(text=_GOOD_MD)

    rm = run_review("p", root=tmp_path, complete_fn=counting)
    assert call_count["synth"] == 0  # no final pass on no_concerns
    assert "addressed_concerns" not in rm


def test_final_pass_skipped_on_advisory_only(tmp_path):
    """Advisory-only critique -> no final pass (latency proportional to need)."""
    _seed(tmp_path, "p", {"status": "success", "paper_title": "T"}, {"status": "success"})
    call_count = {"synth": 0}

    def counting(model, messages, tools):
        u = messages[-1]["content"]
        if "<critic_concerns>" in u:
            call_count["synth"] += 1
            return LLMResponse(text=_GOOD_SYNTH_AUDIT)
        if "<draft_risk_matrix>" in u:
            return LLMResponse(text=_critique_with([_CONCERN_ADVISORY]))
        if '"risk_score"' in u and "Return ONLY" in u:
            return LLMResponse(text=GOOD_CORE)
        return LLMResponse(text=_GOOD_MD)

    rm = run_review("p", root=tmp_path, complete_fn=counting)
    assert call_count["synth"] == 0
    assert "addressed_concerns" not in rm


def test_final_pass_runs_on_blocking_concern(tmp_path):
    """Blocking concern -> final pass runs -> addressed_concerns in rm."""
    _seed(tmp_path, "p", {"status": "success", "paper_title": "T"}, {"status": "success"})
    rm = run_review("p", root=tmp_path,
                    complete_fn=_backend(critique=_critique_with([_CONCERN_BLOCKING])))
    assert "addressed_concerns" in rm
    # Default synth fixture has empty addressed_concerns, so the blocking
    # concern is auto-deferred.
    assert len(rm["addressed_concerns"]) == 1
    assert rm["addressed_concerns"][0]["id"] == "K1"
    assert rm["addressed_concerns"][0]["resolution"] == "deferred"
    assert "auto-deferred" in rm["addressed_concerns"][0]["reason"]


def test_final_pass_honours_model_supplied_resolutions(tmp_path):
    """When Synthesiser emits explicit resolutions, they win over auto-deferral.

    Includes an actual rm revision so reconciliation (Invariant 2, 0053) does
    not downgrade the 'incorporated' resolution for lack of a diff.
    """
    _seed(tmp_path, "p", {"status": "success", "paper_title": "T"}, {"status": "success"})
    # Patch 0051: audit response is the standalone Call 1.
    audit_response = json.dumps({
        "addressed_concerns": [
            {"id": "K1", "resolution": "incorporated",
             "reason": "Tightened evidence cite to DoFiguresTables.R:12."},
            {"id": "K2", "resolution": "refuted",
             "reason": "Draft already cites the specific line."},
        ],
    })
    # Patch 0053: an incorporated claim needs a real diff to survive
    # reconciliation. Provide a small rm tweak in the revisions response.
    revisions_response = json.dumps({
        "revised_risk_matrix": {
            **{k: v for k, v in json.loads(GOOD_CORE).items()},
            "verdict": "MINOR REVISION",  # same as draft but represents a "decision"
            "risk_score": 35,  # changed from 30 in GOOD_CORE -> real diff
            "paper_id": "p", "paper_title": "T",
            "assessed_at": "2024-01-01T00:00:00Z", "upstream_status": {},
            "assessment_status": "complete",
        },
        "revised_markdown_files": None,
    })
    crit = _critique_with([_CONCERN_BLOCKING, _CONCERN_MATERIAL])
    rm = run_review("p", root=tmp_path,
                    complete_fn=_backend(critique=crit,
                                         synth_audit=audit_response,
                                         synth_revisions=revisions_response))
    by_id = {a["id"]: a for a in rm["addressed_concerns"]}
    assert by_id["K1"]["resolution"] == "incorporated"
    assert by_id["K2"]["resolution"] == "refuted"


def test_final_pass_revises_risk_matrix_when_emitted(tmp_path):
    """A complete revised_risk_matrix from Call 2 replaces the rm core (identity preserved)."""
    _seed(tmp_path, "p", {"status": "success", "paper_title": "T"}, {"status": "success"})
    audit_response = json.dumps({
        "addressed_concerns": [{"id": "K1", "resolution": "incorporated",
                                "reason": "Escalated to MAJOR per blocking concern."}],
    })
    revised_rm = {
        # All ten required top-level keys present:
        "paper_id": "should-be-overwritten",  # orchestrator overrides
        "paper_title": "should-be-overwritten",
        "assessed_at": "1970-01-01T00:00:00Z",
        "upstream_status": {},
        "assessment_status": "complete",
        "verdict": "MAJOR REVISION",  # changed from MINOR
        "risk_score": 70,
        "risk_level": "HIGH",
        "issues": {"critical": [{"id": "C1", "description": "x", "evidence": "y"}],
                   "major": [], "minor": [], "suggestions": []},
        "required_changes": [{"id": "R1", "description": "x", "addresses": ["C1"]}],
    }
    revisions_response = json.dumps({
        "revised_risk_matrix": revised_rm,
        "revised_markdown_files": None,
    })
    rm = run_review("p", root=tmp_path,
                    complete_fn=_backend(critique=_critique_with([_CONCERN_BLOCKING]),
                                         synth_audit=audit_response,
                                         synth_revisions=revisions_response))
    # Revised fields applied:
    assert rm["verdict"] == "MAJOR REVISION"
    assert rm["risk_score"] == 70
    # Orchestrator-owned fields NOT overwritten by model:
    assert rm["paper_id"] == "p"
    assert rm["paper_title"] == "T"
    assert not rm["assessed_at"].startswith("1970")
    # Audit-trail note records the revision:
    assert "synthesis revisions pass applied" in rm["notes"]
    assert "risk_matrix" in rm["notes"]


def test_final_pass_partial_rm_rejected(tmp_path):
    """An rm revision missing required keys is rejected; draft stands.

    Because the draft stands (no diff), reconciliation (patch 0053
    Invariant 2) honestly downgrades the 'incorporated' claim to
    'deferred' — the Synthesiser said it would change something but did
    not.
    """
    _seed(tmp_path, "p", {"status": "success", "paper_title": "T"}, {"status": "success"})
    audit_response = json.dumps({
        "addressed_concerns": [{"id": "K1", "resolution": "incorporated",
                                "reason": "x"}],
    })
    incomplete = {"verdict": "REJECT", "risk_score": 95}  # missing 8 keys
    revisions_response = json.dumps({
        "revised_risk_matrix": incomplete,
        "revised_markdown_files": None,
    })
    rm = run_review("p", root=tmp_path,
                    complete_fn=_backend(critique=_critique_with([_CONCERN_BLOCKING]),
                                         synth_audit=audit_response,
                                         synth_revisions=revisions_response))
    # Draft preserved: still MINOR REVISION from GOOD_CORE fixture
    assert rm["verdict"] == "MINOR REVISION"
    # Reconciliation downgrades the unfulfilled 'incorporated' claim:
    assert rm["addressed_concerns"][0]["resolution"] == "deferred"
    assert "no diff against the draft" in rm["addressed_concerns"][0]["reason"]


def test_final_pass_revises_markdown_files_when_emitted(tmp_path):
    """A revised md file replaces the draft on disk; strip-fence applied."""
    _seed(tmp_path, "p", {"status": "success", "paper_title": "T"}, {"status": "success"})
    audit_response = json.dumps({
        "addressed_concerns": [{"id": "K1", "resolution": "incorporated",
                                "reason": "x"}],
    })
    # The Synthesiser may re-wrap; the strip-fence pass from 0043 must catch it.
    revised_body = (
        "# Final Review (revised)\n\nVerdict: **MAJOR REVISION**\n\n"
        "## Checklist\n- [x] **[PASS]** item\n\n"
        "Revised body that is well over the minimum length threshold so that "
        "validation passes downstream and the final review carries every "
        "structural marker the per-file validators check.\n"
    )
    revisions_response = json.dumps({
        "revised_risk_matrix": None,
        "revised_markdown_files": {
            "final_review.md": f"```markdown\n{revised_body}```",  # re-wrapped
        },
    })
    run_review("p", root=tmp_path,
               complete_fn=_backend(critique=_critique_with([_CONCERN_BLOCKING]),
                                    synth_audit=audit_response,
                                    synth_revisions=revisions_response))
    fr = (tmp_path / "ai4r" / "p" / "review" / "final_review.md").read_text()
    assert not fr.lstrip().startswith("```")  # 0043 strip applied to revision
    assert "Final Review (revised)" in fr


def test_final_pass_unknown_md_filename_silently_dropped(tmp_path):
    """Synthesiser emitting an unrecognised filename is ignored, not crashed."""
    _seed(tmp_path, "p", {"status": "success", "paper_title": "T"}, {"status": "success"})
    audit_response = json.dumps({
        "addressed_concerns": [{"id": "K1", "resolution": "incorporated",
                                "reason": "x"}],
    })
    revisions_response = json.dumps({
        "revised_risk_matrix": None,
        "revised_markdown_files": {"made_up_file.md": "evil content"},
    })
    rm = run_review("p", root=tmp_path,
                    complete_fn=_backend(critique=_critique_with([_CONCERN_BLOCKING]),
                                         synth_audit=audit_response,
                                         synth_revisions=revisions_response))
    rdir = tmp_path / "ai4r" / "p" / "review"
    assert not (rdir / "made_up_file.md").exists()
    assert (rdir / "final_review.md").is_file()
    # No real revision happened, so the "revisions pass applied" note absent.
    assert "synthesis revisions pass applied" not in rm.get("notes", "")


def test_final_pass_llm_transport_failure_falls_back_to_draft(tmp_path):
    """Audit-call LLM failure -> draft stands, every concern auto-deferred.

    Updated for 0051: the failure note now says "synthesis audit pass failed"
    rather than "synthesis final pass failed" because the audit is Call 1.
    """
    _seed(tmp_path, "p", {"status": "success", "paper_title": "T"}, {"status": "success"})

    def selective(model, messages, tools):
        u = messages[-1]["content"]
        # Audit prompt has <critic_concerns> but not <incorporated_concerns>.
        if "<critic_concerns>" in u and "<incorporated_concerns>" not in u:
            raise RuntimeError("synth audit gateway down")
        if "<draft_risk_matrix>" in u:
            return LLMResponse(text=_critique_with([_CONCERN_BLOCKING, _CONCERN_MATERIAL]))
        if '"risk_score"' in u and "Return ONLY" in u:
            return LLMResponse(text=GOOD_CORE)
        return LLMResponse(text=_GOOD_MD)

    rm = run_review("p", root=tmp_path, complete_fn=selective)
    assert rm["assessment_status"] == "complete"  # not degraded
    assert "synthesis audit pass failed" in rm["notes"]
    assert "llm_request_failed" in rm["notes"]
    by_id = {a["id"]: a for a in rm["addressed_concerns"]}
    assert by_id["K1"]["resolution"] == "deferred"
    assert by_id["K2"]["resolution"] == "deferred"


def test_final_pass_parse_failure_falls_back_to_draft(tmp_path, monkeypatch):
    """Audit-call JSON parse + repair exhausted -> draft stands."""
    from tools.orchestrator import review as review_mod

    monkeypatch.setattr(review_mod, "_repair_json_deterministic", lambda text: None)
    monkeypatch.setattr(
        review_mod, "_repair_json_once",
        lambda bad, error, *, model, complete_fn: None,
    )
    _seed(tmp_path, "p", {"status": "success", "paper_title": "T"}, {"status": "success"})
    rm = run_review("p", root=tmp_path,
                    complete_fn=_backend(critique=_critique_with([_CONCERN_BLOCKING]),
                                         synth_audit="not JSON at all {{{"))
    assert "synthesis audit pass failed" in rm["notes"]
    assert "output_parse_failed" in rm["notes"]
    assert rm["addressed_concerns"][0]["resolution"] == "deferred"


def test_revisions_call_failure_preserves_audit_trail(tmp_path):
    """Patch 0051: Call 2 transport failure -> audit persists, no revisions.

    With patch 0053 layered on top: incorporated claims without an actual
    diff get honestly downgraded to deferred by reconciliation. The audit
    trail still persists (K1/K2 still appear in addressed_concerns) but the
    resolutions reflect reality: incorporated -> deferred ("no diff"),
    refuted stays as the Synthesiser's explicit decision.
    """
    _seed(tmp_path, "p", {"status": "success", "paper_title": "T"}, {"status": "success"})
    audit_response = json.dumps({
        "addressed_concerns": [
            {"id": "K1", "resolution": "incorporated",
             "reason": "Will tighten the verdict + cite specifically."},
            {"id": "K2", "resolution": "refuted",
             "reason": "Draft already addresses this in issues.major."},
        ],
    })

    def two_call_selective(model, messages, tools):
        u = messages[-1]["content"]
        if "<incorporated_concerns>" in u:
            raise RuntimeError("revisions gateway down")  # Call 2 dies
        if "<critic_concerns>" in u:
            return LLMResponse(text=audit_response)      # Call 1 succeeds
        if "<draft_risk_matrix>" in u:
            return LLMResponse(text=_critique_with([_CONCERN_BLOCKING, _CONCERN_MATERIAL]))
        if '"risk_score"' in u and "Return ONLY" in u:
            return LLMResponse(text=GOOD_CORE)
        return LLMResponse(text=_GOOD_MD)

    rm = run_review("p", root=tmp_path, complete_fn=two_call_selective)
    by_id = {a["id"]: a for a in rm["addressed_concerns"]}
    # K1's incorporated claim went unfulfilled (revisions died) -> reconciliation
    # downgrades it to deferred with an honest reason.
    assert by_id["K1"]["resolution"] == "deferred"
    assert "no diff" in by_id["K1"]["reason"]
    # K2's refuted resolution was an explicit Synthesiser decision; preserved.
    assert by_id["K2"]["resolution"] == "refuted"
    # Two notes now: synthesis-call-failure + reconciliation downgrade.
    assert "synthesis revisions pass failed" in rm["notes"]
    assert "reconciliation" in rm["notes"]
    # Draft rm/md unchanged.
    assert rm["verdict"] == "MINOR REVISION"


def test_revisions_call_skipped_when_no_incorporated(tmp_path):
    """All concerns refuted -> Call 2 not invoked, no latency cost."""
    _seed(tmp_path, "p", {"status": "success", "paper_title": "T"}, {"status": "success"})
    audit_response = json.dumps({
        "addressed_concerns": [
            {"id": "K1", "resolution": "refuted", "reason": "Already addressed."},
            {"id": "K2", "resolution": "deferred", "reason": "Out of scope."},
        ],
    })
    call_count = {"revisions": 0}

    def counting(model, messages, tools):
        u = messages[-1]["content"]
        if "<incorporated_concerns>" in u:
            call_count["revisions"] += 1
            return LLMResponse(text=_GOOD_SYNTH_REVISIONS)
        if "<critic_concerns>" in u:
            return LLMResponse(text=audit_response)
        if "<draft_risk_matrix>" in u:
            return LLMResponse(text=_critique_with([_CONCERN_BLOCKING, _CONCERN_MATERIAL]))
        if '"risk_score"' in u and "Return ONLY" in u:
            return LLMResponse(text=GOOD_CORE)
        return LLMResponse(text=_GOOD_MD)

    rm = run_review("p", root=tmp_path, complete_fn=counting)
    assert call_count["revisions"] == 0  # no incorporated -> Call 2 skipped
    by_id = {a["id"]: a for a in rm["addressed_concerns"]}
    assert by_id["K1"]["resolution"] == "refuted"
    assert by_id["K2"]["resolution"] == "deferred"


def test_final_pass_blocking_only_addresses_blocking_and_material(tmp_path):
    """Auto-deferral fills in missing required_ids (blocking + material), not advisory."""
    _seed(tmp_path, "p", {"status": "success", "paper_title": "T"}, {"status": "success"})
    crit = _critique_with([_CONCERN_BLOCKING, _CONCERN_MATERIAL, _CONCERN_ADVISORY])
    rm = run_review("p", root=tmp_path, complete_fn=_backend(critique=crit))
    ids = {a["id"] for a in rm["addressed_concerns"]}
    assert ids == {"K1", "K2"}  # K3 advisory omitted from auto-deferral


# --- Synthesiser prompt tightening (patch 0048) -------------------------------
#
# These lock the anti-hedge / verdict-must-cite / concrete-R-row directives
# into the four prompt builders. The directives are belt-and-braces against
# style failures the Critic was deliberately scoped NOT to catch (see
# HANDOFF_supplement_post-0045 "Style linter" queued item). Failures here
# mean the prompt regressed — not that the model misbehaved.


def test_risk_prompt_demands_concrete_required_changes():
    from tools.orchestrator.review import _risk_prompt

    p = _risk_prompt("ctx", "complete")
    # Names the failure mode and gives a concrete example to anchor to.
    assert "concrete and actionable" in p
    assert "action verb" in p
    assert "improve the documentation" in p  # named as a rejected pattern


def test_md_prompt_demands_anti_hedge_and_cited_verdict():
    from tools.orchestrator.review import _md_prompt

    p = _md_prompt("a final review", "ctx", "complete")
    # Anti-hedge: names the specific hedging words to avoid.
    assert "hedging" in p.lower()
    for word in ("may", "might", "could", "appears to"):
        assert word in p
    # Verdict-must-cite: requires anchoring to issue IDs.
    assert "issue ID" in p
    assert "C1" in p or "M2" in p
    # Concrete-R-row: same example pattern as _risk_prompt.
    assert "improve documentation" in p or "improve the documentation" in p


def test_checklist_prompt_demands_concrete_required_actions():
    from tools.orchestrator.review import _checklist_prompt

    p = _checklist_prompt("ctx", "complete")
    # Required-action sub-bullets must be concrete.
    assert "Required action" in p
    assert "concrete" in p
    assert "action verb" in p
    # Named negative pattern.
    assert "Ensure reproducibility" in p or "improve documentation" in p


def test_synthesis_revisions_prompt_carries_style_discipline():
    """Revisions emitted by Call 2 must follow the same style rules."""
    from tools.orchestrator.review import _synthesis_revisions_prompt

    rm = {"verdict": "MINOR REVISION", "risk_score": 50}
    md = {"final_review.md": "x", "checklist.md": "y", "exhaustive_audit_report.md": "z"}
    critique = {"concerns": [{"id": "K1", "severity": "blocking",
                              "draft_claim": "x", "concern": "y"}]}
    incorporated = [{"id": "K1", "resolution": "incorporated", "reason": "z"}]
    p = _synthesis_revisions_prompt(rm, md, critique, incorporated)
    assert "style discipline" in p.lower() or "Style discipline" in p
    assert "hedging" in p.lower()
    assert "concrete action" in p
    assert "issue ID" in p


# --- Reconciliation end-to-end (patch 0053) -----------------------------------


def test_reconciliation_degrades_on_verdict_mismatch_end_to_end(tmp_path):
    """The bimj_202400278 failure mode: rm.verdict != final_review.md verdict.

    Synthesiser audit + revisions cooperate to produce an rm with verdict
    MAJOR while final_review.md still carries the draft's MINOR verdict.
    Reconciliation catches the inconsistency and refuses to ship green.
    """
    _seed(tmp_path, "p", {"status": "success", "paper_title": "T"}, {"status": "success"})

    # Audit incorporates K1, intending to escalate the verdict.
    audit_response = json.dumps({
        "addressed_concerns": [
            {"id": "K1", "resolution": "incorporated",
             "reason": "Escalating verdict to MAJOR per blocking concern."},
        ],
    })
    # Revisions produces a new rm with verdict=MAJOR but does NOT update md.
    revised_rm = {
        **json.loads(GOOD_CORE),
        "verdict": "MAJOR REVISION",
        "paper_id": "p", "paper_title": "T",
        "assessed_at": "2024-01-01T00:00:00Z", "upstream_status": {},
        "assessment_status": "complete",
    }
    revisions_response = json.dumps({
        "revised_risk_matrix": revised_rm,
        "revised_markdown_files": None,  # md stays at draft (MINOR REVISION via _GOOD_MD)
    })

    rm = run_review("p", root=tmp_path,
                    complete_fn=_backend(critique=_critique_with([_CONCERN_BLOCKING]),
                                         synth_audit=audit_response,
                                         synth_revisions=revisions_response))
    # Reconciliation catches it: rm says MAJOR, md says MINOR -> failed.
    assert rm["assessment_status"] == "failed"
    assert rm["failure_mode"] == "verdict_inconsistent"
    assert "verdict mismatch" in rm["notes"]
    assert "MAJOR REVISION" in rm["notes"]
    assert "MINOR REVISION" in rm["notes"]


def test_reconciliation_drops_orphan_addresses_end_to_end(tmp_path):
    """A required_changes entry citing a non-existent issue ID is cleaned."""
    _seed(tmp_path, "p", {"status": "success", "paper_title": "T"}, {"status": "success"})
    # rm core fixture with C1 in issues but R1 addressing BOTH C1 and a phantom BLOCKER-0.
    core_with_orphan = json.dumps({
        "verdict": "MINOR REVISION", "risk_score": 30, "risk_level": "MEDIUM",
        "issues": {
            "critical": [{"id": "C1", "description": "x", "evidence": "y"}],
            "major": [], "minor": [], "suggestions": [],
        },
        "required_changes": [
            {"id": "R1", "description": "z", "addresses": ["C1", "BLOCKER-0"]},
        ],
    })
    rm = run_review("p", root=tmp_path, complete_fn=_backend(core=core_with_orphan))
    # Reconciliation drops BLOCKER-0; C1 stays.
    assert rm["required_changes"][0]["addresses"] == ["C1"]
    assert "dropped 1 orphan" in rm.get("notes", "")


# --- patch 0060: per-call retry budget at the Synthesiser revisions site ---


def test_revisions_complete_fn_passes_injected_through():
    """When the caller injects a complete_fn (tests, or any caller with their
    own retry semantics), it must be returned unchanged — caller owns policy."""
    from tools.orchestrator.review import _revisions_complete_fn

    def injected(model, messages, tools):  # pragma: no cover - identity check
        return LLMResponse(text="x")

    assert _revisions_complete_fn(injected) is injected


def test_revisions_complete_fn_wraps_with_synthesis_revisions_policy(monkeypatch):
    """When complete_fn is None (real pipeline run), the helper must wrap the
    default backend with the synthesis_revisions retry policy. This is the
    behaviour change patch 0060 introduces: Call 2 rides out gateway blips
    that would otherwise force reconciliation to degrade the whole Review.
    """
    from tools.orchestrator import review

    captured: dict = {}

    def spy(*, retries, backoff_cap=None):
        captured["retries"] = retries
        captured["backoff_cap"] = backoff_cap
        return lambda m, ms, ts: LLMResponse(text="ok")

    monkeypatch.setattr(review, "with_retry_policy", spy)
    monkeypatch.delenv("AI4R_NUM_RETRIES_SYNTHESIS_REVISIONS", raising=False)
    monkeypatch.delenv("AI4R_BACKOFF_CAP_SYNTHESIS_REVISIONS", raising=False)

    review._revisions_complete_fn(None)
    # The stage-default values from config.py:
    assert captured["retries"] == 5
    assert captured["backoff_cap"] == 30


def test_revisions_complete_fn_honours_env_overrides(monkeypatch):
    """Operator can tune the policy without code changes via env vars."""
    from tools.orchestrator import review

    captured: dict = {}

    def spy(*, retries, backoff_cap=None):
        captured["retries"] = retries
        captured["backoff_cap"] = backoff_cap
        return lambda m, ms, ts: LLMResponse(text="ok")

    monkeypatch.setattr(review, "with_retry_policy", spy)
    monkeypatch.setenv("AI4R_NUM_RETRIES_SYNTHESIS_REVISIONS", "8")
    monkeypatch.setenv("AI4R_BACKOFF_CAP_SYNTHESIS_REVISIONS", "45")

    review._revisions_complete_fn(None)
    assert captured["retries"] == 8
    assert captured["backoff_cap"] == 45


# --- patch 0055: draft cite-format discipline ---------------------------------


def test_available_evidence_files_lists_existing_files_with_anchor_guidance(tmp_path):
    """The enumerator walks kbe/cqv/er/input, labels each file by anchor form,
    and counts lines for markdown so the model knows the valid extent."""
    from tools.orchestrator.review import _available_evidence_files

    base = tmp_path / "ai4r" / "p"
    (base / "kbe").mkdir(parents=True)
    (base / "kbe" / "kbe_output.json").write_text('{"k": 1}')
    (base / "kbe" / "notes.md").write_text("line 1\nline 2\nline 3\n")
    (base / "cqv").mkdir()
    (base / "cqv" / "cqv_output.json").write_text('{"c": 2}')
    (base / "cqv" / "repo_analysis.md").write_text("only one line\n")

    out = _available_evidence_files(base, "p")

    # JSON files get key-path guidance, NOT line guidance.
    assert "ai4r/p/kbe/kbe_output.json" in out
    assert "ai4r/p/cqv/cqv_output.json" in out
    assert "JSON — cite as PATH#KEY_PATH" in out
    assert "NEVER use #L<n>" in out
    # Markdown files get line bounds.
    assert "ai4r/p/kbe/notes.md" in out
    assert "1 <= n <= 4" in out  # 3 newlines -> 4 line slots
    assert "ai4r/p/cqv/repo_analysis.md" in out
    assert "1 <= n <= 2" in out  # 1 newline -> 2 line slots


def test_available_evidence_files_excludes_review_dir(tmp_path):
    """The Review's own output directory is NOT citable (doesn't exist at
    draft time anyway, but never list a file written by the prompt's own
    output)."""
    from tools.orchestrator.review import _available_evidence_files

    base = tmp_path / "ai4r" / "p"
    (base / "kbe").mkdir(parents=True)
    (base / "kbe" / "kbe_output.json").write_text("{}")
    (base / "review").mkdir()
    (base / "review" / "should_not_appear.md").write_text("x\n")
    (base / "logs").mkdir()
    (base / "logs" / "workflow.log").write_text("x\n")

    out = _available_evidence_files(base, "p")
    assert "kbe_output.json" in out
    assert "should_not_appear" not in out
    assert "workflow.log" not in out


def test_available_evidence_files_empty_workspace_returns_placeholder(tmp_path):
    """Pre-seed call sites (early tests with no on-disk workspace) get a
    placeholder line, not a crash."""
    from tools.orchestrator.review import _available_evidence_files

    out = _available_evidence_files(tmp_path / "ai4r" / "nonexistent", "nonexistent")
    assert "no evidence files" in out


def test_risk_prompt_with_evidence_files_carries_cite_discipline():
    """The cite-format rules and the available-files block are present
    universally
    when ``evidence_files`` is supplied, the list appears
    inside the block, otherwise a placeholder line is shown. The rules are
    always there because they reference the block by name."""
    from tools.orchestrator.review import _risk_prompt

    # With evidence_files: the listing appears inside the block.
    p = _risk_prompt(
        "ctx", "complete",
        evidence_files="  - ai4r/p/kbe/kbe_output.json  [JSON — cite as PATH#KEY_PATH; NEVER use #L<n>]",
    )
    assert "<available_evidence_files>" in p
    assert "ai4r/p/kbe/kbe_output.json" in p
    assert "Cite-format discipline" in p
    # Forbidden forms named explicitly.
    assert "NEVER use #L<n>" in p
    assert "do NOT invent file names" in p
    assert "OMIT the claim" in p
    # Valid forms shown by example.
    assert "key_path" in p.lower() or "KEY_PATH" in p

    # Without evidence_files: placeholder appears, rules still present.
    p_bare = _risk_prompt("ctx", "complete")
    assert "<available_evidence_files>" in p_bare
    assert "no evidence files listed" in p_bare
    assert "Cite-format discipline" in p_bare


def test_md_prompt_with_evidence_files_carries_cite_discipline():
    """Same rules apply to the markdown-document prompts — the smoke run
    showed final_review.md was the worst offender for fabricated cites."""
    from tools.orchestrator.review import _md_prompt

    p = _md_prompt(
        "a final review", "ctx", "complete",
        evidence_files="  - ai4r/p/cqv/cqv_output.json  [JSON — cite as PATH#KEY_PATH; NEVER use #L<n>]",
    )
    assert "<available_evidence_files>" in p
    assert "ai4r/p/cqv/cqv_output.json" in p
    assert "Cite-format discipline" in p
    assert "do NOT invent file names" in p
    # The string-as-line-anchor form is explicitly forbidden (the
    # `#L"reproducibility_gaps"` form seen in the smoke run).
    assert '#L"' in p  # the forbidden example is named


def test_run_review_wires_evidence_files_into_draft_prompts(tmp_path):
    """End-to-end: run_review threads the on-disk file list into both the
    risk_matrix and markdown prompts. This is the wiring patch 0055 adds."""
    _seed(tmp_path, "p", {"status": "success", "paper_title": "T"}, {"status": "success"})

    captured: list[str] = []

    def capturing_backend(model, messages, tools):
        u = messages[-1]["content"]
        captured.append(u)
        if '"risk_score"' in u and "Return ONLY" in u:
            return LLMResponse(text=GOOD_CORE)
        return LLMResponse(text=_GOOD_MD)

    run_review("p", root=tmp_path, complete_fn=capturing_backend)

    # The seed wrote kbe_output.json and cqv_output.json
    # the draft prompts should both list them under <available_evidence_files>.
    risk_prompts = [p for p in captured if '"risk_score"' in p and "Return ONLY" in p]
    assert risk_prompts, "no risk_matrix draft prompt captured"
    rp = risk_prompts[0]
    assert "<available_evidence_files>" in rp
    assert "ai4r/p/kbe/kbe_output.json" in rp
    assert "ai4r/p/cqv/cqv_output.json" in rp
    assert "Cite-format discipline" in rp

    # At least one markdown draft prompt also wired the file list.
    md_prompts = [
        p for p in captured
        if '"risk_score"' not in p and "<available_evidence_files>" in p
    ]
    assert md_prompts, "no markdown draft prompt with evidence_files captured"
    assert "ai4r/p/kbe/kbe_output.json" in md_prompts[0]


def test_run_review_handles_unreadable_markdown_in_evidence_enumeration(tmp_path):
    """If a markdown file is unreadable (encoding error), the enumerator
    falls back to a bound-less guide instead of crashing. End-to-end the
    pipeline must still run."""
    _seed(tmp_path, "p", {"status": "success", "paper_title": "T"}, {"status": "success"})
    # Write a not-quite-utf8 byte sequence to the cqv markdown.
    (tmp_path / "ai4r" / "p" / "cqv" / "repo_analysis.md").write_bytes(b"\xff\xfe broken bytes\n")

    def be(model, messages, tools):
        u = messages[-1]["content"]
        if '"risk_score"' in u and "Return ONLY" in u:
            return LLMResponse(text=GOOD_CORE)
        return LLMResponse(text=_GOOD_MD)

    rm = run_review("p", root=tmp_path, complete_fn=be)
    # No crash, pipeline completed.
    assert rm["paper_id"] == "p"


# --- patch 0062: checklist cite discipline ------------------------------------


def test_checklist_prompt_with_evidence_files_carries_cite_discipline():
    """The checklist prompt requires '[AUDIT NOTE] citing file:line' so it
    also produces cite-bearing output. Same fabrication risk as the
    risk_matrix and final_review prompts — propagate the same discipline."""
    from tools.orchestrator.review import _checklist_prompt

    p = _checklist_prompt(
        "ctx", "complete",
        evidence_files="  - ai4r/p/cqv/cqv_output.json  [JSON — cite as PATH#KEY_PATH; NEVER use #L<n>]",
    )
    assert "<available_evidence_files>" in p
    assert "ai4r/p/cqv/cqv_output.json" in p
    assert "Cite-format discipline" in p
    # Same forbidden-form rules surfaced as in risk/md prompts.
    assert "do NOT invent file names" in p
    assert "NEVER use #L<n>" in p
    assert "OMIT the claim" in p


def test_checklist_prompt_without_evidence_files_uses_placeholder():
    """Bare-call backward-compat: block + rules always present, list is a placeholder."""
    from tools.orchestrator.review import _checklist_prompt

    p = _checklist_prompt("ctx", "complete")
    assert "<available_evidence_files>" in p
    assert "no evidence files listed" in p
    assert "Cite-format discipline" in p
    # Pre-existing structural expectations preserved.
    assert "Required action" in p
    assert "[VERDICT]" in p


def test_run_review_wires_evidence_files_into_checklist_prompt(tmp_path):
    """End-to-end: run_review threads the on-disk file list into the checklist
    prompt (not just risk_matrix and md_prompt)."""
    _seed(tmp_path, "p", {"status": "success", "paper_title": "T"}, {"status": "success"})

    captured: list[str] = []

    def capturing_backend(model, messages, tools):
        u = messages[-1]["content"]
        captured.append(u)
        if '"risk_score"' in u and "Return ONLY" in u:
            return LLMResponse(text=GOOD_CORE)
        return LLMResponse(text=_GOOD_MD)

    run_review("p", root=tmp_path, complete_fn=capturing_backend)

    # Identify the checklist prompt by its rubric tokens.
    checklist_prompts = [p for p in captured if "bj-01-readme" in p]
    assert checklist_prompts, "no checklist prompt captured"
    cl = checklist_prompts[0]
    assert "<available_evidence_files>" in cl
    assert "ai4r/p/kbe/kbe_output.json" in cl
    assert "ai4r/p/cqv/cqv_output.json" in cl
    assert "Cite-format discipline" in cl


# --- patch 0064: enumerate JSON top-level keys in evidence files block ---


def test_summarise_json_top_level_dict_with_arrays(tmp_path):
    """Top-level keys are listed with array lengths shown as `key[N]` and
    non-array keys as bare names. Gives the model concrete anchors."""
    import json

    from tools.orchestrator.review import _summarise_json_top_level

    p = tmp_path / "out.json"
    p.write_text(json.dumps({
        "paper_title": "T",
        "identified_assumptions": [{"a": 1}] * 7,
        "reproducibility_gaps": ["g"] * 13,
        "structured_knowledge": ["s"] * 28,
    }))
    out = _summarise_json_top_level(p)
    assert out is not None
    assert "top-level keys:" in out
    assert "paper_title" in out
    assert "identified_assumptions[7]" in out
    assert "reproducibility_gaps[13]" in out
    assert "structured_knowledge[28]" in out


def test_summarise_json_top_level_dict_empty(tmp_path):
    """Empty dicts have no informative keys to list — return None."""
    from tools.orchestrator.review import _summarise_json_top_level

    p = tmp_path / "empty.json"
    p.write_text("{}")
    assert _summarise_json_top_level(p) is None


def test_summarise_json_top_level_caps_at_12_keys(tmp_path):
    """Very wide JSON gets capped to keep prompt mass bounded; an ellipsis
    indicates more keys exist on disk."""
    import json

    from tools.orchestrator.review import _summarise_json_top_level

    data = {f"k{i}": i for i in range(20)}
    p = tmp_path / "wide.json"
    p.write_text(json.dumps(data))
    out = _summarise_json_top_level(p)
    assert out is not None
    assert "..." in out
    # First 12 keys listed (insertion order in modern Python dicts).
    assert "k0" in out and "k11" in out
    assert "k12" not in out


def test_summarise_json_top_level_top_level_array(tmp_path):
    """A bare top-level array (rare but valid JSON) reports its length."""
    import json

    from tools.orchestrator.review import _summarise_json_top_level

    p = tmp_path / "arr.json"
    p.write_text(json.dumps([1, 2, 3, 4]))
    out = _summarise_json_top_level(p)
    assert out == "top-level array, 4 item(s)"


def test_summarise_json_top_level_malformed_returns_none(tmp_path):
    """Malformed JSON returns None (no crash) so the helper falls back to
    bare 'cite as PATH#KEY_PATH' guidance."""
    from tools.orchestrator.review import _summarise_json_top_level

    p = tmp_path / "bad.json"
    p.write_text("{ malformed")
    assert _summarise_json_top_level(p) is None


def test_summarise_json_top_level_unicode_error_safe(tmp_path):
    """Bytes that aren't valid UTF-8 don't crash the helper."""
    from tools.orchestrator.review import _summarise_json_top_level

    p = tmp_path / "binary.json"
    p.write_bytes(b"\xff\xfe not utf-8")
    assert _summarise_json_top_level(p) is None


def test_available_evidence_files_includes_json_key_summary(tmp_path):
    """End-to-end on the enumerator: each JSON file gets a follow-up
    'top-level keys: ...' line below its main listing entry."""
    import json

    from tools.orchestrator.review import _available_evidence_files

    base = tmp_path / "ai4r" / "p"
    (base / "kbe").mkdir(parents=True)
    (base / "kbe" / "kbe_output.json").write_text(json.dumps({
        "paper_title": "T",
        "reproducibility_gaps": ["g"] * 13,
        "identified_assumptions": [{"a": 1}] * 7,
    }))
    (base / "cqv").mkdir()
    (base / "cqv" / "cqv_output.json").write_text(json.dumps({
        "repository_audit": {"x": 1},
        "statistical_validity": ["s"] * 5,
    }))

    out = _available_evidence_files(base, "p")
    lines = out.splitlines()

    # kbe block: the listing line is followed by the key summary line.
    kbe_idx = next(i for i, line in enumerate(lines) if "kbe_output.json" in line)
    assert "top-level keys:" in lines[kbe_idx + 1]
    assert "reproducibility_gaps[13]" in lines[kbe_idx + 1]
    assert "identified_assumptions[7]" in lines[kbe_idx + 1]

    # cqv block: same pattern.
    cqv_idx = next(i for i, line in enumerate(lines) if "cqv_output.json" in line)
    assert "top-level keys:" in lines[cqv_idx + 1]
    assert "statistical_validity[5]" in lines[cqv_idx + 1]
    assert "repository_audit" in lines[cqv_idx + 1]


def test_available_evidence_files_skips_summary_on_malformed_json(tmp_path):
    """Malformed JSON: listing line stays, summary line is omitted (no crash,
    no misleading guide)."""
    from tools.orchestrator.review import _available_evidence_files

    base = tmp_path / "ai4r" / "p"
    (base / "kbe").mkdir(parents=True)
    (base / "kbe" / "kbe_output.json").write_text("{ malformed")

    out = _available_evidence_files(base, "p")
    assert "kbe_output.json" in out
    assert "top-level keys" not in out


# ---------------------------------------------------------------------------
# LLM visual adjudication (patch 0084)
# ---------------------------------------------------------------------------



def _write_png(path: Path, colour: tuple[int, int, int] = (200, 100, 50)) -> None:
    """Write a tiny valid 2x2 PNG. Avoids Pillow dependency in tests."""
    # Minimal PNG: 2x2 RGB, no compression tricks — just enough for base64 encoding.
    import struct
    import zlib
    def chunk(name: bytes, data: bytes) -> bytes:
        c = name + data
        return struct.pack(">I", len(data)) + c + struct.pack(">I", zlib.crc32(c) & 0xFFFFFFFF)
    raw = b""
    for _ in range(2):         # 2 rows
        raw += b"\x00"         # filter byte
        for __ in range(2):    # 2 pixels
            raw += bytes(colour)
    ihdr = struct.pack(">IIBBBBB", 2, 2, 8, 2, 0, 0, 0)
    png = (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", ihdr)
        + chunk(b"IDAT", zlib.compress(raw))
        + chunk(b"IEND", b"")
    )
    path.write_bytes(png)


def _adj_backend(classification: str = "cosmetic", detail: str = "looks fine"):
    """Fake complete_fn that returns a canned adjudication JSON."""
    def backend(model, messages, tools):
        return LLMResponse(text=json.dumps({
            "classification": classification, "detail": detail,
        }))
    return backend


def _mismatch_comparison(tid: str, matched_file: str) -> dict:
    return {
        "artifact": tid, "kind": "figure",
        "status": "mismatch_flagged", "method": "phash",
        "detail": "pHash distance 18 > 10",
        "needs_visual_review": True,
        "metadata": {"hamming_distance": 18, "matched_file": matched_file},
    }


def _make_target(tid: str, ref_rel: str) -> dict:
    return {
        "id": tid, "kind": "figure", "label": f"Figure {tid}",
        "what_it_shows": "classifier performance",
        "caption": "ROC curves", "source_page": 4,
        "priority": "primary", "reference_path": ref_rel,
    }


# ---- _build_vision_messages ------------------------------------------------

def test_build_vision_messages_returns_list(tmp_path):
    ref = tmp_path / "ref.png"
    rep = tmp_path / "rep.png"
    _write_png(ref)
    _write_png(rep)
    msgs = _build_vision_messages(ref, rep, {"label": "Figure 1"})
    assert msgs is not None
    assert len(msgs) == 1
    content = msgs[0]["content"]
    assert content[0]["type"] == "image"
    assert content[1]["type"] == "image"
    assert content[2]["type"] == "text"


def test_build_vision_messages_none_for_unsupported(tmp_path):
    ref = tmp_path / "ref.svg"
    rep = tmp_path / "rep.png"
    ref.write_text("<svg/>")
    _write_png(rep)
    assert _build_vision_messages(ref, rep, {}) is None


def test_build_vision_messages_includes_context(tmp_path):
    ref = tmp_path / "ref.png"
    rep = tmp_path / "rep.png"
    _write_png(ref)
    _write_png(rep)
    target = {"label": "Figure 3", "what_it_shows": "AUC curves", "caption": "ROC"}
    msgs = _build_vision_messages(ref, rep, target)
    assert msgs is not None
    text_block = msgs[0]["content"][2]["text"]
    assert "Figure 3" in text_block
    assert "AUC curves" in text_block


# ---- _adjudicate_one -------------------------------------------------------

def test_adjudicate_one_cosmetic(tmp_path):
    ref = tmp_path / "ref.png"
    rep = tmp_path / "rep.png"
    _write_png(ref)
    _write_png(rep)
    result = _adjudicate_one(ref, rep, {}, "m", _adj_backend("cosmetic", "font differs"))
    assert result["classification"] == "cosmetic"
    assert "font differs" in result["detail"]


def test_adjudicate_one_substantive(tmp_path):
    ref = tmp_path / "ref.png"
    rep = tmp_path / "rep.png"
    _write_png(ref)
    _write_png(rep)
    result = _adjudicate_one(ref, rep, {}, "m", _adj_backend("substantive", "wrong trend"))
    assert result["classification"] == "substantive"


def test_adjudicate_one_bad_classification_defaults_to_substantive(tmp_path):
    ref = tmp_path / "ref.png"
    rep = tmp_path / "rep.png"
    _write_png(ref)
    _write_png(rep)
    result = _adjudicate_one(ref, rep, {}, "m", _adj_backend("unknown_value", ""))
    assert result["classification"] == "substantive"


def test_adjudicate_one_model_error_returns_error_dict(tmp_path):
    ref = tmp_path / "ref.png"
    rep = tmp_path / "rep.png"
    _write_png(ref)
    _write_png(rep)

    def boom(model, messages, tools):
        raise RuntimeError("network down")

    result = _adjudicate_one(ref, rep, {}, "m", boom)
    assert result["error"] is True
    assert result["classification"] == "substantive"  # safe default


def test_adjudicate_one_unsupported_format(tmp_path):
    ref = tmp_path / "ref.svg"
    rep = tmp_path / "rep.png"
    ref.write_text("<svg/>")
    _write_png(rep)
    result = _adjudicate_one(ref, rep, {}, "m", _adj_backend())
    assert result["skipped"] is True


# ---- _run_visual_adjudications ---------------------------------------------

def test_run_visual_adjudications_cosmetic_becomes_pass(tmp_path):
    ref = tmp_path / "ref.png"
    rep = tmp_path / "rep.png"
    _write_png(ref)
    _write_png(rep)

    kbe_dir = tmp_path / "kbe"
    (kbe_dir / "references").mkdir(parents=True)
    import shutil
    shutil.copy(ref, kbe_dir / "references" / "fig-1.png")

    er = {"status": "success", "comparisons": [
        _mismatch_comparison("fig-1", str(rep)),
    ]}
    kbe = {"reproduction_targets": [_make_target("fig-1", "references/fig-1.png")]}
    review_dir = tmp_path
    result = _run_visual_adjudications(er, kbe, review_dir, "m", _adj_backend("cosmetic"))
    assert result[0]["status"] == "pass"
    assert result[0]["needs_visual_review"] is False
    assert result[0]["visual_adjudication"]["classification"] == "cosmetic"


def test_run_visual_adjudications_substantive_becomes_fail(tmp_path):
    ref = tmp_path / "ref.png"
    rep = tmp_path / "rep.png"
    _write_png(ref)
    _write_png(rep)
    kbe_dir = tmp_path / "kbe"
    (kbe_dir / "references").mkdir(parents=True)
    import shutil
    shutil.copy(ref, kbe_dir / "references" / "fig-1.png")

    er = {"status": "success", "comparisons": [_mismatch_comparison("fig-1", str(rep))]}
    kbe = {"reproduction_targets": [_make_target("fig-1", "references/fig-1.png")]}
    result = _run_visual_adjudications(er, kbe, tmp_path, "m", _adj_backend("substantive"))
    assert result[0]["status"] == "fail"


def test_run_visual_adjudications_skips_non_figure(tmp_path):
    er = {"status": "success", "comparisons": [{
        "artifact": "tbl-1", "kind": "table",
        "status": "mismatch_flagged", "needs_visual_review": True,
        "method": "none", "detail": "", "metadata": {},
    }]}
    result = _run_visual_adjudications(er, {}, tmp_path, "m", _adj_backend())
    assert result[0]["status"] == "mismatch_flagged"   # unchanged


def test_run_visual_adjudications_skips_missing_reference(tmp_path):
    rep = tmp_path / "rep.png"
    _write_png(rep)
    (tmp_path / "kbe").mkdir()
    er = {"status": "success", "comparisons": [_mismatch_comparison("fig-1", str(rep))]}
    kbe = {"reproduction_targets": [_make_target("fig-1", "references/missing.png")]}
    result = _run_visual_adjudications(er, kbe, tmp_path, "m", _adj_backend())
    assert result[0]["visual_adjudication"]["skipped"] is True
    assert result[0]["status"] == "mismatch_flagged"   # unchanged


def test_run_visual_adjudications_skips_no_matched_file(tmp_path):
    ref = tmp_path / "ref.png"
    _write_png(ref)
    kbe_dir = tmp_path / "kbe"
    (kbe_dir / "references").mkdir(parents=True)
    import shutil
    shutil.copy(ref, kbe_dir / "references" / "fig-1.png")

    er = {"status": "success", "comparisons": [{
        "artifact": "fig-1", "kind": "figure",
        "status": "mismatch_flagged", "needs_visual_review": True,
        "method": "phash", "detail": "", "metadata": {},  # no matched_file
    }]}
    kbe = {"reproduction_targets": [_make_target("fig-1", "references/fig-1.png")]}
    result = _run_visual_adjudications(er, kbe, tmp_path, "m", _adj_backend())
    assert result[0]["visual_adjudication"]["skipped"] is True


def test_run_review_writes_visual_adjudications_file(tmp_path):
    """When adjudications run, visual_adjudications.json is written to review/."""
    ref = tmp_path / "ref.png"
    rep = tmp_path / "rep.png"
    _write_png(ref)
    _write_png(rep)

    review_dir = tmp_path / "ai4r" / "p"
    kbe_dir = review_dir / "kbe"
    refs_dir = kbe_dir / "references"
    refs_dir.mkdir(parents=True)
    import shutil
    shutil.copy(ref, refs_dir / "fig-1.png")

    (kbe_dir / "kbe_output.json").write_text(json.dumps({
        "paper_id": "p", "status": "success", "paper_title": "T",
        "reproduction_targets": [_make_target("fig-1", "references/fig-1.png")],
    }))

    cqv_dir = review_dir / "cqv"
    cqv_dir.mkdir(parents=True)
    (cqv_dir / "cqv_output.json").write_text(json.dumps({
        "paper_id": "p", "status": "success",
    }))

    er_dir = review_dir / "er"
    er_dir.mkdir(parents=True)
    (er_dir / "er_output.json").write_text(json.dumps({
        "paper_id": "p", "status": "success",
        "comparisons": [_mismatch_comparison("fig-1", str(rep))],
    }))

    def backend(model, messages, tools):
        # Vision call has image content; other calls have text content.
        first = messages[-1]["content"]
        if isinstance(first, list):
            return LLMResponse(text=json.dumps({
                "classification": "cosmetic", "detail": "only font differs",
            }))
        # Fallback for any text-based model call
        return LLMResponse(text=json.dumps({
            "risk_score": 20, "risk_level": "LOW", "verdict": "ACCEPT",
            "issues": {"critical": [], "major": [], "minor": [], "suggestions": []},
            "required_changes": [],
        }))

    run_review("p", root=tmp_path, complete_fn=backend)

    adj_file = review_dir / "review" / "visual_adjudications.json"
    assert adj_file.is_file()
    adjs = json.loads(adj_file.read_text())
    adj = next(a for a in adjs if a.get("artifact") == "fig-1")
    assert adj["status"] == "pass"
    assert adj["visual_adjudication"]["classification"] == "cosmetic"
