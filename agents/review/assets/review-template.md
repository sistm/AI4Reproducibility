<!--
  review-template.md — canonical format for checklist.md output
  =============================================================
  The Review agent uses this as its format reference when generating
  checklist.md. The model must:
    1. Reproduce this exact section/item structure.
    2. Replace every [VERDICT] token with one of: PASS · FAIL · UNVERIFIED
    3. Replace every [AUDIT NOTE] with one evidenced sentence (cite file:line).
    4. Append a "**Required action:**" sub-bullet on FAIL items only.
    5. Use [x] for PASS, [ ] for FAIL and UNVERIFIED.
    6. Never add items not in checklist.yaml; never drop items.
    7. UNVERIFIED must name the upstream cause (e.g. "CQV partial — check not run").
  Severity legend: ★★ critical · ★ major · · minor · ○ suggestion
-->

# Reproducibility Checklist — {review_title}
*{paper_title}*  |  Assessment: {assessment_status}  |  Verdict: {verdict}

> This checklist covers all 24 items in the AI4Reproducibility rubric, grouped
> by section. Authors are expected to address every **[FAIL]** item before
> resubmission. **[UNVERIFIED]** items could not be assessed due to upstream
> pipeline limitations; authors should nonetheless ensure compliance.

---

## Documentation

- [{pass_bj01}] **[VERDICT] Include a README file** (`bj-01-readme` ★)  
  A README file (README.txt, README.md, or README.pdf) is present at the
  repository root and includes version and dependency information. For R,
  ideally the output of `sessionInfo()` after loading all packages.  
  [AUDIT NOTE]

- [{pass_bj02}] **[VERDICT] Describe how to run your code** (`bj-02-run-instructions` ★)  
  The README describes exactly which files to run in which order, or a single
  entry-point script (e.g. `main.R`, `main.py`) reproduces all results.  
  [AUDIT NOTE]

- [{pass_bj05}] **[VERDICT] Report runtime and hardware** (`bj-05-runtime-hardware` ·)  
  The README states the order-of-magnitude runtime (minutes / hours / days)
  and the hardware used.  
  [AUDIT NOTE]

- [{pass_bj06}] **[VERDICT] Explain parallelisation** (`bj-06-parallelisation` ·)  
  If the code uses parallelisation, the README says so and explains how to
  adapt it to a reviewer's setup.  
  [AUDIT NOTE]

- [{pass_bj09}] **[VERDICT] Add helpful comments** (`bj-09-helpful-comments` ·)  
  Code comments state which figure or table in the manuscript each block
  produces.  
  [AUDIT NOTE]

- [{pass_sessioninfo}] **[VERDICT] R session info captured** (`audit-doc-sessioninfo-r` ★)  
  For R submissions: the README or supplement contains a `sessionInfo()` block
  (or `renv.lock`) with R version and package versions pinned.  
  [AUDIT NOTE]

- [{pass_pyreq}] **[VERDICT] Python dependency manifest present** (`audit-doc-requirements-python` ★)  
  For Python submissions: `requirements.txt`, `environment.yml`, or equivalent
  is present at the repository root with pinned versions.  
  [AUDIT NOTE]

---

## Completeness

- [{pass_bj03}] **[VERDICT] All code and data included** (`bj-03-code-and-data` ★★)  
  All code and data needed to reproduce every figure, table, and number in the
  paper are included. When data cannot be made public, comparable pseudo-data
  is provided and original data is available to editors on request.  
  [AUDIT NOTE]

- [{pass_bj11}] **[VERDICT] Intermediate results provided** (`bj-11-intermediate-results` ★)  
  For simulations exceeding a few hours: intermediate results are provided
  (or uploaded to Zenodo / figshare / OSF), or a reduced-replication setting
  is documented.  
  [AUDIT NOTE]

- [{pass_restricted}] **[VERDICT] Restricted-data handling documented** (`audit-data-restricted-handling` ★)  
  When the original data cannot be released, pseudo-data of comparable size
  and structure is provided, and a documented access path for reviewers
  (controlled-access portal, accession number, or contact) is given.  
  [AUDIT NOTE]

---

## Organisation

- [{pass_bj04}] **[VERDICT] Results clearly linked to paper** (`bj-04-results-linked` ·)  
  Figures and tables are exported to appropriately named files
  (e.g. `figure1.pdf`, `table2.csv`) or clearly labelled in a notebook.  
  [AUDIT NOTE]

