# Security Review for R Code

## Critical: Any Dynamic Code Execution

### eval() and parse()
```r
# DANGER: Arbitrary code execution
user_input <- "system('rm -rf /')"
eval(parse(text = user_input))

# DANGER: User-controlled expressions
expr <- readline("Enter expression: ")
eval(parse(text = expr))

# SAFE: Controlled evaluation
# If absolutely necessary, use sandboxed environment
sandbox <- new.env()
sandbox$allowed_func <- function(x) x + 1
eval(quote(allowed_func(1)), sandbox)  # Only has access to sandbox

# SAFER: Avoid eval, use proper parsing
# Instead of eval(parse(text = formula)), use:
# formula(class ~ var1 + var2)  # Constructs formula object
```

### get() and do.call()
```r
# DANGER: Dynamic function call from user input
func_name <- readline("Function: ")  # e.g., "system"
get(func_name)("ls")

# SAFER: Whitelist allowed functions
allowed_funcs <- c("mean", "sum", "sd")
func_name <- match.arg(func_name, allowed_funcs)
get(func_name)(data)
```

## Command Injection

### system() and shell.exec()
```r
# DANGER: Unsanitized input in system call
filename <- readline("Filename: ")
system(paste("cat", filename))  # Could be "; rm -rf /"

# DANGER: Using shell = TRUE
system("ls", intern = TRUE)  # Uses shell - command injection risk

# SAFE: Avoid system() with user input
# Use R's file operations instead
readLines(filename)  # Read file contents safely
file.info(filename)  # Get file info safely

# If system call required, sanitize rigorously
safe_filename <- gsub("[^a-zA-Z0-9./_-]", "", filename)
system(paste("cat", safe_filename))
# BETTER: Use whitelist approach
```

### download.file()
```r
# DANGER: Arbitrary URL
url <- readline("URL: ")
download.file(url, destfile = "output")

# Could download malicious content or exfiltrate data
# Also: default method = "auto" on Windows uses shell injection

# SAFER: Whitelist allowed URLs
allowed_domains <- c("data.example.com", "trusted.cdn.org")
url <- parse_url(url)
stopifnot(url$hostname %in% allowed_domains)
download.file(url, destfile = "output", method = "libcurl")

# Verify checksums
library(tools)
verify_checksum <- function(file, expected_hash) {
  actual_hash <- md5sum(file)
  stopifnot(actual_hash == expected_hash)
}
```

## Path Traversal

### File Operations
```r
# DANGER: Path traversal
filename <- readline("File: ")  # Could be "../../etc/passwd"
readLines(filename)

# SAFE: Validate and restrict paths
normalize_path <- function(path, base_dir = "data/") {
  # Remove any path traversal
  cleaned <- gsub("\\.\\.", "", path)
  # Ensure relative to base
  full_path <- file.path(base_dir, cleaned)
  # Verify it's still within base
  stopifnot(grepl(paste0("^", normalizePath(base_dir)), normalizePath(full_path)))
  full_path
}
readLines(normalize_path(filename))
```

### write operations
```r
# DANGER: Overwrite arbitrary files
output_file <- readline("Output: ")
writeLines(data, output_file)

# SAFE: Restrict to allowed directory
output_dir <- "output/"
safe_path <- function(filename) {
  path <- file.path(output_dir, filename)
  stopifnot(dirname(path) == normalizePath(output_dir))
  path
}
writeLines(data, safe_path(filename))
```

## Credential Handling

### Hardcoded Secrets
```r
# DANGER: Secrets in code
api_key <- "sk-1234567890abcdef"
password <- "hunter2"

# SAFE: Use environment variables
api_key <- Sys.getenv("API_KEY")
password <- Sys.getenv("DATABASE_PASSWORD")

# SAFE: Use secret management services
# AWS Secrets Manager, HashiCorp Vault, etc.

# SAFE: Use .Renviron (add to .gitignore)
# API_KEY=xxxxx
# In code: Sys.getenv("API_KEY")

# SAFE: Use keyring package
library(keyring)
api_key <- key_get("my_service", "api_key")
```

