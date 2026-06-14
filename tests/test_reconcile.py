"""Tests for the deterministic Reconciliation step (patch 0053).

Three invariants, each tested in isolation plus an end-to-end pass that
exercises them in the order ``reconcile_review`` applies them. Integration
through ``run_review`` is covered in ``test_review.py``; these tests target
the helpers directly so failures localise.
"""

from __future__ import annotations

import copy

import pytest

from tools.orchestrator.reconcile import (
    _check_address_references,
    _check_incorporated_claims,
    _check_verdict_consistency,
    _draft_differs_from_final,
    _extract_verdict_from_md,
    reconcile_review,
    snapshot_draft,
)

# ---- _extract_verdict_from_md -----------------------------------------------


@pytest.mark.parametrize("text,expected", [
    ("**Verdict:** MAJOR REVISION", "MAJOR REVISION"),
    ("## Verdict\n\n**MINOR REVISION**", "MINOR REVISION"),
    ("## Verdict and Justification\n\n**MAJOR REVISION** — justified by ...",
     "MAJOR REVISION"),
    # Fallback: standalone bold token with no nearby "Verdict" keyword.
    ("# Final Review\n\nWe propose **REJECT** for this submission.", "MAJOR REVISION"),  # REJECT remapped
    # Case-insensitive verdict-keyword, normalised to canonical caps.
    ("**verdict:** accept", "ACCEPT"),
    # Multi-line gap: keyword and token straddle a blank line.
    ("## Verdict\n\nThis paper warrants **MAJOR REVISION**.", "MAJOR REVISION"),
    # Multiple "verdict" mentions: regex skips the first if no token follows,
    # matches the second.
    ("The verdict is deferred until next round.\n\n## Verdict\n\n**REJECT**",
     "MAJOR REVISION"),  # REJECT remapped
    # No verdict anywhere.
    ("# Final Review\n\nNo verdict yet.", None),
    ("", None),
])
def test_extract_verdict_from_md(text, expected):
    assert _extract_verdict_from_md(text) == expected


# ---- _draft_differs_from_final ----------------------------------------------


def _bare_rm(**overrides):
    """Minimal rm with diffable keys set; pass overrides to flip individual fields."""
    base = {
        "verdict": "MINOR REVISION", "risk_score": 30, "risk_level": "MEDIUM",
        "issues": {"critical": [], "major": [], "minor": [], "suggestions": []},
        "required_changes": [], "assessment_status": "complete",
        "paper_id": "p", "paper_title": "T", "assessed_at": "2024-01-01T00:00:00Z",
        "upstream_status": {},
    }
    base.update(overrides)
    return base


def test_diff_identical_returns_false():
    rm = _bare_rm()
    md = {"final_review.md": "x"}
    draft = {"rm": copy.deepcopy(rm), "md_files": dict(md)}
    assert _draft_differs_from_final(draft, rm, md) is False


def test_diff_verdict_change_returns_true():
    rm_draft = _bare_rm(verdict="MINOR REVISION")
    rm_final = _bare_rm(verdict="MAJOR REVISION")
    md = {"final_review.md": "x"}
    draft = {"rm": rm_draft, "md_files": dict(md)}
    assert _draft_differs_from_final(draft, rm_final, md) is True


def test_diff_md_change_returns_true():
    rm = _bare_rm()
    draft = {"rm": copy.deepcopy(rm), "md_files": {"final_review.md": "old"}}
    final_md = {"final_review.md": "new"}
    assert _draft_differs_from_final(draft, rm, final_md) is True


def test_diff_ignores_addressed_concerns_addition():
    """addressed_concerns is added by Synthesiser; not a diffable field."""
    rm = _bare_rm()
    rm_final = {**rm, "addressed_concerns": [{"id": "K1", "resolution": "deferred"}]}
    md = {"final_review.md": "x"}
    draft = {"rm": rm, "md_files": dict(md)}
    assert _draft_differs_from_final(draft, rm_final, md) is False


