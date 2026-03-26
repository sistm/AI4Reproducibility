# R Code Quality Verification Checklist

## Syntax & Correctness

| Item | YES | NO | Risk Explanation |
|------|-----|-----|-------------------|
| Code parses without syntax errors | [ ] | [ ] | Syntax errors prevent execution; undefined behavior |
| No undefined variable references | [ ] | [ ] | Undefined variables cause runtime errors or unexpected NSE behavior |
| All function calls have required arguments | [ ] | [ ] | Missing arguments cause runtime failures |
| No missing package imports | [ ] | [ ] | Missing imports cause "object not found" errors |
| Brackets/braces are balanced | [ ] | [ ] | Unbalanced brackets cause parse failures |

## Code Structure

| Item | YES | NO | Risk Explanation |
|------|-----|-----|-------------------|
| Functions have single responsibility | [ ] | [ ] | Multi-purpose functions are harder to test and maintain |
| No duplicate code blocks | [ ] | [ ] | Duplication causes maintenance burden and inconsistency |
| No dead code (unreachable) | [ ] | [ ] | Dead code indicates refactoring needed, confuses readers |
| Nested complexity ≤ 4 levels | [ ] | [ ] | Deep nesting is difficult to reason about |
| No implicit global state modification | [ ] | [ ] | Hidden state causes non-reproducible behavior |

## Data Handling

| Item | YES | NO | Risk Explanation |
|------|-----|-----|-------------------|
| No growing vectors in loops | [ ] | [ ] | O(n²) performance; memory fragmentation |
| Data frames not mutated unexpectedly | [ ] | [ ] | Side effects break reproducibility |
| Column types explicitly handled | [ ] | [ ] | Implicit coercion causes silent bugs |
| NA handling is explicit | [ ] | [ ] | Implicit NA handling causes incorrect results |
| Noattach()usage | [ ] | [ ] | Namespace pollution; hard to debug |

## Statistical Validity

| Item | YES | NO | Risk Explanation |
|------|-----|-----|-------------------|
| Statistical test assumptions verified | [ ] | [ ] | Violated assumptions invalidate results |
| No p-hacking (multiple testing without correction) | [ ] | [ ] | Inflated false positive rate |
| No data leakage in model training | [ ] | [ ] | Overoptimistic performance estimates |
| Confidence intervals have correct coverage | [ ] | [ ] | Misleading uncertainty estimates |
| Sampling is representative | [ ] | [ ] | Biased samples cause incorrect inference |
| No post-hoc hypothesis adjustment without mention | [ ] | [ ] | Selective reporting inflates false positives |
| Model diagnostics examined | [ ] | [ ] | Unchecked assumptions lead to invalid models |

## Performance

| Item | YES | NO | Risk Explanation |
|------|-----|-----|-------------------|
| No unnecessary copies of large objects | [ ] | [ ] | Memory bloat, cache misses |
| Vectorized operations used where possible | [ ] | [ ] | Loops are orders of magnitude slower |
| data.table/dplyr appropriate for data size | [ ] | [ ] | Wrong tool causes performance degradation |
| No repeated expensive operations in loop | [ ] | [ ] | Exponential slowdown |
| Lazy evaluation exploited where appropriate | [ ] | [ ] | Forced evaluation causes unnecessary work |

## Security

| Item | YES | NO | Risk Explanation |
|------|-----|-----|-------------------|
| Noeval()orparse()with user input | [ ] | [ ] | Arbitrary code execution vulnerability |
| No system()calls with unsanitized input | [ ] | [ ] | Command injection vulnerability |
| No hardcoded credentials/API keys | [ ] | [ ] | Secret exposure in code |
| File paths sanitized | [ ] | [ ] | Path traversal vulnerability |
| No download.file()to arbitrary URLs | [ ] | [ ] | Data exfiltration/injection risk |
| No unsafe serialization (readRDS untrusted) | [ ] | [ ] | Code execution via crafted objects |

## Reproducibility

| Item | YES | NO | Risk Explanation |
|------|-----|-----|-------------------|
| set.seed() called before stochastic operations | [ ] | [ ] | Non-deterministic results |
| renv/renv.lock captures dependencies | [ ] | [ ] | Dependency drift causes different results |
| Working directory not hardcoded | [ ] | [ ] | Path dependency breaks on other machines |
| No hidden global options (options()) | [ ] | [ ] | Undocumented behavior affects results |
| Random seeds documented in comments | [ ] | [ ] | Seed rationale aids debugging |
| All external data sources versioned | [ ] | [ ] | Data drift changes results |

## Documentation

| Item | YES | NO | Risk Explanation |
|------|-----|-----|-------------------|
| All exported functions documented | [ ] | [ ] | API unusable without docs |
| Function docstrings include Args/Returns | [ ] | [ ] | Type information needed for IDE support |
| Complex statistical methods explained | [ ] | [ ] | Results misinterpreted without context |
| Code has explanatory comments | [ ] | [ ] | Logic opaque to future maintainers |
| README or vignette describes workflow | [ ] | [ ] | Usage unclear without documentation |

## Testing

| Item | YES | NO | Risk Explanation |
|------|-----|-----|-------------------|
| Unit tests exist for critical functions | [ ] | [ ] | Regression detection impossible |
| Edge cases tested (empty, NA, zero) | [ ] | [ ] | Edge case failures in production |
| Statistical test results validated | [ ] | [ ] | Incorrect statistical implementation undetected |
| Integration tests cover pipeline | [ ] | [ ] | Component integration fails undetected |
| Snapshot tests for complex outputs | [ ] | [ ] | Silent behavior changes undetected |

## Dependencies

| Item | YES | NO | Risk Explanation |
|------|-----|-----|-------------------|
| Minimum required versions specified | [ ] | [ ] | API changes break code |
| No transitive dependency conflicts | [ ] | [ ] | Version resolution failures |
| Deprecated packages avoided | [ ] | [ ] | Future maintainability risk |
| Heavy dependencies justified | [ ] | [ ] | Bloat increases attack surface |

## Execution Safety

| Item | YES | NO | Risk Explanation |
|------|-----|-----|-------------------|
| tryCatch() around risky operations | [ ] | [ ] | Failures crash entire pipeline |
| Stop-on-error for critical operations | [ ] | [ ] | Silent failures propagate |
| No infinite loops without timeout | [ ] | [ ] | Process hangs indefinitely |
| Memory limits respected | [ ] | [ ] | OOM kills process |
| Progress indication for long operations | [ ] | [ ] | User cannot assess stuckness |

---

## Scoring

Calculate overall score: (YES / Total) × 100

- ≥95%: Production-ready
- 80-94%: Minor issues, review recommended
- 60-79%: Significant issues, must address
- <60%: Major issues, do not deploy

## Risk Categories by Score

| Score Range | Classification | Action |
|-------------|---------------|--------|
| 90-100 | Low Risk | Approve with optional suggestions |
| 75-89 | Medium Risk | Approve with required fixes |
| 50-74 | High Risk | Do not approve until fixes applied |
| <50 | Critical Risk | Reject; fundamental redesign needed |