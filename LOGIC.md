# LOGIC — AI4Reproducibility Architecture

This document describes how the pipeline is wired together: what each agent
does, what it reads and writes, how stages communicate, and what the failure
modes are. It is the entry point for new contributors and the reference for
existing ones when memory fades.

The visual companion is [`assets/ai4re.logic.png`](assets/ai4re.logic.png).
The orchestration prompt is [`.kilocode/workflows/ai4r.md`](.kilocode/workflows/ai4r.md).

---

## 1. Pipeline at a glance

Four agents over two stages, separated by a soft execution boundary.

```
                      ┌──────────────── Stage 1 ─────────────────┐
                      │                                          │
   ╭─────────╮        │   ╭──────────╮      ╭──────────╮         │   ╭──────────╮
   │ paper.  │───────▶│   │   KBE    │      │   CQV    │         │   │  Review  │
   │ pdf     │        │   │  agent   │      │  agent   │         │   │  agent   │
   ╰─────────╯        │   ╰────┬─────╯      ╰────┬─────╯         │   ╰────┬─────╯
                      │        │                  │              │        │
                      │   kbe_output.json   cqv_output.json      │   final_review.md
   ╭─────────╮        │        │                  │              │   exhaustive_audit_report.md
   │ code.zip│───────▶│        │             repo_analysis.md    │   checklist.md
   ╰─────────╯        │        │                  │              │   risk_matrix.json
                      │        ▼                  ▼              │        ▲
                      │   ╭──────────────────────────────╮       │        │
                      │   │   ER agent (optional / v0)   │───────┼────────┘
                      │   │   er_output.json             │       │
                      │   ╰──────────────────────────────╯       │
                      └──────────────────────────────────────────┘
                                                   ▲
                                                   │
                            ╭──────────────────────┴───────────────────╮
                            │   prepare_review.sh    validate_review.sh │
                            ╰───────────────────────────────────────────╯
```

