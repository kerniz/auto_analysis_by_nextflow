#!/usr/bin/env Rscript
# DNA Methylation Analysis
# nf-core/methylseq 출력 → Bismark coverage 기반 메틸화 분석
#
# Usage:
#   Rscript methylation_analysis.R \
#     --coverage_file bismark_coverage.cov.gz \
#     --output_dir results/analysis/ \
#     [--min_coverage 10] [--diff_threshold 25]

suppressPackageStartupMessages({
  library(optparse)
  library(jsonlite)
})

# ── Argument Parsing ──────────────────────────────
option_list <- list(
  make_option("--coverage_file", type = "character",
              help = "Bismark coverage file (.cov or .cov.gz)"),
  make_option("--output_dir", type = "character",
              help = "Output directory for results"),
  make_option("--min_coverage", type = "integer", default = 10,
              help = "Minimum read coverage [default: 10]"),
  make_option("--diff_threshold", type = "double", default = 25,
              help = "Methylation difference threshold in percent [default: 25]")
)

parser <- OptionParser(option_list = option_list,
                       description = "DNA methylation analysis (nf-core/methylseq)")
opt <- parse_args(parser)

if (is.null(opt$coverage_file) || is.null(opt$output_dir)) {
  print_help(parser)
  quit(status = 1)
}

dir.create(opt$output_dir, recursive = TRUE, showWarnings = FALSE)

# ── Load ggplot2 ──────────────────────────────────
tryCatch({
  suppressPackageStartupMessages({
    library(ggplot2)
  })
}, error = function(e) {
  summary <- list(
    success = FALSE,
    error = paste("Required R package not available:", e$message)
  )
  write(toJSON(summary, auto_unbox = TRUE, pretty = TRUE),
        file.path(opt$output_dir, "summary.json"))
  quit(status = 1)
})

# ── Read Bismark Coverage File ───────────────────
cat("Reading coverage file:", opt$coverage_file, "\n")

tryCatch({
  # Bismark coverage format: chr, start, end, methylation%, count_meth, count_unmeth
  if (grepl("\\.gz$", opt$coverage_file)) {
    cov <- read.delim(gzfile(opt$coverage_file), header = FALSE,
                      stringsAsFactors = FALSE)
  } else {
    cov <- read.delim(opt$coverage_file, header = FALSE,
                      stringsAsFactors = FALSE)
  }

  colnames(cov) <- c("chr", "start", "end", "methylation_pct",
                      "count_methylated", "count_unmethylated")
}, error = function(e) {
  summary <- list(
    success = FALSE,
    error = paste("Failed to read coverage file:", e$message)
  )
  write(toJSON(summary, auto_unbox = TRUE, pretty = TRUE),
        file.path(opt$output_dir, "summary.json"))
  quit(status = 1)
})

# Calculate total coverage per CpG
cov$total_coverage <- cov$count_methylated + cov$count_unmethylated

cat("Loaded", nrow(cov), "CpG sites\n")

# ── Filter by Minimum Coverage ───────────────────
filtered <- cov[cov$total_coverage >= opt$min_coverage, ]
cat("After filtering (coverage >=", opt$min_coverage, "):",
    nrow(filtered), "CpG sites\n")

if (nrow(filtered) == 0) {
  summary <- list(
    success = TRUE,
    total_cpgs = nrow(cov),
    filtered_cpgs = 0,
    message = "No CpGs passed coverage filter"
  )
  write(toJSON(summary, auto_unbox = TRUE, pretty = TRUE),
        file.path(opt$output_dir, "summary.json"))
  cat("No CpGs passed coverage filter.\n")
  quit(status = 0)
}

# ── Global Methylation Statistics ────────────────
global_mean <- mean(filtered$methylation_pct)
global_median <- median(filtered$methylation_pct)
global_sd <- sd(filtered$methylation_pct)

cat("Global methylation: mean =", round(global_mean, 2),
    "%, median =", round(global_median, 2), "%\n")

# ── Identify Highly/Lowly Methylated Regions ─────
highly_methylated <- filtered[filtered$methylation_pct >= (100 - opt$diff_threshold), ]
lowly_methylated <- filtered[filtered$methylation_pct <= opt$diff_threshold, ]
intermediate <- filtered[filtered$methylation_pct > opt$diff_threshold &
                         filtered$methylation_pct < (100 - opt$diff_threshold), ]

cat("Highly methylated (>=", 100 - opt$diff_threshold, "%):",
    nrow(highly_methylated), "\n")
cat("Lowly methylated (<=", opt$diff_threshold, "%):",
    nrow(lowly_methylated), "\n")
cat("Intermediate:", nrow(intermediate), "\n")

