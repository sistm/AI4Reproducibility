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
    _checklist_prompt,
    _context_blob,
    _load_checklist_rubric,
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

# Default Synthesis final-pass response: empty addressed_concerns and no
# revisions. _normalise_addressed will auto-defer any actionable concerns
# the critique surfaced. Tests that need a substantive final-pass override
# via the `synth=` parameter.
_GOOD_SYNTH = (
    '{"addressed_concerns": [], "revised_risk_matrix": null, '
    '"revised_markdown_files": null}'
)


def _backend(
    core: str = GOOD_CORE,
    md: str = _GOOD_MD,
    critique: str = _GOOD_CRITIQUE,
    synth: str = _GOOD_SYNTH,
):
    def b(model, messages, tools):
        u = messages[-1]["content"]
        # Synthesis final-pass: has BOTH <draft_risk_matrix> and <critic_concerns>.
        # Check this FIRST since it shares the draft tag with the Critic prompt.
        if "<critic_concerns>" in u:
            return LLMResponse(text=synth)
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
    malformed = '{"risk_score": 40, "verdict": "REJECT" oops'
    repaired = {
        "risk_score": 40, "risk_level": "MEDIUM", "verdict": "REJECT",
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
    assert rm["verdict"] == "REJECT"
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


def test_er_present_included_unstripped():
    """ER output is passed through as-is (no strip set)."""
    er = {"status": "skipped", "reason": "deferred", "internal_note": "keep this"}
    blob = _context_blob(None, None, er)
    assert "er_output:" in blob
    assert "internal_note" in blob


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
            "evidence_refs": ["ai4r/p/review/risk_matrix.json#/issues/critical/0"],
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
    "evidence_refs": ["ai4r/p/cqv/repo_analysis.md"],
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
            return LLMResponse(text=_GOOD_SYNTH)
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
            return LLMResponse(text=_GOOD_SYNTH)
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
    """When Synthesiser emits explicit resolutions, they win over auto-deferral."""
    _seed(tmp_path, "p", {"status": "success", "paper_title": "T"}, {"status": "success"})
    synth_response = json.dumps({
        "addressed_concerns": [
            {"id": "K1", "resolution": "incorporated",
             "reason": "Tightened evidence cite to DoFiguresTables.R:12."},
            {"id": "K2", "resolution": "refuted",
             "reason": "Draft already cites the specific line."},
        ],
        "revised_risk_matrix": None,
        "revised_markdown_files": None,
    })
    crit = _critique_with([_CONCERN_BLOCKING, _CONCERN_MATERIAL])
    rm = run_review("p", root=tmp_path,
                    complete_fn=_backend(critique=crit, synth=synth_response))
    by_id = {a["id"]: a for a in rm["addressed_concerns"]}
    assert by_id["K1"]["resolution"] == "incorporated"
    assert by_id["K2"]["resolution"] == "refuted"


def test_final_pass_revises_risk_matrix_when_emitted(tmp_path):
    """A complete revised_risk_matrix replaces the rm core (identity preserved)."""
    _seed(tmp_path, "p", {"status": "success", "paper_title": "T"}, {"status": "success"})
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
    synth = json.dumps({
        "addressed_concerns": [{"id": "K1", "resolution": "incorporated",
                                 "reason": "Escalated to MAJOR per blocking concern."}],
        "revised_risk_matrix": revised_rm,
        "revised_markdown_files": None,
    })
    rm = run_review("p", root=tmp_path,
                    complete_fn=_backend(critique=_critique_with([_CONCERN_BLOCKING]),
                                          synth=synth))
    # Revised fields applied:
    assert rm["verdict"] == "MAJOR REVISION"
    assert rm["risk_score"] == 70
    # Orchestrator-owned fields NOT overwritten by model:
    assert rm["paper_id"] == "p"
    assert rm["paper_title"] == "T"
    assert not rm["assessed_at"].startswith("1970")
    # Audit-trail note records the revision:
    assert "synthesis final pass revised" in rm["notes"]
    assert "risk_matrix" in rm["notes"]


def test_final_pass_partial_rm_rejected(tmp_path):
    """An rm revision missing required keys is rejected; draft stands."""
    _seed(tmp_path, "p", {"status": "success", "paper_title": "T"}, {"status": "success"})
    incomplete = {"verdict": "REJECT", "risk_score": 95}  # missing 8 keys
    synth = json.dumps({
        "addressed_concerns": [{"id": "K1", "resolution": "incorporated",
                                 "reason": "x"}],
        "revised_risk_matrix": incomplete,
        "revised_markdown_files": None,
    })
    rm = run_review("p", root=tmp_path,
                    complete_fn=_backend(critique=_critique_with([_CONCERN_BLOCKING]),
                                          synth=synth))
    # Draft preserved: still MINOR REVISION from GOOD_CORE fixture
    assert rm["verdict"] == "MINOR REVISION"
    # Synthesiser's addressed_concerns still applied
    assert rm["addressed_concerns"][0]["resolution"] == "incorporated"


def test_final_pass_revises_markdown_files_when_emitted(tmp_path):
    """A revised md file replaces the draft on disk; strip-fence applied."""
    _seed(tmp_path, "p", {"status": "success", "paper_title": "T"}, {"status": "success"})
    # The Synthesiser may re-wrap; the strip-fence pass from 0043 must catch it.
    revised_body = (
        "# Final Review (revised)\n\nVerdict: **MAJOR REVISION**\n\n"
        "## Checklist\n- [x] **[PASS]** item\n\n"
        "Revised body that is well over the minimum length threshold so that "
        "validation passes downstream and the final review carries every "
        "structural marker the per-file validators check.\n"
    )
    synth = json.dumps({
        "addressed_concerns": [{"id": "K1", "resolution": "incorporated",
                                 "reason": "x"}],
        "revised_risk_matrix": None,
        "revised_markdown_files": {
            "final_review.md": f"```markdown\n{revised_body}```",  # re-wrapped
        },
    })
    run_review("p", root=tmp_path,
               complete_fn=_backend(critique=_critique_with([_CONCERN_BLOCKING]),
                                     synth=synth))
    fr = (tmp_path / "ai4r" / "p" / "review" / "final_review.md").read_text()
    assert not fr.lstrip().startswith("```")  # 0043 strip applied to revision
    assert "Final Review (revised)" in fr


def test_final_pass_unknown_md_filename_silently_dropped(tmp_path):
    """Synthesiser emitting an unrecognised filename is ignored, not crashed."""
    _seed(tmp_path, "p", {"status": "success", "paper_title": "T"}, {"status": "success"})
    synth = json.dumps({
        "addressed_concerns": [{"id": "K1", "resolution": "incorporated",
                                 "reason": "x"}],
        "revised_risk_matrix": None,
        "revised_markdown_files": {"made_up_file.md": "evil content"},
    })
    rm = run_review("p", root=tmp_path,
                    complete_fn=_backend(critique=_critique_with([_CONCERN_BLOCKING]),
                                          synth=synth))
    # made_up_file.md not written; only the standard three exist.
    rdir = tmp_path / "ai4r" / "p" / "review"
    assert not (rdir / "made_up_file.md").exists()
    assert (rdir / "final_review.md").is_file()
    # Audit-trail note absent since no real revision happened.
    assert "synthesis final pass revised" not in rm.get("notes", "")


def test_final_pass_llm_transport_failure_falls_back_to_draft(tmp_path):
    """Final-pass LLM failure -> draft stands, every concern auto-deferred."""
    _seed(tmp_path, "p", {"status": "success", "paper_title": "T"}, {"status": "success"})

    def selective(model, messages, tools):
        u = messages[-1]["content"]
        if "<critic_concerns>" in u:
            raise RuntimeError("synth gateway down")
        if "<draft_risk_matrix>" in u:
            return LLMResponse(text=_critique_with([_CONCERN_BLOCKING, _CONCERN_MATERIAL]))
        if '"risk_score"' in u and "Return ONLY" in u:
            return LLMResponse(text=GOOD_CORE)
        return LLMResponse(text=_GOOD_MD)

    rm = run_review("p", root=tmp_path, complete_fn=selective)
    assert rm["assessment_status"] == "complete"  # not degraded
    assert "synthesis final pass failed" in rm["notes"]
    assert "llm_request_failed" in rm["notes"]
    # All actionable concerns auto-deferred
    by_id = {a["id"]: a for a in rm["addressed_concerns"]}
    assert by_id["K1"]["resolution"] == "deferred"
    assert by_id["K2"]["resolution"] == "deferred"


def test_final_pass_parse_failure_falls_back_to_draft(tmp_path, monkeypatch):
    """Final-pass JSON parse + repair exhausted -> draft stands."""
    from tools.orchestrator import review as review_mod

    monkeypatch.setattr(review_mod, "_repair_json_deterministic", lambda text: None)
    monkeypatch.setattr(
        review_mod, "_repair_json_once",
        lambda bad, error, *, model, complete_fn: None,
    )
    _seed(tmp_path, "p", {"status": "success", "paper_title": "T"}, {"status": "success"})
    rm = run_review("p", root=tmp_path,
                    complete_fn=_backend(critique=_critique_with([_CONCERN_BLOCKING]),
                                          synth="not JSON at all {{{"))
    assert "synthesis final pass failed" in rm["notes"]
    assert "output_parse_failed" in rm["notes"]
    assert rm["addressed_concerns"][0]["resolution"] == "deferred"


def test_final_pass_blocking_only_addresses_blocking_and_material(tmp_path):
    """Auto-deferral fills in missing required_ids (blocking + material), not advisory."""
    _seed(tmp_path, "p", {"status": "success", "paper_title": "T"}, {"status": "success"})
    crit = _critique_with([_CONCERN_BLOCKING, _CONCERN_MATERIAL, _CONCERN_ADVISORY])
    rm = run_review("p", root=tmp_path, complete_fn=_backend(critique=crit))
    ids = {a["id"] for a in rm["addressed_concerns"]}
    assert ids == {"K1", "K2"}  # K3 advisory omitted from auto-deferral
