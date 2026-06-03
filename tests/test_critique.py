"""Tests for the Critic stage runner (tools.orchestrator.critique).

These cover ``run_critique`` in isolation — the integration with ``run_review``
that wires the Critic into the pipeline lives in patch 0046, with its tests in
``test_review.py``.

Test infrastructure mirrors the sister stages: an injected ``complete_fn``
returns a canned ``LLMResponse`` matching the call's role (Critic vs the
optional JSON-repair reprompt). No network, no real model.
"""

from __future__ import annotations

import json

from tools.orchestrator.critique import run_critique
from tools.orchestrator.llm import LLMResponse

# ---- Fixtures ----------------------------------------------------------------


def _draft() -> dict:
    """Minimal valid Synthesiser draft for tests not exercising prompt content."""
    return {
        "risk_matrix": {
            "verdict": "MAJOR REVISION",
            "risk_score": 65,
            "risk_level": "HIGH",
            "issues": {
                "critical": [{"id": "C1", "description": "x", "evidence": "path"}],
                "major": [], "minor": [], "suggestions": [],
            },
            "required_changes": [{"id": "R1", "description": "y", "addresses": ["C1"]}],
        },
        "md_files": {
            "final_review.md": "# Review\nVerdict: MAJOR REVISION\nx\n",
            "checklist.md": "# Checklist\n- [x] **[PASS]** item\n",
            "exhaustive_audit_report.md": "# Audit\n## Inputs\nx\n",
        },
    }


def _upstream() -> dict:
    return {
        "kbe": {"status": "success", "paper_title": "T"},
        "cqv": {"status": "success"},
    }


_GOOD_CRITIQUE = json.dumps({
    "status": "complete",
    "concerns": [
        {
            "id": "K1",
            "category": "evidence_gap",
            "severity": "blocking",
            "draft_claim": "Critical: Code uses absolute paths.",
            "concern": "Cited evidence path is too generic to verify against CQV.",
            "evidence_refs": ["ai4r/p/review/risk_matrix.json#/issues/critical/0"],
            "suggested_action": "Tighten cite to specific file:line from CQV evidence.",
        },
    ],
})


def _backend(text: str = _GOOD_CRITIQUE):
    def b(model, messages, tools):
        return LLMResponse(text=text)
    return b


def _raises(model, messages, tools):
    raise RuntimeError("transport down")


# ---- Happy paths -------------------------------------------------------------


def test_complete_critique_writes_file_and_returns_dict(tmp_path):
    out = run_critique("p", upstream=_upstream(), draft=_draft(),
                       root=tmp_path, complete_fn=_backend())
    assert out["status"] == "complete"
    assert out["paper_id"] == "p"
    assert "critique_timestamp" in out
    assert len(out["concerns"]) == 1
    assert out["concerns"][0]["id"] == "K1"
    # File on disk matches the returned dict
    on_disk = json.loads((tmp_path / "ai4r" / "p" / "review" / "critique.json").read_text())
    assert on_disk == out


def test_no_concerns_is_first_class(tmp_path):
    """A positive endorsement: model said no_concerns, returned empty list."""
    payload = json.dumps({"status": "no_concerns", "concerns": []})
    out = run_critique("p", upstream=_upstream(), draft=_draft(),
                       root=tmp_path, complete_fn=_backend(payload))
    assert out["status"] == "no_concerns"
    assert out["concerns"] == []
    assert out["failure_mode"] is None


def test_complete_with_empty_concerns_promotes_to_no_concerns(tmp_path):
    """status=complete + concerns=[] is indistinguishable from no_concerns; promote."""
    payload = json.dumps({"status": "complete", "concerns": []})
    out = run_critique("p", upstream=_upstream(), draft=_draft(),
                       root=tmp_path, complete_fn=_backend(payload))
    assert out["status"] == "no_concerns"


