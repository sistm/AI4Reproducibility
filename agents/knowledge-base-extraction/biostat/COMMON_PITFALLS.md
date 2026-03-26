# Common Pitfalls in Biostatistics Research

Catalog of frequent analytical and interpretative errors with examples and explanations.

---

## 1. Confusing Correlation with Causation

### Description

Assuming that because two variables are associated, one causes the other.

### Example

```
Finding: People who exercise regularly have lower rates of heart disease.
Incorrect: Exercise causes lower heart disease.
Correct: Exercise associated with lower heart disease.
         Could be: healthier people exercise more (self-selection),
         or common cause (wealthier → better diet + exercise)
```

### Explanation

| Factor | Impact |
|--------|--------|
| Confounding | Unmeasured third variable drives both |
| Reverse causality | Outcome causes exposure, not vice versa |
| Selection bias | Who gets selected affects association |
| Chance | Random correlation without meaning |

### Correct Approach

1. Establish temporal sequence (exposure precedes outcome)
2. Control for known confounders
3. Use causal inference methods (instrumental variables, propensity scores)
4. Consider biological plausibility
5. Replicate in different populations

---

## 2. Ignoring Confounders

### Description

Failing to adjust for variables associated with both exposure and outcome.

### Example

```
Study: Coffee drinking associated with increased lung cancer risk
Problem: Coffee drinkers more likely to be smokers
         Smoking is confounder (associated with both)
         Unadjusted analysis overestimates effect
```

### Detection

- Baseline table shows imbalance on key variables
- DAG analysis reveals backdoor paths
- Literature indicates known confounders
- Expert knowledge of domain

### Correct Approach

| Method | When |
|--------|------|
| Stratification | Few confounders, categorical |
| Regression adjustment | Continuous confounders |
| Propensity score | Many confounders, balance check |
| Matching | Reduce confounding |
| Instrumental variable | Unmeasured confounding |

---

## 3. Improper Normalization

### Description

Applying inappropriate standardization that distorts the data or introduces bias.

### Example

```
Problem: Normalizing to mean=0, std=1 using training data only
         Then applying same transformation to test data
         BUT: if test distribution differs, values become extreme

Problem: Z-scoring without checking for outliers
         Single outlier dominates mean/std
         Normalized values become misleading

Problem: Batch effect correction without replicates
         Incorrectly attributing variance to batch
```

### Detection

- Outliers in normalized data
- Distribution differs across batches
- Normalization parameters not reported
- Training/test normalization inconsistency

### Correct Approach

1. Report normalization parameters
2. Check for outliers before normalization
3. Use robust normalization (median, IQR)
4. Validate on held-out data
5. Report both raw and normalized results

---

## 4. Data Leakage

### Description

Information from the test set influences the training process.

### Example

```
Example 1: Feature Selection Before Split
- Select features using all data
- Split into train/test
- Train model on selected features
- Test performance (optimistically biased)

Example 2: Preprocessing Before Split
- Normalize using mean/std of all data
- Train on normalized data
- Test on same normalized scale (information leak)

Example 3: Target Leakage
- Using future information as predictor
- e.g., "days_since_admission" includes day of outcome
```

### Detection

- Performance too good to be true
- Feature importance includes impossible predictors
- Code shows preprocessing before split
- Time-series uses future data

### Correct Approach

```
Correct Pipeline:
1. Split data first (train/validation/test)
2. Fit preprocessing on training ONLY
3. Transform test using training parameters
4. Report both in-sample and out-of-sample
```

---

## 5. Post-Hoc Hypothesis Generation

### Description

Formulating hypotheses after seeing results, presenting as if pre-specified.

### Example

```
Paper states:
"We hypothesized that subgroup X would benefit more"
But: Subgroup X was only examined after seeing overall result

This is p-hacking - making discoveries appear confirmatory
```

### Detection

- Subgroups not pre-registered
- Analysis mentions "unexpectedly" or "interestingly"
- Many subgroup analyses without correction
- Significant subgroups in absence of overall effect

### Correct Approach

1. Pre-register all analyses
2. Distinguish pre-specified vs exploratory
3. Apply correction for multiple testing
4. Report all subgroups examined
5. Be transparent about post-hoc nature

