# Testing Guide for R Code

## Testing Framework: testthat

### Setup
```r
# Install
install.packages("testthat")

# Structure
tests/
├── testthat/
│   ├── test-helper.R      # Test fixtures
│   ├── test-utils.R       # Helper functions
│   ├── test-main.R       # Main tests
```

### Basic Test Structure
```r
library(testthat)

test_that("function does expected thing", {
  result <- my_function(input)
  expect_equal(result, expected_output)
})

test_that("function handles errors", {
  expect_error(my_function(invalid_input))
  expect_error(my_function(NULL), "must be numeric")
})
```

## Expectation Functions

### Equality
```r
# For exact equality
expect_equal(actual, expected)
expect_equal(actual, expected, tolerance = 1e-6)

# For approximate equality  
expect_equal(0.1 + 0.2, 0.3, tolerance = 1e-10)

# For objects (not values)
expect_identical(actual, expected)  # Same object, class, attributes

# For factors
expect_equal(levels(result), c("a", "b", "c"))
```

### Type and Class
```r
expect_type(x, "double")
expect_s3_class(x, "data.frame")
expect_s4_class(x, "lm")
expect_is(x, "numeric")
```

### Structure
```r
expect_length(x, 10)
expect_named(x, c("a", "b", "c"))
expect_true(nrow(df) > 0)
expect_false(is.null(result))
```

### Conditions
```r
expect_error(f())
expect_warning(f())
expect_message(f())

# Or specific messages
expect_error(f(), "must be numeric")
```

## Unit Testing Functions

### Pure Functions
```r
# Test deterministic transformations
test_that("normalize scales data correctly", {
  df <- data.frame(x = c(0, 50, 100))
  result <- normalize(df$x, method = "minmax")
  expect_equal(min(result), 0)
  expect_equal(max(result), 1)
})
```

### Edge Cases
```r
test_that("function handles edge cases", {
  # Empty input
  expect_equal(my_func(integer(0)), numeric(0))
  
  # NA values
  expect_equal(my_func(c(1, NA, 3)), c(2, NA, 4))
  
  # Single element
  expect_equal(my_func(5), 10)
  
  # All same values
  expect_equal(my_func(c(1, 1, 1)), c(2, 2, 2))
})
```

### Invalid Inputs
```r
test_that("function rejects invalid inputs", {
  # Wrong type
  expect_error(my_func("string"))
  
  # Wrong length
  expect_error(my_func(1:10), "must have length 3")
  
  # Out of range
  expect_error(my_func(-1), "must be positive")
})
```

## Statistical Test Validation

### Test Statistics
```r
test_that("t-test produces correct statistic", {
  set.seed(42)
  x <- rnorm(30, mean = 1)
  y <- rnorm(30, mean = 0)
  
  result <- t.test(x, y)
  
  expect_equal(result$statistic, -3.47, tolerance = 0.1)
  expect_equal(result$p.value, 0.001, tolerance = 0.001)
})
```

### Model Output
```r
test_that("linear model produces expected coefficients", {
  data <- data.frame(x = 1:10, y = 2 * (1:10) + 3 + rnorm(10, 0, 1))
  model <- lm(y ~ x, data)
  
  # Check coefficient exists and has reasonable value
  expect_true("x" %in% names(coef(model)))
  expect_gt(coef(model)["x"], 1.5)  # Should be close to 2
  expect_lt(coef(model)["x"], 2.5)
})
```

### Statistical Equality
```r
# For floating-point results, use tolerance
test_that("bootstrapped CI has correct coverage", {
  set.seed(42)
  boot_result <- bootstrap_ci(data, R = 1000)
  
  # Coverage should be approximately 95%
  expect_gt(boot_result$coverage, 0.93)
  expect_lt(boot_result$coverage, 0.97)
})
```

## Snapshot Testing

### Use Cases
```r
# Complex outputs that change infrequently
# Visualizations
# Large data structures

library(testthat)
library(golden)
```

### Implementation
```r
# Create snapshot
test_that("plot matches snapshot", {
  p <- create_plot(data)
  expect_snapshot(p)  # Creates reference in tests/snapshots/
})

# On CI, compare against stored snapshots
# Update with testthat::snapshot_accept() when changes are intentional
```

## Integration Testing

### Pipeline Tests
```r
test_that("full pipeline produces correct output", {
  # Set up temp directory
  temp_dir <- tempfile()
  dir.create(temp_dir)
  on.exit(unlink(temp_dir, recursive = TRUE))
  
  # Create test data
  write_csv(test_data, file.path(temp_dir, "input.csv"))
  
  # Run pipeline
  run_pipeline(input_dir = temp_dir, output_dir = temp_dir)
  
  # Check output
  result <- read_csv(file.path(temp_dir, "output.csv"))
  expect_equal(nrow(result), 100)
  expect_equal(names(result), c("id", "value", "prediction"))
})
```

### Database/External Services
```r
test_that("database query returns expected results", {
  skip_if_no_db()  # Skip if no test DB
  
  result <- query_test_db()
  expect_equal(nrow(result), expected_rows)
})
```

## Test Organization

### Describe Blocks
```r
describe("calculate_stats()", {
  it("returns mean and sd", {
    result <- calculate_stats(c(1, 2, 3))
    expect_equal(result$mean, 2)
    expect_equal(result$sd, 1)
  })
  
  it("handles NA values", {
    result <- calculate_stats(c(1, NA, 3))
    expect_true(is.na(result$mean))
  })
})
```

### Fixtures
```r
# In tests/testthat/helper.R
test_that("fixture setup", {
  # Set up common test data
  data <- data.frame(
    x = 1:100,
    group = rep(c("A", "B"), 50)
  )
  assign("test_data", data, envir = .GlobalEnv)
})

teardown({
  # Clean up
  rm("test_data", envir = .GlobalEnv)
})
```

## Test Coverage

### Measuring Coverage
```r
library(coverage)

# Run tests with coverage
cov <- coverage::covr::package()

# Minimum coverage thresholds
# Production: > 80%
# Critical paths: > 95%
```

### What to Test
```r
# Priority 1: Critical functions (statistical calculations, transformations)
# Priority 2: Public API
# Priority 3: Edge cases and error handling
# Avoid: Testing trivial wrappers, plot functions without visual diff
```

## CI Integration

### GitHub Actions
```r
# .github/workflows/R.yml
name: R Tests

on: [push, pull_request]

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      - uses: r-lib/actions/setup-r@v2
      - name: Install dependencies
        run: |
          install.packages(c("testthat", "covr"))
          devtools::install_deps(dependencies = TRUE)
      - name: Run tests
        run: devtools::test()
      - name: Coverage
        run: covr::codecov()
```

## Testing Checklist

- [ ] All public functions tested
- [ ] Edge cases covered (empty, NA, zero, one element)
- [ ] Error conditions tested
- [ ] Statistical outputs validated against known values
- [ ] Integration tests cover full pipeline
- [ ] Snapshot tests for complex outputs
- [ ] Tests run in CI
- [ ] Coverage tracked