# Knowledge Base Extraction (KBE) Agent

see [LOGIC.md §3.1](../../LOGIC.md#31-kbe--knowledge-base-extraction) for this agent's place in the pipeline.

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

## Output

Structured outputs following the workflow specification:
- **`kbe_output.json`** - Structured knowledge extraction with atomic knowledge blocks
- **`notes.md`** - Additional observations and reproducibility gaps

**Output Location:** `/ai4r/{review_title}/kbe/`

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

---

## Failure Handling

The KBE agent MUST always produce its two output files (`kbe_output.json`
and `notes.md`) even when extraction fails. Downstream agents and the
post-flight validator depend on the files being present and well-formed.
A crashed agent that writes nothing will hard-fail the entire pipeline.

### Status enum

Every `kbe_output.json` MUST include a top-level `status` field with one
of these values:

| Value     | Meaning                                                            |
|-----------|---------------------------------------------------------------------|
| `success` | Extraction completed normally; full structured knowledge produced.  |
| `partial` | Some sections extracted; others failed or were skipped.             |
| `failed`  | Extraction could not produce useful structured knowledge.           |

`skipped` is reserved for downstream consumers and is never emitted by KBE.

### Known failure modes

| `failure_mode`         | Trigger                                                               | Recommended status |
|------------------------|------------------------------------------------------------------------|-------------------|
| `pdf_not_found`        | `input/paper.pdf` is absent.                                          | `failed`          |
| `pdf_unreadable`       | `pdf2text` returns `success: false` or empty text.                    | `failed`          |
| `pdf_encrypted`        | `pdf2text` raises a password / encryption error.                      | `failed`          |
| `text_too_short`       | Cleaned text < 1000 characters (likely a scan or wrong file).         | `failed`          |
| `llm_request_failed`   | The model call raised (network, auth, 5xx) for every section.         | `failed`          |
| `domain_unrecognized`  | No biostat/ML/NLP template matches; falls back to generic extraction. | `partial`         |
| `template_partial`     | Some template sections extracted, others left empty.                  | `partial`         |
| `parse_error`          | An internal extraction step crashed.                                  | `partial`         |

### Required output on failure

When `status != "success"`, `kbe_output.json` MUST conform to this shape:

```json
{
  "paper_id": "<review_title from arguments>",
  "paper_title": null,
  "extraction_timestamp": "<ISO 8601 UTC>",
  "status": "failed",
  "failure_mode": "pdf_unreadable",
  "failure_reason": "pdf2text returned success=false: 'EOF before %%EOF'",
  "structured_knowledge": null,
  "identified_assumptions": [],
  "statistical_methods": [],
  "data_generation_processes": [],
  "reproducibility_gaps": [],
  "partial_data": null,
  "notes": "See notes.md for context."
}
```

For `status: "partial"`, populate every field with whatever was successfully
extracted, leave the rest as empty arrays / null, and set `partial_data` to
a short object describing which template sections succeeded:

```json
"partial_data": {
  "sections_extracted": ["abstract", "methods"],
  "sections_failed": ["results", "discussion"]
}
```

When `partial` includes a successfully parsed title section, `paper_title`
MUST be populated with the extracted title string rather than left null.

### Behavioral rules

1. NEVER raise an unhandled exception. Catch internal errors, classify them
   into a `failure_mode`, and write the failure output.
2. The `paper_id` field MUST be set to the kebab-case `review_title` from
   the workflow arguments, even when no PDF could be read. It is stable
   across all outputs and survives upstream failure.
3. The `paper_title` field is the full human-readable title parsed from
   the manuscript PDF. KBE is the only agent that can populate it. When
   the PDF cannot be read, set it to `null`. When the title section of
   the PDF is successfully parsed, set it to the extracted string.
   Downstream (Review) reads this field — it is the only path by which
   the manuscript's title reaches `risk_matrix.json`.
4. `notes.md` is always written. On failure, it must contain at minimum:
   the failure mode, the failure reason, and any diagnostic output from
   the failing tool (truncated to ~500 lines).
5. Log every failure mode encountered to `ai4r/<review_title>/logs/workflow.log`
   in addition to writing it into `kbe_output.json`.