def test_no_concerns_with_concerns_demotes_to_complete(tmp_path):
    """Inconsistent: model said no_concerns but listed some. Take the concerns."""
    payload = json.dumps({
        "status": "no_concerns",
        "concerns": [{
            "id": "K1", "category": "evidence_gap", "severity": "material",
            "draft_claim": "x", "concern": "y", "evidence_refs": ["a"],
            "suggested_action": "z",
        }],
    })
    out = run_critique("p", upstream=_upstream(), draft=_draft(),
                       root=tmp_path, complete_fn=_backend(payload))
    assert out["status"] == "complete"
    assert len(out["concerns"]) == 1


# ---- Orchestrator-owned identity --------------------------------------------


def test_paper_id_is_forced_from_orchestrator(tmp_path):
    """Even if the model emits a paper_id, the orchestrator overwrites it."""
    payload = json.dumps({
        "paper_id": "evil-hijack",
        "critique_timestamp": "1970-01-01T00:00:00Z",
        "status": "no_concerns",
        "concerns": [],
    })
    out = run_critique("real-title", upstream=_upstream(), draft=_draft(),
                       root=tmp_path, complete_fn=_backend(payload))
    assert out["paper_id"] == "real-title"
    assert not out["critique_timestamp"].startswith("1970")


def test_non_kebab_review_title_is_failure(tmp_path):
    out = run_critique("Not Kebab", upstream=_upstream(), draft=_draft(),
                       root=tmp_path, complete_fn=_backend())
    assert out["status"] == "failed"
    assert out["failure_mode"] == "bad_review_title"
    # File still written
    assert (tmp_path / "ai4r" / "Not Kebab" / "review" / "critique.json").is_file()


# ---- Concern validation ------------------------------------------------------


def test_invalid_category_drops_concern(tmp_path):
    payload = json.dumps({
        "status": "complete",
        "concerns": [
            {"id": "K1", "category": "not_a_real_category", "severity": "material",
             "draft_claim": "x", "concern": "y", "evidence_refs": [], "suggested_action": "z"},
            {"id": "K2", "category": "evidence_gap", "severity": "material",
             "draft_claim": "valid", "concern": "valid", "evidence_refs": ["a"],
             "suggested_action": "do something"},
        ],
    })
    out = run_critique("p", upstream=_upstream(), draft=_draft(),
                       root=tmp_path, complete_fn=_backend(payload))
    assert len(out["concerns"]) == 1
    assert out["concerns"][0]["id"] == "K2"


def test_invalid_severity_drops_concern(tmp_path):
    payload = json.dumps({
        "status": "complete",
        "concerns": [{
            "id": "K1", "category": "evidence_gap", "severity": "critical",  # wrong vocab
            "draft_claim": "x", "concern": "y", "evidence_refs": ["a"],
            "suggested_action": "z",
        }],
    })
    out = run_critique("p", upstream=_upstream(), draft=_draft(),
                       root=tmp_path, complete_fn=_backend(payload))
    # The concern was dropped; with concerns=[], status promotes to no_concerns.
    assert out["concerns"] == []
    assert out["status"] == "no_concerns"


def test_blocking_concern_without_refs_or_action_is_downgraded(tmp_path):
    """SKILL rule: blocking concerns MUST have refs AND action; otherwise downgrade."""
    payload = json.dumps({
        "status": "complete",
        "concerns": [
            {"id": "K1", "category": "evidence_gap", "severity": "blocking",
             "draft_claim": "x", "concern": "y", "evidence_refs": [],
             "suggested_action": "do x"},   # no refs -> downgrade
            {"id": "K2", "category": "evidence_gap", "severity": "blocking",
             "draft_claim": "x", "concern": "y", "evidence_refs": ["a"],
             "suggested_action": ""},        # no action -> downgrade
            {"id": "K3", "category": "evidence_gap", "severity": "blocking",
             "draft_claim": "x", "concern": "y", "evidence_refs": ["a"],
             "suggested_action": "do x"},    # both present -> stays blocking
        ],
    })
    out = run_critique("p", upstream=_upstream(), draft=_draft(),
                       root=tmp_path, complete_fn=_backend(payload))
    by_id = {c["id"]: c for c in out["concerns"]}
    assert by_id["K1"]["severity"] == "material"
    assert by_id["K2"]["severity"] == "material"
    assert by_id["K3"]["severity"] == "blocking"


