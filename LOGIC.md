# LOGIC — AI4Reproducibility Architecture

This document is the technical reference for the pipeline: what each stage
does, how data flows between them, what the internal structure of each agent
looks like, and what happens when things go wrong.

The orchestrator entry point is `tools/orchestrator/run.py`.
The visual companion is [`assets/ai4re.logic.png`](assets/ai4re.logic.png).

---

## 1. Pipeline overview

The pipeline has **three sequential stages** separated by clear data contracts.
Stages 1a and 1b (CQV and KBE) run in parallel and are intentionally isolated
from each other. Stage 2 (ER) is optional. Stage 3 (Review) synthesises all
upstream outputs into a final verdict.

```
  INPUTS
  ------
  paper.pdf ------------------------------------------------+
  code.zip / assets/ ------------------+                   |
                                       |                   |
                                       v                   v
          +----------------------------+    +--------------------------+
          |  STAGE 1a . CQV           |    |  STAGE 1b . KBE         |
          |  Code Quality             |    |  Knowledge-Base         |
          |  Verification             |    |  Extraction             |
          |                           |    |                         |
          |  (1) Stat-judge pre-pass  |    |  . PDF extraction       |
          |    16 LLM calls           |    |  . Domain templates     |
          |    (evidence -> verdict)  |    |  . Statistical methods  |
          |                           |    |  . Reproduction targets |
          |  (2) 33 static checks     |    |  . Assumptions          |
          |    (deterministic: AST,   |    |                         |
          |     regex, heuristics)    |    |  Reads the manuscript;  |
          |                           |    |  CQV never does.        |
          |  (3) Main LLM audit       |    +-------------+-----------+
          |    (4 file-reading tools) |                  |
          |                           |                  |
          |  (4) Evidence rehydration |                  |
          |    (+-5 lines of context  |                  |
          |     per cited line)       |                  |
          +-------------+-------------+                  |
                        |                                |
                cqv_output.json                  kbe_output.json
                repo_analysis.md                 notes.md
                        |                                |
                        +----------------+---------------+
                                         |
                                         v
          +----------------------------------------------+
          |  STAGE 2 . ER  (optional: --er-enabled)      |
          |  Experimental Run                            |
          |                                              |
          |  . Execute submission code in isolation      |
          |  . Compare produced figures/tables against   |
          |    manuscript references via pHash           |
          |  . Populate dynamic checklist items          |
          +--------------------+-------------------------+
                               |
                       er_output.json
                               |
                               v
          +----------------------------------------------+
          |  STAGE 3 . Review                            |
          |                                              |
          |  . Wire ER comparisons -> checklist items    |
          |    (deterministic, before LLM call)          |
          |  . LLM synthesis of all upstream evidence    |
          |  . Reconcile verdict from narrative text     |
          |  . Coherence clamp: verdict <-> risk_score   |
          |  . Assemble four-file deliverable            |
          +--------------------+-------------------------+
                               |
          +--------------------+-------------------------+
          |  OUTPUT                                      |
          |  final_review.md                            |
          |  exhaustive_audit_report.md                 |
          |  checklist.md                               |
          |  risk_matrix.json                           |
          |                                             |
          |  verdict in {ACCEPT,                        |
          |               MINOR REVISION,               |
          |               MAJOR REVISION,               |
          |               UNABLE_TO_ASSESS}             |
          +---------------------------------------------+
```

**Why KBE and CQV are isolated from each other:** if the same agent read
both the paper and the code, its code judgment would be contaminated by
what the paper claims, and vice versa. Subtask isolation enforces this
as a hard boundary.

---

## 2. Per-submission file layout

Every run materialises under one directory keyed to the review title.

```
ai4r/<review_title>/
├── input/
│   ├── paper.pdf               # manuscript (caller-supplied)
│   └── assets/                 # code supplement (extracted from zip)
├── kbe/
│   ├── kbe_output.json         # structured paper knowledge
│   └── notes.md                # human-readable extraction notes
├── cqv/
│   ├── cqv_output.json         # code-quality audit + checklist evidence
│   └── repo_analysis.md        # human-readable repo analysis
├── er/
│   └── er_output.json          # comparison results, or {"status":"skipped"}
├── review/
│   ├── final_review.md         # reviewer-facing narrative
│   ├── exhaustive_audit_report.md   # full per-item findings with evidence
│   ├── checklist.md            # populated checklist
│   └── risk_matrix.json        # structured verdict + risk score
└── logs/
    └── workflow.log            # appended by every stage
```