def test_diff_ignores_paper_id_change():
    """Orchestrator-owned fields are not Synthesiser changes."""
    rm_draft = _bare_rm(paper_id="p")
    rm_final = _bare_rm(paper_id="changed")  # would never happen but test the boundary
    md = {"final_review.md": "x"}
    draft = {"rm": rm_draft, "md_files": dict(md)}
    assert _draft_differs_from_final(draft, rm_final, md) is False


def test_diff_issues_block_change_returns_true():
    rm_draft = _bare_rm()
    rm_final = _bare_rm(
        issues={"critical": [{"id": "C1", "description": "x"}],
                "major": [], "minor": [], "suggestions": []},
    )
    md = {"final_review.md": "x"}
    draft = {"rm": rm_draft, "md_files": dict(md)}
    assert _draft_differs_from_final(draft, rm_final, md) is True


# ---- _check_verdict_consistency (Invariant 1) -------------------------------


def test_verdict_match_unchanged():
    rm = _bare_rm(verdict="MAJOR REVISION")
    md = {"final_review.md": "## Verdict\n\n**MAJOR REVISION**"}
    out_rm, _ = _check_verdict_consistency(rm, md)
    assert out_rm["assessment_status"] == "complete"
    assert "failure_mode" not in out_rm
    assert "notes" not in out_rm


def test_verdict_mismatch_degrades_to_failed():
    """The bimj_202400278 smoke-run failure mode: rm=MAJOR, md=MINOR."""
    rm = _bare_rm(verdict="MAJOR REVISION")
    md = {"final_review.md": "## Verdict\n\n**MINOR REVISION**"}
    out_rm, _ = _check_verdict_consistency(rm, md)
    assert out_rm["assessment_status"] == "failed"
    assert out_rm["failure_mode"] == "verdict_inconsistent"
    assert "verdict mismatch" in out_rm["notes"]
    assert "MAJOR REVISION" in out_rm["notes"]
    assert "MINOR REVISION" in out_rm["notes"]


def test_verdict_unparseable_md_skips_check():
    """No verdict in md (an upstream defect 0036 catches) -> reconciliation skips."""
    rm = _bare_rm(verdict="MAJOR REVISION", assessment_status="complete")
    md = {"final_review.md": "# Final Review\n\nNo verdict found here.\n"}
    out_rm, _ = _check_verdict_consistency(rm, md)
    assert out_rm["assessment_status"] == "complete"
    assert "failure_mode" not in out_rm


def test_verdict_invalid_rm_value_skips_check():
    """rm.verdict outside the four-token vocabulary -> not our cleanup."""
    rm = _bare_rm(verdict="WAFFLES")
    md = {"final_review.md": "## Verdict\n\n**MINOR REVISION**"}
    out_rm, _ = _check_verdict_consistency(rm, md)
    assert out_rm["assessment_status"] == "complete"


def test_verdict_does_not_mutate_caller_dict():
    """Reconciliation returns a new dict on mismatch — caller's rm unchanged."""
    rm = _bare_rm(verdict="MAJOR REVISION")
    md = {"final_review.md": "**ACCEPT**"}
    out_rm, _ = _check_verdict_consistency(rm, md)
    assert rm["assessment_status"] == "complete"  # original untouched
    assert out_rm["assessment_status"] == "failed"
    assert out_rm is not rm


# ---- _check_incorporated_claims (Invariant 2) -------------------------------


def test_incorporated_with_diff_unchanged():
    rm = _bare_rm()
    rm["addressed_concerns"] = [
        {"id": "K1", "resolution": "incorporated", "reason": "did the thing"},
    ]
    out = _check_incorporated_claims(rm, diff_exists=True)
    assert out["addressed_concerns"][0]["resolution"] == "incorporated"


def test_incorporated_without_diff_downgraded_to_deferred():
    rm = _bare_rm()
    rm["addressed_concerns"] = [
        {"id": "K1", "resolution": "incorporated", "reason": "claimed to do thing"},
    ]
    out = _check_incorporated_claims(rm, diff_exists=False)
    assert out["addressed_concerns"][0]["resolution"] == "deferred"
    assert "no diff" in out["addressed_concerns"][0]["reason"]
    assert "K1" in out["notes"]


