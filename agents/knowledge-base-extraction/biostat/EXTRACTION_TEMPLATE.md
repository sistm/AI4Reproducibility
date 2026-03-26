# Biostatistics Extraction Template

Template for extracting structured knowledge from biostatistics and clinical research papers.

---

## 1. Paper Metadata

| Field | Value | Source |
|-------|-------|--------|
| Title | | Title section |
| Authors | | Author list |
| Year | | Publication date |
| Journal | | Source |
| Domain | Biostatistics/Clinical Research | Classification |
| Study Type | | Design section |

### Study Type Classification

- Randomized Controlled Trial (RCT)
- Cohort Study (prospective/retrospective)
- Case-Control Study
- Cross-Sectional Study
- Meta-Analysis
- Survival Analysis
- Diagnostic Accuracy Study

---

## 2. Objective

| Element | Extraction |
|---------|------------|
| Primary Aim | Specific research question |
| Secondary Aims | Additional hypotheses |
| Null Hypothesis | Formal statistical hypothesis |
| Alternative Hypothesis | Directional/non-directional |
| Significance Level | α (typically 0.05) |
| Power | 1-β (typically 0.80) |

---

## 3. Data Description

### 3.1 Data Source

| Element | Value |
|---------|-------|
| Source Name | e.g., NHANES, SEER, UK Biobank, trial name |
| Data Type | Primary collection / Secondary analysis |
| Access | Public / Restricted / Application required |
| Link | URL or reference |

### 3.2 Sample

| Element | Value |
|---------|-------|
| Total N | Total participants |
| Events N | Number of events (for survival) |
| Groups | Number of arms/groups |
| Inclusion Criteria | Explicit eligibility |
| Exclusion Criteria | Explicit ineligibility |

### 3.3 Missing Data

| Element | Extraction |
|---------|------------|
| Complete Cases N | Participants with full data |
| Missing N | Per variable |
| Missing Mechanism | MCAR / MAR / MNAR (stated or implied) |
| Imputation Method | If any |
| Sensitivity Analysis | For missing data |

---

## 4. Statistical Model

### 4.1 Model Specification

| Element | Value |
|---------|-------|
| Model Type | |
| Family | Gaussian / Binomial / Poisson / Cox / ... |
| Link Function | Identity / Log / Logit / ... |

### 4.2 Variables

| Role | Variable Name | Type | Coding |
|------|---------------|------|--------|
| Outcome | | Continuous / Binary / Count / Time-to-event | |
| Primary Exposure | | | |
| Covariate 1 | | | |
| Covariate 2 | | | |
| ... | | | |

### 4.3 Model Equation

```
h(t|X) = h₀(t) × exp(β₁X₁ + β₂X₂ + ... + βₖXₖ)
```

Or equivalent formulation for other models.

### 4.4 Assumptions

| Assumption | Status | Verification |
|------------|--------|--------------|
| Linearity | [ ] stated [ ] checked | Method used |
| Independence | [ ] stated [ ] checked | Method used |
| Homoscedasticity | [ ] stated [ ] checked | Method used |
| Normality | [ ] stated [ ] checked | Method used |
| Proportional Hazards | [ ] stated [ ] checked | Method used |
| No Multicollinearity | [ ] stated [ ] checked | Method used |

---

## 5. Methodology Pipeline

### 5.1 Data Preprocessing

| Step | Details | Parameters |
|------|---------|------------|
| 1. | | |
| 2. | | |
| 3. | | |

### 5.2 Feature Engineering

| Feature | Transformation | Justification |
|---------|----------------|---------------|
| | | |

### 5.3 Model Fitting

| Element | Value |
|---------|-------|
| Software | SAS / R / Stata / Python |
| Package | Version |
| Estimation Method | MLE / REML / Bayesian |
| Convergence | Converged / Iterations |

### 5.4 Validation

| Method | Implementation |
|--------|----------------|
| Internal | Cross-validation (k=?), Bootstrap |
| External | Separate cohort |
| Sensitivity | Alternative specifications |

---

## 6. Key Results

### 6.1 Primary Outcome

| Metric | Estimate | 95% CI | P-value | Interpretation |
|--------|----------|--------|---------|-----------------|
| Effect Size | | | | |
| Hazard Ratio | | | | |
| Odds Ratio | | | | |
| Risk Difference | | | | |

### 6.2 Secondary Outcomes

| Outcome | Effect Size | 95% CI | P-value |
|---------|-------------|--------|---------|
| | | | |

### 6.3 Subgroup Analyses

| Subgroup | Effect Size | 95% CI | P-value | Interaction P |
|----------|-------------|--------|---------|---------------|
| | | | | |

---

## 7. Validation Strategy

### 7.1 Statistical Validation

| Test | Purpose | Result |
|------|---------|--------|
| Goodness-of-fit | Model adequacy | |
| Discrimination | AUC / C-statistic | |
| Calibration | Observed vs expected | |
| Bootstrap | Internal validation | |

### 7.2 Sensitivity Analyses

| Analysis | Change | Result |
|----------|--------|--------|
| Complete cases only | Missing excluded | |
| Multiple imputation | Imputed dataset | |
| Alternative model | Different specification | |

---

## 8. Reproducibility Gaps

### Critical Gaps

| Gap | Present | Details |
|-----|---------|---------|
| Random seed specified | [ ] Yes [ ] No | |
| Preprocessing documented | [ ] Yes [ ] No | |
| Code available | [ ] Yes [ ] No | |
| Data accessible | [ ] Yes [ ] No | |

### Missing Parameters

| Parameter | Expected | Found |
|-----------|----------|-------|
| | | |

---

## 9. Risks & Biases

| Bias Type | Assessment | Mitigation Applied |
|-----------|------------|---------------------|
| Selection bias | [ ] High [ ] Medium [ ] Low | |
| Information bias | [ ] High [ ] Medium [ ] Low | |
| Confounding | [ ] High [ ] Medium [ ] Low | |
| Survivorship bias | [ ] High [ ] Medium [ ] Low | |
| Publication bias | [ ] High [ ] Medium [ ] Low | |
| P-hacking | [ ] High [ ] Medium [ ] Low | |

---

## 10. Output Format

```json
{
  "paper_id": "DOI or unique identifier",
  "metadata": {
    "title": "",
    "authors": [],
    "year": null,
    "study_type": ""
  },
  "objective": {
    "primary_aim": "",
    "null_hypothesis": "",
    "alpha": 0.05,
    "power": 0.80
  },
  "data": {
    "source": "",
    "n_total": null,
    "n_complete": null,
    "missing_mechanism": "",
    "imputation_method": ""
  },
  "model": {
    "type": "",
    "outcome": {"name": "", "type": ""},
    "exposures": [],
    "covariates": [],
    "assumptions": {}
  },
  "results": {
    "primary": {"effect_size": null, "ci": [], "p_value": null},
    "secondary": []
  },
  "reproducibility": {
    "code_available": false,
    "data_accessible": false,
    "seed_specified": false,
    "gaps": []
  },
  "risks": {
    "biases": [],
    "limitations": []
  }
}
```
