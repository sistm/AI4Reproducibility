# AI4Reproducibility

**Lead developer:** Boris P. Hejblum -- [boris.hejblum@u-bordeaux.fr](mailto:boris.hejblum@u-bordeaux.fr)
**Developer:** Jad El Karchi -- [jad.el-karchi@u-bordeaux.fr](mailto:jad.el-karchi@u-bordeaux.fr)

Inserm UMR 1219 BPH / SISTM team -- University of Bordeaux & Inria

![Python](https://img.shields.io/badge/Python-3.12+-blue)
![Tests](https://img.shields.io/badge/tests-653%20passing-brightgreen)
![License](https://img.shields.io/badge/license-Apache%202.0-blue)

> **AI4Reproducibility** is an agentic pipeline for automated reproducibility
> review of scientific paper submissions. It reads a manuscript PDF and its
> associated code supplement, and produces a structured audit report with a
> three-level verdict (Accept, Minor Revision, Major Revision).

---

## Overview

Verifying reproducibility during peer review is time-consuming, subjective,
and hard to standardise. AI4Reproducibility addresses this by running four
specialised agents in sequence -- each with a clearly bounded role -- to
produce a comprehensive, evidence-anchored assessment.

The pipeline is designed for biostatistics and computational biology
submissions but is domain-adaptable through its YAML-driven rubric system.

---

## Pipeline

```
  paper.pdf --------------------------------+
  code supplement ----------------+         |
                                  |         |
                      +-----------+--+  +---+----------+
                      |  CQV         |  |  KBE        |  <- Stage 1 (parallel)
                      |  Code audit  |  |  Paper read |
                      +-------+------+  +------+-------+
                              |                |
                      +-------+----------------+
                      |  ER  (optional)              <- Stage 2
                      |  Experimental run
                      +-------+-------------------------
                              |
                      +-------+------+
                      |  Review      |               <- Stage 3
                      |  Synthesis   |
                      +-------+------+
                              |
              +---------------+----------------+
              |  final_review.md               |
              |  exhaustive_audit_report.md    |
              |  checklist.md                  |
              |  risk_matrix.json              |
              +--------------------------------+
```

**Stage 1 -- KBE and CQV run in parallel with isolated contexts** (neither
can see the other's inputs or outputs). This prevents the code reviewer
from being biased by what the paper claims, and vice versa.

**Stage 2 -- ER** is optional (`--er-enabled`). It executes the submission
code in an isolated environment and compares produced figures and tables
against the manuscript references using perceptual hashing.

**Stage 3 -- Review** sees all upstream outputs at once and synthesises them
into a final verdict. Verdicts are one of: **Accept**, **Minor Revision**,
**Major Revision**, or **Unable to Assess**.

---

## Agents

### KBE -- Knowledge-Base Extraction

Reads the manuscript PDF; all other agents are forbidden from doing so.
Extracts the statistical methods, assumptions, and data-generation
processes. Identifies specific *reproduction targets*: the figures, tables,
and headline numerical results that must be reproduced. This identification
drives the optional ER comparison step.

### CQV -- Code-Quality Verification

Never reads the manuscript. Analyses the code supplement through three
internal passes:

1. **Stat-judge pre-pass** -- 16 bounded LLM calls, each evaluating a
   specific code-quality dimension (NA handling, multiple-testing correction,
   CI construction, deprecated packages, etc.) against a curated rubric and
   targeted evidence snippets extracted from the source code.
2. **Static checks** -- 33 deterministic checks implemented in Python
   (AST analysis, regex heuristics, file-layout checks). No LLM involved.
   Covers: reproducibility setup, seed hygiene, dangerous patterns, import
   completeness, dead code, loop invariants, undefined references, and more.
3. **Main LLM audit** -- a model call with file-reading tools that produces
   the structured `cqv_output.json`. Stat-judge verdicts are injected as
   pre-determined answers so the model does not re-debate them.

After the model returns, each cited line is enriched with +-5 lines of
source context (evidence rehydration) so the Review agent can cite code
precisely.

### ER -- Experimental Run *(optional)*

Executes the submission code in a Docker container, collects produced
outputs, and compares them against manuscript reference images using
perceptual hashing. Populates dynamic checklist items that CQV cannot
evaluate without running the code.

Enable with `--er-enabled` on the command line.

### Review -- Synthesis

Sees all upstream outputs simultaneously. Deterministically wires ER
comparison results to checklist items before the LLM call (so the model
cannot override them), then generates the four-file deliverable:
`final_review.md`, `exhaustive_audit_report.md`, `checklist.md`,
`risk_matrix.json`. The risk score and verdict are post-processed to
enforce mutual consistency (a low risk score cannot accompany a Major
Revision verdict, and vice versa).

---

## Requirements

| Dependency | Required | Notes |
|---|---|---|
| Python >= 3.12 | Yes | |
| LLM API key | Yes | Configured via env vars (LiteLLM router) |
| Docker >= 29 | Optional | Only for Stage 2 ER (`--er-enabled`) |
| `tree-sitter-languages` + `tree-sitter==0.21.*` | Optional | Enables 4 AST-based static checks; other 29 still run without it |

Install the package and its dependencies:

```bash
pip install -e ".[pdf]"
# Optional AST checks:
pip install tree-sitter-languages "tree-sitter>=0.21,<0.22"
```

---

## Usage

```bash
# 1. Place the manuscript and code supplement in the run directory
mkdir -p ai4r/my-paper/input
cp manuscript.pdf ai4r/my-paper/input/paper.pdf
cp code_supplement.zip ai4r/my-paper/input/assets/

# 2. Run the pipeline
python -m tools.orchestrator.run my-paper

# 3. With experimental run (requires Docker)
python -m tools.orchestrator.run my-paper --er-enabled

# 4. Find results in
ls ai4r/my-paper/review/
#  final_review.md  exhaustive_audit_report.md  checklist.md  risk_matrix.json
```

---

## Repository structure

```
ai4reproducibility/
|
+-- CHECKLIST.md           # Rendered reproducibility rubric (24 items)
+-- CQV_CHECKLIST.md       # Rendered code-quality rubric (36 items)
+-- LOGIC.md               # Pipeline architecture reference
+-- checklist.yaml         # Source-of-truth reproducibility rubric
+-- cqv_checklist.yaml     # Source-of-truth code-quality rubric
|
+-- agents/                # Agent skills and reference documents
|   +-- knowledge-base-extraction/
|   +-- code-quality-verification/
|   +-- experimental-run/
|   +-- critique/
|   +-- review/
|
+-- tools/
|   +-- orchestrator/      # Pipeline orchestration
|   |   +-- run.py         # Entry point
|   |   +-- kbe.py         # KBE stage
|   |   +-- cqv.py         # CQV stage (with rehydration)
|   |   +-- er.py          # ER stage (optional)
|   |   +-- review.py      # Review stage
|   |   +-- stat_judges.py # 16 LLM stat/quality judges
|   |   +-- stat_evidence.py # Evidence extraction for judges
|   |   +-- reconcile.py   # Verdict reconciliation
|   +-- cqv_agent/
|   |   +-- static_checks/ # 33 deterministic checks
|   |       +-- dispatch.py
|   |       +-- check_r_ast.py      # AST checks (tree-sitter)
|   |       +-- r_heuristics.py     # R-specific heuristics
|   |       +-- heuristics_cross_lang.py
|   |       +-- danger_patterns.py
|   |       +-- file_inventory.py
|   +-- tools.py           # Tool registry for agents
|   +-- checklist_render.py # YAML -> Markdown + schema validation
|
+-- tests/                 # 653 tests (pytest)
|   +-- fixtures/
|
+-- prepare_review.sh      # Pre-flight setup script
+-- validate_review.sh     # Post-flight validation script
+-- assets/                # Images and media
```

---

## Quality guarantees

- **No LLM in the critical path of static checks** -- all 33 static checks
  are deterministic Python. They cannot hallucinate.
- **Evidence-anchored findings** -- every finding in the final report must
  cite a file path and line number. Findings without evidence are not
  permitted by the output schema.
- **Fail-safe continuation** -- if one agent fails, the others still run.
  Affected checklist items are marked *Unverified* rather than silently
  passed or failed. A fully degraded run still produces a valid JSON with
  `verdict: UNABLE_TO_ASSESS`.
- **Bias separation** -- KBE and CQV run in isolated contexts. Neither can
  see the other's inputs.
- **Coherence enforcement** -- the final verdict and risk score are
  post-processed to be mutually consistent.

---

## Citation

If you use AI4Reproducibility in your research, please cite:

```bibtex
@software{ai4reproducibility2025,
  title  = {{AI4Reproducibility}: Agentic Pipeline for Automated Reproducibility Review},
  author = {Hejblum, Boris P. and El Karchi, Jad},
  year   = {2025},
  url    = {https://github.com/sistm/AI4Reproducibility}
}
```

---

## License

Apache 2.0 -- see [`LICENSE.txt`](LICENSE.txt).
