# Experimental Run (ER) Agent

see [LOGIC.md §3.3](../../LOGIC.md#33-er--experimental-run-partially-designed-deferred)
and [LOGIC.md §6](../../LOGIC.md#6-er-design-decisions-locked--do-not-re-litigate-without-a-smoke)
for this agent's place in the pipeline.

## Capabilities

ER is the only stage that executes submission code. It runs the supplement in a
sandboxed Docker container, reconstructs the environment from `renv.lock`, runs
the main entry point (or documented checkpoint scripts in spot-check mode), and
compares produced figures and tables against the manuscript references.

ER never reads the manuscript text directly. Its inputs are the extracted code
supplement and the upstream `cqv_output.json` (for `execution_environment` and
the main entry point).

---

## README pre-flight (runs before any execution)

ER makes a single LLM call to read the README and decide the execution mode.
The decision tree is deterministic; the model only extracts metadata:

| Condition | Mode | Checklist flag | Verdict impact |
|---|---|---|---|
| No README | `skipped_no_readme` | `MISSING_README` | major revision |
| Runtime not documented | `skipped_no_runtime_docs` | `MISSING_RUNTIME_DOCS` | major revision |
| Runtime within budget | `full_run` | — | runs fully |
| Runtime over budget, intermediate results documented | `spot_check` | — | runs checkpoints |
| Runtime over budget, no intermediate results | `skipped_no_intermediate_docs` | `MISSING_INTERMEDIATE_DOCS` | major revision |

The budget defaults to 3 hours (`AI4R_ER_TIMEOUT_SECONDS`). A submission that
cannot be reproduced within the budget AND does not document independently
checkable intermediate outputs is a reproducibility failure the reviewer must
see — hence the major-revision flags.

---

## Execution environment

The R version and package list come from `renv.lock` (preferring the
`execution_environment` block CQV already extracted; ER re-parses the lockfile
if absent). The R version selects the Docker image tag
`ghcr.io/sistm/ai4reproducibility:r<version>`. No lockfile → `skipped_no_data`.

The container is a fat base image with the common CRAN system libraries
pre-installed (LOGIC.md §3.3). The run sequence: `renv::restore()` with the
network on, then the entry point with `--network none`, `--memory 4g`, `--rm`.

---

## Output comparison

- **Figures:** perceptual-hash (pHash) gate. Below the Hamming threshold →
  pass with no LLM call. Above → escalate to an LLM visual comparison that
  classifies the mismatch as cosmetic (rendering drift → pass) or substantive
  (wrong data/model → fail). Pixel hashing is never used; it false-fails on
  rendering differences.
- **Tables:** numerical comparison with relative tolerance (default 1%).
- **Plot data:** when the run exposes underlying coordinates (e.g. a saved
  `.rds`), compare numerically — the most defensible evidence for the reviewer.

---

## Output contract

ER writes `er/er_output.json` with at least a `status` key (validator
requirement). Fields:

- `status` — `success` | `failed` | `skipped` | `skipped_no_runtime_docs` |
  `skipped_no_intermediate_docs` | `skipped_no_data` | `skipped_no_readme`
- `execution_mode` — the pre-flight decision
- `checklist_flags` — flags Review surfaces (may be empty)
- `preflight` — the full pre-flight assessment
- `execution_environment` — R version + packages
- `run` — returncode, timed_out, stdout/stderr tails, artifacts (when executed)
- `comparisons` — per-artifact comparison results (when references exist)

ER never raises; any failure becomes a non-success status with a `failure_mode`.
