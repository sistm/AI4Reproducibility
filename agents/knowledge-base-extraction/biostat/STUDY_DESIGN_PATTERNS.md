# Study Design Patterns in Biostatistics

Reference for identifying, evaluating, and extracting knowledge from common epidemiological and clinical study designs.

---

## 1. Randomized Controlled Trial (RCT)

### Structure

```
[Randomization] → [Intervention Arm] → [Outcome Assessment]
                 → [Control Arm]      → [Outcome Assessment]
```

| Component | Requirement |
|-----------|--------------|
| Allocation | Random assignment (computer-generated, stratified, block) |
| Blinding | Single (participant), Double (participant+assessor), Triple |
| Control | Placebo, Standard of care, No treatment |
| Follow-up | Pre-specified duration, Loss-to-follow-up documented |
| Analysis | Intent-to-treat (primary), Per-protocol (sensitivity) |

### Strengths

1. **Causal inference**: Randomization balances confounders (known and unknown)
2. **Baseline balance**: Groups comparable at baseline
3. **Internal validity**: High (with proper implementation)
4. **Statistical power**: Efficient design for causal effects

### Failure Modes

| Mode | Detection | Impact |
|------|-----------|--------|
| Selection bias | Inadequate randomization method | Confounding |
| Performance bias | Unequal treatment delivery | Effect dilution |
| Detection bias | Unblinded outcome assessment | Detection bias |
| Attrition bias | Differential loss to follow-up | Selection |
| Reporting bias | Selective outcome reporting | False positives |
| Carryover effect | Washout period inadequate | Contamination |

### Extraction Checklist

- [ ] Registration number (ClinicalTrials.gov)
- [ ] Randomization method (computer, centralized)
- [ ] Allocation concealment (sealed envelopes, pharmacy)
- [ ] Blinding (who is blinded)
- [ ] Sample size calculation (power, alpha, effect size)
- [ ] Analysis populations (ITT, per-protocol)
- [ ] Flow diagram (CONSORT)

---

## 2. Cohort Study

### Structure

```
[Exposure Assessment] → [Follow-up] → [Outcome Assessment]
                       (Forward in time)
```

| Type | Description |
|------|-------------|
| Prospective | Recruit exposed/unexposed, follow forward |
| Retrospective | Use existing records to reconstruct exposure/outcome |
| Historical | Link past records to present outcomes |

### Strengths

1. **Temporal sequence**: Establishes exposure precedes outcome
2. **Multiple outcomes**: Can study several outcomes from one exposure
3. **Rare exposures**: Efficient for rare exposures
4. **Incidence rates**: Direct calculation of risk

### Failure Modes

| Mode | Detection | Impact |
|------|-----------|--------|
| Selection bias | Inappropriate reference population | External validity |
| Loss to follow-up | >20% or differential | Selection bias |
| Confounding | Unmeasured confounders | Causal misattribution |
| Information bias | Differential exposure ascertainment | Misclassification |
| Surveillance bias | More monitoring in exposed | Detection bias |

### Extraction Checklist

- [ ] Source population defined
- [ ] Cohort entry criteria specified
- [ ] Exposure measurement method
- [ ] Validation of exposure measurement
- [ ] Outcome definition (validated if possible)
- [ ] Follow-up duration and completeness
- [ ] Confounders measured and adjusted

---

## 3. Case-Control Study

### Structure

```
[Outcome Present] → [Assess Prior Exposure]
[Outcome Absent]   → [Assess Prior Exposure]
      (Backward in time)
```

### Strengths

1. **Efficiency**: Good for rare outcomes
2. **Sample size**: Smaller than cohort for rare outcomes
3. **Speed**: Faster than prospective cohort
4. **Multiple exposures**: Can study many exposures

### Failure Modes

| Mode | Detection | Impact |
|------|-----------|--------|
| Selection bias | Control selection from different source | Recall bias |
| Recall bias | Cases recall exposure differently | Information bias |
| Reverse causality | Outcome influences exposure assessment | Causal direction |
| Confounding | Unmeasured or residual confounding | Spurious association |
| Sampling bias | Cases not representative | Selection bias |

### Extraction Checklist

- [ ] Case definition (diagnostic criteria)
- [ ] Case source (hospital, population-based)
- [ ] Control selection (same source, matching)
- [ ] Matching variables specified
- [ ] Exposure measurement (blinded to outcome)
- [ ] Odds ratio calculation method
- [ ] Confounding adjustment method

---

## 4. Cross-Sectional Study

### Structure

```
[Exposure + Outcome] → [Measured at Single Time Point]
```

### Strengths

1. **Feasibility**: Quick and inexpensive
2. **Multiple variables**: Can measure many at once
3. **Prevalence**: Direct estimate of disease prevalence
4. **Hypothesis generating**: Useful for pilot work

### Failure Modes

| Mode | Detection | Impact |
|------|-----------|--------|
| Temporal ambiguity | Cannot establish direction | Causality unclear |
| Prevalence-incidence bias | Neyman bias | Estimates biased |
| Non-response bias | Systematic non-participation | Selection bias |
| Survival bias | Survivors differ from cases | Prevalent cases biased |

### Extraction Checklist

