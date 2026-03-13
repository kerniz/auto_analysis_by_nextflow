#!/usr/bin/env Rscript
# Variant Analysis for WGS/WES
# nf-core/sarek 출력 → VCF 기반 변이 분석
#
# Usage:
#   Rscript variant_analysis.R \
#     --vcf_file variants.vcf \
#     --output_dir results/analysis/ \
#     [--min_qual 30] [--min_depth 10] \
#     [--annotation_file annotated.vcf]

suppressPackageStartupMessages({
  library(optparse)
  library(jsonlite)
})

# ── Argument Parsing ──────────────────────────────
option_list <- list(
  make_option("--vcf_file", type = "character",
              help = "Input VCF file from sarek variant calling"),
  make_option("--output_dir", type = "character",
              help = "Output directory for results"),
  make_option("--min_qual", type = "double", default = 30,
              help = "Minimum variant quality [default: 30]"),
  make_option("--min_depth", type = "integer", default = 10,
              help = "Minimum read depth [default: 10]"),
  make_option("--annotation_file", type = "character", default = NULL,
              help = "Optional SnpEff/VEP annotation VCF")
)

parser <- OptionParser(option_list = option_list,
                       description = "WGS/WES variant analysis (nf-core/sarek)")
opt <- parse_args(parser)

