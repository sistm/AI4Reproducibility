# Anti-Patterns in R Code

## Critical Anti-Patterns

### 1. Growing Vectors in Loops
```r
# BAD: O(n²) complexity
result <- c()
for (i in 1:10000) {
  result <- c(result, some_computation(i))
}

# GOOD: Pre-allocate
result <- rep(NA_real_, 10000)
for (i in 1:10000) {
  result[i] <- some_computation(i)
}

# BEST: Vectorized
result <- sapply(1:10000, some_computation)
# or
result <- vapply(1:10000, some_computation, double(1))
```

### 2. Using attach()
```r
# BAD: Pollutes namespace, hard to debug
df <- data.frame(x = 1:10, y = rnorm(10))
attach(df)
mean(x)  # Which x? Global? Attached? Hard to tell
y <- x + 1
detach()

# GOOD: Explicit references
df$x
df$y
# Or use with() for temporary scope
with(df, mean(x))
```

### 3. Global Variables
```r
# BAD: Hidden state, non-reproducible
global_config <- read_config()
process_data <- function() {
  return(global_config$value * 10)  # Depends on external state
}

# GOOD: Pass as parameters
process_data <- function(data, config) {
  return(config$value * 10)
}
# Or use environments explicitly
config_env <- new.env()
config_env$value <- 42
get_config <- function() config_env
```

### 4. Magic Numbers
```r
# BAD: Undocumented values
if (score > 0.75) {
  # What is 0.75?
}

# GOOD: Named constants
SIGNIFICANCE_THRESHOLD <- 0.05
CONFIDENCE_LEVEL <- 0.75
if (score > CONFIDENCE_LEVEL) {
  # Clear what 0.75 means
}

# Or use function parameters with defaults
calculate_cutoff <- function(x, threshold = 0.05) {
  # ...
}
```

### 5. Copy-Paste Code
```r
# BAD: Duplicated logic
process_a <- function(df) {
  df <- filter(df, type == "A")
  df <- mutate(df, value = value * 2)
  df <- group_by(df, category)
  df <- summarize(df, total = sum(value))
  return(df)
}

process_b <- function(df) {
  df <- filter(df, type == "B")  # Different filter
  df <- mutate(df, value = value * 2)  # Same
  df <- group_by(df, category)  # Same
  df <- summarize(df, total = sum(value))  # Same
  return(df)
}

# GOOD: Extract common pattern
process_by_type <- function(df, type) {
  df <- filter(df, type == !!type)
  df <- mutate(df, value = value * 2)
  df <- group_by(df, category)
  df <- summarize(df, total = sum(value))
  return(df)
}

process_a <- function(df) process_by_type(df, "A")
process_b <- function(df) process_by_type(df, "B")
```

## Common Errors

### 6. Incomplete Returns
```r
# BAD: Missing return for some branches
check_value <- function(x) {
  if (x < 0) return(NULL)
  if (x > 100) return(NULL)
  # What if x is exactly 0? Or 50? Returns NULL implicitly!
  # This is a bug - different from returning something
}

# GOOD: Explicit return paths
check_value <- function(x) {
  if (x < 0) return(NULL)
  if (x > 100) return(NULL)
  return(TRUE)  # Explicit return for valid inputs
}
```

### 7. Confusing Print vs Return
```r
# BAD: print() returns NULL
log_value <- function(x) {
  print(x + 1)  # Prints to console
  # Returns NULL implicitly!
}

result <- log_value(5)
# result is NULL, not 6

# GOOD: Return the value
log_value <- function(x) {
  value <- x + 1
  message(value)  # For side effect
  return(value)   # Return for use
}

# Or use invisible() for silent return
log_value <- function(x) {
  invisible(x + 1)  # Returns value but doesn't print
}
```

### 8. Implicit Type Coercion
```r
# BAD: Silent coercion to unexpected type
x <- c(1, 2, 3)
y <- c("a", "b", "c")
combined <- c(x, y)
# combined is now c("1", "2", "3", "a", "b", "c")

# Check before combining
if (is.numeric(x) && is.numeric(y)) {
  combined <- c(x, y)
} else {
  stop("Cannot combine different types")
}

# BAD: Factor to numeric trap
f <- factor(c(1, 2, 3))
as.numeric(f)  # Returns 1, 2, 3 (internal codes), NOT values!
as.numeric(as.character(f))  # Correct way

# GOOD: Check and convert explicitly
convert_to_numeric <- function(x) {
  if (is.factor(x)) {
    as.numeric(as.character(x))
  } else {
    as.numeric(x)
  }
}
```