- [ ] Sampling frame defined
- [ ] Sampling method (random, stratified, cluster)
- [ ] Response rate and non-response analysis
- [ ] Temporal relationship unclear
- [ ] Prevalence calculation (crude, age-standardized)
- [ ] Association measure (OR, PR)

---

## 5. Longitudinal Study

### Structure

```
[Baseline] → [Time 1] → [Time 2] → ... → [Time K]
             Measurement at each time point
```

### Types

| Type | Description |
|------|-------------|
| Panel study | Same individuals repeated |
| Trend study | Different samples over time |
| Cohort panel | Cohort followed over time |

### Strengths

1. **Temporal dynamics**: Capture changes over time
2. **Incidence**: Can calculate incidence rates
3. **Causality**: Better temporal sequencing
4. **Within-person change**: Individual trajectories

### Failure Modes

| Mode | Detection | Impact |
|------|-----------|--------|
| Attrition | Dropout over time | Selection bias |
| Practice effects | Learning over assessments | Measurement bias |
| Interval selection | Wrong measurement frequency | Missing data patterns |
| Lead time bias | Earlier detection | Overestimation of survival |

### Extraction Checklist

- [ ] Number of measurement waves
- [ ] Time intervals specified
- [ ] Attrition rate per wave
- [ ] Missing data mechanism
- [ ] Analytical approach (GEE, mixed models, growth curves)
- [ ] Repeated measures analysis

---

## 6. Meta-Analysis

### Structure

```
[Study 1] → [Effect Estimate]
[Study 2] → [Effect Estimate]
...
[Study K] → [Effect Estimate]
               ↓
        [Pooled Estimate]
```

### Strengths

1. **Precision**: Increased statistical power
2. **Generalizability**: Synthesize across populations
3. **Consistency**: Quantify heterogeneity
4. **Evidence synthesis**: Comprehensive view

### Failure Modes

| Mode | Detection | Impact |
|------|-----------|--------|
| Publication bias | Significant results published | Overestimation |
| Study heterogeneity | Unexplained variation | Inappropriate pooling |
| Quality variation | Methodological flaws | Garbage in, garbage out |
| Aggregation bias | Ecological fallacy | Individual-level inferences |
| Duplicate data | Same patients in multiple studies | Double-counting |

### Extraction Checklist

- [ ] Search strategy (databases, terms, dates)
- [ ] Inclusion/exclusion criteria
- [ ] PRISMA flow diagram
- [ ] Study quality assessment
- [ ] Heterogeneity statistics (I², Q-test)
- [ ] Publication bias assessment (funnel plot, Egger)
- [ ] Sensitivity analysis
- [ ] Fixed vs random effects justification
- [ ] Subgroup analyses pre-specified

---

## 7. Diagnostic Accuracy Study

### Structure

```
[Patients] → [Index Test] → [Reference Standard] → [Classification]
```

### Metrics

| Metric | Definition | Use |
|--------|------------|-----|
| Sensitivity | TP / (TP + FN) | Rule out disease |
| Specificity | TN / (TN + FP) | Rule in disease |
| PPV | TP / (TP + FP) | Post-test probability if positive |
| NPV | TN / (TN + FN) | Post-test probability if negative |
| AUC | Area under ROC | Overall accuracy |

### Failure Modes

| Mode | Detection | Impact |
|------|-----------|--------|
| Spectrum bias | Severe vs mild cases | Inflated sensitivity |
| Verification bias | Not all receive reference | Bias |
| Review bias | Reference standard interpreted with index | Overestimation |
| Incorporation bias | Index test part of reference | Overestimation |
| Disease prevalence | Different population | PPV/NPV changes |

### Extraction Checklist

- [ ] Consecutive or random sampling
- [ ] Spectrum of disease (severity)
- [ ] Blinding of reference standard
- [ ] Reference standard validity
- [ ] Appropriate sample size
- [ ] Confidence intervals for metrics
- [ ] ROC curve and AUC

---

## 8. Bayesian Analysis

### Structure

```
[Prior Distribution] + [Likelihood] → [Posterior Distribution]
```

### Components

| Component | Description |
|-----------|-------------|
| Prior | Knowledge before data (informative, weakly informative, flat) |
| Likelihood | Data model P(data|parameters) |
| Posterior | Updated belief P(parameters|data) |
| Credible interval | Bayesian CI (interpretable as probability) |

### Strengths

1. **Natural interpretation**: Direct probability statements
2. **Incorporate prior knowledge**: Use external evidence
3. **Small samples**: Priors provide regularization
4. **Complex models**: MCMC for non-standard problems

### Failure Modes

| Mode | Detection | Impact |
|------|-----------|--------|
| Prior sensitivity | Results depend heavily on prior | Robustness concern |
| MCMC convergence | Poor mixing, too few iterations | Wrong estimates |
| Model misspecification | Wrong likelihood | Biased inference |
| Computational issues | Improper posterior | Unreliable results |

### Extraction Checklist

- [ ] Prior specification and justification
- [ ] Prior sensitivity analysis
- [ ] MCMC diagnostics (trace plots, ESS, R-hat)
- [ ] Posterior summaries (mean, median, CI)
- [ ] Credible intervals reported
- [ ] Model checking (posterior predictive)