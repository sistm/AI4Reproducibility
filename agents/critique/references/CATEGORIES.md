# Critique Categories

The Critic raises concerns in exactly five categories. Each is defined by a
contrast: what makes a concern in this category VALID, and what makes a
superficially-similar concern OUT OF SCOPE for the Critic (typically because
it belongs to a different layer — Synthesiser prompt discipline, upstream
agents, or the eventual style linter).

The numbered examples here are loaded verbatim into the Critic's prompt so
the model anchors to concrete patterns rather than free-interpreting the
category labels.

---

## 1. `evidence_gap`

The draft makes a claim and cites an evidence path, but the cited path does
not actually support the claim.

### VALID concerns

- A `critical` issue cites `repo_analysis.md#absolute-path-001` but CQV's
  evidence array points to specific `file:line` references that the draft
  did not surface. The Critic's `suggested_action` is to narrow the cite.
- The verdict cites `kbe_output.json#L11` but line 11 of the actual file
  contains no claim relevant to the issue (anchor is hallucinated or stale).
- `required_changes[].addresses` references issue ID `M1` but no issue in
  `issues.major` has that ID.

### NOT a concern in this category

- A claim with NO cite at all → that is `under_charitable` (escalation
  without evidence) or `missing_upstream_signal` (made-up finding).
- A cite that is correct but to a section the reviewer thinks is "weak
  evidence" → not Critic's job to re-judge upstream confidence.
- A cite formatted as `path/file.md` rather than `path/file.md#anchor` →
  style, handled by Synthesiser prompt or linter.

---

## 2. `over_charitable`

The draft softened or omitted a material upstream finding. The
Synthesiser pulled its punch where the evidence didn't warrant it.

### VALID concerns

- CQV reports `status: "failed"` with `failure_mode: "assets_directory_empty"`,
  but the draft's `upstream_status.cqv.status` is `"partial"`.
- KBE flagged a `reproducibility_gap` with `impact: "critical"` (e.g. "no
  random seed in any script"); the draft mentions it as a `minor` issue
  or as a `suggestion`.
- CQV's `reproducibility_blockers` array is non-empty but the draft's
  `issues.critical` does not reference any of those blockers by ID.
- An MTP statistical-validity check failed in CQV but the draft's verdict
  is `ACCEPT` or `MINOR REVISION` with no mention.

### NOT a concern in this category

- The draft used different severity vocabulary (CQV `major` → draft
  `MAJOR`). That's the documented mapping, not over-charity.
- The draft consolidated three CQV minor issues into one with cumulative
  wording — that's synthesis, not softening, as long as none are dropped.
- The draft chose `MINOR REVISION` over `MAJOR REVISION` when the
  evidence genuinely permits either. The Critic challenges unsupported
  softening, not borderline judgment calls.

---

## 3. `under_charitable`

The draft escalated an upstream finding without new justification — turned
a minor into a critical, or invented a critical that upstream did not flag.

### VALID concerns

- CQV reports a missing README as a `minor` repository_audit finding; the
  draft has it as `issues.critical`.
- The draft's `issues.critical` includes "code uses absolute paths" but
  CQV's evidence array only documents this in one isolated file with a
  workaround noted.
- The verdict is `REJECT` with `risk_score: 95`, but the upstream stages
  reported only `partial` (not `failed`) and the critical findings are all
  borderline-major in upstream classification.

### NOT a concern in this category

- The draft escalates because two `major` issues compound (e.g. no seed
  AND no session info). Compounding is legitimate synthesis.
- The draft adds a critical based on KBE+CQV combined (e.g. KBE says
  "depends on PISA data"; CQV says "PISA data not included"). The
  combined claim is not in either upstream alone, but is supported by
  both — fine.

---

## 4. `internal_inconsistency`

The draft's own fields contradict each other, independent of upstream.

### VALID concerns

- `verdict: "ACCEPT"` with `risk_score: 80` and `risk_level: "HIGH"`.
- `verdict: "REJECT"` but `issues.critical` is empty.
- `risk_level: "LOW"` with `issues.critical` containing two entries.
- `required_changes[].addresses` lists issue IDs that don't exist in the
  `issues` block.
- The narrative in `final_review.md` says "verdict: MAJOR REVISION" but
  `risk_matrix.json` carries `verdict: "MINOR REVISION"`.
- `assessment_status: "complete"` but `notes` says markdown validation
  failed (this case should already be caught by patch 0036; if it slips
  through, the Critic catches it).

### NOT a concern in this category

- `risk_score: 65` with `risk_level: "HIGH"`. The boundaries between
  levels are conventional, not strict. The Critic only flags when the
  pairing is structurally implausible.
- The risk_score is "high relative to the gravity of the issues" in the
  Critic's opinion. That's re-judgment, not inconsistency.

---

## 5. `missing_upstream_signal`

Upstream flagged something material that the draft does not mention at all
— not as a critical, not as a minor, not in the prose anywhere.

### VALID concerns

- KBE's `reproducibility_gaps` array contains "no software versions
  recorded"; the draft has no issue or recommendation about software
  versioning.
- CQV's `statistical_validity` section contains a `fail` verdict on
  multiple-testing correction; the draft's `issues` blocks make no
  reference to multiple testing.
- CQV reports `dependency_validation.status: "failed"`; the draft has no
  issue, recommendation, or note about dependencies.

### NOT a concern in this category

- Upstream made a `pass` finding that the draft doesn't mention. Pass
  findings don't need surfacing.
- Upstream flagged a stylistic preference (e.g. "code could be more
  readable"). Style observations from upstream are not material.
- The draft mentions the upstream finding briefly but not as prominently
  as the Critic would prefer. That's editorial.

---

## Severity assignment

For every concern, choose severity from `blocking` / `material` /
`advisory`:

- `blocking` — the Synthesiser final pass MUST address (incorporate, refute
  with reason, or defer with reason). Reserve for: any `evidence_gap` that
  invalidates a `critical` issue; any `over_charitable` that softens a
  `failed` upstream status; any `internal_inconsistency` between verdict
  and risk_score that would mislead a reader; any `missing_upstream_signal`
  for an upstream `critical` finding.
- `material` — the Synthesiser should address. Includes most
  `evidence_gap` on `major` issues, `under_charitable` escalations, and
  `missing_upstream_signal` for `major` upstream findings.
- `advisory` — consider. Used for `evidence_gap` on `minor` issues and
  for any concern where the Critic's confidence is moderate.

If a concern can't be assigned severity above `advisory` because the
evidence is thin, that's a signal it isn't a Critic-grade concern and
should be dropped from the output rather than included weakly.
