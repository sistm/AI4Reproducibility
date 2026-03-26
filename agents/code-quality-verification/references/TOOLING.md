# R Code Quality Tooling

## Linting and Style

### lintr
```r
# Installation
install.packages("lintr")

# Run on file
lintr::lint("script.R")

# Run on package
lintr::lint_package("mypackage")

# Common lints
# - syntax errors
# - unused imports/variables
# - style violations

# Configuration .lintr
linters: with_defaults(
  trailing_blank_lines_linter = NULL,
  object_usage_linter = NULL
)
exclusions:
  inst/doc: 1
  tests: 2
```

### styler
```r
# Installation
install.packages("styler")

# Style file in place
styler::style_file("script.R")

# Style active file in RStudio
styler::style_active_file()

# Style package
styler::style_pkg()

# Addins: "Style active file", "Style selection"
```

### languageserver (IDE Support)
```r
# Installation - enables R language server
install.packages("languageserver")

# Provides:
# - Auto-completion
# - Diagnostics (lintr integration)
# - Go to definition
# - Find references
# - Outline/view functions
```

## Environment Management

### renv
```r
# Installation
install.packages("renv")

# Initialize in project
renv::init()

# Snapshot current state
renv::snapshot()

# Restore from lockfile
renv::restore()

# Check for issues
renv::healthcheck()

# Update specific package
renv::update("dplyr")
```

### Project Initialization
```r
# Create new RStudio project with renv
# File > New Project > New Directory > R Package
# Check "Use renv with this project"

# Or manually
renv::init()

# Creates:
# - renv/activate.R
# - renv.lock
# - .Rprofile
```

## Profiling Tools

### profvis
```r
# Installation
install.packages("profvis")

# Interactive profiling
profvis({
  # Code to profile
  result <- lapply(1:1000, function(i) {
    rnorm(1000)
  })
})

# Save to HTML for viewing
library(htmltools)
p <- profvis({
  # code
})
save_html(p, "profile.html")

# From command line
Rscript -e 'profvis::profvis(source("script.R"))'
```

### microbenchmark
```r
# Installation
install.packages("microbenchmark")

# Compare operations
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

# Result shows:
# - min, median, mean, max
# - n = number of iterations
```

### lobstr (Memory)
```r
# Installation
install.packages("lobstr")

# Object size
lobstr::obj_size(df)

# Reference structure
lobstr::ref()

# Memory tree
lobstr::mem_tree(obj)

# Example: finding memory leaks
x <- list()
for (i in 1:100) {
  x[[i]] <- data.frame(matrix(rnorm(1000), 100, 10))
}
lobstr::obj_size(x)
```

## Development Tools

### devtools
```r
# Installation
install.packages("devtools")

# Common functions
devtools::load_all()     # Load package
devtools::test()         # Run tests
devtools::check()        # R CMD check
devtools::build()        # Build package
devtools::install()      # Install package

# Check package
devtools::check(vignettes = FALSE, args = c("--no-manual"))

# Interactive development
devtools::load_all()
# Edit source files, re-load with Cmd+Shift+L (RStudio)
```

### roxygen2 (Documentation)
```r
# Installation
install.packages("roxygen2")

# Add roxygen2 tags
#' Function description
#'
#' @param x Description
#' @return Description
#' @export
my_func <- function(x) { }

# Generate documentation
roxygen2::roxygenise()

# Or in devtools workflow
devtools::document()
```

### testthat
```r
# Installation
install.packages("testthat")

# Run tests
devtools::test()
# Or
testthat::test_dir("tests/")

# Specific test file
testthat::test_file("tests/testthat/test-example.R")
```

## CI/CD Integration

### GitHub Actions
```r
# .github/workflows/R.yml
on: [push, pull_request]

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      - uses: r-lib/actions/setup-r@v2
        with:
          r-version: '4.3'
      - name: Install dependencies
        run: |
          install.packages(c("devtools", "covr"))
          devtools::install_deps()
      - name: Run tests
        run: devtools::test(coverage = TRUE)
      - name: Test coverage
        run: covr::codecov()
```

### Docker
```r
# Dockerfile for R
FROM rocker/r-ver:4.3

# Install system dependencies
RUN apt-get update && apt-get install -y \
    libcurl4-openssl-dev \
    libssl-dev \
    && rm -rf /var/lib/apt/lists/*

# Copy project files
COPY . /project
WORKDIR /project

# Restore R packages
RUN Rscript -e 'renv::restore()'

# Run
CMD ["Rscript", "pipeline.R"]
```

## Static Analysis Tools

### goodpractice
```r
install.packages("goodpractice")
goodpractice::gp("path/to/package")
```

### cyclocomp
```r
install.packages("cyclocomp")
cyclocomp::cyclocomp_package("mypackage")
# Reports cyclomatic complexity of functions
```

### pkgcheck
```r
# R-universe or local
remotes::install_github("ropensci/pkgcheck")
pkgcheck::pkgcheck("mypackage")
```

## Editor Integration

### RStudio
```r
# Settings > Code > Editing
# - Tab size: 2
# - Insert spaces for tabs: checked
# - Auto-indent: checked

# Addins
# - RStudio Pkg Manager
# - Assign in place
# - Style selection
```

### VS Code (with R Extension)
```r
# Install R extension
# Add to settings.json:
{
  "r.rpath.linux": "/usr/bin/R",
  "r.lintr.linters": "with_defaults()",
  "editor.formatOnSave": true
}
```

## Tool Selection Matrix

| Purpose | Tool | Use Case |
|---------|------|----------|
| Linting | lintr | CI, IDE integration |
| Formatting | styler | Pre-commit, CI |
| Environment | renv | Project reproducibility |
| Profiling | profvis | Runtime analysis |
| Benchmarking | microbenchmark | Performance comparison |
| Memory | lobstr | Memory leaks, sizing |
| Testing | testthat | Unit tests |
| Documentation | roxygen2 | Package docs |
| CI | GitHub Actions | Automated checks |
| Container | Docker | Deployment |