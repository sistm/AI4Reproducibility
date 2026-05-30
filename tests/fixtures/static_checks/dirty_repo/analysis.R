# Bad practice fixture
rm(list = ls())
setwd("/Users/researcher/myproject")

install.packages("ggplot2")
library(ggplot2)

attach(mtcars)

data <- readRDS("/home/me/data.rds")
result <- eval(parse(text = "1+1"))
system("rm -rf /tmp/old")

api_key = "sk-1234567890abcdef1234567890"