if (is.null(opt$vcf_file) || is.null(opt$output_dir)) {
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

# ── Parse VCF ─────────────────────────────────────
cat("Reading VCF file:", opt$vcf_file, "\n")

parse_vcf <- function(vcf_path) {
  lines <- readLines(vcf_path)

  # Extract header lines for sample names
  header_line <- lines[grepl("^#CHROM", lines)]
  if (length(header_line) == 0) {
    stop("No #CHROM header line found in VCF")
  }
  header_fields <- strsplit(header_line, "\t")[[1]]
  sample_names <- header_fields[10:length(header_fields)]

  # Filter out comment lines
  data_lines <- lines[!grepl("^#", lines)]
  if (length(data_lines) == 0) {
    return(data.frame())
  }

  # Parse data lines
  parsed <- strsplit(data_lines, "\t")
  df <- data.frame(
    CHROM = sapply(parsed, `[`, 1),
    POS = as.integer(sapply(parsed, `[`, 2)),
    ID = sapply(parsed, `[`, 3),
    REF = sapply(parsed, `[`, 4),
    ALT = sapply(parsed, `[`, 5),
    QUAL = suppressWarnings(as.numeric(sapply(parsed, `[`, 6))),
    FILTER = sapply(parsed, `[`, 7),
    INFO = sapply(parsed, `[`, 8),
    stringsAsFactors = FALSE
  )

  # Extract DP from INFO field
  dp_matches <- regmatches(df$INFO, regexpr("DP=([0-9]+)", df$INFO))
  df$DP <- suppressWarnings(as.integer(gsub("DP=", "", dp_matches)))
  df$DP[is.na(df$DP)] <- 0

  return(df)
}

vcf_df <- tryCatch({
  parse_vcf(opt$vcf_file)
}, error = function(e) {
  summary <- list(
    success = FALSE,
    error = paste("Failed to parse VCF:", e$message)
  )
  write(toJSON(summary, auto_unbox = TRUE, pretty = TRUE),
        file.path(opt$output_dir, "summary.json"))
  quit(status = 1)
})

if (nrow(vcf_df) == 0) {
  summary <- list(
    success = TRUE,
    total_variants = 0,
    filtered_variants = 0,
    message = "No variants found in VCF file"
  )
  write(toJSON(summary, auto_unbox = TRUE, pretty = TRUE),
        file.path(opt$output_dir, "summary.json"))
  cat("No variants found in VCF file.\n")
  quit(status = 0)
}

cat("Loaded", nrow(vcf_df), "variants\n")

# ── Filter Variants ──────────────────────────────
vcf_df$QUAL[is.na(vcf_df$QUAL)] <- 0
filtered <- vcf_df[vcf_df$QUAL >= opt$min_qual & vcf_df$DP >= opt$min_depth, ]
cat("After filtering (QUAL >=", opt$min_qual, ", DP >=", opt$min_depth, "):",
    nrow(filtered), "variants\n")

# ── Classify Variant Types ───────────────────────
classify_variant <- function(ref, alt) {
  # Handle multi-allelic (take first alt)
  alt_first <- strsplit(alt, ",")[[1]][1]
  ref_len <- nchar(ref)
  alt_len <- nchar(alt_first)

  if (ref_len == 1 && alt_len == 1) {
    return("SNV")
  } else if (ref_len != alt_len) {
    return("InDel")
  } else if (ref_len > 1 && alt_len > 1 && ref_len == alt_len) {
    return("MNV")
  } else {
    return("Other")
  }
}

filtered$variant_type <- mapply(classify_variant, filtered$REF, filtered$ALT)

cat("Variant types:\n")
print(table(filtered$variant_type))

# ── Chromosome Distribution ─────────────────────
chrom_counts <- as.data.frame(table(filtered$CHROM))
colnames(chrom_counts) <- c("chromosome", "count")
chrom_counts <- chrom_counts[order(-chrom_counts$count), ]

# ── Write Output Files ───────────────────────────
write.csv(filtered, file.path(opt$output_dir, "filtered_variants.csv"),
          row.names = FALSE)

variant_stats <- data.frame(
  category = c("total_input", "after_filter",
                names(table(filtered$variant_type))),
  count = c(nrow(vcf_df), nrow(filtered),
            as.integer(table(filtered$variant_type))),
  stringsAsFactors = FALSE
)
write.csv(variant_stats, file.path(opt$output_dir, "variant_stats.csv"),
          row.names = FALSE)

# ── Annotation Parsing (if provided) ─────────────
gene_impacts <- NULL
if (!is.null(opt$annotation_file) && file.exists(opt$annotation_file)) {
  cat("Parsing annotation file:", opt$annotation_file, "\n")
  tryCatch({
    ann_lines <- readLines(opt$annotation_file)
    ann_data <- ann_lines[!grepl("^#", ann_lines)]

    if (length(ann_data) > 0) {
      # Extract ANN or CSQ fields from INFO
      gene_list <- c()
      impact_list <- c()

      for (line in ann_data) {
        fields <- strsplit(line, "\t")[[1]]
        info <- fields[8]

        # SnpEff ANN format: ANN=ALT|Effect|Impact|GeneName|...
        ann_match <- regmatches(info, regexpr("ANN=[^;]+", info))
        if (length(ann_match) > 0) {
          ann_str <- gsub("ANN=", "", ann_match)
          ann_parts <- strsplit(strsplit(ann_str, ",")[[1]][1], "\\|")[[1]]
          if (length(ann_parts) >= 4) {
            gene_list <- c(gene_list, ann_parts[4])
            impact_list <- c(impact_list, ann_parts[3])
          }
        }

        # VEP CSQ format: CSQ=ALT|Consequence|IMPACT|SYMBOL|...
        csq_match <- regmatches(info, regexpr("CSQ=[^;]+", info))
        if (length(csq_match) > 0 && length(ann_match) == 0) {
          csq_str <- gsub("CSQ=", "", csq_match)
          csq_parts <- strsplit(strsplit(csq_str, ",")[[1]][1], "\\|")[[1]]
          if (length(csq_parts) >= 4) {
            gene_list <- c(gene_list, csq_parts[4])
            impact_list <- c(impact_list, csq_parts[3])
          }
        }
      }

      if (length(gene_list) > 0) {
        gene_impacts <- data.frame(
          gene = gene_list,
          impact = impact_list,
          stringsAsFactors = FALSE
        )
        write.csv(gene_impacts,
                  file.path(opt$output_dir, "gene_impacts.csv"),
                  row.names = FALSE)
        cat("Extracted", nrow(gene_impacts), "gene annotations\n")
      }
    }
  }, error = function(e) cat("Annotation parsing error:", e$message, "\n"))
}

# ── Chromosome Distribution Plot ─────────────────
tryCatch({
  # Order chromosomes naturally
  chrom_order <- c(paste0("chr", c(1:22, "X", "Y", "M")),
                   as.character(c(1:22, "X", "Y", "MT")))
  chrom_counts$chromosome <- factor(
    chrom_counts$chromosome,
    levels = intersect(chrom_order, chrom_counts$chromosome)
  )
  chrom_counts <- chrom_counts[!is.na(chrom_counts$chromosome), ]

  pdf(file.path(opt$output_dir, "chromosome_distribution.pdf"),
      width = 10, height = 6)
  p <- ggplot(chrom_counts, aes(x = chromosome, y = count)) +
    geom_bar(stat = "identity", fill = "steelblue") +
    theme_minimal() +
    labs(title = "Variant Distribution by Chromosome",
         x = "Chromosome", y = "Number of Variants") +
    theme(axis.text.x = element_text(angle = 45, hjust = 1))
  print(p)
  dev.off()
}, error = function(e) cat("Chromosome plot error:", e$message, "\n"))

# ── Variant Type Pie Chart ───────────────────────
tryCatch({
  type_counts <- as.data.frame(table(filtered$variant_type))
  colnames(type_counts) <- c("type", "count")

  pdf(file.path(opt$output_dir, "variant_types.pdf"), width = 7, height = 5)
  p <- ggplot(type_counts, aes(x = "", y = count, fill = type)) +
    geom_bar(stat = "identity", width = 1) +
    coord_polar("y") +
    theme_void() +
    labs(title = "Variant Type Distribution") +
    scale_fill_brewer(palette = "Set2")
  print(p)
  dev.off()
}, error = function(e) cat("Variant type plot error:", e$message, "\n"))

# ── Summary JSON ──────────────────────────────────
type_table <- as.list(table(filtered$variant_type))

summary <- list(
  success = TRUE,
  total_variants = nrow(vcf_df),
  filtered_variants = nrow(filtered),
  min_qual = opt$min_qual,
  min_depth = opt$min_depth,
  variant_types = type_table,
  chromosomes_with_variants = nrow(chrom_counts),
  top_chromosomes = head(
    setNames(as.list(chrom_counts$count),
             as.character(chrom_counts$chromosome)), 5
  )
)

if (!is.null(gene_impacts) && nrow(gene_impacts) > 0) {
  impact_table <- as.list(table(gene_impacts$impact))
  summary$annotation <- list(
    total_annotated = nrow(gene_impacts),
    unique_genes = length(unique(gene_impacts$gene)),
    impact_distribution = impact_table,
    top_genes = head(names(sort(table(gene_impacts$gene),
                                decreasing = TRUE)), 10)
  )
}

write(toJSON(summary, auto_unbox = TRUE, pretty = TRUE),
      file.path(opt$output_dir, "summary.json"))

cat("Analysis complete. Results in:", opt$output_dir, "\n")