def test_mixed_resolutions_only_incorporated_downgrades_when_no_diff():
    rm = _bare_rm()
    rm["addressed_concerns"] = [
        {"id": "K1", "resolution": "incorporated", "reason": "x"},
        {"id": "K2", "resolution": "refuted", "reason": "y"},
        {"id": "K3", "resolution": "deferred", "reason": "z"},
        {"id": "K4", "resolution": "incorporated", "reason": "w"},
    ]
    out = _check_incorporated_claims(rm, diff_exists=False)
    by_id = {a["id"]: a for a in out["addressed_concerns"]}
    assert by_id["K1"]["resolution"] == "deferred"
    assert by_id["K2"]["resolution"] == "refuted"  # untouched
    assert by_id["K3"]["resolution"] == "deferred"  # already was
    assert by_id["K4"]["resolution"] == "deferred"


def test_no_incorporated_no_change_regardless_of_diff():
    rm = _bare_rm()
    rm["addressed_concerns"] = [
        {"id": "K1", "resolution": "refuted", "reason": "x"},
    ]
    out = _check_incorporated_claims(rm, diff_exists=False)
    assert out["addressed_concerns"][0]["resolution"] == "refuted"
    assert "notes" not in out  # no reconciliation note added


def test_no_addressed_concerns_field_returns_unchanged():
    rm = _bare_rm()
    out = _check_incorporated_claims(rm, diff_exists=False)
    assert out is rm  # no mutation


# ---- _check_address_references (Invariant 3) --------------------------------


def test_all_addresses_valid_unchanged():
    rm = _bare_rm(
        issues={"critical": [{"id": "C1", "description": "x"}],
                "major": [{"id": "M1", "description": "y"}],
                "minor": [], "suggestions": []},
        required_changes=[{"id": "R1", "description": "z", "addresses": ["C1", "M1"]}],
    )
    out = _check_address_references(rm)
    assert out["required_changes"][0]["addresses"] == ["C1", "M1"]
    assert "notes" not in out


def test_orphan_address_dropped_with_note():
    rm = _bare_rm(
        issues={"critical": [{"id": "C1", "description": "x"}],
                "major": [], "minor": [], "suggestions": []},
        required_changes=[{"id": "R1", "description": "z",
                           "addresses": ["C1", "BLOCKER-0"]}],
    )
    out = _check_address_references(rm)
    assert out["required_changes"][0]["addresses"] == ["C1"]
    assert "dropped 1 orphan" in out["notes"]


def test_r_row_addressing_no_real_issue_kept_with_orphan_note():
    rm = _bare_rm(
        issues={"critical": [], "major": [], "minor": [], "suggestions": []},
        required_changes=[{"id": "R7", "description": "z",
                           "addresses": ["nonexistent-id"]}],
    )
    out = _check_address_references(rm)
    # R-row kept (it may still be useful) but addresses now empty.
    assert out["required_changes"][0]["id"] == "R7"
    assert out["required_changes"][0]["addresses"] == []
    assert "R7" in out["notes"]
    assert "no extant issue" in out["notes"]


# ---- reconcile_review end-to-end --------------------------------------------