The post-flight validator (`validate_review.sh`) treats any missing or
structurally invalid output file as a hard failure.

---

## 3. Stages in detail

### 3.1 Stage 1a — CQV (Code-Quality Verification)

**Entry point:** `tools/orchestrator/cqv.py :: run_cqv()`
**Reads:** `input/assets/`
**Writes:** `cqv/cqv_output.json`, `cqv/repo_analysis.md`

CQV runs four internal passes in sequence.

#### Pass 1: Stat-judge pre-pass

`tools/orchestrator/stat_evidence.py` scans all `.R` / `.py` / `.Rmd`
source files with per-check regex pattern sets, extracting the lines most
relevant to each of the 16 code-quality / statistical LLM checks.
`tools/orchestrator/stat_judges.py` then makes one bounded LLM call per
check (rubric + evidence -> verdict). Evidence budgets are graduated by
severity: critical 8 000 chars, major 6 000, minor 4 000, suggestion 3 000.

The 16 judges span seven categories:

| Category | Checks |
|---|---|
| Statistical validity | test assumptions, MTP correction, data leakage, CI construction, representative sampling, post-hoc adjustment, model diagnostics |
| Data handling | NA handling, explicit types, dataframe mutation |
| Performance | redundant object copies |
| Security | path sanitisation |
| Documentation | docstring quality |
| Testing | edge-case coverage, integration test coverage |
| Dependencies | deprecated packages |

Verdicts (`pass` / `fail` / `not_applicable` / `unverified`) from this
pass are injected as pre-determined answers into the main prompt so the
main LLM does not re-debate them.

#### Pass 2: Static checks

`tools/cqv_agent/static_checks/dispatch.py` routes 33 named checks across
six modules. All 33 are fully implemented — no stubs remain:

| Module | Checks |
|---|---|
| `file_inventory.py` | archive layout, environment tooling, main entry point, output naming, file naming hygiene, readme, sessioninfo, python requirements, version pinning, test directory |
| `r_heuristics.py` | set.seed scope, imports complete, function docs, unbounded loops, global state mutation |
| `danger_patterns.py` | no absolute paths, no workspace clear, no auto-install, no eval/parse, no system calls, no hardcoded secrets, no attach, no arbitrary downloads, no unsafe deserialisation, path helpers |
| `heuristics_cross_lang.py` | parse success, duplicate code blocks, growing vectors, error handling coverage |
| `check_r_ast.py` (tree-sitter, optional) | undefined references, function signatures, dead code, loop invariants |

Each check returns `pass`, `fail`, `warning`, or `not_implemented` (only
for AST checks when the optional `tree-sitter-languages` dep is absent).

#### Pass 3: Main LLM audit

The main CQV model call receives the static-check verdicts and the
stat-judge verdicts as context, and uses four file-reading tools
(`list_files`, `read_file`, `get_dependencies`, `extract_zip`) to
produce the structured `repository_audit` JSON.

#### Pass 4: Evidence rehydration

After the model returns, `_rehydrate_evidence()` walks every
`{file, line}` evidence object and splices in a +-5-line source context
block with the cited line marked `>>`. This context travels to Review,
where it anchors citations in the audit report without requiring Review
to re-open files.

---

### 3.2 Stage 1b — KBE (Knowledge-Base Extraction)

**Entry point:** `tools/orchestrator/kbe.py :: run_kbe()`
**Reads:** `input/paper.pdf`, `agents/knowledge-base-extraction/biostat/*.md`
**Writes:** `kbe/kbe_output.json`, `kbe/notes.md`

KBE is the only agent allowed to read the manuscript. It extracts:

- **paper_title** — the only field in the entire pipeline that originates
  from the manuscript; downstream agents copy it verbatim.
- **Statistical methods, assumptions, data-generation process** — used by
  the Review agent to cross-reference against the code audit.
