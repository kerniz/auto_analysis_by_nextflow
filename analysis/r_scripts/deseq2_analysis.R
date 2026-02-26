#!/usr/bin/env Rscript
# DESeq2 Analysis for Bulk RNA-seq
# nf-core/rnaseq 출력 → DESeq2 분석
#
# Usage:
#   Rscript deseq2_analysis.R \
#     --counts_matrix salmon.merged.gene_counts.tsv \
#     --output_dir results/analysis/ \
#     [--fc_threshold 1.5] \
#     [--padj_threshold 0.05] \
#     [--top_n 50]

suppressPackageStartupMessages({
  library(optparse)
  library(jsonlite)
})

# ── Argument Parsing ──────────────────────────────
option_list <- list(
  make_option("--counts_matrix", type = "character",
              help = "Path to merged gene counts TSV from salmon"),
  make_option("--tx2gene", type = "character", default = NULL,
              help = "Path to tx2gene mapping file (optional)"),
  make_option("--sample_info", type = "character", default = NULL,
              help = "Path to sample metadata CSV (optional)"),
  make_option("--output_dir", type = "character",
              help = "Output directory for results"),
  make_option("--fc_threshold", type = "double", default = 1.5,
              help = "Log2 fold-change threshold [default: 1.5]"),
  make_option("--padj_threshold", type = "double", default = 0.05,
              help = "Adjusted p-value threshold [default: 0.05]"),
  make_option("--top_n", type = "integer", default = 50,
              help = "Number of top genes for heatmap [default: 50]")
)

parser <- OptionParser(option_list = option_list,
                       description = "DESeq2 analysis for bulk RNA-seq data")
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

# ── Load Data ─────────────────────────────────────
cat("Loading counts matrix:", opt$counts_matrix, "\n")
counts_raw <- read.delim(opt$counts_matrix, row.names = 1, check.names = FALSE)

# Remove non-numeric columns (gene_name, etc.)
numeric_cols <- sapply(counts_raw, is.numeric)
counts <- as.matrix(counts_raw[, numeric_cols])

# Round counts to integers (salmon may produce non-integer)
counts <- round(counts)

# Ensure positive counts
counts[counts < 0] <- 0

cat("Loaded", nrow(counts), "genes x", ncol(counts), "samples\n")

# ── Create Sample Info ────────────────────────────
if (!is.null(opt$sample_info) && file.exists(opt$sample_info)) {
  sample_info <- read.csv(opt$sample_info)
} else {
  # Auto-generate: all samples as single group for QC
  sample_info <- data.frame(
    sample = colnames(counts),
    condition = rep("group1", ncol(counts)),
    stringsAsFactors = FALSE
  )
  # If >= 2 samples, split into two groups for demonstration
  if (ncol(counts) >= 2) {
    half <- ceiling(ncol(counts) / 2)
    sample_info$condition[1:half] <- "group1"
    sample_info$condition[(half + 1):ncol(counts)] <- "group2"
  }
}

rownames(sample_info) <- sample_info$sample

# ── DESeq2 Analysis ──────────────────────────────
cat("Running DESeq2...\n")
dds <- DESeqDataSetFromMatrix(
  countData = counts,
  colData = sample_info,
  design = ~ condition
)

# Filter low-count genes
keep <- rowSums(counts(dds)) >= 10
dds <- dds[keep, ]

dds <- DESeq(dds)
res <- results(dds, alpha = opt$padj_threshold)

# ── Results Table ─────────────────────────────────
res_df <- as.data.frame(res)
res_df$gene <- rownames(res_df)
res_df <- res_df[order(res_df$padj, na.last = TRUE), ]

write.csv(res_df, file.path(opt$output_dir, "deseq2_results.csv"),
          row.names = FALSE)

# Significant DEGs
sig <- res_df[!is.na(res_df$padj) &
              res_df$padj < opt$padj_threshold &
              abs(res_df$log2FoldChange) > log2(opt$fc_threshold), ]

