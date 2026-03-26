# Static Analysis Rules for R Code

## Parse-Time Checks

### Syntax Errors
- Unbalanced parentheses, brackets, braces
- Missing commas in function calls
- Invalid operator usage
- Incomplete expressions

### Undefined References
- Variables not defined in any scope
- Functions not in loaded packages or defined locally
- Non-existent column references in data frame operations

## Lint-Style Issues

### Unused Objects
```r
# BAD: x defined but never used
x <- some_computation()
y <- other_computation()

# GOOD: Comment unused or remove
# x <- some_computation()  # TODO: use in future
y <- other_computation()
```

### Missing Semicolons
- Typically not required in R, but watch for accidental semicolon usage

### Line Length
- Lines > 80 characters reduce readability
- Break long statements across lines

## Semantic Analysis

### Dead Code Detection

```r
# Unreachable after return
f <- function(x) {
  return(x + 1)
  print("dead")  # Never executes
}

# Unreachable after stop
g <- function(x) {
  if (!is.numeric(x)) stop("must be numeric")
  print("reached")  # Reachable
  stop("always stops")
  print("never")  # Unreachable
}

# Unreachable after browser/debug
h <- function(x) {
  browser()
  print("debug stops here")  # Unreachable in non-interactive
}
```

### Unused Variables

```r
# Unused in function
compute_something <- function(data) {
  result <- sum(data$value)  # result unused
  return(data)  # returns input unchanged
}

# Unused loop variable
for (i in 1:10) {
  print(i)  # i used, OK
}
for (i in 1:10) {
  print("hello")  # i unused - declare as _ or remove
}
```

### Scope Leakage

```r
# Global assignment in function (discouraged)
leaky <- function() {
  global_var <<- "assigned"  # Modifies global scope
}

# Using global variable without declaration
f <- function() {
  return(hidden_global)  # Depends on external state
}
```

## Non-Standard Evaluation (NSE) Risks

### Tidyverse NSE
```r
# DANGER: Column name evaluated in context
df <- data.frame(x = 1:3, y = 4:6)
col_name <- "x"
df$col_name  # Returns NULL - uses literal "col_name"

# SAFER: Use .data or .env pronouns
library(dplyr)
df %>% filter(.data[[col_name]] > 1)

# SAFER: Use .env
df %>% filter(.env$threshold > 0)
```

### Lazy Evaluation Pitfalls
```r
# Delayed evaluation can cause surprising behavior
f <- function(x) {
  # x not evaluated until used
  if (FALSE) {
    stop("never called")  # Does not execute
  }
  x + 1  # Only evaluated if reached
}

# force() to evaluate immediately
g <- function(x) {
  force(x)  # Evaluates x now
  # ...
}
```

## Function Analysis

### Missing Return Values
```r
# Implicit return - last expression returned
add <- function(a, b) a + b  # OK - explicit

# Missing return in early exit
compute <- function(x) {
  if (x < 0) return(NULL)  # OK - explicit
  x * 2
}

# Confusion: print() returns NULL, not the value
bad <- function(x) {
  print(x * 2)  # Returns NULL implicitly
}
good <- function(x) {
  x * 2  # Returns value
}
```

### Argument Matching
```r
# Positional vs named
f <- function(a, b, c) NULL

f(1, 2, 3)           # All positional
f(a = 1, b = 2, c = 3)  # All named
f(1, b = 2, 3)       # Mixed - dangerous with defaults

# Partial matching (discouraged)
options(warnPartialMatchDollar = TRUE)  # Warn on partial match
df$x  # Partial match for $ - dangerous
df$xy  # Matches "xy" or "xyzz" if no exact match
```

## Package Analysis

### Masked Functions
```r
library(dplyr)
library(base)  # base::filter masked by dplyr

# Explicitly disambiguate
dplyr::filter(df, condition)
base::filter(df, condition)

# Check for masking
conflicts(detail = TRUE)
```

### Hidden Dependencies
```r
# Uses packages without explicit import
library(dplyr)  # Explicit
select(df, x)    # Uses dplyr::select

# Check: loaded but not imported
# Running code requires knowledge of what's loaded
```

## Complexity Metrics

### Cyclomatic Complexity
- Count decision points (if, for, while, &&, ||)
- Complexity > 10 indicates need for refactoring

### Nesting Depth
```r
# Deep nesting - hard to follow
if (a) {
  if (b) {
    if (c) {
      if (d) {
        # 4 levels deep
      }
    }
  }
}

# Better: early returns or guard clauses
f <- function(a, b, c, d) {
  if (!a) return(NULL)
  if (!b) return(NULL)
  if (!c) return(NULL)
  if (!d) return(NULL)
  # Main logic
}
```

## Type Inference Issues

### Implicit Coercion
```r
# Numeric to character
x <- c(1, 2, 3)
y <- c("a", "b", "c")
z <- c(x, y)  # All coerced to character

# Factor to numeric
f <- factor(c(1, 2, 3))
as.numeric(f)  # Returns codes 1,2,3 NOT 1,2,3!
as.numeric(as.character(f))  # Correct
```

### NA Propagation
```r
# NA in comparisons
NA > 3        # Returns NA (not TRUE/FALSE)
TRUE | NA     # Returns TRUE (short-circuit)
FALSE & NA    # Returns FALSE (short-circuit)

# Check for NA explicitly
is.na(x)
```

## Code Patterns

### Redundant Operations
```r
# Redundant factor conversion
as.factor(as.character(f))

# Redundant subsetting
df[which(df$x > 0), ]  # which() unnecessary
df[df$x > 0, ]         # Same result
```

### Inefficient Patterns
```r
# paste0 vs paste
paste0("a", "b")  # Faster than paste("a", "b")
paste("a", "b")   # Adds space by default

# Single-element vector indexing
x[1]           # Returns first element (or NA if empty)
x[[1]]         # Returns first element (error if not list)