---

## 6. Overinterpreting P-Values

### Description

Treating p < 0.05 as "significant" without considering clinical relevance or precision.

### Example

```
Large study: n = 100,000
Result: HR = 1.05, 95% CI [1.04, 1.06], p < 0.001
Overinterpretation: "Strong evidence of effect"
Reality: 5% increase in risk, clinically trivial

vs.

Small study: n = 50
Result: HR = 2.5, 95% CI [0.9, 6.9], p = 0.08
Underinterpretation: "No significant effect"
Reality: Imprecise estimate, clinically interesting
```

### Correct Interpretation

| P-value | Interpretation |
|---------|---------------|
| < 0.05 | Evidence against null (not proof of effect) |
| > 0.05 | Inconclusive (not proof of no effect) |
| Small | Precise estimate, strong evidence |
| Large | Effect could be null or imprecise |

### Better Approach

1. Report effect sizes with confidence intervals
2. Focus on CI width, not p-value
3. Consider clinical significance
4. Report precision (SE, sample size)
5. Use equivalence/non-inferiority tests when appropriate

---

## 7. Ignoring Missing Data

### Description

Analyzing only complete cases without acknowledging selection bias.

### Example

```
Original sample: n = 1000
Complete cases: n = 650
Analysis: Uses only n = 650

Assumption: Missing completely at random (MCAR)
Reality: Those with missing data differ systematically
Result: Biased estimates, uncertain generalizability
```

### Detection

- No mention of missing data
- Complete case analysis without justification
- Missingness related to outcome
- No sensitivity analysis

### Correct Approach

| Missing Data Method | When Appropriate |
|--------------------|------------------|
| Complete case | MCAR, small proportion |
| Single imputation | MCAR |
| Multiple imputation | MAR |
| Inverse probability weighting | Missing not at random |
| Sensitivity analysis | MNAR |

---

## 8. Binary Categorization of Continuous Variables

### Description

Converting continuous variables to binary (high/low) using arbitrary cutpoints.

### Example

```
Continuous: BMI = 28.5
Binary: BMI > 25 (overweight)

Problems:
- Loss of information
- Arbitrary cutpoint selection
- Induced selection bias
- Reduced statistical power
```

### Detection

- Medians used as cutpoints
- "High" and "low" groups without clinical justification
- Results depend on cutpoint choice
- No sensitivity to cutpoint

### Correct Approach

1. Keep variables continuous
2. Use polynomial terms if non-linear
3. Use splines for flexible relationships
4. If dichotomizing, justify clinically
5. Sensitivity analysis across cutpoints

---

## 9. Ignoring Clustering

### Description

Treating observations as independent when they are nested/hierarchical.

### Example

```
Study: Patients within hospitals
Analysis: Treats all n = 5000 as independent
Reality: Patients in same hospital more similar

Effect:
- Standard errors too small
- Confidence intervals too narrow
- Overconfident conclusions
- Type I error inflated
```

### Detection

- Multi-level data structure (patients in hospitals)
- Cluster-level interventions
- Repeated measures on same individuals
- Geographic clustering

### Correct Approach

| Method | Application |
|--------|-------------|
| Mixed effects models | Random intercepts/slopes |
| GEE with robust SEs | Population-averaged |
| Cluster-robust SEs | Adjustment |
| Fixed effects for clusters | When few clusters |

---

## 10. Model Overfitting

### Description

Fitting complex models to limited data, capturing noise rather than signal.

### Example

```
Data: n = 200 patients, p = 50 variables
Model: Logistic regression with all 50 predictors

Result:
- In-sample accuracy: 85%
- Out-of-sample accuracy: 55%

The model memorized noise in training data
```

### Detection

- Many predictors relative to events (EPV < 10)
- In-sample much better than out-of-sample
- Unstable coefficients (large changes with small data changes)
- No cross-validation

### Correct Approach

| Technique | Purpose |
|-----------|---------|
| Penalization (LASSO, ridge) | Shrink coefficients |
| Feature selection | Reduce dimensionality |
| Cross-validation | Estimate out-of-sample |
| Bootstrap validation | Internal validation |
| External validation | Separate cohort |