### 9. NA Handling Issues
```r
# BAD: NA in comparisons gives NA, not TRUE/FALSE
x <- c(1, 2, NA, 4)
x > 2  # Returns TRUE, FALSE, NA, TRUE

# Filter with NA conditions:
df <- data.frame(x = c(1, 2, NA, 4))
df[df$x > 2, ]  # NA row included, not filtered

# GOOD: Explicit NA handling
df <- data.frame(x = c(1, 2, NA, 4))
df %>% filter(x > 2 & !is.na(x))

# Or use subset with complete.cases
df[complete.cases(df$x) & df$x > 2, ]
```

### 10. Missing Error Handling
```r
# BAD: Silent failures
read_data <- function(path) {
  data <- read.csv(path)  # If file doesn't exist, stops with error
  # But what if encoding is wrong? Returns gibberish
  # What if file is empty? Returns 0-row data frame
  return(data)
}

# GOOD: Explicit validation
read_data <- function(path) {
  stopifnot(file.exists(path), "File does not exist")
  
  data <- read.csv(path)
  stopifnot(nrow(data) > 0, "File is empty")
  
  required_cols <- c("date", "value")
  missing <- setdiff(required_cols, names(data))
  stopifnot(length(missing) == 0, "Missing columns: ", paste(missing, collapse = ", "))
  
  return(data)
}
```

## Performance Anti-Patterns

### 11. Repeated Expensive Computations
```r
# BAD: Recompute in loop
results <- list()
for (i in seq_along(df$group)) {
  group_data <- df[df$group == df$group[i], ]  # Filter every iteration
  results[[i]] <- mean(group_data$value)
}

# GOOD: Pre-compute or use group operations
library(dplyr)
results <- df %>%
  group_by(group) %>%
  mutate(group_mean = mean(value)) %>%
  ungroup() %>%
  pull(group_mean)
```

### 12. Unnecessary Copies
```r
# BAD: Creates copies
modify_data <- function(df) {
  df$new_col <- df$old_col * 2  # Creates copy of df
  return(df)
}

# With large data, use data.table for in-place modification
library(data.table)
modify_data <- function(dt) {
  dt[, new_col := old_col * 2][]  # Modifies in place
}
```

### 13. Inefficient String Operations
```r
# BAD: String building in loop
result <- ""
for (i in 1:1000) {
  result <- paste0(result, i, ",")  # Each paste creates new string
}

# GOOD: Use vectorized paste
result <- paste0(1:1000, ",")
paste(1:1000, collapse = ",")  # Even better
```

## Statistical Anti-Patterns

### 14. Ignoring Model Assumptions
```r
# BAD: Use t-test without checking assumptions
result <- t.test(group1, group2)  # Assumes normality, equal variance

# GOOD: Check first
shapiro.test(group1)  # Normality
var.test(group1, group2)  # Equal variance

# Or use robust alternative
wilcox.test(group1, group2)  # Non-parametric
```

### 15. Post-Hoc Model Selection
```r
# BAD: Try many models, report best
models <- list(
  lm(y ~ x),
  lm(y ~ x + z),
  lm(y ~ x + z + w),
  lm(y ~ x * z)
)
best_model <- models[[which.min(sapply(models, AIC))]]

# This inflates false positives - need correction
# Or pre-register model specification
```

## Code Smell

### 16. Long Functions
```r
# BAD: 200-line function does everything
process_all <- function(...) {
  # 50 lines of data loading
  # 50 lines of cleaning
  # 30 lines of transformation
  # 40 lines of modeling
  # 30 lines of output
}

# GOOD: Split into focused functions
load_data <- function(...) { ... }
clean_data <- function(data, ...) { ... }
transform_data <- function(data, ...) { ... }
build_model <- function(data, ...) { ... }
generate_output <- function(model, ...) { ... }
```

### 17. Deeply Nested Conditionals
```r
# BAD: Pyramid of doom
if (condition1) {
  if (condition2) {
    if (condition3) {
      # Finally do something
    }
  }
}

# GOOD: Early returns / guard clauses
process <- function(input) {
  if (is.null(input)) return(NULL)
  if (!is_valid(input)) return(NULL)
  
  # Main logic here
}
```

### 18. Inconsistent Naming
```r
# BAD: Mixed styles
user.name <- "alice"  # dot.case
userId <- 123        # camelCase
user_count <- 5      # snake_case

# Pick one: snake_case for variables and functions
user_name <- "alice"
user_id <- 123
user_count <- 5
```

## Summary

| Anti-Pattern | Severity | Fix |
|-------------|----------|-----|
| Growing vectors | Critical | Pre-allocate |
| attach() | High | Use explicit references |
| Global variables | High | Pass parameters |
| Magic numbers | Medium | Named constants |
| Copy-paste | Medium | Extract to function |
| Missing error handling | High | Validate inputs |
| Type coercion | High | Check types explicitly |
| Deep nesting | Medium | Early returns |
| Long functions | Medium | Split into smaller functions |