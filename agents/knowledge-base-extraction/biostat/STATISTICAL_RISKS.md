# Statistical Risks in Biostatistics Research

Catalog of common statistical risks, their detection patterns, impact assessment, and mitigation strategies.

---

## 1. P-Hacking

### Definition

Manipulating analysis pipeline to achieve statistical significance (p < 0.05) through selective reporting, data dredging, or analytical flexibility.

### Detection Patterns

| Pattern | Indicator |
|---------|-----------|
| Multiple outcomes | >5 primary outcomes without adjustment |
| Flexible analysis | Multiple model specifications, report best |
| Data-dependent decisions | Subgroup selection post-hoc |
| Stopping rules | Early stopping without pre-specification |
| Missing data handling | Multiple imputations, select favorable |

### Impact

- **Severity**: CRITICAL
- **False positive rate**: Inflated to 30-60% (vs nominal 5%)
- **Effect size inflation**: 50-100% overestimation
- **Replication rate**: <40% for p-hacked results

### Mitigation

1. Pre-registration of analysis plan
2. Bonferroni or FDR correction
3. Report all analyses conducted
4. Independent validation cohort
5. Effect size + confidence interval focus

---

## 2. Multiple Testing Without Correction

### Definition

Conducting multiple statistical tests without appropriate adjustment, inflating family-wise error rate.

### Detection Patterns

| Pattern | Indicator |
|---------|-----------|
| Multiple comparisons | >10 tests, no correction |
| Hierarchical testing | Unclear primary/secondary |
| Post-hoc hypotheses | "We also explored..." |
| Multiple subgroups | >5 without interaction test |
| Multiple timepoints | Repeated measures uncorrected |

### Impact

- **Severity**: CRITICAL
- **FWER**: 40% with 10 tests (vs 5% nominal)
- **Discovery bias**: False positives dominate
- **Effect on meta-analysis**: Inflated pooled estimates

### Mitigation

| Method | When Appropriate |
|--------|------------------|
| Bonferroni | Conservative, few tests |
| Holm-Bonferroni | Less conservative |
| Benjamini-Hochberg | FDR control, exploratory |
| Dunnett's test | Multiple vs control |
| Tukey's HSD | All pairwise comparisons |

---

## 3. Model Misspecification

### Definition

Using statistical model that does not match data generating mechanism.

### Detection Patterns

| Pattern | Indicator |
|---------|-----------|
| Residual plots | Systematic patterns |
| Goodness-of-fit | Significant lack-of-fit |
| Link function | Wrong family selected |
| Non-linearity | Unmodelled curvature |
| Interaction | Omitted interaction terms |

### Impact

- **Severity**: CRITICAL
- **Bias direction**: Often unpredictable
- **Effect on estimates**: Inconsistent
- **Inference validity**: Invalid confidence intervals

### Mitigation

1. Specification tests (Link test, Ramsey RESET)
2. Model selection criteria (AIC, BIC)
3. Non-parametric sensitivity analysis
4. Bootstrap for inference
5. Domain knowledge integration

---

## 4. Violated Independence Assumptions

### Definition

Statistical inference assumes independence; violations introduce bias.

### Detection Patterns

| Violation Type | Detection |
|----------------|-----------|
| Clustered data | ICC > 0.05 |
| Repeated measures | Autocorrelation in residuals |
| Time series | Serial correlation |
| Spatial data | Spatial autocorrelation |
| Matched designs | Pair correlation |

### Impact

- **Severity**: CRITICAL
- **Standard errors**: Underestimated 20-200%
- **Type I error**: Inflated 2-10x
- **Coverage**: CI coverage <90%

### Mitigation

| Approach | Application |
|----------|-------------|
| Mixed effects models | Clustered/hierarchical |
| GEE | Population-averaged |
| Generalized estimating | Correlated outcomes |
| Time series models | Autocorrelated |
| Spatial models | Geographic correlation |

---

## 5. Overfitting in Small Samples

### Definition

Complex model fitted to insufficient data, capturing noise rather than signal.

### Detection Patterns

| Pattern | Indicator |
|---------|-----------|
| Events per variable | EPV < 10-20 |
| Model complexity | k > n/10 |
| Training error | Much lower than test error |
| Cross-validation | High variance across folds |
| Bootstrap | Unstable estimates |

### Impact

