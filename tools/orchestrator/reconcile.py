"""Deterministic reconciliation of Review's final artifacts (patch 0053).

The Critic + Synthesiser loop converges on consistent rm/md when both LLM
calls succeed; when either fails, the audit trail (added by 0051) survives
but the shipped artifacts can still be internally inconsistent. The
bimj_202400278 smoke run is the worked example: `rm.verdict == 'MAJOR
REVISION'` but `final_review.md` says `'MINOR REVISION'`, both written,
pipeline reports PASS.

Reconciliation is the deterministic last-line check. No LLM calls; pure
inspection of the in-memory rm + md_files against a snapshot of the
pre-Critic draft. Three invariants are enforced; failures are either
mechanically corrected (with a `notes` line documenting what was done) or,
when the structural drift cannot be safely repaired, the rm's
``assessment_status`` is degraded to ``failed`` so the artifacts do not
ship green when they aren't.

Invariants enforced (v1):

1. **Verdict consistency** between ``rm.verdict`` and the verdict parsed
   from ``final_review.md``. Mismatch -> ``assessment_status: "failed"``,
   ``failure_mode: "verdict_inconsistent"``. v1 degrades rather than
   rewrites; a future patch can add the middle-ground "rewrite when an
   explicit incorporated concern names which side is canonical" path.

2. **Incorporated-claims integrity.** If ``addressed_concerns`` contains
   any entry with ``resolution: "incorporated"`` and the final rm/md
   differ in zero bytes from the pre-Critic draft, the Synthesiser
   claimed an incorporation it didn't perform. Downgrade every such
   entry to ``deferred`` so the audit trail is honest. Aggregate check —
   a per-concern mapping is deferred to 0056.

3. **Address-reference cleanup.** Every
   ``required_changes[].addresses[]`` ID must match an existing issue
   ID in ``rm.issues.{critical,major,minor,suggestions}``. Drop unknown
   IDs; record what was dropped in ``notes``.

Out of scope for 0053 (queued for later patches):
* Verdict/risk_score/risk_level structural coherence — see handoff.
* Iterative reconciliation that re-prompts the Synthesiser to fix what
  it found — see handoff (0057+).
* Per-concern diff mapping for Invariant 2 — see handoff (0056+).
"""

from __future__ import annotations

import copy
import re
from typing import Any

# Snapshot the rm fields the Synthesiser could plausibly change. Excluded:
# paper_id/paper_title/assessed_at/upstream_status (orchestrator-owned), and
# addressed_concerns/notes/raw_model_output (added by Synthesiser/orchestrator
# after the draft, so always "different" — would defeat the diff check).
_DIFFABLE_RM_KEYS = (
    "verdict",
    "risk_score",
    "risk_level",
    "issues",
    "required_changes",
    "assessment_status",
)

_VERDICTS = {"ACCEPT", "MINOR REVISION", "MAJOR REVISION"}

# First pass: the word "verdict" (case-insensitive) followed within ~150 chars
# (possibly crossing a heading + blank-line gap) by one of the verdict tokens.
# REJECT is kept in the regex to detect legacy narratives; _normalise_verdict
# remaps it to MAJOR REVISION before any set-membership check.
_VERDICT_NEAR_KEYWORD = re.compile(
    r"(?i)verdict\b.{0,150}?\b(ACCEPT|MINOR\s+REVISION|MAJOR\s+REVISION|REJECT)\b",
    re.DOTALL,
)
# Fallback: any standalone bold verdict token. Catches `**MAJOR REVISION**`
# emitted without a preceding "Verdict" label.
_BOLD_VERDICT = re.compile(
    r"\*\*\s*(ACCEPT|MINOR\s+REVISION|MAJOR\s+REVISION|REJECT)\s*\*\*"
)


def _normalise_verdict(raw: str) -> str:
    """Collapse whitespace; remap legacy REJECT to MAJOR REVISION."""
    v = re.sub(r"\s+", " ", raw).strip().upper()
    if v == "REJECT":
        v = "MAJOR REVISION"
    return v


def _extract_verdict_from_md(text: str) -> str | None:
    """Parse a verdict token out of ``final_review.md``.

    Two-pass strategy: prefer a verdict near the keyword "verdict" (handles
    `## Verdict\n\n**MAJOR REVISION**`, `**Verdict:** MINOR REVISION`, etc.);
    fall back to any standalone bold verdict token. Returns the verdict in
    canonical upper-case form, or None if no verdict could be parsed (which
    is its own structural defect, but one that 0036's per-file validator
    catches — reconciliation skips rather than re-fails on top).
    """
    if not text:
        return None
    m = _VERDICT_NEAR_KEYWORD.search(text)
    if m:
        return _normalise_verdict(m.group(1))
    m = _BOLD_VERDICT.search(text)
    if m:
        return _normalise_verdict(m.group(1))
    return None


