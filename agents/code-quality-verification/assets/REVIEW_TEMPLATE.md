# R Script Review Template

## Document Information

| Field | Value |
|-------|-------|
| Reviewer | [AGENT NAME] |
| Date | [YYYY-MM-DD] |
| File | [FILENAME.R] |
| Version | [GIT HASH OR VERSION] |
| Lines of Code | [N] |

---

## Executive Summary

### Risk Score
[0-100]

### Verdict
- [ ] APPROVED - Production ready
- [ ] APPROVED WITH CONDITIONS - Minor issues to fix
- [ ] NEEDS REVISION - Significant issues
- [ ] REJECTED - Critical issues; do not deploy

### Summary Statement
[2-3 sentence overview of code quality and primary concerns]

---

## Risk Overview

| Severity | Count | Examples |
|----------|-------|----------|
| Critical (P0) | N | [Brief description] |
| High (P1) | N | [Brief description] |
| Medium (P2) | N | [Brief description] |
| Low (P3) | N | [Brief description] |

---

## Critical Issues (P0)

### Issue 1: [Title]
**Location**: Line [N]
**Category**: [Security/Statistical/Correctness]

**Description**:
[Exact code snippet and why it is problematic]

**Impact**:
[What happens if this issue is not fixed]

**Recommendation**:
```r
# Refactored code
[Fixed version]
```

### Issue 2: [Title]
... (repeat as needed)

---

## High Priority Issues (P1)

### Issue 1: [Title]
**Location**: Lines [M-N]
**Category**: [Performance/Reproducibility/Maintainability]

**Description**:
[Code snippet and concern]

**Recommendation**:
```r
# Preferred approach
[Alternative code]
```

---

## Medium Priority Issues (P2)

| # | Location | Category | Issue | Recommendation |
|---|----------|----------|-------|----------------|
| 1 | Line N | Style | [Issue] | [Fix] |
| 2 | ... | ... | ... | ... |

---

## Improvement Suggestions (Optional)

### Performance Optimizations
- [Suggestion with rationale]

### Code Organization
- [Suggestion with rationale]

### Documentation
- [Suggestion with rationale]

---

## Refactored Code Snippets

### Snippet 1: [Function Name]
```r
# BEFORE (problematic)
[Original code]

# AFTER (improved)
[Refactored code]
```

---

## Performance Notes

### Bottleneck Analysis
| Function | Complexity | Impact |
|----------|------------|--------|
| [func] | O(n²) | High |

### Recommended Profiling
```r
# Use profvis for runtime analysis
library(profvis)
profvis({
  # Wrap code here
})
```

---

## Statistical Concerns

### Assumption Violations
- [Test and violation]

### Validity Risks
- [Statistical issue]

### Recommendations
- [Remediation steps]

---

## Final Verdict

### Required Actions
- [ ] Fix all Critical (P0) issues
- [ ] Address all High (P1) issues
- [ ] Review Medium (P2) items

### Approval Conditions
[Specific requirements for approval]

### Reviewer Notes
[Any additional context for future reviewers]

---

## Appendix: Code Under Review

```r
# Full or relevant code sections
[Code]