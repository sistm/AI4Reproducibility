# Analysis helpers sourced by main.R.

# Run the primary analysis pipeline and return results.
run_analysis <- function() {
  set.seed(42)
  x <- rnorm(100)
  list(mean = mean(x), sd = sd(x))
}