### Logging Secrets
```r
# DANGER: Logging sensitive data
log_msg <- paste("API response:", response)
# Or
cat("Password used:", password)

# SAFE: Redact sensitive fields
log_response <- response
log_response$password <- "***REDACTED***"
log_info(log_response)

# SAFE: Use conditional logging
log_debug <- function(msg, level = "DEBUG") {
  if (Sys.getenv("DEBUG") == "TRUE") {
    message(paste("[", level, "]", msg))
  }
}
```

## Unsafe Package Usage

### readRDS with Untrusted Data
```r
# DANGER: Deserializing untrusted objects
obj <- readRDS(untrusted_file)
# Can execute arbitrary code via special S3 classes

# SAFE: Validate before loading
validate_rds <- function(file) {
  # Check file header
  header <- readBin(file, "raw", 6)
  expected <- as.raw(c(0x1f, 0x8b, 0x08))  # RDS is gzipped
  # Use only for locally created, trusted RDS files
  # Consider alternative formats for untrusted data
}
```

### load() and source()
```r
# DANGER: Loading untrusted .RData files
load(untrusted_file)
# Can restore malicious objects or overwrite existing ones

# SAFE: Use .RData only from trusted sources
# Prefer readRDS for single objects

# DANGER: source() with untrusted file
source(untrusted_file)
# Executes arbitrary R code

# SAFE: Only source from trusted, version-controlled files
```

### External Package Risks
```r
# Check package for known vulnerabilities
# Use devtools::check() for local packages
# Review package source for:
# - eval() calls
# - system() calls  
# - file operations with user input
# - network requests

# Prefer vetted, well-maintained packages
# Avoid: obscure packages, unmaintained packages
```

## Input Validation

### Validate All External Input
```r
validate_input <- function(x, type = "numeric", ...) {
  switch(type,
    numeric = {
      stopifnot(is.numeric(x), !is.na(x), x > 0, ...)
    },
    character = {
      stopifnot(is.character(x), nchar(x) > 0, ...)
    },
    factor = {
      stopifnot(is.factor(x), x %in% allowed_levels, ...)
    }
  )
  x
}

# Use early returns for validation
process_input <- function(raw_input) {
  if (!is.null(raw_input)) {
    input <- validate_input(raw_input, type = "numeric", min = 0)
  }
  # Continue processing...
}
```

## Network Security

### HTTPS Only
```r
# DANGER: HTTP endpoint
url <- "http://api.example.com/data"

# SAFE: HTTPS only
url <- "https://api.example.com/data"

# Verify certificates
httr::GET(url, httr::config(ssl_verifyhost = 2))
```

### API Keys in Requests
```r
# DANGER: Exposing key in URL
GET("https://api.example.com?key=MY_SECRET_KEY")

# SAFE: Use headers
GET("https://api.example.com/data",
    add_headers(Authorization = paste("Bearer", Sys.getenv("API_KEY"))))
```

## Summary: Security Red Flags

| Pattern | Severity | Risk |
|---------|----------|------|
| eval(parse(...)) | Critical | Arbitrary code execution |
| system(user_input) | Critical | Command injection |
| download.file(url) | Critical | Arbitrary network access |
| readRDS(untrusted) | High | Object deserialization attack |
| source(untrusted) | High | Code execution |
| password in code | Critical | Credential exposure |
| file operations without validation | High | Path traversal |

## Security Checklist

- [ ] No eval(), parse(), system() with user input
- [ ] No hardcoded credentials
- [ ] File operations validate paths
- [ ] External URLs use HTTPS
- [ ] Input validation on all user data
- [ ] Secrets from environment, not code
- [ ] Logging does not expose sensitive data