- **reproduction_targets** — an array of `{id, kind, label, caption,
  what_it_shows, source_page, priority}` objects identifying the specific
  figures, tables, and numerical results that must be reproduced. The ER
  stage reads this array directly to know what to compare.

---

### 3.3 Stage 2 — ER (Experimental Run) — optional

**Entry point:** `tools/orchestrator/er.py :: run_er(enabled=False)`
**Reads:** `input/assets/`, `kbe/kbe_output.json` (reproduction targets)
**Writes:** `er/er_output.json`
**CLI flag:** `--er-enabled`

When disabled (the default), ER writes `{"status": "skipped"}` and the
rest of the pipeline treats all dynamic checklist items as unverified.

When enabled, ER executes the submission code in an isolated Docker
environment, collects produced outputs, and compares them against the
manuscript reference images using perceptual hashing (pHash, threshold
`DEFAULT_PHASH_THRESHOLD = 10`). The output `comparisons` array records
`pass`, `fail`, `mismatch_flagged`, or `no_artifact_produced` per target.

---

### 3.4 Stage 3 — Review (Synthesis)

**Entry point:** `tools/orchestrator/review.py :: run_review()`
**Reads:** `kbe/kbe_output.json`, `cqv/cqv_output.json`, `er/er_output.json`
**Writes:** `review/final_review.md`, `review/exhaustive_audit_report.md`,
           `review/checklist.md`, `review/risk_matrix.json`

Review is the only agent that sees all upstream outputs simultaneously.

Three pre-LLM steps run before the main model call:

1. **Dynamic checklist wiring** — ER comparison results are deterministically
   mapped to checklist items (`audit-verify-figures-match`,
   `audit-verify-tables-match`) so the LLM cannot contradict them.
2. **Upstream-status check** — if KBE or CQV returned `failed` / `partial`,
   dependent checklist items are pre-marked Unverified.
3. **Checklist prompt assembly** — pre-determined verdicts are injected with
   a "do NOT override" instruction block.

After the main model call, `_normalise_core()` applies two post-processing
rules:

- **REJECT remapping** — any model output of `REJECT` is normalised to
  `MAJOR REVISION` (REJECT is not a valid output verdict).
- **Coherence clamp** — verdict and `risk_score` must be consistent.
  `ACCEPT` is clamped to [0-35], `MINOR REVISION` to [15-60],
  `MAJOR REVISION` to [40-100]. Inconsistent pairs (e.g. ACCEPT/80) are
  silently corrected.

---

## 4. Context-separation policy

| Stage | May read | May not read |
|---|---|---|
| KBE | paper PDF, KBE skill + biostat templates | code, CQV output |
| CQV | code assets, CQV skill + references | paper PDF, KBE output |
| ER | code assets, KBE reproduction targets | paper PDF |
| Review | KBE + CQV + ER outputs, Review skill | raw paper PDF, raw code |

The orchestrator runs KBE and CQV as isolated Python subprocesses so their
in-memory state cannot bleed. Review runs in the main process because it
must see everything.

---

## 5. Checklists

The pipeline is driven by two YAML rubrics.

| YAML | Schema | Rendered Markdown | Items |
|---|---|---|---|
| `checklist.yaml` | `checklist.schema.json` | `CHECKLIST.md` | 24 |
| `cqv_checklist.yaml` | `cqv_checklist.schema.json` | `CQV_CHECKLIST.md` | 36 |

`tools/checklist_render.py` generates and validates the Markdown views.
The YAML is always authoritative.

### Check types

| `check_type` | Implemented by | Count |
|---|---|---|
| `static` | `tools/cqv_agent/static_checks/` (deterministic) | 33 |
| `llm` | `tools/orchestrator/stat_judges.py` (bounded LLM call) | 16 |
| `dynamic` | `tools/orchestrator/er.py` (requires `--er-enabled`) | varies |

---

## 6. Python orchestrator

The primary entry point is `tools/orchestrator/run.py`.

```bash
# Standard run (ER skipped)
python -m tools.orchestrator.run smoke-test

# With experimental run enabled
python -m tools.orchestrator.run smoke-test --er-enabled
```

The orchestrator:

