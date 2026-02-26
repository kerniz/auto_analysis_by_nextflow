"""
Differential Expression Gene Analyzer
차등 발현 유전자 분석기

nf-core 파이프라인 출력(DESeq2, Seurat)을 파싱하여
DEG 분석 결과를 구조화합니다.
"""

import csv
import json
from pathlib import Path
from typing import Dict, List, Optional, Any, Tuple

try:
    import pandas as pd
    HAS_PANDAS = True
except ImportError:
    HAS_PANDAS = False


class DEGAnalyzer:
    """
    차등 발현 유전자 분석기

    nf-core/rnaseq와 nf-core/scrnaseq 파이프라인 출력 포맷을 파싱하여
    DEG 목록, 분류, 상위 유전자를 추출합니다.
    """

    def __init__(
        self,
        fc_threshold: float = 1.5,
        padj_threshold: float = 0.05,
    ):
        """
        Args:
            fc_threshold: Fold-change 절대값 임계치 (log2FC)
            padj_threshold: adjusted p-value 임계치
        """
        self.fc_threshold = fc_threshold
        self.padj_threshold = padj_threshold

    async def analyze_deseq2_output(
        self, results_path: Path
    ) -> Dict[str, Any]:
        """
        DESeq2 결과 파싱 (nf-core/rnaseq 출력)

        Args:
            results_path: DESeq2 결과 CSV/TSV 파일 경로

        Returns:
            파싱된 DEG 분석 결과
        """
        results_path = Path(results_path)

        if not results_path.exists():
            return {"error": f"파일을 찾을 수 없음: {results_path}"}

        try:
            if HAS_PANDAS:
                return self._parse_deseq2_pandas(results_path)
            else:
                return self._parse_deseq2_csv(results_path)
        except Exception as e:
            return {"error": f"DESeq2 결과 파싱 실패: {str(e)}"}

    def _parse_deseq2_pandas(self, path: Path) -> Dict[str, Any]:
        """pandas로 DESeq2 결과 파싱"""
        sep = "\t" if path.suffix in (".tsv", ".txt") else ","
        df = pd.read_csv(path, sep=sep)

        # 컬럼명 정규화
        col_map = {}
        for col in df.columns:
            lower = col.lower().strip()
            if "log2fold" in lower or "log2fc" in lower:
                col_map["log2fc"] = col
            elif "padj" in lower or "adj" in lower:
                col_map["padj"] = col
            elif "pvalue" in lower or "p-value" in lower or "pval" in lower:
                col_map["pvalue"] = col
            elif "gene" in lower or "id" in lower or "symbol" in lower:
                col_map["gene"] = col
            elif "basemean" in lower:
                col_map["basemean"] = col

        if "log2fc" not in col_map or "padj" not in col_map:
            return {
                "error": "필수 컬럼(log2FoldChange, padj) 미발견",
                "available_columns": list(df.columns),
            }

        fc_col = col_map["log2fc"]
        padj_col = col_map["padj"]
        gene_col = col_map.get("gene", df.columns[0])

        # NA 제거
        df = df.dropna(subset=[fc_col, padj_col])

        # 유의한 DEG 필터링
        significant = df[
            (df[padj_col] < self.padj_threshold) &
            (df[fc_col].abs() >= self.fc_threshold)
        ]

        up = significant[significant[fc_col] > 0]
        down = significant[significant[fc_col] < 0]

        return {
            "total_genes": len(df),
            "significant_deg_count": len(significant),
            "upregulated_count": len(up),
            "downregulated_count": len(down),
            "fc_threshold": self.fc_threshold,
            "padj_threshold": self.padj_threshold,
            "top_upregulated": [
                {
                    "gene": row[gene_col],
                    "log2fc": round(float(row[fc_col]), 4),
                    "padj": float(row[padj_col]),
                }
                for _, row in up.nlargest(20, fc_col).iterrows()
            ],
            "top_downregulated": [
                {
                    "gene": row[gene_col],
                    "log2fc": round(float(row[fc_col]), 4),
                    "padj": float(row[padj_col]),
                }
                for _, row in down.nsmallest(20, fc_col).iterrows()
            ],
        }

    def _parse_deseq2_csv(self, path: Path) -> Dict[str, Any]:
        """pandas 없이 CSV 파싱"""
        sep = "\t" if path.suffix in (".tsv", ".txt") else ","

        with open(path, "r") as f:
            reader = csv.DictReader(f, delimiter=sep)
            rows = list(reader)

        if not rows:
            return {"error": "빈 파일", "total_genes": 0}

        # 컬럼명 찾기
        headers = list(rows[0].keys())
        fc_col = next(
            (h for h in headers if "log2fold" in h.lower() or "log2fc" in h.lower()),
            None
        )
        padj_col = next(
            (h for h in headers if "padj" in h.lower() or "adj" in h.lower()),
            None
        )
        gene_col = next(
            (h for h in headers if "gene" in h.lower() or "symbol" in h.lower()),
            headers[0]
        )

        if not fc_col or not padj_col:
            return {"error": "필수 컬럼 미발견", "available_columns": headers}

        up_genes = []
        down_genes = []
        total = 0

        for row in rows:
            try:
                fc = float(row[fc_col])
                padj = float(row[padj_col])
                total += 1

                if padj < self.padj_threshold and abs(fc) >= self.fc_threshold:
                    entry = {
                        "gene": row[gene_col],
                        "log2fc": round(fc, 4),
                        "padj": padj,
                    }
                    if fc > 0:
                        up_genes.append(entry)
                    else:
                        down_genes.append(entry)
            except (ValueError, KeyError):
                continue

        up_genes.sort(key=lambda x: x["log2fc"], reverse=True)
        down_genes.sort(key=lambda x: x["log2fc"])

        return {
            "total_genes": total,
            "significant_deg_count": len(up_genes) + len(down_genes),
            "upregulated_count": len(up_genes),
            "downregulated_count": len(down_genes),
            "fc_threshold": self.fc_threshold,
            "padj_threshold": self.padj_threshold,
            "top_upregulated": up_genes[:20],
            "top_downregulated": down_genes[:20],
        }

    async def analyze_seurat_markers(
        self, results_path: Path
    ) -> Dict[str, Any]:
        """
        Seurat marker gene 결과 파싱 (nf-core/scrnaseq 출력)

        Args:
            results_path: Seurat FindAllMarkers 결과 파일 경로

        Returns:
            클러스터별 마커 유전자 분석 결과
        """
        results_path = Path(results_path)

        if not results_path.exists():
            return {"error": f"파일을 찾을 수 없음: {results_path}"}

        try:
            if not HAS_PANDAS:
                return {"error": "pandas 필요 (pip install pandas)"}

            sep = "\t" if results_path.suffix in (".tsv", ".txt") else ","
            df = pd.read_csv(results_path, sep=sep)

            # 클러스터 컬럼 찾기
            cluster_col = next(
                (c for c in df.columns if "cluster" in c.lower()),
                None
            )
            gene_col = next(
                (c for c in df.columns if "gene" in c.lower() or "symbol" in c.lower()),
                df.columns[0] if len(df.columns) > 0 else None
            )
            fc_col = next(
                (c for c in df.columns if "avg_log2fc" in c.lower() or "log2fc" in c.lower()),
                None
            )
            padj_col = next(
                (c for c in df.columns if "p_val_adj" in c.lower() or "padj" in c.lower()),
                None
            )

            if not cluster_col or not gene_col:
                return {
                    "error": "필수 컬럼(cluster, gene) 미발견",
                    "available_columns": list(df.columns),
                }

            clusters = {}
            for cluster_id in df[cluster_col].unique():
                cluster_df = df[df[cluster_col] == cluster_id]

                # 유의한 마커만 필터
                if padj_col and fc_col:
                    sig = cluster_df[
                        (cluster_df[padj_col] < self.padj_threshold) &
                        (cluster_df[fc_col] > 0)
                    ]
                else:
                    sig = cluster_df

                top_markers = []
                for _, row in sig.head(10).iterrows():
                    marker = {"gene": row[gene_col]}
                    if fc_col:
                        marker["log2fc"] = round(float(row[fc_col]), 4)
                    if padj_col:
                        marker["padj"] = float(row[padj_col])
                    top_markers.append(marker)

                clusters[str(cluster_id)] = {
                    "total_markers": len(sig),
                    "top_markers": top_markers,
                }

            return {
                "total_clusters": len(clusters),
                "total_markers": len(df),
                "clusters": clusters,
            }

        except Exception as e:
            return {"error": f"Seurat 결과 파싱 실패: {str(e)}"}

    def get_top_genes(
        self,
        deg_results: Dict[str, Any],
        n: int = 50,
    ) -> List[Dict[str, Any]]:
        """
        DEG 결과에서 상위 N개 유전자 추출

        상향/하향 조절 유전자를 log2FC 절대값 기준으로 정렬하여 반환합니다.
        """
        up = deg_results.get("top_upregulated", [])
        down = deg_results.get("top_downregulated", [])

        all_genes = []
        for g in up:
            g["direction"] = "up"
            all_genes.append(g)
        for g in down:
            g["direction"] = "down"
            all_genes.append(g)

        all_genes.sort(key=lambda x: abs(x.get("log2fc", 0)), reverse=True)
        return all_genes[:n]

    def classify_genes(
        self, deg_results: Dict[str, Any]
    ) -> Dict[str, List[str]]:
        """
        DEG를 상향/하향 조절로 분류하여 유전자 심볼 리스트 반환

        Returns:
            {"upregulated": [...], "downregulated": [...]}
        """
        up_genes = [g["gene"] for g in deg_results.get("top_upregulated", [])]
        down_genes = [g["gene"] for g in deg_results.get("top_downregulated", [])]

        return {
            "upregulated": up_genes,
            "downregulated": down_genes,
        }

    def get_gene_symbols(self, deg_results: Dict[str, Any]) -> List[str]:
        """모든 유의한 DEG의 유전자 심볼 리스트 반환"""
        classified = self.classify_genes(deg_results)
        return classified["upregulated"] + classified["downregulated"]
