#!/usr/bin/env python3
"""
Scanpy Analysis for scRNA-seq
nf-core/scrnaseq 출력 → scanpy 분석 (R 없이도 가능한 대안)

Usage:
    python scanpy_analysis.py \
        --input_dir filtered_feature_bc_matrix/ \
        --output_dir results/analysis/ \
        [--min_genes 200] [--max_genes 5000] \
        [--max_mt_pct 20] [--n_pcs 30] [--resolution 0.8]
"""

import argparse
import json
import sys
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(
        description="Scanpy scRNA-seq analysis"
    )
    parser.add_argument("--input_dir", type=str, default=None,
                        help="Filtered feature-barcode matrix directory")
    parser.add_argument("--input_h5ad", type=str, default=None,
                        help="Input h5ad file (alternative to input_dir)")
    parser.add_argument("--output_dir", type=str, required=True,
                        help="Output directory")
    parser.add_argument("--min_genes", type=int, default=200)
    parser.add_argument("--max_genes", type=int, default=5000)
    parser.add_argument("--max_mt_pct", type=float, default=20.0)
    parser.add_argument("--n_pcs", type=int, default=30)
    parser.add_argument("--resolution", type=float, default=0.8)
    args = parser.parse_args()

    if not args.input_dir and not args.input_h5ad:
        parser.error("Either --input_dir or --input_h5ad is required")

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    try:
        import matplotlib
        import pandas as pd
        import scanpy as sc
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError as e:
        summary = {"success": False, "error": f"Package not available: {e}"}
        (output_dir / "summary.json").write_text(json.dumps(summary, indent=2))
        sys.exit(1)

    sc.settings.figdir = str(output_dir)
    sc.settings.verbosity = 1

    # ── Load Data ─────────────────────────────────
    print("Loading data...")
    if args.input_h5ad and Path(args.input_h5ad).exists():
        adata = sc.read_h5ad(args.input_h5ad)
    else:
        adata = sc.read_10x_mtx(args.input_dir, var_names="gene_symbols",
                                 cache=True)

    initial_cells = adata.n_obs
    print(f"Loaded {adata.n_obs} cells x {adata.n_vars} genes")

    # ── QC ────────────────────────────────────────
    adata.var["mt"] = adata.var_names.str.startswith(("MT-", "mt-"))
    sc.pp.calculate_qc_metrics(adata, qc_vars=["mt"],
                                percent_top=None, log1p=False,
                                inplace=True)

    # QC violin plot
    try:
        fig, axes = plt.subplots(1, 3, figsize=(12, 4))
        sc.pl.violin(adata, ["n_genes_by_counts"], ax=axes[0], show=False)
        sc.pl.violin(adata, ["total_counts"], ax=axes[1], show=False)
        sc.pl.violin(adata, ["pct_counts_mt"], ax=axes[2], show=False)
        plt.tight_layout()
        plt.savefig(output_dir / "violin_qc.pdf")
        plt.close()
    except Exception as e:
        print(f"QC violin error: {e}")

    # Filter
    sc.pp.filter_cells(adata, min_genes=args.min_genes)
    adata = adata[adata.obs.n_genes_by_counts < args.max_genes, :]
    adata = adata[adata.obs.pct_counts_mt < args.max_mt_pct, :]

    print(f"After QC: {adata.n_obs} cells")

    # ── Normalize + HVG ───────────────────────────
    sc.pp.normalize_total(adata, target_sum=1e4)
    sc.pp.log1p(adata)
    sc.pp.highly_variable_genes(adata, min_mean=0.0125, max_mean=3,
                                 min_disp=0.5)

    adata.raw = adata
    adata = adata[:, adata.var.highly_variable]

    # ── PCA + Neighbors + Clustering ──────────────
    sc.pp.scale(adata, max_value=10)
    sc.tl.pca(adata, n_comps=args.n_pcs)
    sc.pp.neighbors(adata, n_pcs=args.n_pcs)
    sc.tl.leiden(adata, resolution=args.resolution)
    sc.tl.umap(adata)

    n_clusters = len(adata.obs["leiden"].unique())
    print(f"Found {n_clusters} clusters")

    # ── UMAP Plot ─────────────────────────────────
    try:
        fig, ax = plt.subplots(figsize=(8, 6))
        sc.pl.umap(adata, color="leiden", ax=ax, show=False,
                   title=f"UMAP - {n_clusters} clusters")
        plt.tight_layout()
        plt.savefig(output_dir / "umap.pdf")
        plt.close()
    except Exception as e:
        print(f"UMAP plot error: {e}")

    # ── Find Markers ──────────────────────────────
    print("Finding markers...")
    sc.tl.rank_genes_groups(adata, "leiden", method="wilcoxon")

    # Extract markers to DataFrame
    markers_list = []
    for cluster in adata.obs["leiden"].unique():
        try:
            result = sc.get.rank_genes_groups_df(adata, group=str(cluster))
            result["cluster"] = cluster
            markers_list.append(result)
        except Exception:
            pass

    if markers_list:
        markers_df = pd.concat(markers_list, ignore_index=True)
        markers_df.to_csv(output_dir / "markers.csv", index=False)

        top_markers = markers_df.groupby("cluster").head(10)
        top_markers.to_csv(output_dir / "top_markers.csv", index=False)
    else:
        markers_df = pd.DataFrame()

    # ── Cell Counts ───────────────────────────────
    cell_counts = adata.obs["leiden"].value_counts().reset_index()
    cell_counts.columns = ["cluster", "cell_count"]
    cell_counts.to_csv(output_dir / "cell_type_counts.csv", index=False)

    # ── Summary ───────────────────────────────────
    top_genes = {}
    for cluster in sorted(adata.obs["leiden"].unique()):
        cluster_markers = markers_df[markers_df["cluster"] == cluster]
        top_genes[str(cluster)] = cluster_markers.head(3)["names"].tolist()

    summary = {
        "success": True,
        "initial_cells": int(initial_cells),
        "filtered_cells": int(adata.n_obs),
        "total_genes": int(adata.raw.n_vars),
        "n_clusters": n_clusters,
        "resolution": args.resolution,
        "n_pcs": args.n_pcs,
        "cells_per_cluster": {
            str(row["cluster"]): int(row["cell_count"])
            for _, row in cell_counts.iterrows()
        },
        "total_markers": len(markers_df),
        "top_markers_per_cluster": top_genes,
        "qc_params": {
            "min_genes": args.min_genes,
            "max_genes": args.max_genes,
            "max_mt_pct": args.max_mt_pct,
        },
    }

    (output_dir / "summary.json").write_text(
        json.dumps(summary, indent=2)
    )

    print(f"Analysis complete. Results in: {output_dir}")


if __name__ == "__main__":
    main()
