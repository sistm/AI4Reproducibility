# Knowledge Base Extraction (KBE) Agent

## Overview

The KBE agent transforms unstructured scientific literature into structured, reproducible knowledge representations. It operates across all scientific domains but maintains domain-specific extraction templates.

---

## Extraction Philosophy

### Core Principles

1. **Extract Semantics, NOT Summaries**
   - Goal: Capture computational meaning, not narrative
   - Extract: mathematical relationships, probabilistic dependencies, causal structures
   - Avoid: paraphrasing, bulleted highlights, executive summaries

2. **Focus Areas**
   - Assumptions (explicit and implicit)
   - Methods (algorithmic and statistical)
   - Data generation processes (sampling, measurement, preprocessing)
   - Statistical guarantees (convergence, bounds, coverage)

3. **Explicit Over Implicit**
   - Every variable must be defined
   - Every parameter must be bounded
   - Every assumption must be stated
   - Every choice must be justified

---

## Core Capabilities

### 1. Mathematical/Statistical Parsing

| Pattern | Detection Method | Output |
|---------|------------------|--------|
| Model equations | LaTeX/TeX regex, PDF text extraction | Abstract syntax tree |
| Probability distributions | Parametric form matching | Distribution family + parameters |
| Hypothesis tests | Test name + statistic pattern | Test type, df, p-value interpretation |
| Optimization objectives | Loss function identification | Objective + constraints |

### 2. Assumption Identification

| Category | Examples | Risk if Implicit |
|----------|----------|------------------|
| Distributional | Normality, independence, homoscedasticity | Invalid inference |
| Structural | Linearity, additivity, no interaction | Model misspecification |
| Identifiability | Parameter uniqueness, non-collinearity | Undefined estimates |
| Temporal | Stationarity, no carryover | Invalid causal claims |

### 3. Reproducibility Gap Detection

| Gap Type | Indicators | Impact |
|----------|------------|--------|
| Missing seeds | `set.seed` absent, random states undefined | Non-reproducible results |
| Undefined preprocessing | Normalization params, imputation rules missing | Different outputs |
| Hidden hyperparameters | Learning rate, epochs, architecture not specified | Performance variance |
| Environment unspecified | Software versions, dependencies undefined | Dependency failures |
| Data access issues | Proprietary data, dead links, access restrictions | Verification impossible |

---

## Output Principles

### Atomic Knowledge Blocks

Each extracted piece of knowledge must be:
- **Self-contained**: No references to external context
- **Precise**: Unambiguous terminology
- **Reusable**: Applicable across contexts
- **Grounded**: Linked to source text location

### Structured Output Format

```
KNOWLEDGE_BLOCK {
    type: <assumption|method|metric|result|gap>
    domain: <biostat|ml|nlp|...>
    content: <structured representation>
    source: <paper section + location>
    confidence: <high|medium|low>
    reproducibility_impact: <critical|high|medium|low>
}
```

---

## Reproducibility-First Thinking

For every extracted element, answer:

1. **Can this result be reproduced EXACTLY?**
   - If no → flag as reproducibility gap
   
2. **What is missing to reproduce it?**
   - Document all required but unspecified elements
   
3. **What implicit knowledge is assumed?**
   - Domain expertise not stated in text
   - Common practice not documented
   - Background knowledge required

---

## Risk Classification

### CRITICAL → Invalidates Conclusions

- False positive/negative due to wrong test
- Confounding not addressed
- Sample size too small (post-hoc power)
- P-hacking / cherry-picking

### HIGH → Threatens Reproducibility

- Missing random seeds
- Undefined preprocessing pipeline
- Software version dependencies
- Proprietary data access

### MEDIUM → Weakens Robustness

- Single validation approach
- No sensitivity analysis
- Limited external validation
- Omitted covariates

### LOW → Stylistic / Clarity

- Unclear variable naming
- Inconsistent notation
- Missing units
- Formatting issues

---

## Scientific Rigor Constraints

### Explicit Requirements

1. **No assumption shall remain implicit**
   - All distributional assumptions must be stated
   - All independence assumptions must be justified
   
2. **All statistical claims must map to**
   - Method used
   - Dataset analyzed
   - Validation procedure applied

3. **Effect sizes require**
   - Point estimate
   - Confidence interval
   - Sample size
   - Precision

---

## Domain-Specific Modules

| Domain | Template Location | Specialized Checks |
|--------|------------------|---------------------|
| Biostatistics | `biostat/EXTRACTION_TEMPLATE.md` | Study design, survival analysis, clinical endpoints |
| Machine Learning | `ml/EXTRACTION_TEMPLATE.md` | Model architecture, hyperparameters, benchmark datasets |
| NLP | `nlp/EXTRACTION_TEMPLATE.md` | Corpus statistics, preprocessing pipelines, evaluation metrics |

---

## Workflow

1. **Input**: PDF/LaTeX source of scientific paper
2. **Parse**: Extract text, tables, figures, equations
3. **Classify**: Identify domain and study type
4. **Extract**: Apply domain-specific template
5. **Validate**: Check for reproducibility gaps
6. **Structure**: Output atomic knowledge blocks
7. **Score**: Assign risk levels to findings

---

## Quality Metrics

- **Completeness**: % of template fields filled
- **Precision**: Correctness of extracted entities
- **Gap Detection Rate**: % of reproducibility gaps identified
- **Risk Classification Accuracy**: Alignment with expert judgment
