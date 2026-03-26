# Metrics and Validation in Biostatistics

Comprehensive reference for statistical metrics, their appropriate use, and common misuses.

---

## 1. Area Under ROC Curve (AUC/C-Statistic)

### Definition

Area under the receiver operating characteristic curve, plotting true positive rate (sensitivity) vs false positive rate (1-specificity) across all threshold values.

### When Valid

| Scenario | Requirement |
|----------|-------------|
| Binary outcome | True positive/negative defined |
| Rank-based comparison | All subjects can be ranked |
| Model discrimination | Comparing risk scores |
| Prevalence independence | AUC invariant to prevalence |

### Formula

```
AUC = (TP_rate_at_threshold1 + TP_rate_at_threshold2 + ... + TP_rate_at_thresholdN) / N
      OR equivalently: probability that random positive ranks higher than random negative
```

### Interpretation

| AUC Range | Interpretation |
|-----------|----------------|
| 0.50 | No discrimination (random) |
| 0.50-0.70 | Poor |
| 0.70-0.80 | Acceptable |
| 0.80-0.90 | Excellent |
| >0.90 | Outstanding |

### Misuse Cases

| Misuse | Problem |
|--------|---------|
| Using AUC for imbalanced data | May appear good despite poor calibration |
| Comparing AUC without calibration | AUC doesn't measure accuracy |
| AUC threshold-based decisions | No optimal cutoff determined |
| AUC for time-to-event without handling | Must use time-dependent AUC |
| Ignoring competing risks | Overestimation in survival |

### Validation

- Bootstrap for confidence intervals
- Compare to reference standard
- Report both optimism-corrected and raw

---

## 2. Sensitivity and Specificity

### Definition

| Metric | Formula | Meaning |
|--------|---------|---------|
| Sensitivity | TP / (TP + FN) | True positive rate |
| Specificity | TN / (TN + FP) | True negative rate |
| PPV | TP / (TP + FP) | Probability test+ is truly+ |
| NPV | TN / (TN + FN) | Probability test- is truly- |

### When Valid

- Gold standard available
- Test results independent of reference standard
- Spectrum of disease represented
- Consecutive or random sampling

### Relationship

```
As threshold moves:
- Higher sensitivity → Lower specificity
- Lower threshold → More positives → Higher sensitivity, Lower specificity
```

### Misuse Cases

| Misuse | Problem |
|--------|---------|
| Applying sensitivity/specificity to different prevalence | PPV/NPV change with prevalence |
| Using single cutpoint | Ignores trade-off |
| Ignoring disease spectrum | Results may not generalize |
| Verification bias | Not all tested receive reference |
| Spectrum bias | Severe vs mild cases affect metrics |

### Clinical Application

| Clinical Goal | Metric to Optimize |
|---------------|-------------------|
| Rule out disease | High sensitivity (high NPV) |
| Rule in disease | High specificity (high PPV) |
| Screening (low disease prevalence) | High sensitivity |
| Confirmatory (high pre-test probability) | High specificity |

---

## 3. Hazard Ratios (HR)

### Definition

Instantaneous risk ratio comparing hazard rates between groups in survival analysis.

### When Valid

| Requirement | Explanation |
|-------------|-------------|
| Proportional hazards | Hazard ratio constant over time |
| Correct model specification | Assumptions met |
| Censoring non-informative | Censoring unrelated to outcome |
| No unmeasured confounding | In observational studies |

### Formula

```
HR = exp(β) where β is coefficient in Cox model

Interpretation: At any time t, hazard in exposed / hazard in unexposed = HR
```

### Interpretation

| HR Value | Interpretation |
|----------|----------------|
| 1.0 | No effect |
| 2.0 | Twice the hazard |
| 0.5 | Half the hazard |
| 1.1 | 10% increased hazard |

### Misuse Cases

| Misuse | Problem |
|--------|---------|
| Interpret as risk ratio | HR ≠ cumulative risk ratio |
| Ignore non-proportionality | PH assumption violation |
| Report without CI | No precision estimate |
| Apply to non-eligible population | External validity |
| Interpret at all times | May change over time |

### Validation

- Schoenfeld residuals (proportional hazards)
- Log-minus-log plots
- Stratified analysis
- Time-varying coefficients

---

## 4. Confidence Intervals (CI)

### Definition

Range of plausible values for parameter, constructed to have specified coverage probability under repeated sampling.

### When Valid

| Condition | Requirement |
|-----------|--------------|
| Large sample | CLT approximation valid |
| Correct model | Assumptions met |
| Repeated sampling | Design-based interpretation |
| Unbiased estimator | No systematic error |

### Types

| Method | Use |
|--------|-----|
| Normal-based | Large n, known assumptions |
| Bootstrap percentile | Unknown distribution |
| Bootstrap BCa | Bias-corrected |
| Bayesian credible | Posterior interpretation |
| Exact (Clopper-Pearson) | Small samples, binary |

### Interpretation

```
95% CI: If we repeat study many times, 95% of intervals contain true parameter
NOT: 95% probability true parameter is in interval (that's Bayesian)
```

### Misuse Cases

| Misuse | Problem |
|--------|---------|
| "Statistically significant" if CI excludes null | Overemphasis on significance |
| CI implies probability | Frequentist CI has no probability for single interval |
| Wide CI ignored | Imprecise estimate still informative |
| CI without point estimate | Missing effect size |
| Not accounting for multiple testing | Inflation of error rate |

---

## 5. Calibration vs Discrimination

### Definitions

| Property | Definition | Measures |
|----------|------------|----------|
| Discrimination | Ability to rank order | AUC, C-statistic |
| Calibration | Agreement between predicted and observed | Brier score, calibration slope/intercept, calibration curves |

