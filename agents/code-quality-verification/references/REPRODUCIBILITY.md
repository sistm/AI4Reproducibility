# Reproducibility Guidelines for R Code

## Core Principle

Reproducible code produces identical results when executed in the same environment. Non-reproducible code is scientific fraud unless documented as exploratory.

## Random Seeds

### Required: Set Seed Before Stochastic Operations
```r
# BAD: No seed - different results each run
result <- rnorm(1000)
model <- randomForest(x, y)  # Random forest has internal randomness
boot_results <- bootstrap(data, 1000)

# GOOD: Set seed with documented rationale
set.seed(20240326)  # "Reproducible bootstrap for confidence intervals"
result <- rnorm(1000)
model <- randomForest(x, y, set.seed = 20240326)  # If supported
```

### Seed Placement
```r
# For operations that use multiple random numbers
set.seed(42)
# First stochastic operation
sim1 <- rnorm(100)

# If continuing same logical block, don't reset seed
# (adds more random draws, but still deterministic)
sim2 <- rnorm(100)

# Document why you chose specific seed
# If using multiple seeds for robustness, document each
```

### Functions with Hidden Randomness
```r
# randomForest, caret train, many ML packages
library(caret)
set.seed(42)
trainControl(method = "cv", seeds = 42)  # Explicit seed control

# bootstrap from boot package
library(boot)
boot(data, statistic, R = 1000, seed = 42)

# Parallel random number generation
library(furrr)
plan(multisession, workers = 4)
set.seed(42)  # Sets seed for all workers
```

## Environment Capture (renv)

### Project Initialization
```r
# Initialize renv in project root
renv::init()

# This creates:
# - renv/activate.R
# - renv.lock
# - .Rprofile
```

### Lockfile Management
```r
# Record current state
renv::snapshot()

# Restore from lockfile
renv::restore()

# Check for updates
renv::audit()

# Update specific package
renv::update("dplyr")
```

### Lockfile Best Practices
```
# Always commit renv.lock to version control
git add renv.lock
git commit -m "Lock package versions"

# Never edit renv.lock manually

# Test on clean environment before release
renv::isolated()  # Creates isolated library
```

### .Rprofile Structure
```r
# In project root .Rprofile
source("renv/activate.R")

# Optional: custom settings
options(repos = c(CRAN = "https://cloud.r-project.org"))
```

## Dependency Management

### Package Version Specification
```r
# In DESCRIPTION
Imports: 
    dplyr (>= 1.0.0),
    tidyr (>= 1.2.0),
    purrr (>= 0.3.4)

# Or in renv.lock, exact versions are recorded

# Check package versions installed
renv::healthcheck()
```

### External Dependencies
```r
# System dependencies (e.g., Java for rJava)
# Document in README
# For Docker, use rocker/r-ver:4.3 with apt-get install
```

## Deterministic Pipelines

### Common Non-Deterministic Operations
```r
# Hash-based operations
# Using digest package with stable salt
library(digest)
digest(object, salt = "fixed_salt")

# Factors - alphabetical ordering
# Explicitly set levels
df$category <- factor(df$category, levels = c("low", "medium", "high"))

# sort() is stable but document if relying on this
sorted <- sort(data, na.last = TRUE)  # Document na.last behavior
```

### Parallel Execution Order
```r
# BAD: Results depend on worker completion order
future_lapply(1:100, function(i) {
  compute_something(i)
})

# GOOD: Use indices in results
results <- future_lapply(1:100, function(i) {
  list(index = i, value = compute_something(i))
})
results <- do.call(rbind, lapply(results, `[`))
```

## Data Versioning

### Data Files
```r
# Track data hashes
library(tools)
md5sum("data/raw.csv")

# Or use data.hash in .gitignore
# Document data version in code or config
data_version <- "v2024-03-26"
read_csv(paste0("data/raw_", data_version, ".csv"))
```

### Database Connections
```r
# Document query snapshot or use versioned extracts
# If using live DB, note that results may change
# For reproducibility, use exported data with version

# Record session info
sessionInfo()
# Or
renv::snapshot()
```

## Working Directory

### Avoid Hardcoded Paths
```r
# BAD: Absolute paths
data <- read.csv("/home/user/project/data/file.csv")

# GOOD: Relative to project root
data <- read.csv("data/file.csv")

# Or use here package
library(here)
data <- read.csv(here("data", "raw", "file.csv"))

# For script-specific paths, use dirname of script
script_dir <- dirname(rstudioapi::getSourceEditorContext()$path)
# or
script_dir <- dirname(sys.frame(1)$ofile)  # If running from file
```

### Project Structure
```
project/
├── .Rprofile
├── renv/
├── data/
│   └── raw/
├── scripts/
├── output/
└── renv.lock
```

## Script vs Notebook Issues

### Reproducibility Differences
```r
# Script: Runs sequentially, clean state each run
source("pipeline.R")

# Notebook: State persists between cells
# May have hidden dependencies
# Cell order matters

# For notebooks, add setup cell
rm(list = ls())  # Clear environment
options(echo = FALSE)
set.seed(42)
```

### Execution Mode
```r
# Make notebooks reproducible by running all cells
# Document which cells can be re-run
# Use params for different configurations
params <- list(
  dataset = "train.csv",
  model = "glm"
)
```

## Session Information

### Record for Debugging
```r
# At end of script or in log
sink("session_info.txt")
sessionInfo()
sink()

# Or more detailed
renv::record()  # Creates DESCRIPTION-like record

# Package versions
renv::dependencies()  # Lists dependencies with versions
```

### CI/CD Integration
```r
# In CI pipeline
# Use docker with pinned R version and packages
# Run with re-producible flag
R --vanilla -e 'source("pipeline.R")'

# Or use renv::consent(provided = TRUE) for non-interactive
```

## Checklist

- [ ] All stochastic operations have documented set.seed()
- [ ] renv.lock is committed to version control
- [ ] No hardcoded absolute paths
- [ ] Data versions documented or checksums provided
- [ ] SessionInfo recorded for debugging
- [ ] Tested on clean R environment
- [ ] Pipeline runs in documented order