#!/usr/bin/env Rscript
# Peak Differential Analysis for ATAC-seq / ChIP-seq
# nf-core/atacseq or nf-core/chipseq 출력 → DESeq2 기반 차등 접근성/결합 분석
#
# Usage:
#   Rscript peak_analysis.R \
#     --counts_matrix consensus_peaks_featurecounts.txt \
#     --output_dir results/analysis/ \
#     [--peaks_bed consensus_peaks.bed] \
#     [--padj_threshold 0.05] [--fc_threshold 1.5]

suppressPackageStartupMessages({
  library(optparse)
  library(jsonlite)
})

# ── Argument Parsing ──────────────────────────────
option_list <- list(
  make_option("--counts_matrix", type = "character",
              help = "FeatureCounts output (read counts per peak region)"),
  make_option("--peaks_bed", type = "character", default = NULL,
              help = "Consensus peaks BED file (optional, for annotation)"),
  make_option("--output_dir", type = "character",
              help = "Output directory for results"),
  make_option("--padj_threshold", type = "double", default = 0.05,
              help = "Adjusted p-value threshold [default: 0.05]"),
  make_option("--fc_threshold", type = "double", default = 1.5,
              help = "Log2 fold-change threshold [default: 1.5]")
)

parser <- OptionParser(option_list = option_list,
                       description = "Differential peak analysis (ATAC/ChIP)")
opt <- parse_args(parser)

if (is.null(opt$counts_matrix) || is.null(opt$output_dir)) {
  print_help(parser)
  quit(status = 1)
}

dir.create(opt$output_dir, recursive = TRUE, showWarnings = FALSE)

# ── Load DESeq2 ───────────────────────────────────
tryCatch({
  suppressPackageStartupMessages({
    library(DESeq2)
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

# ── Load Counts ───────────────────────────────────
cat("Loading count matrix:", opt$counts_matrix, "\n")

# featureCounts format has metadata columns before count columns
raw <- read.delim(opt$counts_matrix, comment.char = "#", check.names = FALSE)

# Identify count columns (skip Geneid, Chr, Start, End, Strand, Length)
meta_cols <- c("Geneid", "Chr", "Start", "End", "Strand", "Length")
count_cols <- setdiff(colnames(raw), meta_cols)

# If no known meta columns, assume first column is ID, rest are counts
if (length(count_cols) == ncol(raw)) {
  counts <- as.matrix(raw[, -1])
  rownames(counts) <- raw[, 1]
} else {
  counts <- as.matrix(raw[, count_cols])
  rownames(counts) <- raw$Geneid
}

counts <- round(counts)
counts[counts < 0] <- 0

cat("Loaded", nrow(counts), "peaks x", ncol(counts), "samples\n")

# ── Sample Info ───────────────────────────────────
sample_info <- data.frame(
  sample = colnames(counts),
  condition = rep("group1", ncol(counts)),
  stringsAsFactors = FALSE
)
if (ncol(counts) >= 2) {
  half <- ceiling(ncol(counts) / 2)
  sample_info$condition[1:half] <- "group1"
  sample_info$condition[(half + 1):ncol(counts)] <- "group2"
}
rownames(sample_info) <- sample_info$sample

# ── DESeq2 Analysis ──────────────────────────────
cat("Running DESeq2 on peak counts...\n")
dds <- DESeqDataSetFromMatrix(
  countData = counts,
  colData = sample_info,
  design = ~ condition
)

keep <- rowSums(counts(dds)) >= 5
dds <- dds[keep, ]

dds <- DESeq(dds)
res <- results(dds, alpha = opt$padj_threshold)

# ── Results ───────────────────────────────────────
res_df <- as.data.frame(res)
res_df$peak <- rownames(res_df)
res_df <- res_df[order(res_df$padj, na.last = TRUE), ]

sig <- res_df[!is.na(res_df$padj) &
              res_df$padj < opt$padj_threshold &
              abs(res_df$log2FoldChange) > log2(opt$fc_threshold), ]

write.csv(res_df, file.path(opt$output_dir, "diff_peaks.csv"),
          row.names = FALSE)

cat("Total peaks tested:", sum(!is.na(res_df$padj)), "\n")
cat("Significant peaks:", nrow(sig), "\n")

# ── Peak Annotation (if BED file provided) ───────
if (!is.null(opt$peaks_bed) && file.exists(opt$peaks_bed)) {
  tryCatch({
    peaks <- read.delim(opt$peaks_bed, header = FALSE,
                        col.names = c("chr", "start", "end", "name", "score", "strand"))
    # Merge with significant peaks
    if (nrow(sig) > 0 && "peak" %in% colnames(sig)) {
      annotated <- merge(sig, peaks, by.x = "peak", by.y = "name", all.x = TRUE)
      write.csv(annotated, file.path(opt$output_dir, "peak_annotation.csv"),
                row.names = FALSE)
    }
  }, error = function(e) cat("Peak annotation error:", e$message, "\n"))
}

# ── Volcano Plot ──────────────────────────────────
tryCatch({
  pdf(file.path(opt$output_dir, "volcano_plot.pdf"), width = 8, height = 6)
  plot_df <- res_df[!is.na(res_df$padj), ]
  plot_df$significant <- abs(plot_df$log2FoldChange) > log2(opt$fc_threshold) &
                         plot_df$padj < opt$padj_threshold
  p <- ggplot(plot_df, aes(x = log2FoldChange, y = -log10(padj),
                           color = significant)) +
    geom_point(alpha = 0.5, size = 1) +
    scale_color_manual(values = c("grey60", "red3")) +
    theme_minimal() +
    labs(title = "Differential Peaks Volcano Plot",
         x = "Log2 Fold Change", y = "-Log10 Adjusted P-value") +
    theme(legend.position = "none")
  print(p)
  dev.off()
}, error = function(e) cat("Volcano plot error:", e$message, "\n"))

# ── PCA Plot ──────────────────────────────────────
tryCatch({
  vsd <- vst(dds, blind = TRUE)
  pdf(file.path(opt$output_dir, "pca_plot.pdf"), width = 7, height = 5)
  pca_data <- plotPCA(vsd, intgroup = "condition", returnData = TRUE)
  pct_var <- round(100 * attr(pca_data, "percentVar"))
  p <- ggplot(pca_data, aes(x = PC1, y = PC2, color = condition)) +
    geom_point(size = 3) + theme_minimal() +
    labs(title = "PCA - Peak Counts",
         x = paste0("PC1 (", pct_var[1], "%)"),
         y = paste0("PC2 (", pct_var[2], "%)"))
  print(p)
  dev.off()
}, error = function(e) cat("PCA plot error:", e$message, "\n"))

# ── Summary JSON ──────────────────────────────────
more_accessible <- nrow(sig[sig$log2FoldChange > 0, ])
less_accessible <- nrow(sig[sig$log2FoldChange < 0, ])

summary <- list(
  success = TRUE,
  total_peaks = nrow(res_df),
  peaks_tested = sum(!is.na(res_df$padj)),
  significant_peaks = nrow(sig),
  more_accessible = more_accessible,
  less_accessible = less_accessible,
  fc_threshold = opt$fc_threshold,
  padj_threshold = opt$padj_threshold,
  samples = ncol(counts)
)

write(toJSON(summary, auto_unbox = TRUE, pretty = TRUE),
      file.path(opt$output_dir, "summary.json"))

cat("Analysis complete. Results in:", opt$output_dir, "\n")
