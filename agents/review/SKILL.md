---
name: review
description: |
  Synthesise a reproducibility verdict for a scientific paper from the upstream KBE and CQV (and ER) outputs. Use when asked to: produce a review verdict, assemble the risk matrix, or judge computational reproducibility from already-extracted knowledge and code-audit results. Does NOT execute code, parse the PDF, or re-run static checks — it is judgment and synthesis over upstream JSON. Outputs FOUR structured files: final_review.md, exhaustive_audit_report.md, checklist.md, and risk_matrix.json
---

# Reproducibility Review

see [LOGIC.md §3.4](../../LOGIC.md#34-review) for this agent's place in the pipeline.

Synthesise a reproducibility verdict from the upstream KBE and CQV (and ER) outputs. Review does not execute code, parse the PDF, or re-run static checks — its job is judgment and synthesis (see LOGIC.md §3.4).

## Workflow

### 1. Read the upstream outputs

Review never reads the manuscript PDF or the code itself — KBE and CQV (and,
when enabled, ER) do that. Start by reading their JSON outputs:

- `kbe/kbe_output.json` — extracted paper knowledge (title, assumptions,
  statistical methods, data-generation processes, reproducibility gaps).
- `cqv/cqv_output.json` — the code-quality audit (repository audit, dependency
  validation, reproducibility blockers, execution readiness).
- `er/er_output.json` — execution results, when ER is enabled (skipped in v0).

### 2. Assess coverage and degradation

Inspect each upstream `status` field BEFORE any synthesis (see Failure
Handling). Decide `assessment_status` from the upstream state: `complete` when
KBE and CQV both succeeded, `partial` when any upstream output is `partial` or
`failed` (affected checklist items become Unverified), `failed` when no
meaningful verdict can be produced. Synthesise only from what the upstream
outputs contain — never re-derive paper or code facts, and never execute code
or re-run static checks (that is ER's and CQV's job).

### 3. Generate Exhaustive Audit Report

Output **`exhaustive_audit_report.md`** using template in `assets/audit-report-template.md`
- Comprehensive audit synthesising the KBE and CQV findings
- Inputs section quoting each upstream `status` (and any `failure_mode`)
- Code-quality findings as reported by CQV, cited by evidence path
- Execution results from ER when enabled (omitted while ER is skipped)

### 4. Generate Final Review Summary

Output **`final_review.md`** using template in `references/full-audit-checklist.md`
- Executive summary with overall assessment
- Verdict (ACCEPT/MINOR REVISION/MAJOR REVISION/REJECT)
- Key findings and recommendations

### 5. Generate Biometrical Journal Essential Checklist

Output **`checklist.md`** using template in `assets/review-template.md`
- Biometrical Journal essential reproducibility compliance checklist
- All items checked or documented with explanations
- list all Critical issues, Major issues, Minor issues, and Suggestions for Improvement

### 6. Generate Risk Matrix

Output **`risk_matrix.json`** with exactly this schema:

```json
{
  "paper_id": "kebab-case-slug-matching-review-title",
  "paper_title": "Full Human-Readable Title",
  "assessed_at": "2026-05-29T14:30:00Z",
  "risk_score": 42,
  "risk_level": "MEDIUM",
  "verdict": "MINOR REVISION",
  "issues": {
    "critical": [{"id": "C1", "description": "...", "evidence": "ai4r/<slug>/cqv/repo_analysis.md#L42"}],
    "major":    [{"id": "M1", "description": "...", "evidence": "..."}],
    "minor":    [{"id": "m1", "description": "...", "evidence": "..."}],
    "suggestions": [{"id": "S1", "description": "..."}]
  },
  "required_changes": [
    {"id": "R1", "description": "...", "addresses": ["C1"], "done": false}
  ]
}
```

Field constraints:
- `risk_score` is an integer 0-100 where higher means *less* reproducible.
- `risk_level` is one of `LOW` (0-25), `MEDIUM` (26-50), `HIGH` (51-75), `CRITICAL` (76-100).
- `verdict` is exactly one of `ACCEPT`, `MINOR REVISION`, `MAJOR REVISION`, `REJECT`.
- Every issue object MUST have an `evidence` field pointing to a file path
  (with optional `#L<line>` anchor) under `ai4r/<review_title>/`. Issues
  without traceable evidence MUST NOT be included — they belong in the
  `final_review.md` narrative instead.
- The `assessed_at` field is an ISO 8601 UTC timestamp.

### 7. Output Location

All outputs saved to: `/ai4r/{review_title}/review/`

**Severity levels:
- **Critical**: Blocks reproduction (missing code/data, crashes, fundamentally wrong results)
- **Major**: Significantly impedes reproduction (missing docs, manual steps needed, partial failures)
- **Minor**: Does not block reproduction (style issues, missing but inferable info)
- **Suggestions**: Best practices not followed

---

## Principles

**Synthesise, don't re-derive** — Build the verdict from the KBE and CQV outputs; never read the paper or run code yourself.
**Cite evidence** — Every issue points to a file path under `ai4r/<review_title>/`; findings without traceable evidence belong in the narrative, not the risk matrix.
**Never invent** — When an upstream output is degraded, mark items Unverified rather than guessing.
**Be constructive** — Goal is helping authors improve their supplement.
**Document thoroughly** — Another reviewer should understand exactly how the verdict was reached.

---

## References

- `references/full-audit-checklist.md` — Complete checklist for documentation, completeness, organization, quality, reproducibility, and advices to add to the items from the template
- `assets/audit-report-template.md` — Detailed output template for the Exhaustive Audit Report document
- `assets/review-template.md` — Template output for the Biometrical Journal essential Checklist document
- `references/full-audit-checklist.md` — Template for the Final Review Summary document

---

## Failure Handling

The Review agent has two distinct failure responsibilities:

1. **Upstream failure** — KBE or CQV (or ER) emitted `status: "failed"` or
   `status: "partial"`. Review must degrade gracefully and never invent
   evidence to fill the gap.
2. **Self failure** — Review itself cannot complete the audit. Even then,
   Review MUST produce all four required files. A missing output file is
   a hard pipeline failure.

### Handling upstream failure (degraded inputs)

Before doing any analysis, read each upstream JSON and inspect its `status`
field. Apply these rules:

| Upstream status                  | Action                                                                                                                                              |
|----------------------------------|------------------------------------------------------------------------------------------------------------------------------------------------------|
| KBE `failed`                     | Do not infer methodology, statistical methods, or assumptions. Mark every checklist item that depends on paper context as **Unverified**.            |
| KBE `partial`                    | Use only `partial_data.sections_extracted`. Mark items that depend on missing sections as **Unverified**.                                            |
| CQV `failed`                     | Do not pretend to have audited the code. Every code-quality, dependency, and reproducibility checklist item becomes **Unverified**.                  |
| CQV `partial`                    | Use only `partial_data.checks_completed`. Items dependent on failed/skipped checks become **Unverified**.                                            |
| ER `skipped` (default)           | No action; ER is expected to be skipped in v0. Do not penalize.                                                                                      |
| ER `failed` (when enabled)       | Report execution failure as a finding. Do not infer results from CQV alone.                                                                          |

"Unverified" items count as evidence gaps in the risk model. They MUST be
listed explicitly in `checklist.md` with a brief reason (e.g. "Unverified —
CQV failed: assets_directory_empty"). They MUST NOT be silently passed.

When upstream degradation is the *primary* reason the audit cannot be
completed, the agent's own status becomes `partial` (see below).

### Self-status enum

The risk matrix gets a new field `assessment_status` distinct from
`verdict`. The split lets a successful audit reach `verdict: REJECT`
without confusing it with an audit that couldn't run.

| `assessment_status` | Meaning                                                                                       |
|---------------------|------------------------------------------------------------------------------------------------|
| `complete`          | All checklist items were either Pass, Fail, or Suggestion with concrete evidence.              |
| `partial`           | One or more items marked Unverified due to upstream gaps; verdict still issued with caveat.    |
| `failed`            | Review could not produce a meaningful verdict at all.                                          |

### Verdict enum (extended)

The original four values plus one sentinel for the failure case:

`ACCEPT` | `MINOR REVISION` | `MAJOR REVISION` | `REJECT` | `UNABLE_TO_ASSESS`

`UNABLE_TO_ASSESS` is only valid when `assessment_status` is `failed`.

### Known self-failure modes

| `failure_mode`              | Trigger                                                                  |
|-----------------------------|---------------------------------------------------------------------------|
| `all_upstream_failed`       | KBE and CQV both have `status: "failed"` and ER is skipped/failed.        |
| `llm_request_failed`        | The risk-matrix model call raised (network, auth, 5xx).                   |
| `output_parse_failed`       | Risk-matrix JSON could not be parsed and both repair paths failed; raw retained in `raw_model_output`. |
| `output_recovered_by_repair`| Risk-matrix JSON was salvaged via `json_repair` or a single reprompt; raw retained for verification (does **not** force `assessment_status: failed`). |
| `template_render_error`     | One of the markdown templates failed to render with available evidence.   |
| `parse_error`               | Reading an upstream JSON raised an error.                                 |

### Required outputs when assessment_status = "partial"

All four files are written normally, but:

- `final_review.md` opens with a one-paragraph "Limitations of this audit"
  notice listing which upstream stages were degraded and what that means
  for confidence in the verdict.
- `checklist.md` marks each affected item as **Unverified** with the reason.
- `exhaustive_audit_report.md` quotes the failure modes verbatim from
  upstream JSONs in its "Inputs" section.
- `risk_matrix.json` sets `assessment_status: "partial"`, lists the upstream
  failures under a top-level `upstream_status` block, and may still issue a
  conventional verdict.

### Required outputs when assessment_status = "failed"

All four files are still written. Concrete minimum content:

`risk_matrix.json`:

```json
{
  "paper_id": "<review_title>",
  "paper_title": "<from kbe_output.json paper_title, or null>",
  "assessed_at": "<ISO 8601 UTC>",
  "assessment_status": "failed",
  "failure_mode": "all_upstream_failed",
  "failure_reason": "KBE: pdf_unreadable; CQV: assets_directory_empty",
  "upstream_status": {
    "kbe": {"status": "failed", "failure_mode": "pdf_unreadable"},
    "cqv": {"status": "failed", "failure_mode": "assets_directory_empty"},
    "er":  {"status": "skipped"}
  },
  "risk_score": null,
  "risk_level": null,
  "verdict": "UNABLE_TO_ASSESS",
  "issues": {"critical": [], "major": [], "minor": [], "suggestions": []},
  "required_changes": []
}
```

`final_review.md`, `exhaustive_audit_report.md`, and `checklist.md` each
contain a one-section explanation of why the audit could not be completed,
quoting the upstream failure modes verbatim.

### Behavioral rules

1. NEVER raise an unhandled exception. Catch parse / template / schema
   errors and write a `failed` review.
2. Always read all upstream JSONs FIRST, before any analysis or report
   generation. Decide `assessment_status` from upstream state and adjust
   the workflow accordingly.
3. Every Unverified checklist item MUST cite the upstream failure that
   caused it. "Unverified" without attribution is a SKILL violation.
4. The `paper_id` field MUST be set to the kebab-case `review_title` from
   the workflow arguments, even when no paper or repo could be read. It is
   stable across all outputs and survives upstream failure.
5. The `paper_title` field MUST be copied from `kbe_output.json.paper_title`.
   When that source value is `null` (KBE could not parse the title), Review
   sets `paper_title` to `null` as well. Review MUST NOT infer or invent a
   title from any other source.
6. `risk_score` and `risk_level` are nullable ONLY when
   `assessment_status: "failed"`. For `partial` they must still be computed
   on the evidence that exists.
7. Log every self-failure to `ai4r/<review_title>/logs/workflow.log` in
   addition to writing it into the four output files.
