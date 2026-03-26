# R Style Guide

## tidyverse Style Guide Reference

This guide follows the [tidyverse style guide](https://style.tidyverse.org/) with additions for production R code.

## File Organization

### Script Structure
```r
# Section: Header ----
# -----------------------------------------------------------------------------
# Purpose: [One sentence]
# Author: [Name]
# Date: YYYY-MM-DD
# ---------------------------------------------------------------------------

# Load libraries ----
library(dplyr)
library(tidyr)

# Helper functions ----
# Place utilities after imports, before main logic

# Main execution ----
# Only runs when script is sourced directly
if (sys.nframe() == 0L) {
  # Main pipeline
}
```

### Function Order
```r
# 1. Main/public functions first
# 2. Private/helpers last
# 3. Related functions grouped

#' Public function description
#' @param x Description
#' @return Description
#' @export
public_func <- function(x) {
  # Uses private_func
  private_func(x)
}

#' Private function
#' @param x Description
#' @keywords internal
private_func <- function(x) {
  # Implementation
}
```

## Naming Conventions

### Variables and Functions
```r
# snake_case: lowercase with underscores
user_name <- "alice"
calculate_mean <- function(x) mean(x)

# Avoid: camelCase, PascalCase, all lowercase with no separator

# Good: descriptive names
processed_data <- df
prediction_model <- model

# Avoid: abbreviations unless well-known (df, dt, lm)
# Avoid: single letters except in standard contexts (i, j, x, y in math)
```

### Constants
```r
# SCREAMING_SNAKE_CASE for constants
MAX_ITERATIONS <- 1000
DEFAULT_THRESHOLD <- 0.05
```

### Columns
```r
# Column names: snake_case
df$date_of_birth  # NOT dateOfBirth or dateOfBirth
df$user_id        # NOT userId or userID

# Boolean: prefix with is_, has_, should_
df$is_active
df$has_error
df$should_normalize
```

### Files
```r
# kebab-case for file names (hyphens)
# load-data.R
# plot-results.R

# NOT: load_data.R (inconsistent with function names)
# NOT: loadData.R (camelCase conflicts)
```

## Function Design

### Argument Order
```r
# 1. Data (most important) - usually first
# 2. Required parameters
# 3. Optional parameters with defaults
# 4. dots (...) for additional parameters

process_data <- function(data, group_var, output_dir = "output/", ...) {
  # ...
}
```

### Argument Naming
```r
# Use explicit names, not positional
calculate_statistics(df, col = "value", method = "mean")
# NOT: calculate_statistics(df, "value", "mean")
```

### Default Values
```r
# Avoid: NULL defaults that mean "compute default"
# Prefer: explicit NA or computed defaults

# BAD
normalize <- function(x, method = NULL) {
  if (is.null(method)) method <- "zscore"
  # ...
}

# GOOD
normalize <- function(x, method = c("zscore", "minmax")) {
  method <- match.arg(method)
  # ...
}

# ACCEPTABLE - documented default behavior
impute_missing <- function(x, fill = NA_real_) {
  # fill = NA means use median (documented)
}
```

### Return Values
```r
# Explicit return for early exits
find_value <- function(x) {
  for (i in seq_along(x)) {
    if (x[i] > 0) return(x[i])
  }
  return(NULL)
}

# Implicit return for main output
compute_stats <- function(x) {
  # Last expression is return value
  c(mean = mean(x), sd = sd(x))
}

# Never use return() in middle except early exit
```

## Pipe Usage

### When to Use Pipes
```r
# Chain transformations on data
df %>%
  filter(status == "active") %>%
  group_by(category) %>%
  summarize(count = n()) %>%
  ungroup()

# When intermediate results are not needed
```

### When to Avoid Pipes
```r
# Multiple outputs or complex branching
if (is.null(output)) {
  result <- compute_default()
} else {
  result <- compute_custom(output)
}
return(result)

# Calculations with many steps - store intermediate
temp1 <- step_one(data)
temp2 <- step_two(temp1)
final <- step_three(temp2)

# Debugging - need to inspect intermediate
df %>%
  filter(x > 0) %>%
  {browser(); .} %>%  # Debug here
  summarize(y = mean(y))
```

### Pipe Style
```r
# Each step on new line, pipe at end of line
df %>%
  filter(x > 0) %>%
  mutate(y = log(y)) %>%
  select(x, y)

# If pipe doesn't fit, break at verbs
df %>%
  filter(x > 0) %>%
  group_by(category) %>%
  summarize(
    count = n(),
    mean = mean(value)
  )

# Never pipe to assignment (right side)
value <- df %>%
  filter(x > 0) %>%
  pull(y)  # This is OK (assignment at start)
```

## Spacing

### Around Operators
```r
# Spaces around: +, -, *, /, <-, ==, <=, >=, !=
x <- 1 + 2
y == z
a != b

# No spaces: :, ::, @, $, [, [[
mtcars$mpg
dplyr::filter
slot(object, "name")
df[, "col"]
```

### In Function Calls
```r
# Space after function name, between all arguments
mean(x = c(1, 2, 3), na.rm = TRUE)

# No space before [
filter(df, condition)
select(df, col1, col2)

# Exception: braces
if (condition) {  # Space after if
  # code
}
```

### Indentation
```r
# 2 spaces, not tabs
# Align related code

# If statement
if (condition) {
  # Code
} else {
  # Code
}

# Function call across lines
very_long_function_name(
  argument1 = value1,
  argument2 = value2
)
```

## Documentation

### Function Documentation
```r
#' Title line (concise, sentence case)
#'
#' Longer description if needed. Can be multiple sentences.
#'
#' @param x Description of x. Start with verb: "Vector to process"
#'   for multiline, indent 2 spaces.
#' @param group Grouping variable.
#' @param na.rm Remove NA values. Default is FALSE.
#'
#' @return Description of return value.
#'   For vectors, include type: "Numeric vector of length n"
#'
#' @examples
#' process_data(mtcars, "cyl")
#' process_data(mtcars, "cyl", na.rm = TRUE)
#'
#' @export
process_data <- function(x, group, na.rm = FALSE) {
  # Code
}
```

### Inline Comments
```r
# Use for: explain WHY (not WHAT)
# Convert to lowercase for consistency (tidyverse standard)
# Use set.seed for reproducibility in tests

# Avoid: explain obvious WHAT
# x <- x + 1  # Add 1 to x
```

## Package Imports

### Explicit Imports
```r
# Use explicit imports in production code
# Avoid: library() in functions (adds to search path)

# GOOD: roxygen2 @importFrom
#' @importFrom dplyr filter mutate summarize
#' @importFrom purrr map_dbl

# Or explicit calls in code
df <- dplyr::filter(df, condition)
result <- purrr::map_dbl(x, mean)
```

### Namespace Conflicts
```r
# Explicitly qualify conflicting functions
df <- dplyr::filter(df, x > 0)
df <- base::filter(df, x)  # If base filter needed
```

## Code Quality Rules

| Rule | Rationale |
|------|-----------|
| Max line length 80 | Readability |
| No trailing whitespace | Diff noise |
| One statement per line | Clarity |
| No more than one assignment per line | Debugging |
| Avoid nested conditionals > 3 | Complexity |