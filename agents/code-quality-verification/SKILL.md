# R Code Quality Verification Agent

## Capabilities

The R Code Quality Verification Agent performs comprehensive static and semantic analysis of R code to identify quality issues, statistical misuse, security vulnerabilities, and reproducibility risks.

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

## Confidence Scoring

| Aspect | Weight | Criteria |
|--------|--------|----------|
| Parse Success | 100% | Code parses without error |
| Semantics | 70-90% | Type inference, scope resolution |
| Statistical | 60-85% | Context-dependent, requires domain knowledge |
| Security | 80-95% | Pattern matching for known vulnerable constructs |

## Review Philosophy

1. **Assume Production**: Code is running in critical environments (finance, medical, research)
2. **Fail Closed**: Ambiguous issues reported as risks
3. **Reproducibility First**: Determinism and environment capture prioritized
4. **Statistical Rigor**: Statistical code held to higher standard
5. **Security Paranoia**: Any dynamic code execution treated as threat

## Input

- R script file paths (`.R`, `.Rmd`)
- Optional: project context (unit tests, dependencies)

## Output

Structured outputs following the workflow specification:
- **`cqv_output.json`** - Code audit with repository analysis, dependency validation, and reproducibility assessment
- **`repo_analysis.md`** - Detailed repository analysis and findings

**Output Location:** `/ai4r/{review_title}/cqv/`

## File References

- Review template: `assets/review-template.md`
- QA checklist: `references/checklist.md`
- Static analysis rules: `references/static-analysis.md`
- Performance review: `references/performance-review.md`
- Statistical validation: `references/statistical-validation.md`
- Reproducibility: `references/reproducibility.md`
- Security review: `references/security-review.md`