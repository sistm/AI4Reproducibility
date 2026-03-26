# Biostatistics Ontology

Structured vocabulary for the knowledge base extraction system. Defines entities, relationships, and attributes for consistent knowledge representation.

---

## 1. Entities

### 1.1 Dataset

| Attribute | Type | Description |
|-----------|------|-------------|
| id | string | Unique identifier |
| name | string | Dataset name |
| source | string | Origin (registry, study, repository) |
| access | enum | public, restricted, application |
| type | enum | primary, secondary, synthetic |
| n_observations | integer | Number of records |
| n_variables | integer | Number of features |
| missing_mechanism | enum | MCAR, MAR, MNAR, unknown |
| temporal_range | string | Date range of collection |
| population | string | Target population description |

### 1.2 Variable

| Attribute | Type | Description |
|-----------|------|-------------|
| id | string | Unique identifier within dataset |
| name | string | Variable name |
| type | enum | continuous, binary, categorical, count, ordinal, survival |
| role | enum | outcome, exposure, covariate, identifier, weight |
| scale | string | Measurement scale/units |
| description | string | Variable definition |
| missing_pct | float | Percentage missing |
| categories | array | For categorical: valid values |
| range | object | min, max for continuous |
| transformed | boolean | Whether transformation applied |

### 1.3 Model

| Attribute | Type | Description |
|-----------|------|-------------|
| id | string | Unique identifier |
| type | enum | linear, logistic, Cox, Poisson, mixed, Bayesian, ... |
| family | string | Error distribution family |
| link | string | Link function |
| estimation_method | enum | MLE, REML, Bayesian, bootstrap |
| software | string | Package/software name |
| version | string | Software version |
| hyperparameters | object | Model-specific parameters |
| convergence | enum | converged, not_converged, max_iterations |
| iterations | integer | Number of iterations |

### 1.4 Assumption

| Attribute | Type | Description |
|-----------|------|-------------|
| id | string | Unique identifier |
| type | enum | distributional, structural, independence, identifiability, temporal |
| statement | string | Formal assumption description |
| verified | boolean | Whether verification performed |
| verification_method | string | How verified (test, inspection) |
| verification_result | enum | satisfied, violated, unclear |
| impact | enum | critical, high, medium, low |
| violated | boolean | Whether assumption violated |

### 1.5 Metric

| Attribute | Type | Description |
|-----------|------|-------------|
| id | string | Unique identifier |
| name | string | Metric name (AUC, HR, p-value, ...) |
| type | enum | discrimination, calibration, effect_size, association, fit |
| value | float | Point estimate |
| ci_lower | float | Lower 95% CI bound |
| ci_upper | float | Upper 95% CI bound |
| confidence_level | float | CI level (0.95 default) |
| p_value | float | Statistical significance |
| interpretation | string | Clinical/practical interpretation |

### 1.6 Bias

| Attribute | Type | Description |
|-----------|------|-------------|
| id | string | Unique identifier |
| type | enum | selection, information, confounding, publication, detection, recall |
| direction | enum | toward_null, away_from_null, unpredictable |
| magnitude | float | Estimated bias magnitude |
| mitigated | boolean | Whether mitigation applied |
| mitigation_method | string | Method used to reduce bias |
| severity | enum | critical, high, medium, low |

---

## 2. Relationships

### 2.1 depends_on

```
[Entity A] depends_on [Entity B]

Examples:
- Model depends_on Assumption (model validity requires assumption)
- Variable depends_on Variable (transformation depends on source)
- Metric depends_on Model (metric derived from model results)
```

### 2.2 violates

```
[Entity A] violates [Entity B]

Examples:
- Data violates Assumption (data does not meet assumption)
- Model violates Assumption (model specification conflicts)
- Assumption violates Identifiability (cannot identify parameters)
```

### 2.3 validated_by

```
[Entity A] validated_by [Entity B]

Examples:
- Model validated_by Validation (cross-validation, bootstrap)
- Metric validated_by Reference (compared to gold standard)
- Assumption validated_by Test (formal verification)
```

### 2.4 derived_from

```
[Entity A] derived_from [Entity B]

Examples:
- Metric derived_from Model (effect size from regression)
- Variable derived_from Variable (log transformation)
- Dataset derived_from Source (extracted from registry)
```

### 2.5 adjusted_for

```
[Entity A] adjusted_for [Entity B]

Examples:
- Effect adjusted_for Confounder (adjusted estimate)
- Analysis adjusted_for Covariate (covariates included)
- Metric adjusted_for MultipleTesting (corrected p-value)
```

### 2.6 associated_with

```
[Entity A] associated_with [Entity B]

Examples:
- Exposure associated_with Outcome (association measure)
- Variable associated_with Variable (correlation)
- Model associated_with Outcome (model predicts outcome)
```

### 2.7 controls_for

```
[Entity A] controls_for [Entity B]

Examples:
- Design controls_for Confounder (randomization)
- Analysis controls_for Covariate (regression adjustment)
- PropensityScore controls_for Selection (matching/weighting)
```

---

## 3. Attribute Schema

### 3.1 Study Design Attributes

| Attribute | Values |
|-----------|--------|
| design_type | RCT, cohort, case-control, cross-sectional, longitudinal, meta-analysis |
| randomization | simple, block, stratified, cluster |
| blinding | none, single, double, triple |
| allocation_ratio | 1:1, 1:2, 2:1, ... |
| follow_up_duration | duration in months/years |
| sampling_method | random, convenience, consecutive, systematic |

