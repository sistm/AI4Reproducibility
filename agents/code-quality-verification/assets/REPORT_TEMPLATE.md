# R Code Quality Verification Report Template

---

## Executive Summary

| Field | Value |
|-------|-------|
| **Report ID** | [UUID] |
| **Review Date** | [YYYY-MM-DD] |
| **Reviewer** | [Agent/Reviewer Name] |
| **File(s) Reviewed** | [comma-separated list] |
| **Overall Risk Score** | [0-100] |

---

## Verdict

- [ ] **APPROVED** - Code is production-ready
- [ ] **APPROVED WITH CONDITIONS** - Code has minor issues requiring fixes before deployment
- [ ] **NEEDS REVISION** - Significant issues must be addressed
- [ ] **REJECTED** - Critical issues; fundamental redesign required

### Summary
[2-3 paragraph executive summary of findings and recommendation]

---

## Risk Score Breakdown

### Component Scores

| Category | Score | Weight | Weighted Score |
|----------|-------|--------|----------------|
| Correctness | [0-100] | 20% | [weighted] |
| Security | [0-100] | 20% | [weighted] |
| Statistical Validity | [0-100] | 20% | [weighted] |
| Reproducibility | [0-100] | 15% | [weighted] |
| Performance | [0-100] | 10% | [weighted] |
| Maintainability | [0-100] | 10% | [weighted] |
| Documentation | [0-100] | 5% | [weighted] |
| **Total** | | 100% | **[0-100]** |

### Risk Classification

| Score Range | Classification | Color |
|-------------|---------------|-------|
| 90-100 | Low Risk | Green |
| 75-89 | Medium Risk | Yellow |
| 50-74 | High Risk | Orange |
| <50 | Critical Risk | Red |

---

## Issue Breakdown

### Critical Issues (P0) - Must Fix

| # | Location | Issue | Risk | Recommendation |
|---|----------|-------|------|----------------|
| 1 | [Line N] | [Description] | [Security/Statistical/Correctness] | [Fix] |
| 2 | ... | ... | ... | ... |

### High Priority Issues (P1) - Should Fix

| # | Location | Issue | Risk | Recommendation |
|---|----------|-------|------|----------------|
| 1 | [Lines N-M] | [Description] | [Performance/Reproducibility/Maintainability] | [Fix] |
| 2 | ... | ... | ... | ... |

### Medium Priority Issues (P2) - Consider Fixing

| # | Location | Issue | Category | Recommendation |
|---|----------|-------|----------|----------------|
| 1 | [Line N] | [Description] | [Style/Documentation] | [Optional fix] |
| 2 | ... | ... | ... | ... |

### Low Priority Issues (P3) - Optional Improvements

| # | Location | Issue | Category |
|---|----------|-------|----------|
| 1 | [Line N] | [Description] | [Style] |
| 2 | ... | ... | ... |

---

## Detailed Findings

### 1. Security Review

**Status**: [PASS/FAIL]

**Findings**:
- [Security issue 1 with details]
- [Security issue 2 with details]

**Impact**: [What could happen if these issues are exploited]

---

### 2. Statistical Validity

**Status**: [PASS/FAIL/WARNING]

**Findings**:
- [Statistical concern 1 with details]
- [Statistical concern 2 with details]

**Impact**: [How results could be affected]

---

### 3. Reproducibility

**Status**: [PASS/FAIL]

**Findings**:
- [Reproducibility issue 1 with details]
- [Reproducibility issue 2 with details]

**Impact**: [How results might differ across runs]

---

### 4. Performance

**Status**: [PASS/FAIL/WARNING]

**Findings**:
- [Performance issue 1 with details]
- [Performance issue 2 with details]

**Impact**: [Time/memory implications]

---

### 5. Correctness

**Status**: [PASS/FAIL]

**Findings**:
- [Correctness issue 1 with details]
- [Correctness issue 2 with details]

**Impact**: [How code might behave incorrectly]

---

### 6. Maintainability

**Status**: [PASS/FAIL/WARNING]

**Findings**:
- [Maintainability issue 1 with details]
- [Maintainability issue 2 with details]

---

### 7. Documentation

**Status**: [PASS/FAIL/WARNING]

**Findings**:
- [Documentation issue 1 with details]
- [Documentation issue 2 with details]

---

## Recommendations

### Immediate Actions Required

1. **[Critical issue 1]** - [Specific fix]
2. **[Critical issue 2]** - [Specific fix]

### Recommended Improvements

1. **[High priority issue]** - [Specific improvement]
2. **[Medium priority issue]** - [Optional improvement]

### Future Enhancements

1. [Long-term improvement idea]
2. [Additional testing suggestion]

---

## Code Quality Metrics

| Metric | Value | Notes |
|--------|-------|-------|
| Lines of Code | [N] | |
| Functions | [N] | |
| Cyclomatic Complexity (avg) | [N] | Target: < 10 |
| Test Coverage | [N]% | If tests available |
| Lint Issues | [N] | Minor/Major |

---

## Approval Status

### Conditions for Approval

- [ ] Fix all Critical (P0) issues
- [ ] Fix all High (P1) issues  
- [ ] Address Security concerns
- [ ] Ensure Reproducibility

### Post-Approval Requirements

- [ ] Re-review after fixes
- [ ] Verify test coverage
- [ ] Check CI pipeline

---

## Reviewer Notes

[Additional context for future reviewers, caveats, or special considerations]

---

## Appendix

### File(s) Analyzed
```
[File path] - [Lines of code]
[File path] - [Lines of code]
```

### Tool Versions Used
```
R version: [version]
Package versions: [list if available]
```

### Review Configuration
```
Severity thresholds:
- Critical: Security, syntax errors, statistical violations
- High: Reproducibility, logic errors, performance
- Medium: Style, documentation, minor issues
- Low: Preferences, suggestions