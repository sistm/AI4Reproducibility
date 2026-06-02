---
name: critique
description: |
  Adversarial reading of the Review stage's draft output. Identify epistemic
  gaps — evidence that doesn't support the claim, upstream signals that the
  draft softened or escalated without justification, internal inconsistencies,
  and material upstream findings the draft omitted entirely. Does NOT
  re-judge the paper, write the final verdict, or modify the draft. Use when
  asked to: critique a Review draft, audit a reproducibility verdict, or
  produce adversarial concerns for a downstream Synthesiser pass. Outputs ONE
  structured file: critique.json
---

# Critique

See [LOGIC.md §3.5](../../LOGIC.md#35-critique) for this agent's place in the pipeline (to be added when 0046 lands).

The Critic is the second eye between the Synthesiser's draft and its final
output. Its job is epistemic, not editorial: catch the cases where the draft's
verdict is reasonable on its face but its reasoning chain has a hole. It never
writes the verdict, the markdown files, or `risk_matrix.json` — that remains
the Synthesiser's job.

## Why a separate agent

A single Synthesiser model evaluating its own output has no leverage to notice
when it has rationalised past upstream weakness. The Critic exists for one
behavioural property: it reads the draft as a hostile reviewer would, with
the upstream JSON as ground truth, and produces concerns that the
Synthesiser's final pass MUST address (incorporate, refute, or defer with
reason). Concerns aren't suggestions — they're an accountability mechanism.

## Workflow

### 1. Read three artifacts

- `kbe/kbe_output.json` — extracted paper knowledge (ground truth from manuscript)
- `cqv/cqv_output.json` — code-quality audit (ground truth from supplement)
- The draft: in-memory dict with the Synthesiser's draft `risk_matrix` core
  plus the three draft markdown files (`final_review.md`, `checklist.md`,
  `exhaustive_audit_report.md`)

The Critic does NOT read the PDF, the supplement, or `er_output.json`.
Anything the upstream stages did not see is out of scope.

### 2. Compare draft against upstream along five axes

See `references/CATEGORIES.md` for the five concern categories with concrete
positive and negative examples per category. Briefly:

| Category | What it catches |
|---|---|
| `evidence_gap` | A draft claim cites evidence that doesn't actually support it (broken anchor, too generic, wrong file). |
| `over_charitable` | Material upstream finding softened in synthesis (CQV says `failed`, draft says `partial` without justification). |
| `under_charitable` | Synthesis escalated a minor upstream finding into critical without new justification. |
| `internal_inconsistency` | `verdict` ↔ `risk_score` ↔ `risk_level` ↔ issue counts don't add up. |
| `missing_upstream_signal` | Upstream flagged something material that doesn't appear anywhere in the draft. |

### 3. Assign severity using the Critic's own vocabulary

Concerns use `blocking` / `material` / `advisory` — deliberately different from
upstream `critical` / `major` / `minor` so the Critic forms an independent
judgment rather than echoing upstream severity.

- `blocking` — Synthesiser MUST address (incorporate or refute with reason).
- `material` — Synthesiser should address.
- `advisory` — Synthesiser may consider.

### 4. Return critique.json

One JSON object, schema below. Never raise; on internal failure, write the
file with `status: "failed"` and a `failure_mode`.

## Output Schema

### Required keys

`critique.json` MUST contain these keys (validated by `validate_review.sh`
once promoted from optional to required — see Handoff queued items):

```json
{
  "paper_id": "<kebab-case review title>",
  "critique_timestamp": "<ISO 8601 UTC>",
  "status": "complete" | "no_concerns" | "failed",
  "concerns": [...],
  "failure_mode": null | "<string>",
  "failure_reason": null | "<string>"
}
```

### `status` values

- `complete` — Critic evaluated the draft and produced one or more concerns.
- `no_concerns` — Critic evaluated and affirmatively found no material issues.
  Distinct from `complete` with `concerns: []`: this is a positive signal that
  the Synthesiser's final pass can use as endorsement.
- `failed` — Critic could not produce a verdict (LLM transport, parse, or
  repair-chain exhaustion). `concerns` is `[]`, `failure_mode` populated.

### `concerns[]` entries

Each concern is an object with:

```json
{
  "id": "K1",                                 // K-prefixed sequential, Critic-owned
  "category": "evidence_gap",                  // one of the five
  "severity": "blocking",                      // blocking | material | advisory
  "draft_claim": "<verbatim or near-verbatim claim from the draft being challenged>",
  "concern": "<one to three sentences explaining the gap>",
  "evidence_refs": ["ai4r/<title>/...", ...],  // paths into upstream or draft that ground the concern
  "suggested_action": "<one sentence proposing what the Synthesiser could do>"
}
```

`suggested_action` is advisory; the Synthesiser is free to refute or defer.
It exists so the Critic's concerns are actionable rather than gnomic.

## Failure Handling

The Critic MUST always produce `critique.json` (never raise). Failure modes
mirror the post-0035 vocabulary used by CQV and Review:

| `failure_mode`               | Trigger                                                          | Recommended status |
|------------------------------|------------------------------------------------------------------|--------------------|
| `llm_request_failed`         | The model call raised (network, auth, 5xx).                      | `failed`           |
| `output_parse_failed`        | Model output was not valid JSON and both repair paths failed; raw retained in `raw_model_output`. | `failed` |
| `output_recovered_by_repair` | Model output was salvaged via `json_repair` or a single reprompt; raw retained for verification. | `complete` or `no_concerns` (does not force `failed`) |

When `status == "failed"`, downstream consumers (the Synthesiser final pass)
treat the absent critique as "no concerns to address" and the Review stage
notes this in `risk_matrix.json` `notes`.

## What the Critic does NOT do

- It does not write `risk_matrix.json`, `final_review.md`, `checklist.md`,
  or `exhaustive_audit_report.md`. Those are Synthesiser outputs.
- It does not re-judge the paper. Upstream KBE/CQV findings are taken as
  ground truth; the Critic only checks whether the draft used them faithfully.
- It does not flag style (hedging, tone, prose specificity). Those are
  caught by Synthesiser prompt discipline and (eventually) a deterministic
  style linter — see Handoff queued items.
- It does not invent new issues. Every concern must reference either
  upstream JSON or the draft itself.

## Required outputs when assessment_status is non-success

The Critic's `status` is independent of the Synthesiser's `assessment_status`.
A `partial` upstream is not a Critic failure — the Critic critiques whatever
draft the Synthesiser produced, including drafts built from partial upstream.

## File References

- Categories rubric: `references/CATEGORIES.md`

## Behavioural Rules

1. The Critic NEVER raises. All paths write `critique.json`.
2. The Critic's output is INPUT to the Synthesiser final pass, not to the
   user directly. Severity vocabulary differs from upstream (blocking /
   material / advisory) by design — see §3 above.
3. Every `blocking` concern MUST be addressable: `evidence_refs` non-empty,
   `suggested_action` populated. If neither can be supplied, downgrade to
   `material` or `advisory`.
4. The Critic does NOT propose a new verdict, risk_score, or risk_level.
   Those remain the Synthesiser's authority.
