# R Code Quality Verification Agent

see [LOGIC.md §3.2](../../LOGIC.md#32-cqv--code-quality-verification) for this agent's place in the pipeline.

## Capabilities

The R Code Quality Verification Agent performs comprehensive static and semantic analysis of R code to identify quality issues, statistical misuse, security vulnerabilities, and reproducibility risks.

---

## Checklist scope

CQV runs against **two** sets of items, both anchored in `cqv_checklist.yaml`:

1. **Its own items** — every entry under `items:` in `cqv_checklist.yaml`
   (the code-quality rubric).
2. **Borrowed reproducibility items** — every entry under the
   `also_enforces:` block at the top of `cqv_checklist.yaml`. These are
   items defined in the reproducibility rubric (`checklist.yaml`) that CQV
   runs *on behalf of* that rubric, because they are detectable by code
   inspection (see [LOGIC.md §5](../../LOGIC.md#5-checklists-and-the-static-check-tool-layer)).

For each `also_enforces` entry:

- Resolve its `id` against `checklist.yaml` to read the item's full
  description and `tool_id`. (The id is guaranteed to resolve — the
  checklist validator enforces this — so a lookup miss is a pipeline bug,
  not a submission issue.)
- Run the corresponding check. The entry's `note` summarises what to look
  for; most map to an existing static check or a file/pattern scan.
- Record the finding in `cqv_output.json` keyed under the reproducibility
  `id` verbatim (e.g. `bj-10-set-seed`), with file/line evidence (cite
  `{file, line}` only — never paste raw source; the orchestrator attaches the
  exact source line), exactly as for CQV's own items. Review attributes these to the reproducibility
  rubric, so the id must be preserved unchanged.

These items are run **in addition to** CQV's own items, never instead of
them. If an `also_enforces` item cannot be evaluated — for example its
static check is a `not_implemented` stub — record it with that status and
the reason rather than omitting it, so Review marks it Unverified instead
of silently passing it.

---

## Static Code Analysis

### Lintr-Level Checks
- Syntax errors and parse failures
- Undefined variables and functions
- Missing package imports
- Unused imports and variables
- Malformed function calls

### Beyond Lintr
- Unreachable code after return/break/stop
- Unused function arguments (underscore prefix expected)
- Implicit type coercion risks
- NSE (Non-Standard Evaluation) usage in tidyverse
- Missing namespace qualifiers for conflicting functions

---

## Semantic Understanding

### Pipeline Paradigms
- **tidyverse**: dplyr, tidyr, purrr, ggplot2 patterns
- **data.table**: Set-based operations, by-group processing
- **base R**: Vectorized operations, apply family
- **mixing paradigms**: Common failure modes

### Statistical Context
- Statistical test assumptions (normality, independence, equal variance)
- Model specification correctness
- Confidence interval interpretation
- P-value misuse detection

---

## Issue Detection Categories

### Critical (P0)
- Syntax errors preventing execution
- Undefined variable references
- Security vulnerabilities (eval(), system(), download.file())
- Statistical method violations causing incorrect results

### High (P1)
- Unused variables causing confusion
- Missing error handling
- Inefficient patterns (growing vectors)
- Non-reproducible operations (set.seed missing)

### Medium (P2)
- Style violations (naming, formatting)
- Missing documentation
- Suboptimal but functional patterns
- Implicit type conversions

### Low (P3)
- Style preferences
- Minor inefficiencies
- Documentation improvements
- Code organization suggestions

---

## Confidence Scoring

| Aspect | Weight | Criteria |
|--------|--------|----------|
| Parse Success | 100% | Code parses without error |
| Semantics | 70-90% | Type inference, scope resolution |
| Statistical | 60-85% | Context-dependent, requires domain knowledge |
| Security | 80-95% | Pattern matching for known vulnerable constructs |

---

## Review Philosophy

1. **Assume Production**: Code is running in critical environments (finance, medical, research)
2. **Fail Closed**: Ambiguous issues reported as risks
3. **Reproducibility First**: Determinism and environment capture prioritized
4. **Statistical Rigor**: Statistical code held to higher standard
5. **Security Paranoia**: Any dynamic code execution treated as threat

---

## Input

- R script file paths (`.R`, `.Rmd`)
- Optional: project context (unit tests, dependencies)

---

## Output

Structured outputs following the workflow specification:
- **`cqv_output.json`** - Code audit with repository analysis, dependency validation, and reproducibility assessment
- **`repo_analysis.md`** - Detailed repository analysis and findings

**Output Location:** `/ai4r/{review_title}/cqv/`

---

## File References

- Review template: `assets/review-template.md`
- QA checklist: `references/checklist.md`
- Static analysis rules: `references/static-analysis.md`
- Performance review: `references/performance-review.md`
- Statistical validation: `references/statistical-validation.md`
- Reproducibility: `references/reproducibility.md`
- Security review: `references/security-review.md`

---

## Failure Handling

The CQV agent MUST always produce its two output files (`cqv_output.json`
and `repo_analysis.md`) even when verification cannot complete. The
post-flight validator (`assets/validate_review.sh`) treats missing or
malformed outputs as hard pipeline failures.

### Status enum

Every `cqv_output.json` MUST include a top-level `status` field with one
of these values:

| Value     | Meaning                                                              |
|-----------|-----------------------------------------------------------------------|
| `success` | All static checks ran; full repository audit produced.                |
| `partial` | Some checks ran, others crashed or were inapplicable.                 |
| `failed`  | The agent could not perform meaningful verification at all.           |

### Known failure modes

| `failure_mode`               | Trigger                                                            | Recommended status |
|------------------------------|---------------------------------------------------------------------|-------------------|
| `assets_directory_empty`     | `input/assets/` contains no files after preflight extraction.       | `failed`          |
| `archive_extraction_failed`  | The `extract_zip` tool reported failure during preflight.           | `failed`          |
| `language_unrecognized`      | No detectable R / Python / Stata / Julia source files present.      | `failed`          |
| `dependency_parse_failed`    | `get_dependencies` crashed for the detected language.               | `partial`         |
| `static_check_partial`       | Some checks in `references/CHECKLIST.md` ran, others raised.        | `partial`         |
| `repo_too_large`             | Repository exceeds an agent-defined inspection budget.              | `partial`         |
| `unknown_repo_layout`        | Repository present but no main script / README / lockfile found.    | `partial`         |

### Required output on failure

When `status != "success"`, `cqv_output.json` MUST conform to this shape:

```json
{
  "paper_id": "<review_title from arguments>",
  "audit_timestamp": "<ISO 8601 UTC>",
  "status": "failed",
  "failure_mode": "assets_directory_empty",
  "failure_reason": "Preflight extracted 0 files into input/assets/.",
  "repository_audit": null,
  "code_method_alignment": null,
  "dependency_validation": null,
  "execution_readiness": "unknown",
  "reproducibility_blockers": [
    {
      "id": "BLOCKER-0",
      "severity": "CRITICAL",
      "description": "No code supplement available to verify.",
      "evidence": "ai4r/<review_title>/logs/workflow.log"
    }
  ],
  "partial_data": null,
  "notes": "See repo_analysis.md for context."
}
```

For `status: "partial"`, populate fields that completed and set the rest
to `null` or empty arrays. Use `partial_data` to record which checks ran:

```json
"partial_data": {
  "checks_completed": ["readme_present", "dependency_file_present", "set_seed_scan"],
  "checks_failed": ["absolute_path_scan"],
  "checks_skipped": ["docker_build"]
}
```

### Output shape constraints

Keep the final JSON flat and emit each top-level field exactly once:

- Every `evidence` value MUST be a JSON **array** of `{file, line, note?}` objects — never a bare object, and never opened with `{`. Cite `{file, line}` only; the orchestrator attaches the exact source line.
- Do NOT restate `dependency_validation`, `execution_readiness`, or the blockers both nested inside `repository_audit` and at the top level.
- Do NOT list the same blocker `id` more than once; the orchestrator keeps only the first occurrence.

### Behavioral rules

1. NEVER raise an unhandled exception. Wrap every tool invocation and
   classify any error into a `failure_mode`.
2. The `paper_id` field MUST be set to the kebab-case `review_title` from
   the workflow arguments, even when no repository could be inspected. It
   is stable across all outputs and survives upstream failure.
3. CQV MUST NOT include a `paper_title` field. The manuscript PDF is
   outside CQV's allowed reads; the title is populated by KBE and reaches
   Review via `kbe_output.json`. Including a `paper_title` in CQV output
   would be a context-boundary violation.
4. `repo_analysis.md` is always written. On failure, it must list at least:
   the failure mode, the failure reason, the contents of `input/assets/`
   (using `list_files`) if any, and any tool stderr captured.
5. When `status` is `partial` or `failed`, ALWAYS emit at least one entry
   in `reproducibility_blockers` describing the verification gap. Downstream
   the Review agent uses this list to mark checklist items as Unverified
   rather than silently passing them.
6. Log every failure mode to `ai4r/<review_title>/logs/workflow.log` in
   addition to writing it into `cqv_output.json`.
   