def test_missing_concern_id_is_filled_in_sequentially(tmp_path):
    payload = json.dumps({
        "status": "complete",
        "concerns": [
            {"category": "evidence_gap", "severity": "material",
             "draft_claim": "x", "concern": "y", "evidence_refs": ["a"],
             "suggested_action": "z"},
            {"category": "evidence_gap", "severity": "material",
             "draft_claim": "x", "concern": "y", "evidence_refs": ["a"],
             "suggested_action": "z"},
        ],
    })
    out = run_critique("p", upstream=_upstream(), draft=_draft(),
                       root=tmp_path, complete_fn=_backend(payload))
    assert [c["id"] for c in out["concerns"]] == ["K1", "K2"]


def test_empty_draft_claim_or_concern_drops_entry(tmp_path):
    payload = json.dumps({
        "status": "complete",
        "concerns": [
            {"id": "K1", "category": "evidence_gap", "severity": "material",
             "draft_claim": "", "concern": "y", "evidence_refs": ["a"],
             "suggested_action": "z"},   # empty draft_claim
            {"id": "K2", "category": "evidence_gap", "severity": "material",
             "draft_claim": "x", "concern": "   ", "evidence_refs": ["a"],
             "suggested_action": "z"},   # whitespace-only concern
        ],
    })
    out = run_critique("p", upstream=_upstream(), draft=_draft(),
                       root=tmp_path, complete_fn=_backend(payload))
    assert out["concerns"] == []


# ---- Failure modes (mirror 0035) --------------------------------------------


def test_llm_transport_failure(tmp_path):
    out = run_critique("p", upstream=_upstream(), draft=_draft(),
                       root=tmp_path, complete_fn=_raises)
    assert out["status"] == "failed"
    assert out["failure_mode"] == "llm_request_failed"
    assert "transport down" in out["failure_reason"]
    assert (tmp_path / "ai4r" / "p" / "review" / "critique.json").is_file()


def test_parse_failure_retains_raw(tmp_path, monkeypatch):
    from tools.orchestrator import critique as crit_mod

    garbage = "absolutely not JSON {{{ broken"
    monkeypatch.setattr(crit_mod, "_repair_json_deterministic", lambda text: None)
    monkeypatch.setattr(
        crit_mod, "_repair_json_once",
        lambda bad, error, *, model, complete_fn: None,
    )
    out = run_critique("p", upstream=_upstream(), draft=_draft(),
                       root=tmp_path, complete_fn=_backend(garbage))
    assert out["status"] == "failed"
    assert out["failure_mode"] == "output_parse_failed"
    assert out["raw_model_output"] == garbage
    on_disk = json.loads((tmp_path / "ai4r" / "p" / "review" / "critique.json").read_text())
    assert on_disk["raw_model_output"] == garbage


def test_deterministic_repair_recovers(tmp_path, monkeypatch):
    from tools.orchestrator import critique as crit_mod

    malformed = '{"status": "no_concerns", "concerns": []'  # missing closer
    repaired = {"status": "no_concerns", "concerns": []}
    monkeypatch.setattr(crit_mod, "_repair_json_deterministic", lambda text: repaired)
    out = run_critique("p", upstream=_upstream(), draft=_draft(),
                       root=tmp_path, complete_fn=_backend(malformed))
    assert out["status"] == "no_concerns"
    assert out["failure_mode"] == "output_recovered_by_repair"
    assert out["raw_model_output"] == malformed
    assert "deterministic" in out["notes"]


def test_reprompt_repair_recovers(tmp_path, monkeypatch):
    from tools.orchestrator import critique as crit_mod

    malformed = 'garbage'
    repaired = {
        "status": "complete",
        "concerns": [{
            "id": "K1", "category": "evidence_gap", "severity": "material",
            "draft_claim": "x", "concern": "y", "evidence_refs": ["a"],
            "suggested_action": "z",
        }],
    }
    monkeypatch.setattr(crit_mod, "_repair_json_deterministic", lambda text: None)
    monkeypatch.setattr(
        crit_mod, "_repair_json_once",
        lambda bad, error, *, model, complete_fn: repaired,
    )
    out = run_critique("p", upstream=_upstream(), draft=_draft(),
                       root=tmp_path, complete_fn=_backend(malformed))
    assert out["status"] == "complete"
    assert out["failure_mode"] == "output_recovered_by_repair"
    assert "reprompt" in out["notes"]