1. Runs `prepare_review.sh` (pre-flight: directory setup, zip extraction)
2. Calls `run_kbe()` and `run_cqv()` (Stage 1)
3. Calls `run_er(enabled=...)` (Stage 2, writes `{"status":"skipped"}` if off)
4. Calls `run_review()` (Stage 3)
5. Runs `validate_review.sh` (post-flight: schema + file presence checks)

Shell log noise is suppressed at startup: `PYMUPDF_MESSAGE=0` silences
pymupdf's layout hint; the `LiteLLM` / `litellm` loggers are set to ERROR
so provider-failover chatter does not pollute the console.

---

## 7. Failure handling

### Per-agent status codes

Every output JSON includes a top-level `status`:

| Value | Meaning |
|---|---|
| `success` | Normal completion |
| `partial` | Some sections produced, others failed |
| `failed` | Could not produce useful output |
| `skipped` | Intentionally absent (ER when `--er-enabled` is off) |

### Upstream-failure propagation

| Upstream status | Review action |
|---|---|
| KBE `failed` / `partial` | Items needing paper context -> Unverified |
| CQV `failed` / `partial` | Items needing code audit -> Unverified |
| ER `skipped` | Dynamic items -> Unverified (no penalty) |
| ER `failed` | Execution failure recorded as a MAJOR finding |
| All upstream `failed` | `assessment_status = failed`, verdict = `UNABLE_TO_ASSESS` |

### Hard-failure gate

`validate_review.sh` runs at post-flight and exits non-zero if any of the
eight required output files is missing, any JSON is structurally invalid,
or `risk_matrix.json` contains an unknown verdict. There is no automatic
retry.

---

## 8. Tool registry

`tools/tools.py` exposes a `run_tool(name, **kwargs)` interface.

| Stage | Tools |
|---|---|
| KBE | `pdf2text`, `clean_pdf_text` |
| CQV | `list_files`, `read_file`, `get_dependencies`, `extract_zip`, `run_static_check`, `list_static_checks` |
| ER | `launch_env`, `evaluate_results`, `create_file` |
| Review | (general file tools; no exclusive set) |

`run_static_check(tool_id, repo_path)` dispatches to the relevant check
function across six modules. All 33 checks return a real verdict; the four
that require `tree-sitter-languages` return `not_implemented` gracefully
when the optional dependency is absent.

---

## 9. CI and quality gates

`.github/workflows/ci.yml` runs on every push and PR:

1. **Checklist validation** — `python -m tools.checklist_render --all --check`
   validates both YAMLs against their schemas and verifies the Markdown views
   are in sync.
2. **Lint** — `ruff check tools/ tests/`
3. **Tests** — `pytest tests/`  (653 tests, 1 skipped; no LLM access required)

CI does not run an end-to-end pipeline test; that requires LLM access and is
done manually via `python -m tools.orchestrator.run smoke-test`.

---

## 10. Open work

| Item | Status | Notes |
|---|---|---|
| Full ER smoke with real submission zip | Pending | First live ER validation; calibrate pHash threshold |
| Adversarial review loop | Not started | Critic + synthesiser pass would catch more issues |
| End-to-end mini-bench (~5 labelled instances) | Not started | Regression testing for LLM stages |
| ER spot-check mode | Not started | Sample first N figures for rapid iteration |

---

## 11. Glossary

- **Review title** — kebab-case identifier for one submission; becomes the
  directory slug under `ai4r/<title>/` and `paper_id` in every JSON.
- **Reproduction target** — a specific figure, table, or numerical result
  from the manuscript that ER must reproduce. Enumerated by KBE.
- **Static check** — deterministic code analysis (AST, regex, file glob).
  Returns a verdict without any LLM call.
- **Stat judge** — one bounded LLM call evaluating a specific code-quality
  dimension against a curated rubric. Runs in the CQV pre-pass.
- **Evidence** — file path + line number (+ +-5-line context block after
  rehydration) that anchors a finding. Findings without evidence are
  not permitted in `risk_matrix.json`.
- **Degraded continuation** — an agent that cannot complete still writes a
  valid JSON with `status: failed` or `partial`. Hard failures are reserved
  for the post-flight validator.
- **Coherence clamp** — post-normalisation enforcement that verdict and
  risk_score are consistent. ACCEPT -> risk <= 35;
  MINOR REVISION -> risk 15-60; MAJOR REVISION -> risk >= 40.
