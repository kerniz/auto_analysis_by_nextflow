#!/usr/bin/env Rscript
# Seurat Analysis for scRNA-seq
# nf-core/scrnaseq 출력 → Seurat 분석
#
# Usage:
#   Rscript seurat_analysis.R \
#     --input_dir filtered_feature_bc_matrix/ \
#     --output_dir results/analysis/ \
#     [--min_features 200] [--max_features 5000] \
#     [--max_mt_percent 20] [--n_dims 30] [--resolution 0.8]

suppressPackageStartupMessages({
  library(optparse)
  library(jsonlite)
})

# ── Argument Parsing ──────────────────────────────
option_list <- list(
  make_option("--input_dir", type = "character",
              help = "Filtered feature-barcode matrix directory"),
  make_option("--input_rds", type = "character", default = NULL,
              help = "Path to .rds Seurat/SCE object (alternative to input_dir)"),
  make_option("--output_dir", type = "character",
              help = "Output directory for results"),
  make_option("--min_features", type = "integer", default = 200,
              help = "Min features per cell [default: 200]"),
  make_option("--max_features", type = "integer", default = 5000,
              help = "Max features per cell [default: 5000]"),
  make_option("--max_mt_percent", type = "double", default = 20.0,
              help = "Max mitochondrial gene percentage [default: 20]"),
  make_option("--n_dims", type = "integer", default = 30,
              help = "Number of PCA dimensions [default: 30]"),
  make_option("--resolution", type = "double", default = 0.8,
              help = "Clustering resolution [default: 0.8]")
)

parser <- OptionParser(option_list = option_list,
                       description = "Seurat analysis for scRNA-seq data")
opt <- parse_args(parser)

if (is.null(opt$output_dir) || (is.null(opt$input_dir) && is.null(opt$input_rds))) {
  print_help(parser)
  quit(status = 1)
}

dir.create(opt$output_dir, recursive = TRUE, showWarnings = FALSE)

