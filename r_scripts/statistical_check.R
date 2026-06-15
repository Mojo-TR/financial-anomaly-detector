library(anomalize)
library(tibble)
library(dplyr)
library(jsonlite)
library(readr)

args <- commandArgs(trailingOnly = TRUE)
if (length(args) == 0) {
  stop("Usage: Rscript statistical_check.R <path_to_csv>")
}

csv_path <- args[1]

df <- read_csv(csv_path, show_col_types = FALSE)

df <- df %>%
  mutate(date = as.Date(date)) %>%
  arrange(date)

result <- df %>%
  as_tibble() %>%
  time_decompose(daily_return, method = "stl", frequency = "auto", trend = "auto") %>%
  anomalize(remainder, method = "iqr") %>%
  time_recompose()

result <- result %>%
  mutate(
    confidence = round(abs(remainder) / (remainder_l2 - remainder_l1) * 0.5, 6)
  )

output <- as.data.frame(result) %>%
  mutate(
    date = as.character(date),
    is_anomaly = anomaly == "Yes"
  ) %>%
  select(date, is_anomaly, confidence)

cat(toJSON(output, auto_unbox = FALSE))
