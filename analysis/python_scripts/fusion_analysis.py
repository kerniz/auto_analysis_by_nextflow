#!/usr/bin/env python3
"""
Fusion Gene Analysis for RNA Fusions
nf-core/rnafusion 출력 → arriba format 기반 융합 유전자 분석

Usage:
    python fusion_analysis.py \
        --fusion_results fusions.tsv \
        --output_dir results/analysis/ \
        [--min_supporting_reads 2] [--min_confidence medium]
"""

import argparse
import json
import sys
from pathlib import Path

CONFIDENCE_LEVELS = {"low": 0, "medium": 1, "high": 2}


def parse_confidence(value):
    """Convert confidence string to numeric level for comparison."""
    return CONFIDENCE_LEVELS.get(value.lower().strip(), -1)


def classify_fusion_type(chr1, chr2, gene1, gene2):
    """Classify fusion as interchromosomal, intrachromosomal, or read-through."""
    if chr1 != chr2:
        return "interchromosomal"
    # Simple heuristic: if genes are adjacent on same chromosome, likely read-through
    if chr1 == chr2:
        return "intrachromosomal"
    return "unknown"


def main():
    parser = argparse.ArgumentParser(
        description="RNA fusion gene analysis (nf-core/rnafusion)"
    )
    parser.add_argument("--fusion_results", type=str, required=True,
                        help="Path to fusion results TSV (arriba format)")
    parser.add_argument("--output_dir", type=str, required=True,
                        help="Output directory")
    parser.add_argument("--min_supporting_reads", type=int, default=2,
                        help="Minimum supporting reads [default: 2]")
    parser.add_argument("--min_confidence", type=str, default="medium",
                        help="Minimum confidence level [default: medium]")
    args = parser.parse_args()

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    try:
        import pandas as pd
    except ImportError as e:
        summary = {"success": False, "error": f"Package not available: {e}"}
        (output_dir / "summary.json").write_text(json.dumps(summary, indent=2))
        sys.exit(1)

    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        has_matplotlib = True
    except ImportError:
        has_matplotlib = False

    # ── Load Fusion Results ───────────────────────
    print(f"Reading fusion results: {args.fusion_results}")

    try:
        fusions = pd.read_csv(args.fusion_results, sep="\t")
    except Exception as e:
        summary = {
            "success": False,
            "error": f"Failed to read fusion file: {e}",
        }
        (output_dir / "summary.json").write_text(json.dumps(summary, indent=2))
        sys.exit(1)

    # Normalize column names (arriba uses #gene1 sometimes)
    fusions.columns = [c.lstrip("#").strip() for c in fusions.columns]

    # Validate required columns exist
    required_cols = ["gene1", "gene2"]
    missing = [c for c in required_cols if c not in fusions.columns]
    if missing:
        summary = {
            "success": False,
            "error": f"Missing required columns: {missing}",
        }
        (output_dir / "summary.json").write_text(json.dumps(summary, indent=2))
        sys.exit(1)

    total_fusions = len(fusions)
    print(f"Loaded {total_fusions} fusion candidates")

    if total_fusions == 0:
        summary = {
            "success": True,
            "total_fusions": 0,
            "filtered_fusions": 0,
            "message": "No fusion candidates found",
        }
        (output_dir / "summary.json").write_text(json.dumps(summary, indent=2))
        print("No fusion candidates found.")
        sys.exit(0)

    # ── Calculate Supporting Reads ────────────────
    read_cols = []
    for col in ["split_reads1", "split_reads2", "discordant_mates"]:
        if col in fusions.columns:
            fusions[col] = pd.to_numeric(fusions[col], errors="coerce").fillna(0)
            read_cols.append(col)

    if read_cols:
        fusions["total_support"] = fusions[read_cols].sum(axis=1)
    else:
        fusions["total_support"] = 0

    # ── Filter by Supporting Reads ────────────────
    filtered = fusions[
        fusions["total_support"] >= args.min_supporting_reads
    ].copy()

    # ── Filter by Confidence ─────────────────────
    min_conf_level = parse_confidence(args.min_confidence)
    if "confidence" in filtered.columns and min_conf_level >= 0:
        filtered["conf_level"] = filtered["confidence"].apply(parse_confidence)
        filtered = filtered[filtered["conf_level"] >= min_conf_level].copy()
        filtered = filtered.drop(columns=["conf_level"])

    print(f"After filtering: {len(filtered)} fusions")

    # ── Classify Fusion Types ────────────────────
    if "breakpoint1" in filtered.columns and "breakpoint2" in filtered.columns:
        def extract_chrom(bp):
            return str(bp).split(":")[0] if pd.notna(bp) else ""

        filtered["chr1"] = filtered["breakpoint1"].apply(extract_chrom)
        filtered["chr2"] = filtered["breakpoint2"].apply(extract_chrom)
        filtered["fusion_class"] = filtered.apply(
            lambda row: classify_fusion_type(
                row["chr1"], row["chr2"], row["gene1"], row["gene2"]
            ),
            axis=1,
        )
    else:
        filtered["fusion_class"] = "unknown"

    # Also check arriba 'type' column if present
    if "type" in filtered.columns:
        # Arriba has its own type classification; use it to refine read-through
        filtered.loc[
            filtered["type"].str.contains("read_through", case=False, na=False),
            "fusion_class",
        ] = "read-through"

    # ── Rank by Total Supporting Evidence ─────────
    filtered = filtered.sort_values("total_support", ascending=False)

    # ── Write Output Files ───────────────────────
    # Select key columns for output
    output_cols = ["gene1", "gene2"]
    for col in ["breakpoint1", "breakpoint2", "type", "confidence",
                "split_reads1", "split_reads2", "discordant_mates",
                "total_support", "fusion_class", "reading_frames",
                "strand1(gene/fusion)", "strand2(gene/fusion)"]:
        if col in filtered.columns:
            output_cols.append(col)

    available_cols = [c for c in output_cols if c in filtered.columns]
    filtered[available_cols].to_csv(
        output_dir / "filtered_fusions.csv", index=False
    )

    # Summary table
    fusion_summary_df = filtered.groupby(
        ["gene1", "gene2"]
    ).agg(
        total_support=("total_support", "sum"),
        count=("total_support", "count"),
    ).reset_index().sort_values("total_support", ascending=False)

    fusion_summary_df.to_csv(
        output_dir / "fusion_summary.csv", index=False
    )

    # ── Circos-style Plot ────────────────────────
    if has_matplotlib and len(filtered) > 0:
        try:
            fig, ax = plt.subplots(figsize=(10, 10),
                                   subplot_kw={"projection": "polar"})

            # Get unique genes
            genes = list(set(
                filtered["gene1"].tolist() + filtered["gene2"].tolist()
            ))
            gene_angles = {
                gene: (2 * 3.14159 * i / len(genes))
                for i, gene in enumerate(genes)
            }

            # Plot gene positions on circle
            for gene, angle in gene_angles.items():
                ax.plot(angle, 1.0, "o", markersize=8, color="steelblue")
                ax.annotate(
                    gene,
                    xy=(angle, 1.05),
                    ha="center",
                    va="center",
                    fontsize=max(6, min(10, 200 // len(genes))),
                    rotation=0,
                )

            # Draw arcs for fusions
            import numpy as np
            for _, row in filtered.head(50).iterrows():
                g1, g2 = row["gene1"], row["gene2"]
                if g1 in gene_angles and g2 in gene_angles:
                    a1 = gene_angles[g1]
                    a2 = gene_angles[g2]
                    # Draw arc between fusion partners
                    theta = np.linspace(a1, a2, 50)
                    r = 0.3 + 0.7 * np.sin(
                        np.pi * np.linspace(0, 1, 50)
                    ) * 0.5
                    alpha = min(1.0, row["total_support"] / 20)
                    ax.plot(theta, r, "-", alpha=max(0.3, alpha),
                            linewidth=1.5, color="red")

            ax.set_ylim(0, 1.3)
            ax.set_yticklabels([])
            ax.set_xticklabels([])
            ax.set_title("Fusion Gene Partners", pad=20, fontsize=14)
            plt.tight_layout()
            plt.savefig(output_dir / "fusion_circos.pdf")
            plt.close()
        except Exception as e:
            print(f"Circos plot error: {e}")

    # ── Fusion Type Bar Chart ────────────────────
    if has_matplotlib and len(filtered) > 0:
        try:
            type_counts = filtered["fusion_class"].value_counts()
            fig, ax = plt.subplots(figsize=(8, 5))
            type_counts.plot(kind="bar", ax=ax, color="steelblue", alpha=0.8)
            ax.set_title("Fusion Types")
            ax.set_xlabel("Fusion Type")
            ax.set_ylabel("Count")
            plt.xticks(rotation=45, ha="right")
            plt.tight_layout()
            plt.savefig(output_dir / "fusion_types.pdf")
            plt.close()
        except Exception as e:
            print(f"Fusion type plot error: {e}")

    # ── Summary JSON ─────────────────────────────
    type_distribution = (
        filtered["fusion_class"].value_counts().to_dict()
        if "fusion_class" in filtered.columns
        else {}
    )

    confidence_distribution = (
        filtered["confidence"].value_counts().to_dict()
        if "confidence" in filtered.columns
        else {}
    )

    top_fusions = []
    for _, row in filtered.head(10).iterrows():
        fusion_entry = {
            "gene1": row["gene1"],
            "gene2": row["gene2"],
            "total_support": int(row["total_support"]),
        }
        if "confidence" in row:
            fusion_entry["confidence"] = row["confidence"]
        if "fusion_class" in row:
            fusion_entry["type"] = row["fusion_class"]
        top_fusions.append(fusion_entry)

    summary = {
        "success": True,
        "total_fusions": total_fusions,
        "filtered_fusions": len(filtered),
        "min_supporting_reads": args.min_supporting_reads,
        "min_confidence": args.min_confidence,
        "fusion_type_distribution": type_distribution,
        "confidence_distribution": confidence_distribution,
        "unique_gene_pairs": len(fusion_summary_df),
        "top_fusions": top_fusions,
    }

    (output_dir / "summary.json").write_text(
        json.dumps(summary, indent=2)
    )

    print(f"Analysis complete. Results in: {output_dir}")


if __name__ == "__main__":
    main()
