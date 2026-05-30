# Main analysis script.
library(stats)

source(file.path("R", "helpers.R"))

results <- run_analysis()
saveRDS(results, file.path("outputs", "results.rds"))