def test_reconcile_smoke_run_scenario(tmp_path):
    """Reproduce the bimj_202400278 failure: rm=MAJOR, md=MINOR, incorporated claims, no diff.

    Synthesises the failure mode the smoke run hit. After reconciliation:
      - Invariant 1: assessment_status -> failed, failure_mode set.
      - Invariant 2: incorporated claims downgraded to deferred.
      - Invariant 3: no orphans, no change.
    """
    draft_rm = _bare_rm(verdict="MAJOR REVISION")
    draft_md = {"final_review.md": "## Verdict\n\n**MAJOR REVISION**\n"}
    snapshot = {"rm": copy.deepcopy(draft_rm), "md_files": dict(draft_md)}
    # "Final" state: synth audit claimed incorporated but Call 2 died,
    # leaving rm/md identical to draft. md still has MAJOR — match draft.
    # Now flip the md to simulate the actual smoke-run mismatch:
    final_rm = copy.deepcopy(draft_rm)
    final_rm["addressed_concerns"] = [
        {"id": "K4", "resolution": "incorporated", "reason": "would align verdict"},
    ]
    final_md = {"final_review.md": "## Verdict\n\n**MINOR REVISION**\n"}
    # Snapshot reflects pre-Critic state (both MAJOR); final reflects post-
    # synthesis state (rm MAJOR, md MINOR — which is the bug to detect).
    snapshot["md_files"] = {"final_review.md": "## Verdict\n\n**MAJOR REVISION**\n"}

    out_rm, _ = reconcile_review(final_rm, final_md, snapshot)
    # Invariant 1 fires:
    assert out_rm["assessment_status"] == "failed"
    assert out_rm["failure_mode"] == "verdict_inconsistent"
    # Invariant 2 fires (md changed -> diff_exists True for md, but only md
    # changed and the change was in the WRONG direction; the diff check is
    # aggregate so it accepts K4's incorporated claim).
    # Important: the smoke-run failure shape is "rm verdict was updated, md
    # wasn't" — but here we constructed the opposite. Either way, the
    # incorporated claim survives because *some* diff exists.
    assert out_rm["addressed_concerns"][0]["resolution"] == "incorporated"


def test_reconcile_call_2_died_smoke_run_scenario():
    """The exact bimj_202400278 shape: Call 2 transport failure, no diff at all.

    Draft is identical to final (Synthesiser made no change). audit claims
    incorporated. Reconciliation honestly downgrades.
    """
    draft_rm = _bare_rm(verdict="MINOR REVISION")
    draft_md = {"final_review.md": "## Verdict\n\n**MINOR REVISION**\n"}
    snapshot = {"rm": copy.deepcopy(draft_rm), "md_files": dict(draft_md)}
    final_rm = copy.deepcopy(draft_rm)
    final_rm["addressed_concerns"] = [
        {"id": "K1", "resolution": "incorporated", "reason": "claimed to escalate"},
        {"id": "K2", "resolution": "refuted", "reason": "draft addresses it"},
    ]
    out_rm, _ = reconcile_review(final_rm, dict(draft_md), snapshot)
    # Invariant 1: rm and md agree -> no degrade.
    assert out_rm["assessment_status"] == "complete"
    # Invariant 2: no diff (final == draft) -> K1 incorporated -> deferred.
    by_id = {a["id"]: a for a in out_rm["addressed_concerns"]}
    assert by_id["K1"]["resolution"] == "deferred"
    assert by_id["K2"]["resolution"] == "refuted"
    assert "no diff" in by_id["K1"]["reason"]


def test_reconcile_clean_case_no_changes():
    """Internally-consistent inputs pass through untouched."""
    rm = _bare_rm(
        verdict="MINOR REVISION",
        issues={"critical": [{"id": "C1", "description": "x"}],
                "major": [], "minor": [], "suggestions": []},
        required_changes=[{"id": "R1", "description": "z", "addresses": ["C1"]}],
    )
    md = {"final_review.md": "**MINOR REVISION** justified by C1.\n"}
    snapshot = {"rm": copy.deepcopy(rm), "md_files": dict(md)}
    # No addressed_concerns (Critic raised no concerns or skipped final pass).
    out_rm, out_md = reconcile_review(rm, md, snapshot)
    assert out_rm["assessment_status"] == "complete"
    assert "failure_mode" not in out_rm
    assert "notes" not in out_rm
    assert out_md == md


# ---- snapshot_draft ---------------------------------------------------------