# ── Load Seurat ───────────────────────────────────
tryCatch({
  suppressPackageStartupMessages({
    library(Seurat)
    library(ggplot2)
    library(dplyr)
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
cat("Loading data...\n")

if (!is.null(opt$input_rds) && file.exists(opt$input_rds)) {
  obj <- readRDS(opt$input_rds)
  if (!inherits(obj, "Seurat")) {
    # Convert SingleCellExperiment to Seurat if needed
    if (inherits(obj, "SingleCellExperiment")) {
      seurat_obj <- as.Seurat(obj)
    } else {
      stop("Unsupported object type in RDS file")
    }
  } else {
    seurat_obj <- obj
  }
} else {
  counts <- Read10X(data.dir = opt$input_dir)
  seurat_obj <- CreateSeuratObject(
    counts = counts,
    project = "bioauto_scrna",
    min.cells = 3,
    min.features = opt$min_features
  )
}

cat("Initial cells:", ncol(seurat_obj), "\n")
cat("Initial genes:", nrow(seurat_obj), "\n")

# ── QC Filtering ──────────────────────────────────
seurat_obj[["percent.mt"]] <- PercentageFeatureSet(seurat_obj, pattern = "^MT-|^mt-")

initial_cells <- ncol(seurat_obj)

# QC violin plot (before filtering)
tryCatch({
  pdf(file.path(opt$output_dir, "violin_qc.pdf"), width = 10, height = 5)
  p <- VlnPlot(seurat_obj,
                features = c("nFeature_RNA", "nCount_RNA", "percent.mt"),
                ncol = 3, pt.size = 0)
  print(p)
  dev.off()
}, error = function(e) cat("QC violin plot error:", e$message, "\n"))

seurat_obj <- subset(seurat_obj,
  subset = nFeature_RNA > opt$min_features &
           nFeature_RNA < opt$max_features &
           percent.mt < opt$max_mt_percent
)

cat("After QC filtering:", ncol(seurat_obj), "cells\n")

# ── Standard Workflow ─────────────────────────────
cat("Normalizing...\n")
seurat_obj <- NormalizeData(seurat_obj, verbose = FALSE)

cat("Finding variable features...\n")
seurat_obj <- FindVariableFeatures(seurat_obj, selection.method = "vst",
                                    nfeatures = 2000, verbose = FALSE)

cat("Scaling data...\n")
seurat_obj <- ScaleData(seurat_obj, verbose = FALSE)

cat("Running PCA...\n")
seurat_obj <- RunPCA(seurat_obj, npcs = opt$n_dims, verbose = FALSE)

cat("Finding neighbors and clusters...\n")
seurat_obj <- FindNeighbors(seurat_obj, dims = 1:opt$n_dims, verbose = FALSE)
seurat_obj <- FindClusters(seurat_obj, resolution = opt$resolution, verbose = FALSE)

cat("Running UMAP...\n")
seurat_obj <- RunUMAP(seurat_obj, dims = 1:opt$n_dims, verbose = FALSE)

n_clusters <- length(unique(Idents(seurat_obj)))
cat("Found", n_clusters, "clusters\n")

# ── UMAP Plot ─────────────────────────────────────
tryCatch({
  pdf(file.path(opt$output_dir, "umap_clusters.pdf"), width = 8, height = 6)
  p <- DimPlot(seurat_obj, reduction = "umap", label = TRUE, pt.size = 0.5) +
    ggtitle(paste("UMAP -", n_clusters, "clusters"))
  print(p)
  dev.off()
}, error = function(e) cat("UMAP plot error:", e$message, "\n"))

# ── Find Markers ──────────────────────────────────
cat("Finding cluster markers...\n")
markers <- FindAllMarkers(seurat_obj, only.pos = TRUE,
                          min.pct = 0.25, logfc.threshold = 0.25,
                          verbose = FALSE)

write.csv(markers, file.path(opt$output_dir, "cluster_markers.csv"),
          row.names = FALSE)

# Top markers per cluster
top_markers <- markers %>%
  group_by(cluster) %>%
  slice_head(n = 10) %>%
  ungroup()

write.csv(top_markers, file.path(opt$output_dir, "top_markers.csv"),
          row.names = FALSE)

# ── Feature Plots ─────────────────────────────────
tryCatch({
  top5 <- markers %>% group_by(cluster) %>% slice_head(n = 1) %>% pull(gene)
  top5 <- head(unique(top5), 6)
  if (length(top5) > 0) {
    pdf(file.path(opt$output_dir, "umap_features.pdf"), width = 12, height = 8)
    p <- FeaturePlot(seurat_obj, features = top5, ncol = 3)
    print(p)
    dev.off()
  }
}, error = function(e) cat("Feature plot error:", e$message, "\n"))

# ── Cell Type Counts ──────────────────────────────
cell_counts <- as.data.frame(table(Idents(seurat_obj)))
colnames(cell_counts) <- c("cluster", "cell_count")
write.csv(cell_counts, file.path(opt$output_dir, "cell_type_counts.csv"),
          row.names = FALSE)

# ── Save Seurat Object ───────────────────────────
cat("Saving Seurat object...\n")
saveRDS(seurat_obj, file.path(opt$output_dir, "seurat_object.rds"))

# ── Summary JSON ──────────────────────────────────
top_genes_per_cluster <- markers %>%
  group_by(cluster) %>%
  slice_head(n = 3) %>%
  summarise(genes = list(gene)) %>%
  deframe()

summary <- list(
  success = TRUE,
  initial_cells = initial_cells,
  filtered_cells = ncol(seurat_obj),
  total_genes = nrow(seurat_obj),
  n_clusters = n_clusters,
  resolution = opt$resolution,
  n_dims = opt$n_dims,
  cells_per_cluster = setNames(cell_counts$cell_count,
                                as.character(cell_counts$cluster)),
  total_markers = nrow(markers),
  top_markers_per_cluster = top_genes_per_cluster,
  qc_params = list(
    min_features = opt$min_features,
    max_features = opt$max_features,
    max_mt_percent = opt$max_mt_percent
  )
)

write(toJSON(summary, auto_unbox = TRUE, pretty = TRUE),
      file.path(opt$output_dir, "summary.json"))

cat("Analysis complete. Results in:", opt$output_dir, "\n")
