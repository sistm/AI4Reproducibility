# 🧠 AI4R — Automated Scientific Reproducibility Review System

## 🎯 Purpose

This workflow orchestrates a set of specialized AI agents to perform a **rigorous, reproducible, and standardized evaluation of scientific papers**.

The system replaces subjective and inconsistent peer-review practices with:
- Deterministic analysis
- Structured outputs
- Explicit risk identification
- Cross-agent validation

---

## ⚙️ WORKFLOW OVERVIEW

Pipeline execution is **sequential with controlled context propagation**:


INPUT (Paper + Assets)
↓
[KBE Agent] → Domain Understanding
↓
[CQV Agent] → Code & Repository Validation
↓
[Review Agent] → Final Reproducibility Assessment
↓
OUTPUT (Structured Report)


Optional extension:
    ↓

[ER Agent] → Experimental Reproduction (Dockerized)


---

## 🧩 AGENT DEFINITIONS

### 1. 🧬 KBE — Knowledge Base Extraction Agent

**Path:** `agents/knowledge-base-extraction`

**Role:**
- Extract structured scientific knowledge from the paper
- Ignore code and experiments
- Build a **semantic representation of the methodology**

**Inputs:**
- Paper (PDF / text)
- Supplementary materials (non-code)

**Outputs:**
- Structured extraction using domain templates (e.g., biostat/)
- Identified assumptions
- Statistical methods
- Data generation processes
- Reproducibility gaps (non-code)

**Constraints:**
- No summarization
- No interpretation beyond evidence
- All claims must map to explicit text

---

### 2. 💻 CQV — Code Quality Verification Agent

**Path:** `agents/code-quality-verification`

**Role:**
Evaluate the **technical reproducibility of the codebase**

**Inputs:**
- Git repository
- README
- Dependency files

**Outputs:**
- Repository audit
- Code-method alignment analysis
- Dependency validation
- Execution readiness assessment
- Reproducibility blockers

**Checks include:**
- Project structure
- Environment reproducibility (renv, requirements.txt, Docker)
- Data accessibility
- Versioning & licensing
- Hidden dependencies

---
<!-- 
### X. 🧪 ER — Experiment Run Agent (Optional / Future)

**Path:** `agents/experiment-run`

**Role:**
- Attempt execution of experiments in isolated environments

**Capabilities:**
- Auto-generate Docker environments
- Install dependencies
- Run pipelines
- Compare outputs to reported results

**Status:**
- Disabled by default
- Plug-and-play integration into workflow -->

---

### 3. 🧠 Review Agent

**Path:** `agents/review`

**Role:**
Produce the **final reproducibility verdict**

**Inputs:**
- KBE outputs
- CQV outputs
- (Optional) ER outputs
- Global CHECKLIST.md

**Process:**
- Cross-validate findings
- Detect inconsistencies
- Apply checklist rigorously
- Perform self-critique loop

**Outputs:**
- Final review checklist
- Comprehensive audit reports
- Fix advices
- Risk scoring
- Acceptance recommendation
- Justified decision

---

## 🔄 EXECUTION LOGIC

### Step 1 — KBE Execution

- Parse paper
- Apply domain-specific extraction templates
- Output structured knowledge artifacts

→ Save as: `kbe_output.json`

---

### Step 2 — CQV Execution

- Analyze repository
- Validate reproducibility of code

→ Save as: `cqv_output.json`

---

### Step 3 — (Optional) ER Execution

- Trigger ONLY if:
  - Code is runnable
  - Dependencies are resolvable

→ Save as: `er_output.json`

---

### Step 4 — Review Agent

- Merge all outputs from KBE, CQV, and ER agents
- Apply comprehensive checklist
- Generate multiple structured outputs:
  - Executive summary (`final_review.md`)
  - Exhaustive audit report (`exhaustive_audit_report.md`)
  - Biometrical Journal compliance checklist (`checklist.md`)
  - Risk assessment data (`risk_matrix.json`)

→ Save as: `final_review.md`, `exhaustive_audit_report.md`, `checklist.md`, `risk_matrix.json`

---

## 🧠 CONTEXT SHARING STRATEGY

Each agent must operate with **strict scoped context**:

| Agent | Allowed Context |
|------|----------------|
| KBE  | Paper only |
| CQV  | Codebase only |
| ER   | Code + environment |
| Review | ALL outputs |

❗ No agent should infer beyond its scope.

---

## 📏 EVALUATION PRINCIPLES

### 1. Determinism
- Same input → same output

### 2. Evidence-based reasoning
- Every claim must reference:
  - Extracted data OR
  - Code observation

### 3. No hallucination tolerance
- Unknown → explicitly marked as missing

### 4. Conservative judgment
- Missing information = risk

---

## 🚨 RISK MODEL

All agents must classify findings:

- **CRITICAL** → Invalidates reproducibility
- **HIGH** → Strong reproducibility threat
- **MEDIUM** → Weakness in rigor
- **LOW** → Minor issue

---

## 🧱 OUTPUT CONTRACT

### KBE Output
- Structured knowledge
- Assumptions
- Missing elements

### CQV Output
- Code audit
- Reproducibility blockers

### Review Output
- Executive summary (`final_review.md`)
- Exhaustive audit report (`exhaustive_audit_report.md`)
- Biometrical Journal compliance checklist (`checklist.md`)
- Risk score and matrix (`risk_matrix.json`)
- Detailed findings
- Final verdict:
  - ACCEPT
  - MINOR REVISION
  - MAJOR REVISION
  - REJECT

---

## 🔌 EXTENSIBILITY

To enable ER Agent:

1. Add to pipeline after CQV
2. Define trigger conditions
3. Extend Review Agent inputs

No redesign required.

---

## 🧪 FAILURE HANDLING

If any agent fails:

- Log failure explicitly
- Continue pipeline with degraded context
- Increase risk level accordingly

---

## 🧠 META-REASONING LOOP (Review Agent)

The Review Agent must:

1. Generate initial verdict
2. Critically re-evaluate:
   - Missing evidence
   - Contradictions
3. Adjust final decision

---

## 🛠️ IMPLEMENTATION NOTES (KILO)

- Each agent = independent workflow node
- Outputs = structured artifacts (JSON + Markdown)
- Use strict schemas for interoperability
- Avoid free-form outputs

---

## 📁 OUTPUT DIRECTORY STRATEGY (MANDATORY)

Each review execution MUST create a dedicated folder:


/ai4r/{review_title}/


### 🔑 Naming Rules
- `{review_title}` must be:
  - Lowercase
  - Kebab-case
  - Derived from paper title
  - Example:
    - "Deep Learning for Survival Analysis"
    → `deep-learning-survival-analysis`

---

## 📦 FOLDER STRUCTURE PER RUN

**Note:** Create each folder seperately to avoid bugs.

/ai4r/{review_title}/
│
├── input/
│ ├── paper.pdf
│ ├── metadata.json
│ └── assets/
│
├── kbe/
│ ├── kbe_output.json
│ └── notes.md
│
├── cqv/
│ ├── cqv_output.json
│ └── repo_analysis.md
│
├── er/ (optional)
│ ├── er_output.json
│ ├── dockerfile
│ └── execution_logs.txt
│
├── review/
│ ├── final_review.md
│ ├── exhaustive_audit_report.md
│ ├── checklist.md
│ └── risk_matrix.json
│
└── logs/
├── workflow.log
└── agent_traces/

## 🎯 FINAL OBJECTIVE

Deliver a system that:

- Standardizes reproducibility review
- Reduces reviewer workload
- Increases scientific rigor
- Enables scalable peer-review automation