### 3.2 Analysis Attributes

| Attribute | Values |
|-----------|--------|
| analysis_type | intention_to_treat, per_protocol, as_treated |
| missing_handling | complete_case, single_imputation, multiple_imputation, inverse_probability |
| model_selection | aic, bic, cross_validation, bootstrap |
| variable_selection | none, stepwise, lasso, domain_knowledge |
| validation_method | cross_validation, bootstrap, external, temporal |

### 3.3 Reporting Attributes

| Attribute | Values |
|-----------|--------|
| reporting_guideline | CONSORT, STROBE, PRISMA, TRIPOD |
| registration | registered, pre_registration, none |
| conflicts | declared, none |
| funding | source, none_declared |

---

## 4. Knowledge Graph Example

```
Example: Cox Proportional Hazards Model

NODES:
- Dataset: "FRAMINGHAM" (id: ds_001)
- Variable: "time_to_event" (id: var_001, type: survival)
- Variable: "smoking_status" (id: var_002, type: binary)
- Variable: "age" (id: var_003, type: continuous)
- Model: "cox_model_1" (type: Cox)
- Assumption: "proportional_hazards" (type: temporal)
- Metric: "hazard_ratio" (value: 2.3, ci: [1.8, 2.9])
- Bias: "confounding" (type: confounding, mitigated: true)

EDGES:
- Model "cox_model_1" derived_from Dataset "FRAMINGHAM"
- Model "cox_model_1" depends_on Assumption "proportional_hazards"
- Metric "hazard_ratio" derived_from Model "cox_model_1"
- Variable "smoking_status" adjusted_for Variable "age"
- Assumption "proportional_hazards" validated_by "schoenfeld_residuals"
```

---

## 5. Controlled Vocabularies

### 5.1 Study Design Types

```
RCT: Randomized Controlled Trial
  ├── Parallel
  ├── Crossover
  ├── Cluster
  └── Stepped Wedge

COHORT: Cohort Study
  ├── Prospective
  ├── Retrospective
  └── Historical

CASE_CONTROL: Case-Control Study
  ├── Nested
  └── Population-based

CROSS_SECTIONAL: Cross-Sectional Study
SURVIVAL: Survival Analysis Study
META_ANALYSIS: Meta-Analysis
DIAGNOSTIC: Diagnostic Accuracy Study
```

### 5.2 Model Types

```
LINEAR: Linear Regression
LOGISTIC: Logistic Regression
  ├── Binary
  └── Multinomial

POISSON: Poisson Regression
NEGATIVE_BINOMIAL: Negative Binomial
COX: Cox Proportional Hazards
PARAMETRIC_SURVIVAL: Parametric Survival (Weibull, Exponential, etc.)
MIXED: Mixed Effects Model
  ├── Linear Mixed
  └── Generalized Linear Mixed

BAYESIAN: Bayesian Model
TIME_SERIES: Time Series Model
SEM: Structural Equation Model
CAUSAL: Causal Inference Model
  ├── Propensity Score
  ├── Instrumental Variable
  └── Mediation Analysis
```

### 5.3 Bias Types

```
SELECTION: Selection Bias
  ├── Sampling bias
  ├── Attrition bias
  └── Volunteer bias

INFORMATION: Information Bias
  ├── Measurement error
  ├── Misclassification
  └── Recall bias

CONFOUNDING: Confounding Bias
  ├── Measured confounding
  └── Unmeasured confounding

PUBLICATION: Publication Bias
  ├── Reporting bias
  └── Outcome reporting bias

DETECTION: Detection Bias
```

### 5.4 Risk Levels

```
CRITICAL: Invalidates conclusions, cannot interpret results
HIGH: Substantially affects validity or reproducibility
MEDIUM: Affects robustness or precision
LOW: Minor impact, stylistic or clarity
```

---

## 6. Entity Relationship Diagram (Text)

```
Dataset ──┬── contains ── Variable
          ├── generates ── Analysis
          └── produces ── Results

Variable ─┬── role (outcome/exposure/covariate)
          ├── has_type (continuous/binary/categorical)
          └── transformed_to ── Variable

Model ────┬── estimated_from ── Dataset
          ├── uses ── Variable
          ├── depends_on ── Assumption
          └── produces ── Metric

Assumption ─┬── type (distributional/structural/independence)
            ├── verified_by ── Test
            └── violated_by ── Dataset/Model

Metric ────┬── derived_from ── Model
           ├── validated_by ── Validation
           └── interpreted_as ── Interpretation

Bias ──────┬── mitigated_by ── Method
           ├── affects ── Metric
           └── severity ── Level
```

---

## 7. JSON-LD Context

```json
{
  "@context": {
    "dataset": "https://ai4reproducibility.org/ontology#Dataset",
    "variable": "https://ai4reproducibility.org/ontology#Variable",
    "model": "https://ai4reproducibility.org/ontology#Model",
    "assumption": "https://ai4reproducibility.org/ontology#Assumption",
    "metric": "https://ai4reproducibility.org/ontology#Metric",
    "bias": "https://ai4reproducibility.org/ontology#Bias",
    "depends_on": "https://ai4reproducibility.org/ontology#depends_on",
    "violates": "https://ai4reproducibility.org/ontology#violates",
    "validated_by": "https://ai4reproducibility.org/ontology#validated_by",
    "derived_from": "https://ai4reproducibility.org/ontology#derived_from"
  }
}