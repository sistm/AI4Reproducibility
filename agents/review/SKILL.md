---
name: review
description: |
  Review code and data supplements of scientific papers for computational reproducibility. Use when asked to: review a code supplement, check if a paper's code is reproducible, audit a simulation study, evaluate a scientific paper's data and code, or assess computational reproducibility. Actively executes code (fixing minor issues), runs reduced simulations, and compares outputs against reported results. Outputs a structured markdown review document.
---

# Reproducibility Review

Review code and data supplements for computational reproducibility. Actively execute code, fix minor issues, run reduced simulations, and verify results match the paper.

## Workflow

### 1. Read the Paper

Start by reading the paper PDF (and supplement PDF if provided):
- Understand what analyses/simulations were performed
- Catalog all figures, tables, and numerical results to reproduce
- Note computational methods, sample sizes, iterations, parameters
- Understand the scientific claims being made

### 2. Examine Supplement Structure

Assess the code supplement:
```
- List all files and folder structure
- Identify README and documentation
- Locate main/master scripts vs. helper functions
- Identify data files, code files, output files
- Note programming languages used
```

### 3. Environment Setup

Install dependencies flexibly:
- Parse README for stated requirements
- For R: install packages from `library()`/`require()` calls
- For Python: install from `requirements.txt` or `import` statements
- For Julia, MATLAB, Stata, etc.: follow documented setup
- Document all packages installed and versions

### 4. Execute Code with Fixes

Run all code, fixing minor issues as needed:

**Apply these fixes:**
- Wrong file paths → adjust to actual structure
- Missing imports → add required imports
- Path case sensitivity → fix capitalization
- Deprecated functions → update to current equivalents
- Minor syntax errors → correct obvious typos
- Working directory issues → set appropriately

**Document every fix** — these become review items.

### 5. Run Reduced Simulations

For computationally intensive code, create reduced versions targeting < 1 hour runtime:

**Reduction strategies:**
- Monte Carlo replications: 1000 → 50-100
- Sample sizes: reduce if studying asymptotics
- Parameter grid: keep boundaries + middle, drop dense interior
- CV folds: 10 → 3-5
- Bootstrap iterations: reduce proportionally

**Verify qualitative consistency:**
- Do method rankings hold?
- Are key patterns preserved?
- Do conclusions remain supported?

**For unavoidably long computations:**
1. Write a setup script for the reduced run
2. Create handoff document: what's done, what's running, what remains
3. Ask user to run script and resume session with handoff
4. Or: launch subagents to run different settings in parallel while continuing review

### 6. Verify Results

Compare generated outputs to paper:
- Figures: visual/qualitative match
- Tables: values match within rounding
- Text results: numerical claims verified
- Reduced runs: patterns consistent with full results

### 7. Generate Review

Output markdown using template in `assets/review-template.md`.

**Severity levels:**
- **Critical**: Blocks reproduction (missing code/data, crashes, fundamentally wrong results)
- **Major**: Significantly impedes reproduction (missing docs, manual steps needed, partial failures)
- **Minor**: Does not block reproduction (style issues, missing but inferable info)
- **Suggestions**: Best practices not followed

## Principles

**Fix before complaining** — If fixable in 30 seconds, fix it and note as minor issue.

**Verify, don't trust** — Run the code. Check outputs. Compare to paper.

**Be constructive** — Goal is helping authors improve their supplement.

**Document thoroughly** — Another reviewer should understand exactly what you did.

**Qualitative over exact** — For reduced runs, patterns and rankings matter more than exact numbers.

## References

- `references/checklist.md` — Complete checklist for documentation, completeness, organization, quality, reproducibility
- `assets/review-template.md` — Output template for the review document