def _draft_differs_from_final(
    draft: dict[str, Any],
    final_rm: dict[str, Any],
    final_md: dict[str, str],
) -> bool:
    """Did the Critic + Synthesiser loop actually change anything?

    Compares only the rm fields the Synthesiser is allowed to modify
    (see ``_DIFFABLE_RM_KEYS``) plus the full md_files dict. Returns True
    on the first difference found.
    """
    draft_rm = draft.get("rm", {})
    for k in _DIFFABLE_RM_KEYS:
        if draft_rm.get(k) != final_rm.get(k):
            return True
    if draft.get("md_files", {}) != final_md:
        return True
    return False


def _append_note(rm: dict[str, Any], line: str) -> None:
    """Append a reconciliation line to ``rm['notes']`` (creates the key if absent)."""
    existing = rm.get("notes", "")
    rm["notes"] = f"{existing}\n{line}".strip() if existing else line


def _check_verdict_consistency(
    rm: dict[str, Any], md_files: dict[str, str]
) -> tuple[dict[str, Any], dict[str, str]]:
    """Invariant 1: rm.verdict must match the verdict in final_review.md.

    Mismatch -> degrade ``assessment_status`` to ``failed``,
    ``failure_mode`` to ``verdict_inconsistent``, note both observed values.
    Does NOT mechanically rewrite the md to align; that requires deciding
    which side is canonical, which v1 does not attempt (see handoff for the
    middle-ground design).
    """
    parsed = _extract_verdict_from_md(md_files.get("final_review.md", ""))
    rm_verdict_raw = rm.get("verdict")
    if parsed is None or not isinstance(rm_verdict_raw, str):
        return rm, md_files
    rm_verdict = _normalise_verdict(rm_verdict_raw)
    if rm_verdict not in _VERDICTS or parsed not in _VERDICTS:
        # One side has an unrecognised verdict; not our cleanup to do.
        return rm, md_files
    if parsed == rm_verdict:
        return rm, md_files
    rm = dict(rm)
    rm["assessment_status"] = "failed"
    rm["failure_mode"] = "verdict_inconsistent"
    _append_note(
        rm,
        f"[reconciliation: verdict mismatch — risk_matrix.json says "
        f"'{rm_verdict_raw}' but final_review.md says '{parsed}'; "
        "assessment_status degraded to failed]",
    )
    return rm, md_files


def _get_issue_by_id(rm: dict[str, Any], issue_id: str) -> dict[str, Any] | None:
    """Return the first issue matching ``issue_id`` across all severity buckets."""
    for severity in ("critical", "major", "minor", "suggestions"):
        for issue in (rm.get("issues") or {}).get(severity, []) or []:
            if isinstance(issue, dict) and issue.get("id") == issue_id:
                return issue
    return None