The flow is left-to-right. KBE and CQV run independently of each other (they
read different inputs and never see each other's outputs). Their outputs
fan into Review, which assembles the four-file deliverable. ER is optional
and currently always skipped; when implemented it will sit between CQV and
Review.

Deterministic pre-flight and post-flight live in bash scripts called by the
orchestrator at the boundaries.

---

## 2. Per-submission file layout

A single run materialises in one directory. The orchestrator creates this
during pre-flight; agents read and write only within it.

```
ai4r/<review_title>/
├── input/
│   ├── paper.pdf           # the manuscript (caller-supplied)
│   └── assets/             # extracted code supplement (zips extracted here)
├── kbe/
│   ├── kbe_output.json     # structured paper knowledge
│   └── notes.md            # human-readable extraction notes
├── cqv/
│   ├── cqv_output.json     # code-quality audit + checklist evidence
│   └── repo_analysis.md    # human-readable repo analysis
├── er/
│   └── er_output.json      # {"status": "skipped"} by default
├── review/
│   ├── final_review.md             # reviewer-facing summary
│   ├── exhaustive_audit_report.md  # full per-item findings
│   ├── checklist.md                # populated checklist with evidence
│   └── risk_matrix.json            # structured risk + verdict
└── logs/
    └── workflow.log        # appended by every stage
```

Every agent's output file is a stable contract — the validator
(`validate_review.sh`) refuses to mark a run complete unless all eight
files are present and the JSONs have their required top-level keys.

---

## 3. Agents

### 3.1 KBE — Knowledge-Base Extraction

**Skill**: [`agents/knowledge-base-extraction/SKILL.md`](agents/knowledge-base-extraction/SKILL.md)
**Reads**: `input/paper.pdf`, `agents/knowledge-base-extraction/biostat/*.md`
**Writes**: `kbe/kbe_output.json`, `kbe/notes.md`
**Tools**: `pdf2text`, `clean_pdf_text`

KBE is the only agent allowed to read the manuscript. It parses the PDF,
classifies the paper's domain (defaulting to biostat templates), and emits
a structured representation: identified assumptions, statistical methods,
data-generation processes, and the reproducibility gaps the agent flagged
during reading.

The agent is also responsible for populating `paper_title` — the only
field in the entire pipeline that originates from the manuscript text.
Downstream agents (Review) copy this field verbatim; they never re-parse
the PDF.

KBE also emits `reproduction_targets`: the specific figures, tables, and
headline numerical results a reviewer must reproduce. Each is an object with
`id`, `kind` (`figure`/`table`/`numerical_result`), `label`, `caption`,
`what_it_shows`, `source_page`, and `priority`. Because KBE is the only stage
that reads the manuscript, it owns the *identification* of what to reproduce;
the ER stage reads this array to know which produced outputs to compare against
the references. Malformed items (no label/description, unknown `kind`) are
dropped or clamped during output assembly so ER can consume the field directly.

### 3.2 CQV — Code-Quality Verification

**Skill**: [`agents/code-quality-verification/SKILL.md`](agents/code-quality-verification/SKILL.md)
**Reads**: `input/assets/`, `agents/code-quality-verification/references/*.md`
**Writes**: `cqv/cqv_output.json`, `cqv/repo_analysis.md`
**Tools**: `list_files`, `read_file`, `get_dependencies`, `run_static_check` (+ all entries in `tools/cqv_agent/static_checks/`)

CQV is forbidden from reading the manuscript. It inspects the extracted
code supplement, runs the deterministic static checks (see §5), and emits
a structured audit. The audit records per-checklist-item findings with
file/line evidence, so the Review agent can cite specific code locations
in its verdict.

CQV runs items from **both** `checklist.yaml` (the reproducibility rubric)
and `cqv_checklist.yaml` (the code-quality rubric). The cross-reference is
declared in `cqv_checklist.yaml` under the `also_enforces:` block — those
items are CQV's responsibility even though they live in the reproducibility
YAML.

### 3.3 ER — Experimental Run (deferred)

**Skill**: not yet defined
**Reads**: `input/assets/`, planned execution plan from CQV
**Writes**: `er/er_output.json`
**Tools**: `launch_env`, `evaluate_results`, `create_file`

ER is the only agent that would execute submission code, in a Docker
container with reduced runtime parameters. It is currently always skipped
— the workflow writes `{"status": "skipped"}` and proceeds. When
implemented, ER will populate `dynamic` check_type items in both YAMLs
(figure comparison, table comparison, full pipeline runs).

### 3.4 Review

**Skill**: [`agents/review/SKILL.md`](agents/review/SKILL.md)
**Reads**: `kbe/kbe_output.json`, `cqv/cqv_output.json`, `er/er_output.json`, `agents/review/references/full-audit-checklist.md`, `agents/review/assets/*-template.md`, `CHECKLIST.md`
**Writes**: `review/final_review.md`, `review/exhaustive_audit_report.md`, `review/checklist.md`, `review/risk_matrix.json`

Review is the only agent that sees all upstream outputs at once. It runs
in the orchestrator's main context (no subtask isolation) because it needs
that cross-cutting view.

It does not execute code, does not parse the PDF, and does not re-run
static checks — its job is judgment and synthesis. Findings cite evidence
from upstream JSONs by file path; if an upstream output is degraded
(`status: failed` or `partial`), Review marks affected checklist items as
Unverified rather than inventing evidence.

The output schema is locked: `risk_matrix.json` must contain `paper_id`,
`paper_title`, `assessed_at`, `assessment_status`, `verdict`,
`upstream_status`, plus optional `risk_score`, `risk_level`, `issues`,
and `required_changes`. The verdict enum is
`ACCEPT | MINOR REVISION | MAJOR REVISION | REJECT | UNABLE_TO_ASSESS`.

---

## 4. Context-sharing policy

The reason for the split between KBE and CQV is bias control. If the same
agent read both the paper and the code, its code judgment would be
contaminated by what the paper claims, and vice versa. Subtask isolation
enforces this physically.

| Stage  | Allowed reads                                                |
|--------|--------------------------------------------------------------|
| KBE    | paper PDF, KBE skill + biostat templates                     |
| CQV    | extracted code, CQV skill + references                       |
| ER     | extracted code + lockfiles (when enabled)                    |
| Review | KBE/CQV/ER outputs, Review skill + audit references          |

The orchestrator (`.kilocode/workflows/ai4r.md`) spawns KBE and CQV as
Kilo subtasks so their contexts are fresh and bounded. Review runs inline
because it has to see everything anyway.

---

## 5. Checklists and the static-check tool layer

The pipeline is driven by two YAML rubrics, each with its own JSON Schema
and its own generated Markdown view.

| YAML                  | Schema                          | Generated view       | Items |
|-----------------------|---------------------------------|----------------------|-------|
| `checklist.yaml`      | `checklist.schema.json`         | `CHECKLIST.md`       | 24    |
| `cqv_checklist.yaml`  | `cqv_checklist.schema.json`     | `CQV_CHECKLIST.md`   | 36    |

Generation and validation are handled by `tools/checklist_render.py` (run
in CI with `--all --check`). The YAML is authoritative — never hand-edit
the Markdown.

### Item types

Each item declares one `check_type`:

- **`static`** — implemented deterministically in
  `tools/cqv_agent/static_checks/`. Called via `run_static_check(tool_id,
  repo_path)`. 20 implemented; 13 stubbed with `status: not_implemented`.
- **`dynamic`** — requires executing the submission. Implementation is
  deferred to the ER agent.
- **`llm`** — requires LLM judgment. The `tool_id` names a prompt template
  rather than a Python function.

### Cross-references

The reproducibility YAML and the CQV YAML overlap in a controlled way.
Items already declared in the reproducibility YAML are *not* duplicated
in the CQV YAML; instead, `cqv_checklist.yaml` lists them in
`also_enforces:` to record that CQV runs them on behalf of the
reproducibility rubric.

---

## 6. Failure handling

The pipeline favours degraded continuation over hard failure.

### Per-agent status

Every output JSON includes a top-level `status` field with one of:

- `success` — normal completion
- `partial` — some sections succeeded, others didn't
- `failed`  — could not produce useful output
- `skipped` — designated absent (currently only ER)

Every agent's SKILL defines the JSON shape for each of its failure modes.
A crashed agent that writes nothing is a contract violation that hard-fails
the workflow via `validate_review.sh`.

### Upstream-failure propagation

The Review agent inspects upstream `status` fields before doing any
analysis and applies one of these rules:

| Upstream                  | Review action                                                                               |
|---------------------------|---------------------------------------------------------------------------------------------|
| KBE `failed`/`partial`    | Items needing paper context → Unverified                                                    |
| CQV `failed`/`partial`    | Items needing code audit → Unverified                                                       |
| ER `skipped`              | No action (v0 default)                                                                      |
| ER `failed` (when on)     | Execution failure recorded as a finding                                                     |
| All upstream `failed`     | Review's own `assessment_status` becomes `failed`; verdict is `UNABLE_TO_ASSESS`            |

Unverified items are explicit in `checklist.md` with the upstream failure
quoted. They are never silently passed.

### Hard-failure gate

`validate_review.sh` is the only place the workflow can hard-fail. It
runs at Step 5 and exits non-zero if:

- any of the 8 required output files is missing
- any JSON file is missing required top-level keys (`paper_id`, `status`,
  etc. — list in the script)
- `risk_matrix.json` has an invalid verdict enum

If validation fails, the orchestrator surfaces the script's output to the
user. There is no automatic retry.

---

## 7. Drivers and orchestration

### Orchestrator

[`.kilocode/workflows/ai4r.md`](.kilocode/workflows/ai4r.md) is the
production driver. Invoked in Kilo Code via `/ai4r <review_title>`. It is
a prompt: the LLM follows numbered steps, spawning subtasks for KBE and
CQV and running Review inline.

### Pre-flight: `prepare_review.sh`

Called by the orchestrator at Step 0. Pure bash. Responsibilities:

- Validate the `review_title` matches kebab-case
- Create the `ai4r/<title>/` directory tree
- Confirm `input/paper.pdf` exists
- Extract any `.zip` archives in `input/assets/` via the `extract_zip` tool
- Initialise `logs/workflow.log`

Exits non-zero on any failure; the workflow refuses to continue.

### Post-flight: `validate_review.sh`

Called by the orchestrator at Step 5. Pure bash + Python schema check.
Responsibilities:

- Verify all 8 required output files exist and are non-empty
- Parse each JSON output and check required top-level keys
- Print a one-line summary per file
- Exit non-zero on any structural defect

### `assets/execute_workflow.sh` — legacy

This script predates the Kilo orchestrator. It writes hand-crafted
placeholder JSON without calling any LLM, which made it useful as a
file-layout scaffolding test but is **not** a real driver. New work should
use `/ai4r` in Kilo; the shell script is retained only because its file
layout matches the orchestrator's, so it's a fast smoke test for the
post-flight validator.

---

## 8. Tool registry

[`tools/tools.py`](tools/tools.py) is the central registry exposing
functions to agents via `run_tool(name, **kwargs)`. Conceptually:

- **KBE tools**: `pdf2text`, `clean_pdf_text`
- **CQV tools**: `list_files`, `read_file`, `extract_zip`,
  `get_dependencies`, `run_static_check`, `list_static_checks`
- **ER tools** (when enabled): `launch_env`, `evaluate_results`, `create_file`
- **Review tools**: (uses general-purpose file tools; no exclusive set)

The static-check dispatcher (`run_static_check`) is itself a single tool
that internally routes to one of 33 named checks (20 working, 13 stubbed).
This keeps the agent-facing surface small.

---

## 9. CI and quality gates

[`.github/workflows/ci.yml`](.github/workflows/ci.yml) runs on every push
and PR. Three gates:

1. **Checklist validation** — `python -m tools.checklist_render --all
   --check` validates both YAMLs against their schemas and verifies the
   generated Markdown views are in sync with their sources.
2. **Lint** — `ruff check tools/ tests/` enforces style and catches
   common bugs. Fixtures are excluded via `tool.ruff.extend-exclude`.
3. **Test suite** — `pytest tests/` runs ~50 tests, primarily exercising
   the static checks against fixture repos (`tests/fixtures/static_checks/
   {clean,dirty}_repo/`).

CI does not run an end-to-end pipeline test; that requires LLM access and
is left for manual `/ai4r` invocations.

---

## 10. Open work

Tracked under "Sprint" comments in this conversation history; summarised
here for visibility.

- **ER agent**: not implemented. Once ready, will activate `check_type:
  dynamic` items in both YAMLs.
- **13 static-check stubs**: all need an AST or parser. Python side is
  easy (`ast` stdlib); R side needs `tree-sitter-r` or shelling to
  Rscript. The stubs return `status: not_implemented` so Review can
  surface them as Unverified.
- **LLM check prompts**: most `judge_*` tool_ids are placeholder names.
  Each needs a prompt template; the statistical-validity block (7 items)
  is the highest-leverage place to start.
- **Adversarial review pattern**: the Review agent currently runs in a
  single forward pass. A read-only critic + read-write synthesiser loop
  would catch more issues.
- **End-to-end test harness**: a tiny biostat mini-bench (~5 instances)
  with ground-truth labels would catch regressions in the LLM-driven
  stages.

---

## 11. Glossary

- **Review title** — kebab-case identifier for a single submission;
  becomes the slug under `ai4r/<title>/`. Also `paper_id` in every JSON.
- **Reproduction item** — a specific table, figure, or numerical claim
  from the paper that must be reproduced. KBE enumerates these from
  the manuscript.
- **Static check** — deterministic code analysis (regex, file glob, AST)
  with no LLM call. Lives in `tools/cqv_agent/static_checks/`.
- **Evidence** — for any checklist item finding, the file path (and
  optionally line number) that supports the verdict. Findings without
  evidence are not permitted in `risk_matrix.json`.
- **Degraded continuation** — an agent that cannot complete still writes
  a valid output file with `status: failed` or `partial`. Hard failures
  are reserved for the validator.