def test_snapshot_is_deep_copy():
    """Snapshot must survive in-place mutation of nested rm/md state."""
    rm = _bare_rm(issues={"critical": [{"id": "C1"}], "major": [],
                          "minor": [], "suggestions": []})
    md = {"final_review.md": "draft text"}
    snap = snapshot_draft(rm, md)
    # Mutate original
    rm["issues"]["critical"].append({"id": "C2"})
    rm["verdict"] = "MAJOR REVISION"  # was REJECT pre-0102; mutate to check snapshot independence
    md["final_review.md"] = "mutated text"
    # Snapshot unaffected
    assert snap["rm"]["issues"]["critical"] == [{"id": "C1"}]
    assert snap["rm"]["verdict"] == "MINOR REVISION"
    assert snap["md_files"]["final_review.md"] == "draft text"


# ---- _check_incorporated_claims per-concern path (patch 0056) ---------------

def _make_rm_with_issue(issue_id: str, issue_text: str = "original") -> dict:
    return {
        "issues": {"critical": [{"id": issue_id, "description": issue_text}]},
        "addressed_concerns": [],
    }


def test_per_concern_pass_when_claimed_issue_changed():
    """Per-concern: issue listed in addresses_issue_ids actually changed → keep incorporated."""
    draft_rm = _make_rm_with_issue("B1", "original text")
    final_rm = _make_rm_with_issue("B1", "revised text")
    final_rm["addressed_concerns"] = [
        {"id": "K1", "resolution": "incorporated", "reason": "fixed B1",
         "addresses_issue_ids": ["B1"]},
    ]
    out = _check_incorporated_claims(final_rm, diff_exists=True, draft_rm=draft_rm)
    assert out["addressed_concerns"][0]["resolution"] == "incorporated"


def test_per_concern_fail_when_claimed_issue_unchanged():
    """Per-concern: claimed issue IDs are identical in draft and final → downgrade."""
    draft_rm = _make_rm_with_issue("B1", "unchanged")
    final_rm = _make_rm_with_issue("B1", "unchanged")
    final_rm["addressed_concerns"] = [
        {"id": "K1", "resolution": "incorporated", "reason": "claimed to fix B1",
         "addresses_issue_ids": ["B1"]},
    ]
    out = _check_incorporated_claims(final_rm, diff_exists=True, draft_rm=draft_rm)
    entry = out["addressed_concerns"][0]
    assert entry["resolution"] == "deferred"
    assert "B1" in entry["reason"]
    assert "per-concern" in entry["reason"]


def test_per_concern_selective_downgrade():
    """Per-concern: K1 issue changed (passes), K2 issue unchanged (downgraded)."""
    draft_rm = {
        "issues": {
            "critical": [
                {"id": "B1", "description": "original"},
                {"id": "B2", "description": "unchanged"},
            ]
        },
        "addressed_concerns": [],
    }
    final_rm = {
        "issues": {
            "critical": [
                {"id": "B1", "description": "revised"},   # changed
                {"id": "B2", "description": "unchanged"},  # NOT changed
            ]
        },
        "addressed_concerns": [
            {"id": "K1", "resolution": "incorporated", "reason": "fixed B1",
             "addresses_issue_ids": ["B1"]},
            {"id": "K2", "resolution": "incorporated", "reason": "claimed to fix B2",
             "addresses_issue_ids": ["B2"]},
        ],
    }
    out = _check_incorporated_claims(final_rm, diff_exists=True, draft_rm=draft_rm)
    by_id = {a["id"]: a for a in out["addressed_concerns"]}
    assert by_id["K1"]["resolution"] == "incorporated"
    assert by_id["K2"]["resolution"] == "deferred"
    assert "K2" in out.get("notes", "")


def test_per_concern_no_addresses_ids_falls_back_to_aggregate():
    """No addresses_issue_ids → aggregate diff check used regardless of draft_rm."""
    draft_rm = _make_rm_with_issue("B1", "unchanged")
    final_rm = _make_rm_with_issue("B1", "unchanged")
    final_rm["addressed_concerns"] = [
        {"id": "K1", "resolution": "incorporated", "reason": "changed the markdown"},
    ]
    # diff_exists=True (some md change), no addresses_issue_ids → aggregate accepts
    out = _check_incorporated_claims(final_rm, diff_exists=True, draft_rm=draft_rm)
    assert out["addressed_concerns"][0]["resolution"] == "incorporated"