write.csv(sig, file.path(opt$output_dir, "significant_degs.csv"),
          row.names = FALSE)

cat("Total genes tested:", nrow(res_df), "\n")
cat("Significant DEGs:", nrow(sig), "\n")

# ── Visualizations ────────────────────────────────
# Volcano plot
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
    labs(title = "Volcano Plot", x = "Log2 Fold Change",
         y = "-Log10 Adjusted P-value") +
    geom_vline(xintercept = c(-log2(opt$fc_threshold), log2(opt$fc_threshold)),
               linetype = "dashed", color = "blue") +
    geom_hline(yintercept = -log10(opt$padj_threshold),
               linetype = "dashed", color = "blue") +
    theme(legend.position = "none")
  print(p)
  dev.off()
}, error = function(e) cat("Volcano plot error:", e$message, "\n"))

# PCA plot
tryCatch({
  vsd <- vst(dds, blind = TRUE)
  pdf(file.path(opt$output_dir, "pca_plot.pdf"), width = 7, height = 5)
  pca_data <- plotPCA(vsd, intgroup = "condition", returnData = TRUE)
  pct_var <- round(100 * attr(pca_data, "percentVar"))
  p <- ggplot(pca_data, aes(x = PC1, y = PC2, color = condition)) +
    geom_point(size = 3) +
    theme_minimal() +
    labs(title = "PCA Plot",
         x = paste0("PC1 (", pct_var[1], "% variance)"),
         y = paste0("PC2 (", pct_var[2], "% variance)"))
  print(p)
  dev.off()
}, error = function(e) cat("PCA plot error:", e$message, "\n"))

# Heatmap of top genes
tryCatch({
  library(pheatmap)
  vsd <- vst(dds, blind = TRUE)
  top_genes <- head(rownames(res[order(res$padj), ]), opt$top_n)
  top_genes <- top_genes[!is.na(top_genes)]
  if (length(top_genes) > 0) {
    mat <- assay(vsd)[top_genes, ]
    mat <- mat - rowMeans(mat)
    pdf(file.path(opt$output_dir, "heatmap_top50.pdf"), width = 8, height = 10)
    pheatmap(mat, show_rownames = (length(top_genes) <= 50),
             cluster_rows = TRUE, cluster_cols = TRUE,
             main = paste("Top", length(top_genes), "DEGs"))
    dev.off()
  }
}, error = function(e) cat("Heatmap error:", e$message, "\n"))

# MA plot
tryCatch({
  pdf(file.path(opt$output_dir, "ma_plot.pdf"), width = 7, height = 5)
  plotMA(res, main = "MA Plot", ylim = c(-5, 5))
  dev.off()
}, error = function(e) cat("MA plot error:", e$message, "\n"))

# ── Summary JSON ──────────────────────────────────
upregulated <- nrow(sig[sig$log2FoldChange > 0, ])
downregulated <- nrow(sig[sig$log2FoldChange < 0, ])

top_up <- head(sig[sig$log2FoldChange > 0, "gene"], 10)
top_down <- head(sig[sig$log2FoldChange < 0, "gene"], 10)

summary <- list(
  success = TRUE,
  total_genes = nrow(res_df),
  genes_tested = sum(!is.na(res_df$padj)),
  significant_degs = nrow(sig),
  upregulated = upregulated,
  downregulated = downregulated,
  fc_threshold = opt$fc_threshold,
  padj_threshold = opt$padj_threshold,
  top_upregulated_genes = as.list(top_up),
  top_downregulated_genes = as.list(top_down),
  samples = ncol(counts),
  conditions = unique(sample_info$condition)
)

write(toJSON(summary, auto_unbox = TRUE, pretty = TRUE),
      file.path(opt$output_dir, "summary.json"))

cat("Analysis complete. Results in:", opt$output_dir, "\n")