# ---- Workflow log ------------------------------------------------------------


def test_workflow_log_records_critique_run(tmp_path):
    run_critique("logged", upstream=_upstream(), draft=_draft(),
                 root=tmp_path, complete_fn=_backend())
    log = (tmp_path / "ai4r" / "logged" / "logs" / "workflow.log").read_text()
    assert "CRITIQUE status=complete" in log
    assert "concerns=1" in log


# ---- Prompt content ----------------------------------------------------------


def test_prompt_injects_rubric_and_security_notice():
    from tools.orchestrator.critique import _critique_prompt

    prompt = _critique_prompt(_upstream(), _draft())
    assert "SECURITY" in prompt
    assert "untrusted" in prompt
    # Rubric loaded from CATEGORIES.md verbatim — anchor on a known section.
    assert "evidence_gap" in prompt
    assert "over_charitable" in prompt
    # The four upstream/draft tagged fences must be present.
    for tag in ("<upstream_kbe>", "<upstream_cqv>", "<draft_risk_matrix>",
                "<draft_final_review>"):
        assert tag in prompt


def test_prompt_excludes_orchestrator_owned_fields():
    """Anti-prompt-injection: tell the model NOT to set paper_id or timestamp."""
    from tools.orchestrator.critique import _critique_prompt

    prompt = _critique_prompt(_upstream(), _draft())
    assert "Do NOT include paper_id" in prompt
    assert "critique_timestamp" in prompt


# --- Evidence-anchor verification (patch 0050) -------------------------------


def test_resolver_skips_non_ai4r_refs(tmp_path):
    from tools.orchestrator.critique import _resolve_evidence_ref
    assert _resolve_evidence_ref("not-an-ai4r-ref", tmp_path) == ("skip", None)
    assert _resolve_evidence_ref("https://example.com/foo", tmp_path) == ("skip", None)


def test_resolver_skips_draft_virtual_paths(tmp_path):
    """In-memory ``draft_*`` tags don't correspond to on-disk files."""
    from tools.orchestrator.critique import _resolve_evidence_ref
    status, _ = _resolve_evidence_ref("ai4r/p/draft_risk_matrix.json#verdict", tmp_path)
    assert status == "skip"


def test_resolver_file_missing(tmp_path):
    from tools.orchestrator.critique import _resolve_evidence_ref
    status, detail = _resolve_evidence_ref("ai4r/p/cqv/nope.md", tmp_path)
    assert status == "broken"
    assert "does not exist" in detail


def test_resolver_line_in_range(tmp_path):
    from tools.orchestrator.critique import _resolve_evidence_ref
    p = tmp_path / "ai4r" / "p" / "cqv"
    p.mkdir(parents=True)
    (p / "f.md").write_text("a\nb\nc\nd\ne\n")
    assert _resolve_evidence_ref("ai4r/p/cqv/f.md#L3", tmp_path) == ("ok", None)


def test_resolver_line_beyond_eof(tmp_path):
    from tools.orchestrator.critique import _resolve_evidence_ref
    p = tmp_path / "ai4r" / "p" / "cqv"
    p.mkdir(parents=True)
    (p / "f.md").write_text("only\ntwo lines\n")
    status, detail = _resolve_evidence_ref("ai4r/p/cqv/f.md#L46", tmp_path)
    assert status == "broken"
    assert "beyond file extent" in detail


def test_resolver_json_line_anchor_is_imprecise(tmp_path):
    """JSON #L<n> cites are imprecise — JSON line numbers aren't semantic."""
    from tools.orchestrator.critique import _resolve_evidence_ref
    p = tmp_path / "ai4r" / "p" / "kbe"
    p.mkdir(parents=True)
    (p / "kbe_output.json").write_text('{"a": 1}\n')
    status, detail = _resolve_evidence_ref("ai4r/p/kbe/kbe_output.json#L1", tmp_path)
    assert status == "imprecise"
    assert "JSON" in detail