- [{pass_bj08}] **[VERDICT] Code well organised** (`bj-08-organisation` ·)  
  Sensible folder structure, file names, and variable names; code duplication
  avoided via functions.  
  [AUDIT NOTE]

- [{pass_entrypoint}] **[VERDICT] Single entry-point script present** (`audit-org-main-entry-point` ·)  
  A single-entry-point script exists (`main.R`, `master.py`, `run_all.sh`, or
  `Makefile`) to reduce manual orchestration.  
  [AUDIT NOTE]

- [{pass_filenaming}] **[VERDICT] File names descriptive and clean** (`audit-org-file-naming` ·)  
  File names are descriptive (no `x001.R`, `untitled.py`, `copy_of_*`) and
  contain no spaces.  
  [AUDIT NOTE]

---

## Reproducibility

- [{pass_bj07}] **[VERDICT] No absolute paths** (`bj-07-no-absolute-paths` ★)  
  No hard-coded absolute paths in scripts. Paths are relative to the file or
  working directory (when documented). No `setwd()` calls in code.  
  [AUDIT NOTE]

- [{pass_bj10}] **[VERDICT] Random seeds set** (`bj-10-set-seed` ★★)  
  All code that relies on a random number generator initialises a seed so that
  results are exactly reproducible.  
  [AUDIT NOTE]

- [{pass_envtool}] **[VERDICT] Environment reproducibility tooling used** (`audit-doc-env-tool` ○)  
  Docker, `renv`, conda env file, or `uv` lockfile is used. Absence is not a
  failure; presence is a positive signal.  
  [AUDIT NOTE]

- [{pass_platform}] **[VERDICT] Platform-independent path construction** (`audit-repro-platform-independence` ·)  
  Paths are built with `file.path()` (R) or `pathlib` / `os.path.join`
  (Python). No hard-coded `\` or `/` separators.  
  [AUDIT NOTE]

- [{pass_seeddoc}] **[VERDICT] Seed values documented** (`audit-repro-seed-documented` ·)  
  Seed values are documented in the README or set in a single easily
  locatable place (config file or top of main script).  
  [AUDIT NOTE]

---

## Code Quality

- [{pass_nowsclear}] **[VERDICT] No workspace-clearing calls** (`audit-qual-no-workspace-clear` ·)  
  No `rm(list=ls())` or equivalent in shipped code; such calls mask state
  bugs and hinder downstream sourcing.  
  [AUDIT NOTE]

- [{pass_noautoinstall}] **[VERDICT] No silent package auto-installation** (`audit-qual-no-auto-install` ★)  
  No `install.packages()` or `pip install` via subprocess in scripts.
  Dependencies must be declared, not installed at runtime.  
  [AUDIT NOTE]

---

## Packaging

- [{pass_bj12}] **[VERDICT] Single ZIP archive** (`bj-12-single-zip` ·)  
  All code, data, and README are in one ZIP archive (e.g. `Code_and_Data.zip`)
  with subfolders, stripped of unnecessary files.  
  [AUDIT NOTE]

---

## Result Verification *(requires code execution — ER stage)*

- [{pass_figmatch}] **[VERDICT] Generated figures match paper** (`audit-verify-figures-match` ★★)  
  When executed, generated figures match those in the manuscript visually
  and/or numerically within tolerance. Deferred to dynamic execution (ER).  
  [AUDIT NOTE]

- [{pass_tabmatch}] **[VERDICT] Generated tables match paper** (`audit-verify-tables-match` ★★)  
  When executed, generated tables match those in the manuscript within rounding
  tolerance. Deferred to dynamic execution (ER).  
  [AUDIT NOTE]

---

## Summary

| Severity | Total | PASS | FAIL | UNVERIFIED |
|----------|-------|------|------|------------|
| ★★ Critical | {n_critical} | {n_crit_pass} | {n_crit_fail} | {n_crit_unverified} |
| ★ Major     | {n_major}    | {n_maj_pass}  | {n_maj_fail}  | {n_maj_unverified}  |
| · Minor     | {n_minor}    | {n_min_pass}  | {n_min_fail}  | {n_min_unverified}  |
| ○ Suggestion| {n_suggest}  | {n_sug_pass}  | {n_sug_fail}  | {n_sug_unverified}  |

### Required actions (FAIL items only)

List each FAIL item's required action here as a numbered list, cross-referenced
to the checklist item id, ordered critical → major → minor.