### Relationship

- High discrimination ≠ well calibrated
- Well calibrated ≠ high discrimination
- Both important for clinical utility

### Assessment

| Metric | What It Measures |
|--------|------------------|
| AUC | Rank ordering |
| Brier score | Overall prediction error |
| Calibration slope | Over/under-prediction |
| Calibration intercept | Systematic over/under |
| Calibration plot | Visual agreement |

### Misuse Cases

| Misuse | Problem |
|--------|---------|
| Reporting only AUC | Ignores calibration |
| Good calibration with poor discrimination | Rank not useful |
| Perfect discrimination with poor calibration | Predictions wrong |
| Not checking calibration | Overly confident predictions |

### Improvement

| Issue | Solution |
|-------|----------|
| Poor calibration | Recalibrate, use predicted probabilities |
| Poor discrimination | Add predictive features |
| Both poor | Improve model specification |

---

## 6. P-Values

### Definition

Probability of observing data as extreme or more extreme than observed, assuming null hypothesis is true.

### When Valid

| Condition | Requirement |
|-----------|--------------|
| Appropriate test | Matches data structure |
| Correct model | Assumptions met |
| Multiple testing handled | Adjusted for comparisons |
| Pre-specified analysis | Not p-hacked |

### Common Values

| P-value | Interpretation |
|---------|---------------|
| < 0.05 | Evidence against null (not definitive) |
| < 0.01 | Stronger evidence |
| < 0.001 | Very strong evidence |
| > 0.05 | Inconclusive (not evidence for null) |

### Misuse Cases

| Misuse | Problem |
|--------|---------|
| "Significant" = important | Ignores effect size |
| P > 0.05 = no effect | Underpowered, imprecise |
| P-hacking | Multiple analyses, report best |
|fishing | Try enough tests, get p < 0.05 |
| Ignore magnitude | Statistically significant may be trivial |

### Better Practice

1. Report effect size + CI (not just p-value)
2. Pre-register analyses
3. Adjust for multiple testing
4. Distinguish statistical vs clinical significance
5. Report negative results

---

## 7. R² (Coefficient of Determination)

### Definition

Proportion of variance in outcome explained by model.

### Types

| Type | Formula | Use |
|------|---------|-----|
| R² | 1 - SS_res/SS_tot | Linear models |
| Adjusted R² | 1 - [(1-R²)(n-1)/(n-p-1)] | Penalizes complexity |
| Pseudo R² | Various | Logistic, Cox |
| Nagelkerke R² | R² / max_R² | Normalized pseudo R² |

### When Valid

- Linear relationship
- Same outcome scale
- Comparable models
- Not for non-linear models without adaptation

### Misuse Cases

| Misuse | Problem |
|--------|---------|
| Comparing across different outcomes | Not comparable |
| R² small = model useless | May still have predictive value |
| R² large = causal | Correlation ≠ causation |
| R² = 1.0 | Likely overfitting or data leakage |
| R² in logistic | Pseudo R² not interpretable like linear |

---

## 8. Number Needed to Treat (NNT)

### Definition

Number of patients who must receive intervention to achieve one additional favorable outcome compared to control.

### Formula

```
NNT = 1 / (Risk_difference)
Risk_difference = Risk_control - Risk_treatment
```

### When Valid

| Requirement | Explanation |
|-------------|-------------|
| Absolute risk reduction known | Need both event rates |
| Outcome clinically meaningful | Not just surrogate |
| Applicable population | Same as study |
| Time horizon appropriate | Same follow-up |

### Interpretation

| NNT | Quality |
|-----|---------|
| < 10 | Highly effective |
| 10-25 | Moderately effective |
| 25-100 | Weakly effective |
| > 100 | Minimal benefit |
| Negative | Harmful |

### Misuse Cases

| Misuse | Problem |
|--------|---------|
| Using relative risk | Must use absolute |
| Ignoring time | Long-term vs short-term different |
| Applying to different populations | Different baseline risk |
| Confusing NNT with NNH | Harm vs benefit |
| Ignoring uncertainty | Confidence interval needed |

---

## 9. Likelihood Ratio (LR)

### Definition

Ratio of probability of test result under diseased vs non-diseased.

### Types

| Type | Formula | Interpretation |
|------|---------|----------------|
| LR+ | Sens / (1-Spec) | >1 rules in disease |
| LR- | (1-Sens) / Spec | <1 rules out disease |

### Clinical Use

```
Post-test odds = Pre-test odds × LR

Example:
- Pre-test probability: 20% (odds = 0.25)
- LR+: 3.0
- Post-test odds = 0.25 × 3.0 = 0.75
- Post-test probability = 0.75 / (1 + 0.75) = 43%
```

### When Valid

- Test result independent of disease status
- Same population characteristics
- Gold standard correct

---

## 10. Brier Score

### Definition

Mean squared error between predicted probabilities and observed outcomes.

### Formula

```
Brier Score = (1/n) Σ (predicted_prob - outcome)²

Lower is better (0 = perfect, 0.25 = random for binary)
```

### Components

| Component | What It Captures |
|-----------|------------------|
| Discrimination | Ability to separate outcomes |
| Calibration | Agreement with observed rates |

### Interpretation

| Score | Quality |
|-------|---------|
| 0.00 | Perfect |
| < 0.05 | Excellent |
| 0.05-0.10 | Good |
| 0.10-0.20 | Fair |
| 0.20-0.25 | Poor |
| 0.25 | Random |

### Validation

- Bootstrap confidence intervals
- Compare to null model
- Decompose into discrimination + calibration components