def test_resolver_named_anchor_in_markdown_found(tmp_path):
    from tools.orchestrator.critique import _resolve_evidence_ref
    p = tmp_path / "ai4r" / "p" / "cqv"
    p.mkdir(parents=True)
    (p / "f.md").write_text("# Audit\n\nstat-cqv-multiple-testing fired here.\n")
    assert _resolve_evidence_ref("ai4r/p/cqv/f.md#stat-cqv-multiple-testing",
                                   tmp_path) == ("ok", None)


def test_resolver_named_anchor_in_markdown_missing(tmp_path):
    from tools.orchestrator.critique import _resolve_evidence_ref
    p = tmp_path / "ai4r" / "p" / "cqv"
    p.mkdir(parents=True)
    (p / "f.md").write_text("# Audit\n\nNothing relevant here.\n")
    status, detail = _resolve_evidence_ref("ai4r/p/cqv/f.md#STAT-foo", tmp_path)
    assert status == "broken"
    assert "named anchor not found" in detail


def test_resolver_named_anchor_in_json_unverified(tmp_path):
    """JSON named anchors / pointers — skipped (can't validate without parser)."""
    from tools.orchestrator.critique import _resolve_evidence_ref
    p = tmp_path / "ai4r" / "p" / "kbe"
    p.mkdir(parents=True)
    (p / "kbe_output.json").write_text('{"a": 1}\n')
    # Anchor name doesn't appear in file, but we accept it for JSON.
    assert _resolve_evidence_ref("ai4r/p/kbe/kbe_output.json#identified_assumptions[6]",
                                   tmp_path) == ("ok", None)


def test_audit_draft_evidence_flags_broken_and_imprecise(tmp_path):
    """End-to-end audit walks rm.issues and surfaces both broken and imprecise refs."""
    from tools.orchestrator.critique import _audit_draft_evidence
    (tmp_path / "ai4r" / "p" / "cqv").mkdir(parents=True)
    (tmp_path / "ai4r" / "p" / "cqv" / "repo_analysis.md").write_text("# CQV failure\n\n- mode: None\n")
    (tmp_path / "ai4r" / "p" / "kbe").mkdir(parents=True)
    (tmp_path / "ai4r" / "p" / "kbe" / "kbe_output.json").write_text('{"a":1}\n')
    draft = {"risk_matrix": {"issues": {
        "critical": [{"id": "C1", "description": "x",
                      "evidence": "ai4r/p/cqv/repo_analysis.md#L46"}],
        "major": [{"id": "M1", "description": "y",
                   "evidence": "ai4r/p/kbe/kbe_output.json#L1"}],
        "minor": [{"id": "m1", "description": "z",
                   "evidence": "ai4r/p/cqv/repo_analysis.md#mode"}],
        "suggestions": [],
    }}}
    audit = _audit_draft_evidence(draft, tmp_path)
    # C1 broken (line 46 beyond EOF), M1 imprecise (json line cite),
    # m1 ok ("mode" appears in file content).
    assert any("C1" in line and "beyond file extent" in line for line in audit)
    assert any("M1" in line and "JSON" in line for line in audit)
    assert not any("m1" in line for line in audit)


def test_filter_critic_refs_drops_broken_and_records_audit(tmp_path):
    from tools.orchestrator.critique import _filter_critic_refs
    (tmp_path / "ai4r" / "p" / "cqv").mkdir(parents=True)
    (tmp_path / "ai4r" / "p" / "cqv" / "good.json").write_text("{}")
    concerns = [{
        "id": "K1", "category": "evidence_gap", "severity": "material",
        "draft_claim": "x", "concern": "y",
        "evidence_refs": ["ai4r/p/cqv/good.json", "ai4r/p/cqv/missing.md"],
        "suggested_action": "z",
    }]
    out = _filter_critic_refs(concerns, tmp_path)
    assert out[0]["evidence_refs"] == ["ai4r/p/cqv/good.json"]
    assert out[0]["ref_audit"]["dropped"][0]["ref"] == "ai4r/p/cqv/missing.md"