- **Severity**: HIGH
- **Optimism**: 10-30% inflated R²
- **Coefficient instability**: High variance
- **Poor out-of-sample**: 20-40% performance drop
- **Type I error**: Inflated in variable selection

### Mitigation

| Rule | Threshold |
|------|-----------|
| EPV rule | ≥10-20 events per predictor |
| LASSO | Penalized selection |
| Bootstrap | Internal validation |
| Cross-validation | K-fold (K=5-10) |
| External validation | Separate cohort |

---

## 6. Improper Censoring Handling

### Definition

In survival analysis, censoring mechanism not properly addressed.

### Detection Patterns

| Pattern | Indicator |
|---------|-----------|
| Informative censoring | Covariates predict dropout |
| Competing risks | Not accounted for |
| Left truncation | Immortal time bias |
| Loss to follow-up | >20% without analysis |
| Censoring distribution | Not reported |

### Impact

- **Severity**: CRITICAL
- **Bias direction**: Usually toward null
- **Magnitude**: 10-50% effect size bias
- **Hazard ratios**: May reverse direction

### Mitigation

1. Check balance in censored vs observed
2. Use competing risks analysis
3. Apply inverse probability weighting
4. Sensitivity analysis (worst-case)
5. Report censoring reasons

---

## 7. Confounding Unaddressed

### Definition

Failure to control for common cause of exposure and outcome.

### Detection Patterns

| Pattern | Indicator |
|---------|-----------|
| No adjustment | Unadjusted estimates only |
| Incomplete adjustment | Key confounders omitted |
| Over-adjustment | Adjusting for mediators |
| Collider bias | Conditioning on collider |
| Residual confounding | Measured with error |

### Impact

- **Severity**: CRITICAL
- **Direction**: Can inflate, deflate, or reverse
- **Magnitude**: 10-100% bias common
- **Causality**: Invalid causal inference

### Mitigation

| Method | Application |
|--------|-------------|
| Randomization | Ideal (when possible) |
| Stratification | Few confounders |
| Regression adjustment | Measured confounders |
| Propensity score | Many confounders |
| Instrumental variable | Unmeasured confounding |
| Sensitivity analysis | Unmeasured confounding |

---

## 8. Selection Bias

### Definition

Systematic differences between study participants and target population.

### Detection Patterns

| Pattern | Indicator |
|---------|-----------|
| Convenience sampling | Non-random selection |
| Volunteer bias | Self-selection |
| Loss to follow-up | >20% differential |
| Healthy survivor | Baseline differences |
| Publication bias | Only significant results |

### Impact

- **Severity**: CRITICAL
- **External validity**: Compromised
- **Effect estimates**: Non-generalizable
- **Direction**: Usually toward positive findings

### Mitigation

1. Population-based sampling
2. Report participation rates
3. Sensitivity analysis (selection models)
4. Inverse probability weighting
5. Multiple imputation for missingness

---

## 9. Measurement Error

### Definition

Inaccurate measurement of exposures, outcomes, or covariates.

### Detection Patterns

| Pattern | Indicator |
|---------|-----------|
| Self-report | Recall bias |
| Single measurement | Within-person variability |
| Validation study | Not conducted |
| Measurement agreement | Poor correlation |
| Calibration | Not performed |

### Impact

| Error Type | Impact |
|------------|--------|
| Classical (random) | Attenuates effect estimates |
| Differential | Bias direction unpredictable |
| Non-differential | Toward null |
| Berkson | Minimal bias, SE inflated |

### Mitigation

1. Validation substudy
2. Repeated measurements
3. Calibration curves
4. Regression calibration
5. SIMEX (simulation-extrapolation)

---

## 10. Data Leakage

### Definition

Information from test set leaks into training process.

### Detection Patterns

| Pattern | Indicator |
|---------|-----------|
| Preprocessing before split | Normalization on full data |
| Feature selection on all data | Full dataset used |
| Hyperparameter tuning | Test set used |
| Target leakage | Proxy for outcome |
| Duplicate samples | Train/test contamination |

### Impact

- **Severity**: HIGH
- **Performance inflation**: 10-30% optimistic
- **Overfitting**: Poor deployment performance
- **Reproducibility**: Fails on new data

### Mitigation

1. Strict train/validation/test split
2. Nested cross-validation
3. Feature importance from training only
4. Domain expert review
5. Temporal validation (if applicable)