# ── Chromosome-level Statistics ──────────────────
chrom_stats <- aggregate(
  methylation_pct ~ chr,
  data = filtered,
  FUN = function(x) c(mean = mean(x), median = median(x), n = length(x))
)
chrom_stats <- do.call(data.frame, chrom_stats)
colnames(chrom_stats) <- c("chromosome", "mean_methylation",
                           "median_methylation", "cpg_count")
chrom_stats <- chrom_stats[order(-chrom_stats$cpg_count), ]

# ── Write Output Files ───────────────────────────
methylation_stats <- data.frame(
  metric = c("total_cpgs", "filtered_cpgs",
             "global_mean_methylation", "global_median_methylation",
             "global_sd_methylation",
             "highly_methylated", "lowly_methylated", "intermediate"),
  value = c(nrow(cov), nrow(filtered),
            round(global_mean, 4), round(global_median, 4),
            round(global_sd, 4),
            nrow(highly_methylated), nrow(lowly_methylated),
            nrow(intermediate)),
  stringsAsFactors = FALSE
)
write.csv(methylation_stats,
          file.path(opt$output_dir, "methylation_stats.csv"),
          row.names = FALSE)

write.csv(chrom_stats,
          file.path(opt$output_dir, "chromosome_methylation.csv"),
          row.names = FALSE)

# ── Methylation Distribution Plot ────────────────
tryCatch({
  pdf(file.path(opt$output_dir, "methylation_distribution.pdf"),
      width = 8, height = 6)
  p <- ggplot(filtered, aes(x = methylation_pct)) +
    geom_histogram(bins = 50, fill = "steelblue", color = "white",
                   alpha = 0.8) +
    geom_vline(xintercept = global_mean, linetype = "dashed",
               color = "red", linewidth = 0.8) +
    theme_minimal() +
    labs(title = "CpG Methylation Distribution",
         x = "Methylation (%)", y = "Count",
         subtitle = paste("Mean:", round(global_mean, 1), "%")) +
    annotate("text", x = global_mean + 3, y = Inf,
             label = paste("Mean:", round(global_mean, 1), "%"),
             vjust = 2, hjust = 0, color = "red")
  print(p)
  dev.off()
}, error = function(e) cat("Distribution plot error:", e$message, "\n"))

# ── Chromosome Methylation Plot ──────────────────
tryCatch({
  # Order chromosomes naturally
  chrom_order <- c(paste0("chr", c(1:22, "X", "Y", "M")),
                   as.character(c(1:22, "X", "Y", "MT")))
  plot_chrom <- chrom_stats
  plot_chrom$chromosome <- factor(
    plot_chrom$chromosome,
    levels = intersect(chrom_order, plot_chrom$chromosome)
  )
  plot_chrom <- plot_chrom[!is.na(plot_chrom$chromosome), ]

  pdf(file.path(opt$output_dir, "chromosome_methylation.pdf"),
      width = 10, height = 6)
  p <- ggplot(plot_chrom, aes(x = chromosome, y = mean_methylation)) +
    geom_bar(stat = "identity", fill = "darkgreen", alpha = 0.7) +
    geom_errorbar(aes(ymin = mean_methylation - 2,
                      ymax = mean_methylation + 2),
                  width = 0.3, color = "grey40") +
    theme_minimal() +
    labs(title = "Mean Methylation by Chromosome",
         x = "Chromosome", y = "Mean Methylation (%)") +
    theme(axis.text.x = element_text(angle = 45, hjust = 1)) +
    ylim(0, 100)
  print(p)
  dev.off()
}, error = function(e) cat("Chromosome plot error:", e$message, "\n"))

# ── Summary JSON ──────────────────────────────────
summary <- list(
  success = TRUE,
  total_cpgs = nrow(cov),
  filtered_cpgs = nrow(filtered),
  min_coverage = opt$min_coverage,
  diff_threshold = opt$diff_threshold,
  global_methylation = list(
    mean = round(global_mean, 4),
    median = round(global_median, 4),
    sd = round(global_sd, 4)
  ),
  methylation_categories = list(
    highly_methylated = nrow(highly_methylated),
    lowly_methylated = nrow(lowly_methylated),
    intermediate = nrow(intermediate)
  ),
  chromosomes_analyzed = nrow(chrom_stats),
  top_chromosomes_by_cpg_count = head(
    setNames(as.list(chrom_stats$cpg_count),
             as.character(chrom_stats$chromosome)), 5
  )
)

write(toJSON(summary, auto_unbox = TRUE, pretty = TRUE),
      file.path(opt$output_dir, "summary.json"))

cat("Analysis complete. Results in:", opt$output_dir, "\n")
