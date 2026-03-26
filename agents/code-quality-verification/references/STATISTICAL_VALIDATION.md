# Statistical Validation for R Code

## Critical Importance

Statistical errors in production code lead to incorrect decisions in finance, medicine, and research. These errors are often silent - code runs without errors but produces wrong results.

## P-Value Misuse

### Multiple Testing Without Correction
```r
# BAD: Test 20 hypotheses, report lowest p-value
p_values <- sapply(1:20, function(i) {
  t.test(rnorm(50), rnorm(50))$p.value
})
min(p_values)  # ~0.05 even with no real differences

# GOOD: Apply correction
p.adjust(p_values, method = "bonferroni")
p.adjust(p_values, method = "fdr")  # Benjamini-Hochberg
```

### P-Hacking Patterns
```r
# BAD: Try multiple datasets until p < 0.05
for (dataset in list_of_datasets) {
  result <- t.test(dataset)
  if (result$p.value < 0.05) break
}

# GOOD: Pre-register hypotheses, report all tests
# If exploratory, clearly label as such
```

### Interpreting P-Values
```r
# BAD: Equating p-value with effect size
# "p = 0.001 means the effect is huge"

# GOOD: Report effect size alongside p-value
t_test <- t.test(group1, group2)
effect_size <- (mean(group1) - mean(group2)) / sd(pooled)
# Report: "t = 3.5, p = 0.001, Cohen's d = 0.8"
```

## Test Assumptions

### Normality
```r
# BAD: Assume normality, don't check
result <- t.test(data$value ~ data$group)

# GOOD: Check assumptions
shapiro.test(data$value)  # Shapiro-Wilk for normality
# Or visualize
hist(data$value)
qqnorm(data$value)

# If violated: use non-parametric test
wilcox.test(data$value ~ data$group)  # Mann-Whitney U
```

### Homogeneity of Variance
```r
# BAD: Assume equal variances
result <- t.test(data$value ~ data$group)

# GOOD: Check with Levene's test
library(car)
leveneTest(value ~ group, data = data)

# If violated: use Welch's t-test (default in R)
t.test(value ~ group, data = data, var.equal = FALSE)
```

### Independence
```r
# BAD: Treat repeated measures as independent
# Time series, matched pairs, cluster samples

# GOOD: Account for structure
# Paired t-test for matched pairs
t.test(before, after, paired = TRUE)

# Mixed models for hierarchical data
library(lme4)
lme4::lmer(outcome ~ treatment + (1|subject), data = data)
```

## Model Specification

### Linear Models
```r
# BAD: Omitted relevant variables
model <- lm(y ~ x1, data = df)  # Missing x2, confounder

# GOOD: Include theory-driven covariates
model <- lm(y ~ x1 + x2 + x3, data = df)

# Check for omitted variable bias
# Compare coefficient changes when adding variables
```

### Interaction Terms
```r
# BAD: No interaction when effect differs by group
model <- lm(y ~ treatment + age, data = df)
# Treatment effect assumes constant across age

# GOOD: Include interaction if theory suggests moderation
model <- lm(y ~ treatment * age, data = df)
# Or use strata
model <- lm(y ~ treatment, data = subset(df, age_group == "old"))
```

### Nonlinear Relationships
```r
# BAD: Force linear model on nonlinear data
model <- lm(y ~ x, data = df)  # Curved relationship

# GOOD: Fit flexible model
# Polynomial
model <- lm(y ~ poly(x, 2), data = df)

# Splines
library(splines)
model <- lm(y ~ ns(x, df = 3), data = df)
```

## Data Leakage

### Train-Test Contamination
```r
# BAD: Feature engineering on full dataset before split
df$mean_feature <- ave(df$feature, df$id, FUN = mean)
train <- df %>% sample_frac(0.8)
# Now train has leaked information from test

# GOOD: Create features after split
train <- df %>% sample_frac(0.8)
test <- df %>% anti_join(train, by = "id")
train$mean_feature <- ave(train$feature, train$id, FUN = mean)
```