def test_filter_critic_refs_downgrades_blocking_with_no_kept_refs(tmp_path):
    from tools.orchestrator.critique import _filter_critic_refs
    concerns = [{
        "id": "K1", "category": "evidence_gap", "severity": "blocking",
        "draft_claim": "x", "concern": "y",
        "evidence_refs": ["ai4r/p/cqv/missing.md"],
        "suggested_action": "z",
    }]
    out = _filter_critic_refs(concerns, tmp_path)
    assert out[0]["severity"] == "material"  # downgraded
    assert out[0]["evidence_refs"] == []
    assert "ref_audit" in out[0]


def test_filter_critic_refs_preserves_concern_with_no_refs(tmp_path):
    """A concern with zero evidence_refs to start passes through unchanged."""
    from tools.orchestrator.critique import _filter_critic_refs
    concerns = [{
        "id": "K1", "category": "evidence_gap", "severity": "advisory",
        "draft_claim": "x", "concern": "y", "evidence_refs": [],
        "suggested_action": "z",
    }]
    out = _filter_critic_refs(concerns, tmp_path)
    assert out[0]["severity"] == "advisory"
    assert "ref_audit" not in out[0]


def test_critique_prompt_includes_audit_block_when_draft_evidence_broken(tmp_path):
    """End-to-end: a broken draft cite shows up in the Critic prompt's audit block."""
    from tools.orchestrator.critique import _critique_prompt
    (tmp_path / "ai4r" / "p" / "cqv").mkdir(parents=True)
    (tmp_path / "ai4r" / "p" / "cqv" / "repo_analysis.md").write_text("# CQV\n\nshort.\n")
    draft = {"risk_matrix": {"issues": {
        "critical": [{"id": "C1", "description": "x",
                      "evidence": "ai4r/p/cqv/repo_analysis.md#L99"}],
        "major": [], "minor": [], "suggestions": [],
    }}, "md_files": {}}
    prompt = _critique_prompt({"kbe": {}, "cqv": {}}, draft, root=tmp_path)
    assert "<draft_evidence_audit>" in prompt
    assert "C1" in prompt
    assert "beyond file extent" in prompt


def test_critique_prompt_omits_audit_block_when_no_broken_refs(tmp_path):
    """No audit block when all draft refs resolve cleanly."""
    from tools.orchestrator.critique import _critique_prompt
    (tmp_path / "ai4r" / "p" / "cqv").mkdir(parents=True)
    (tmp_path / "ai4r" / "p" / "cqv" / "ok.md").write_text("a\nb\nc\n")
    draft = {"risk_matrix": {"issues": {
        "critical": [{"id": "C1", "description": "x", "evidence": "ai4r/p/cqv/ok.md#L2"}],
        "major": [], "minor": [], "suggestions": [],
    }}, "md_files": {}}
    prompt = _critique_prompt({"kbe": {}, "cqv": {}}, draft, root=tmp_path)
    assert "<draft_evidence_audit>" not in prompt


def test_run_critique_filters_critic_refs_end_to_end(tmp_path):
    """A Critic that cites a missing file: ref dropped from output, ref_audit appears."""
    (tmp_path / "ai4r" / "p" / "kbe").mkdir(parents=True)
    (tmp_path / "ai4r" / "p" / "kbe" / "kbe_output.json").write_text('{}')
    payload = json.dumps({
        "status": "complete",
        "concerns": [{
            "id": "K1", "category": "evidence_gap", "severity": "material",
            "draft_claim": "x", "concern": "y",
            "evidence_refs": ["ai4r/p/kbe/kbe_output.json", "ai4r/p/cqv/nonexistent.md"],
            "suggested_action": "z",
        }],
    })
    out = run_critique("p", upstream=_upstream(), draft=_draft(),
                       root=tmp_path, complete_fn=_backend(payload))
    concern = out["concerns"][0]
    assert concern["evidence_refs"] == ["ai4r/p/kbe/kbe_output.json"]
    assert concern["ref_audit"]["dropped"][0]["ref"] == "ai4r/p/cqv/nonexistent.md"
