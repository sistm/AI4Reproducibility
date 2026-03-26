# Biostatistics Reproducibility Checklist

Systematic verification of reproducibility for clinical and statistical research papers.

---

## 1. Data Accessibility

### Item: Data Fully Accessible

- **Verification**: Check if data can be obtained from cited repository
- **Why it matters**: Independent verification requires access to raw data
- **Risk if missing**: HIGH - Cannot verify any numerical result
- **Assessment**:
  - [ ] Public repository (GitHub, Zenodo, Dryad)
  - [ ] Supplementary files attached
  - [ ] Data request procedure documented
  - [ ] Proprietary/unavailable

---

## 2. Preprocessing Documentation

### Item: Preprocessing Steps Defined

- **Verification**: Review Methods section for data cleaning, transformation
- **Why it matters**: Different preprocessing produces different results
- **Risk if missing**: HIGH - Results become non-reproducible
- **Assessment**:
  - [ ] Missing data handling explicitly stated
  - [ ] Outlier handling rules specified
  - [ ] Variable transformations documented
  - [ ] Coding schemes provided

### Item: Missing Data Handling

- **Verification**: Check for complete case analysis vs imputation
- **Why it matters**: Method choice substantially affects estimates
- **Risk if missing**: MEDIUM - May introduce bias
- **Assessment**:
  - [ ] Amount of missingness reported per variable
  - [ ] Mechanism (MCAR/MAR/MNAR) discussed
  - [ ] Imputation method specified
  - [ ] Sensitivity analysis performed

---

## 3. Randomization & Seeds

### Item: Random Seeds Specified

- **Verification**: Search for `set.seed()`, `random_state`, RNG specification
- **Why it matters**: Enables exact reproduction of stochastic results
- **Risk if missing**: HIGH - Different runs produce different results
- **Assessment**:
  - [ ] Seed value provided
  - [ ] RNG algorithm specified
  - [ ] Multiple seeds used (robustness check)

### Item: Cross-Validation Folds

- **Verification**: Check fold assignment reproducibility
- **Why it matters**: Different folds yield different performance
- **Risk if missing**: MEDIUM - Affects model comparison validity
- **Assessment**:
  - [ ] Fold assignment reproducible
  - [ ] Stratification applied (if applicable)
  - [ ] Number of repeats specified

---

## 4. Model Specification

### Item: Model Parameters Fully Disclosed

- **Verification**: Compare reported vs default parameters
- **Why it matters**: Default parameters vary across software versions
- **Risk if missing**: HIGH - Cannot replicate modeling
- **Assessment**:
  - [ ] All hyperparameters specified
  - [ ] Convergence criteria stated
  - [ ] Regularization parameters provided
  - [ ] Software version documented

### Item: Estimation Method Specified

- **Verification**: Identify MLE, REML, Bayesian, etc.
- **Why it matters**: Different methods yield different estimates
- **Risk if missing**: MEDIUM - May affect inference validity
- **Assessment**:
  - [ ] Estimation method named
  - [ ] Optimization algorithm specified
  - [ ] Starting values provided (if non-standard)

---

## 5. Statistical Testing

### Item: Statistical Tests Justified

- **Verification**: Review test selection rationale
- **Why it matters**: Wrong test = invalid inference
- **Risk if missing**: CRITICAL - Conclusions may be false
- **Assessment**:
  - [ ] Test appropriateness discussed
  - [ ] Assumptions checked
  - [ ] Correction for multiple testing applied
  - [ ] One-sided vs two-sided justified

### Item: Significance Level Defined

- **Verification**: Check α specification
- **Why it matters**: Controls false positive rate
- **Risk if missing**: LOW - Conventionally 0.05
- **Assessment**:
  - [ ] α explicitly stated
  - [ ] Multiple comparisons adjusted
  - [ ] Effect size interpretation provided

---

## 6. Code Availability

### Item: Analysis Code Available

- **Verification**: Check for GitHub link, supplementary code
- **Why it matters**: Code enables exact reproduction
- **Risk if missing**: HIGH - Manual replication error-prone
- **Assessment**:
  - [ ] Complete analysis pipeline
  - [ ] Function definitions included
  - [ ] Dependencies documented
  - [ ] README with execution instructions

### Item: Environment Specified

- **Verification**: Check for requirements.txt, Docker, conda env
- **Why it matters**: Software versions affect results
- **Risk if missing**: MEDIUM - May fail or differ
- **Assessment**:
  - [ ] Software versions listed
  - [ ] Package versions pinned
  - [ ] OS requirements specified
  - [ ] Computational environment documented

---

## 7. Results Reporting

### Item: Complete Results Reported

- **Verification**: Check for selective reporting
- **Why it matters**: Selective reporting indicates p-hacking
- **Risk if missing**: HIGH - Publication bias concern
- **Assessment**:
  - [ ] All outcomes reported
  - [ ] Negative results included
  - [ ] Effect sizes + CIs provided
  - [ ] Sample sizes per analysis stated

### Item: Sensitivity Analyses Performed

- **Verification**: Check for robustness checks
- **Why it matters**: Demonstrates result stability
- **Risk if missing**: MEDIUM - Single specification concern
- **Assessment**:
  - [ ] Alternative specifications tested
  - [ ] Influence of outliers examined
  - [ ] Missing data sensitivity shown

---

## 8. Study Design

### Item: Sample Size Justified

- **Verification**: Check power calculation
- **Why it matters**: Underpowered studies produce false negatives
- **Risk if missing**: HIGH - Type II error concern
- **Assessment**:
  - [ ] Power calculation provided
  - [ ] Effect size assumption stated
  - [ ] Alpha and beta specified
  - [ ] One-sided vs two-sided accounted

### Item: Registration Documented

- **Verification**: Check for clinical trial registration
- **Why it matters**: Prevents post-hoc analysis
- **Risk if missing**: MEDIUM - P-hacking risk
- **Assessment**:
  - [ ] Pre-registration ID provided
  - [ ] Protocol available
  - [ ] Analysis plan followed

---

## Summary Scoring

| Category | Items Complete | Total Items | Score |
|----------|---------------|-------------|-------|
| Data | | 4 | |
| Preprocessing | | 5 | |
| Randomization | | 3 | |
| Model | | 3 | |
| Statistical Tests | | 3 | |
| Code | | 3 | |
| Results | | 3 | |
| Design | | 2 | |
| **TOTAL** | | **26** | |

### Risk Thresholds

- **≥ 90%**: Low risk - Fully reproducible
- **70-89%**: Medium risk - Mostly reproducible with effort
- **< 70%**: High risk - Substantial gaps exist