def _check_incorporated_claims(
    rm: dict[str, Any],
    diff_exists: bool,
    *,
    draft_rm: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Invariant 2: ``incorporated`` must correspond to an actual diff.

    Per-concern path (patch 0056): when an ``incorporated`` entry carries
    ``addresses_issue_ids`` and ``draft_rm`` is provided, verify that at least
    one of the listed issue IDs actually changed between draft and final rm.
    If none changed, downgrade that specific concern to ``deferred``.

    Aggregate fallback: entries without ``addresses_issue_ids`` (or when
    ``draft_rm`` is absent) fall back to the v1 aggregate check — if ANY diff
    exists, the claim is accepted; if zero diff and at least one ``incorporated``
    claim exists, all are downgraded.
    """
    addressed = rm.get("addressed_concerns")
    if not isinstance(addressed, list) or not addressed:
        return rm
    incorporated_ids = [
        a.get("id", "?") for a in addressed
        if isinstance(a, dict) and a.get("resolution") == "incorporated"
    ]
    if not incorporated_ids:
        return rm

    new_addressed: list[Any] = []
    downgraded: list[str] = []

    for entry in addressed:
        if not isinstance(entry, dict) or entry.get("resolution") != "incorporated":
            new_addressed.append(entry)
            continue

        addr_ids = entry.get("addresses_issue_ids")
        has_per_concern = (
            isinstance(addr_ids, list)
            and bool(addr_ids)
            and all(isinstance(x, str) for x in addr_ids)
            and draft_rm is not None
        )

        if has_per_concern:
            changed = any(
                _get_issue_by_id(draft_rm, iid) != _get_issue_by_id(rm, iid)
                for iid in addr_ids
            )
            if changed:
                new_addressed.append(entry)
            else:
                downgraded.append(entry.get("id", "?"))
                new_addressed.append({
                    **entry,
                    "resolution": "deferred",
                    "reason": (
                        f"incorporation claimed for issue(s) {addr_ids} "
                        "but those issues are unchanged "
                        "(reconciliation per-concern check)"
                    ),
                })
        else:
            if diff_exists:
                new_addressed.append(entry)
            else:
                downgraded.append(entry.get("id", "?"))
                new_addressed.append({
                    **entry,
                    "resolution": "deferred",
                    "reason": "incorporation claimed but Synthesiser produced no "
                              "diff against the draft (reconciliation downgrade)",
                })

    if not downgraded:
        return rm
    rm = dict(rm)
    rm["addressed_concerns"] = new_addressed
    _append_note(
        rm,
        f"[reconciliation: {len(downgraded)} 'incorporated' claim(s) "
        f"downgraded to 'deferred': {', '.join(downgraded)}]",
    )
    return rm


def _check_address_references(rm: dict[str, Any]) -> dict[str, Any]:
    """Invariant 3: required_changes[].addresses must point at extant issue IDs.

    Drop unknown IDs; record what was dropped. R-rows that end up addressing
    zero real issues are kept (they may still be useful) but their orphan
    status is noted.
    """
    issues_block = rm.get("issues") or {}
    valid_ids: set[str] = set()
    for severity in ("critical", "major", "minor", "suggestions"):
        for entry in issues_block.get(severity, []) or []:
            if isinstance(entry, dict) and isinstance(entry.get("id"), str):
                valid_ids.add(entry["id"])
    required_changes = rm.get("required_changes")
    if not isinstance(required_changes, list) or not required_changes:
        return rm
    cleaned: list[Any] = []
    total_dropped = 0
    orphan_rows: list[str] = []
    for r in required_changes:
        if not isinstance(r, dict):
            cleaned.append(r)
            continue
        addresses = r.get("addresses")
        if not isinstance(addresses, list):
            cleaned.append(r)
            continue
        kept = [a for a in addresses if isinstance(a, str) and a in valid_ids]
        dropped = len(addresses) - len(kept)
        total_dropped += dropped
        new_r = {**r, "addresses": kept}
        if not kept and addresses:
            orphan_rows.append(r.get("id", "?"))
        cleaned.append(new_r)
    if total_dropped == 0:
        return rm
    rm = dict(rm)
    rm["required_changes"] = cleaned
    detail = f"[reconciliation: dropped {total_dropped} orphan address(es) from required_changes"
    if orphan_rows:
        detail += f"; R-row(s) now addressing no extant issue: {', '.join(orphan_rows)}"
    detail += "]"
    _append_note(rm, detail)
    return rm


def reconcile_review(
    rm: dict[str, Any],
    md_files: dict[str, str],
    draft_snapshot: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, str]]:
    """Apply the three reconciliation invariants; return cleaned (rm, md_files).

    Never raises. Pure inspection — no LLM calls, no file I/O. Run from
    ``run_review`` between the Synthesiser final pass and ``_write_review``.

    The ``draft_snapshot`` MUST be a deep copy of (rm, md_files) taken
    BEFORE the Critic and Synthesiser final pass run; otherwise Invariant 2's
    diff check is meaningless (the snapshot will alias the mutated objects).
    The caller is responsible for taking that deep copy.

    Invariant order: 2 first (uses pre-reconciliation state for its diff
    check), then 1, then 3. Each invariant is independent — failures in one
    don't suppress the others.
    """
    # Invariant 2 detection runs first so its diff check sees the unmodified
    # Synthesiser output. Mutation happens after.
    diff_exists = _draft_differs_from_final(draft_snapshot, rm, md_files)
    rm = _check_incorporated_claims(rm, diff_exists, draft_rm=draft_snapshot.get("rm", {}))
    rm, md_files = _check_verdict_consistency(rm, md_files)
    rm = _check_address_references(rm)
    return rm, md_files


def snapshot_draft(
    rm: dict[str, Any], md_files: dict[str, str]
) -> dict[str, Any]:
    """Take the deep-copy snapshot the caller needs for ``reconcile_review``.

    Separated out so the caller doesn't have to import ``copy`` or remember
    that shallow-copying isn't enough — Synthesiser revisions can mutate
    nested issue lists in place.
    """
    return {
        "rm": copy.deepcopy(rm),
        "md_files": dict(md_files),  # md values are immutable str; shallow copy is fine
    }
