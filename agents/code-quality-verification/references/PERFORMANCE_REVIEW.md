# Performance Review for R Code

## Vectorization vs Loops

### Avoid: Growing Vectors
```r
# BAD: O(n²) complexity, reallocates memory each iteration
result <- c()
for (i in 1:10000) {
  result <- c(result, i * 2)
}

# GOOD: Pre-allocate or use vectorized operations
result <- rep(NA_real_, 10000)
for (i in 1:10000) {
  result[i] <- i * 2
}

# BEST: Vectorized
result <- (1:10000) * 2
```

### Avoid: Sequential Apply with Side Effects
```r
# BAD: for loop with minimal benefit over apply
for (i in seq_along(df$col)) {
  df$new_col[i] <- some_function(df$col[i])
}

# GOOD: sapply/vapply for transformations
df$new_col <- sapply(df$col, some_function)

# BETTER: Vectorized if possible
df$new_col <- some_function(df$col)
```

### Use: purrr for Type-Safe Iteration
```r
library(purrr)
# Map returns list
result_list <- map(df, function(x) mean(x, na.rm = TRUE))

# map_dbl returns double vector
result_dbl <- map_dbl(df, ~ mean(.x, na.rm = TRUE))

# map2 for two inputs
result <- map2(df$x, df$y, ~ .x + .y)

# safely for error handling
safe_result <- safely(some_function, otherwise = NA)(input)
```

## Memory Management

### Avoid: Unnecessary Copies
```r
# BAD: Creates copy on assignment
df <- data.frame(x = 1:1000)
df_copy <- df  # Still points to same data until modified
df_copy$y <- 1  # Now creates actual copy

# GOOD: Explicit copy when needed
df_copy <- data.frame(x = df$x, y = 1)

# In functions: use data.table to modify by reference
library(data.table)
dt <- data.table(x = 1:1000)
setDT(dt)  # Modifies in-place, no copy

# Use copy-on-write for safety, avoid premature optimization
```

### Avoid: Materializing Lazy Operations
```r
# BAD: Forces evaluation multiple times
sum(df$col)  # Materializes
mean(df$col)  # Materializes again

# GOOD: Store intermediate result
col <- df$col
sum(col)
mean(col)
```

### Memory Profiling
```r
library(lobstr)
obj_size(df)  # Size of single object
ref()         # Reference structure

library(profvis)
profvis({
  # Code to profile
})
```

## data.table vs dplyr Tradeoffs

### When to Use data.table
- Large datasets (> 1M rows)
- Complex grouped operations
- Need for in-place modification
- Key-based joins

### When to Use dplyr
- Readable pipelines for data transformation
- tidyselect for column selection
- Complex mutate operations
- Integration with tidyr, ggplot2

### Performance Comparison
```r
library(data.table)
library(dplyr)

# data.table: ~0.1s for 10M rows grouped operation
dt <- data.table::as.data.table(big_df)
result <- dt[, .(sum = sum(x)), by = group]

# dplyr: ~1s for same operation
result <- big_df %>% 
  group_by(group) %>% 
  summarize(sum = sum(x))

# Hybrid approach: dtplyr for translation
library(dtplyr)
result <- lazy_df %>% 
  group_by(group) %>% 
  summarize(sum = sum(x)) %>% 
  collect()  # Execute with data.table
```

## Parallelization

### When to Parallelize
- Independent operations on data chunks
- CPU-bound statistical computations
- Repeated simulations

### Parallel Backends
```r
# Parallel with future
library(future)
plan(multisession)  # Use multiple R sessions

library(furrr)
result <- future_map_dbl(1:100, ~ slow_function(.x))

# Parallel with parallel package
library(parallel)
cl <- makeCluster(4)
result <- parLapply(cl, 1:100, slow_function)
stopCluster(cl)

# Parallel with foreach
library(foreach)
library(doParallel)
registerDoParallel(4)
result <- foreach(i = 1:100) %dopar% slow_function(i)
```

### Parallelization Overhead
- Communication cost between workers
- Not worthwhile for fast operations
- Memory duplication across workers

## Profiling Tools

### profvis
```r
library(profvis)
profvis({
  # Wrap code to profile
  result <- lapply(1:1000, function(i) {
    data <- rnorm(10000)
    fit <- lm(data ~ 1)
    coef(fit)
  })
})

# Save to file for interactive viewing
profvis_output <- profvis({
  # code
})
htmltools::save_html(profvis_output, "profile.html")
```

### microbenchmark
```r
library(microbenchmark)
result <- microbenchmark(
  vectorized = sum(1:10000),
  loop = {
    total <- 0
    for (i in 1:10000) total <- total + i
    total
  },
  times = 100
)
print(result)
# Shows median, mean, and distribution
```

### System Time
```r
start <- Sys.time()
# code
end <- Sys.time()
elapsed <- end - start  # Returns difftime object

# More precise
start <- proc.time()
# code
proc.time() - start  # User, system, and elapsed time
```

## Common Performance Issues

### Issue: Repeated Column Access
```r
# BAD: Accesses column multiple times
mean(df$col, na.rm = TRUE)
sd(df$col, na.rm = TRUE)
median(df$col, na.rm = TRUE)

# GOOD: Store once
col <- df$col
c(mean = mean(col, na.rm = TRUE), 
  sd = sd(col, na.rm = TRUE),
  median = median(col, na.rm = TRUE))
```

### Issue: Inefficient String Operations
```r
# BAD: paste in loop
for (i in 1:1000) {
  strings <- c(strings, paste0("item_", i))
}

# GOOD: paste0 vectorized
strings <- paste0("item_", 1:1000)

# BETTER: sprintf for complex patterns
strings <- sprintf("item_%04d", 1:1000)
```

### Issue: Non-Vectorized Conditionals
```r
# BAD: ifelse creates full copy
result <- ifelse(df$x > 0, df$x, 0)

# GOOD: Use vectorized replacement
result <- df$x
result[result <= 0] <- 0

# Or pmax/pmin
result <- pmax(df$x, 0)
```

## Optimization Decision Tree

1. **Profile first** - Don't optimize without evidence
2. **Algorithm > Implementation** - Better algorithm beats micro-optimizations
3. **Vectorize loops** - Built-in functions use optimized C code
4. **Reduce memory copies** - data.table or in-place modifications
5. **Parallelize** - Only when operations are independent and substantial
6. **Cache** - Memoize expensive computations

## Performance Budget

| Operation | Target |
|-----------|--------|
| 10K row group/summarize | < 100ms |
| 1M row join | < 1s |
| 10M row aggregate | < 10s |
| Statistical model fit | Depends on complexity |

Exceeding budgets requires optimization or sampling.