### Cross-Validation Leakage
```r
# BAD: Preprocessing before CV
scaled <- scale(df)  # Using full data mean/std
kfolds <- KFold(nrow(df), 5)
# Now each fold uses global scaling from all data

# GOOD: Preprocess within each fold
train_indices <- sample(1:nrow(df), size = 0.8*nrow(df))
scaled_train <- scale(df[train_indices, ])
# Apply same scale to test
scaled_test <- scale(df[-train_indices, ],
                    center = attr(scaled_train, "scaled:center"),
                    scale = attr(scaled_train, "scaled:scale"))
```

### Target Leakage
```r
# BAD: Using future information
df$days_until_purchase <- as.Date(df$purchase_date) - as.Date(df$visit_date)
# This is known at prediction time only for past purchases

# GOOD: Only use features available at prediction time
# For real-time predictions, cannot use future data
```

## Overfitting

### Symptom: Perfect Training Performance
```r
# BAD: Model memorizes training data
train_accuracy <- 1.0  # 100% on training
test_accuracy <- 0.6  # 60% on test

# GOOD: Validate on held-out data
# Use cross-validation to estimate generalization error
```

### Regularization
```r
# Use regularized models for high-dimensional data
library(glmnet)
# Lasso: L1 penalty for sparsity
model <- glmnet(x, y, alpha = 1, lambda = 0.1)

# Ridge: L2 penalty for coefficient shrinkage
model <- glmnet(x, y, alpha = 0, lambda = 0.1)

# Elastic net: combination
model <- glmnet(x, y, alpha = 0.5, lambda = 0.1)
```

### Complexity Control
```r
# BAD: Unlimited complexity
tree_model <- rpart(y ~ ., data = train, control = rpart.control(cp = 0))

# GOOD: Cross-validated complexity selection
cv_error <- rpart(y ~ ., data = train, 
                  control = rpart.control(cp = 0.01))
plotcp(cv_error)
```

## Sampling Issues

### Non-Representative Samples
```r
# BAD: Convenience sampling
# "We used available data" without considering bias

# GOOD: Document sampling mechanism
# If using non-probability sample, acknowledge limitations
# Consider inverse probability weighting if possible
```

### Sample Size
```r
# BAD: Underpowered analysis
# 30 samples for 10 predictors

# GOOD: Power analysis before data collection
library(pwr)
pwr.f2.test(u = 10, v = NULL, f2 = 0.15, sig.level = 0.05, power = 0.8)
# u = predictors, f2 = expected effect size
```

### Missing Data
```r
# BAD: Complete case analysis without justification
model <- lm(y ~ x, data = df)  # Drops rows with any NA

# GOOD: Understand missingness mechanism
library(naniar)
gg_miss_var(df)

# Multiple imputation or sensitivity analysis
library(mice)
imp <- mice(df, m = 5)
model <- with(imp, lm(y ~ x))
pooled <- pool(model)
```

## Model Diagnostics

### Regression
```r
# Check linearity, homoscedasticity, normality of residuals
plot(model)
# 1: Residuals vs Fitted - check linearity
# 2: Q-Q plot - check normality
# 3: Scale-Location - check homoscedasticity
# 4: Residuals vs Leverage - check influential points

# Formal tests
car::qqPlot(model)
car::ncvTest(model)  # Non-constant variance
car::outlierTest(model)
```

### Classification
```r
# Check calibration and discrimination
library(verification)
roc.plot(actual, predicted)

# Confusion matrix
table(predicted, actual)
# Calculate: accuracy, precision, recall, F1

# Calibration
calibration <- calibration(actual ~ predicted)
plot(calibration)
```

## Common Statistical Errors

| Error | Detection | Fix |
|-------|-----------|-----|
| Pseudoreplication | Multiple measurements per unit treated as independent | Use mixed models or aggregate |
| Survivorship bias | Only analyzing completed cases | Document exclusions |
| Confirmation bias | Seeking evidence for preferred hypothesis | Pre-register analysis |
| Ecological fallacy | Group-level inferences about individuals | Use appropriate level of analysis |
| Automation bias | Trusting automated analysis | Verify with domain knowledge |

## Validation Checklist

- [ ] Statistical test assumptions checked
- [ ] Effect sizes reported alongside p-values
- [ ] Multiple testing correction applied
- [ ] Cross-validation proper (no leakage)
- [ ] Model diagnostics examined
- [ ] Results compared to sensitivity analyses
- [ ] Limitations acknowledged