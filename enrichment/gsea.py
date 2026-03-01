"""
Gene Set Enrichment Analysis Integration
GSEA 분석 통합 모듈

gseapy 라이브러리를 활용한 유전자 세트 농축 분석.
MSigDB, KEGG, GO 유전자 세트 지원.
"""

import asyncio
from typing import Any

try:
    import gseapy as gp
    HAS_GSEAPY = True
except ImportError:
    HAS_GSEAPY = False

try:
    import pandas as pd
    HAS_PANDAS = True
except ImportError:
    HAS_PANDAS = False


class GSEAAnalyzer:
    """
    GSEA 분석기

    gseapy 라이브러리를 래핑하여 다양한 유전자 세트 데이터베이스에 대한
    농축 분석을 수행합니다.
    """

    AVAILABLE_GENE_SETS = [
        "KEGG_2021_Human",
        "GO_Biological_Process_2023",
        "GO_Molecular_Function_2023",
        "GO_Cellular_Component_2023",
        "MSigDB_Hallmark_2020",
        "Reactome_2022",
        "WikiPathway_2023_Human",
    ]

    def __init__(
        self,
        gene_set_db: str = "KEGG_2021_Human",
        organism: str = "human",
        output_dir: str | None = None,
    ):
        self.gene_set_db = gene_set_db
        self.organism = organism
        self.output_dir = output_dir or "./results/enrichment"

    async def run_gsea(
        self,
        gene_ranking: dict[str, float],
        gene_sets: list[str] | None = None,
        permutation_num: int = 1000,
    ) -> dict[str, Any]:
        """
        Ranked gene list에 대한 GSEA 분석 실행

        Args:
            gene_ranking: {gene_symbol: ranking_metric} 딕셔너리
            gene_sets: 사용할 유전자 세트 (기본: self.gene_set_db)
            permutation_num: 순열 수

        Returns:
            GSEA 결과 딕셔너리
        """
        if not HAS_GSEAPY:
            return {"error": "gseapy 패키지가 설치되지 않음", "install": "pip install gseapy"}

        if not HAS_PANDAS:
            return {"error": "pandas 패키지가 설치되지 않음"}

        gene_set_names = gene_sets or [self.gene_set_db]

        try:
            # ranking을 DataFrame으로 변환
            rnk = pd.DataFrame(
                list(gene_ranking.items()),
                columns=["gene", "score"]
            ).sort_values("score", ascending=False)

            # GSEA prerank 실행 (블로킹 → asyncio.to_thread)
            result = await asyncio.to_thread(
                self._run_prerank,
                rnk,
                gene_set_names[0],
                permutation_num,
            )

            return result

        except Exception as e:
            return {"error": f"GSEA 실행 실패: {str(e)}", "gene_count": len(gene_ranking)}

    def _run_prerank(
        self,
        rnk: "pd.DataFrame",
        gene_set: str,
        permutation_num: int,
    ) -> dict[str, Any]:
        """gseapy prerank 실행 (동기)"""
        pre_res = gp.prerank(
            rnk=rnk,
            gene_sets=gene_set,
            permutation_num=permutation_num,
            outdir=self.output_dir,
            seed=42,
            no_plot=True,
        )

        # 결과 파싱
        res_df = pre_res.res2d
        significant = res_df[res_df["FDR q-val"] < 0.25]

        return {
            "total_gene_sets_tested": len(res_df),
            "significant_at_fdr_025": len(significant),
            "top_enriched": [
                {
                    "term": row["Term"],
                    "es": round(row["ES"], 4),
                    "nes": round(row["NES"], 4),
                    "pval": row["NOM p-val"],
                    "fdr": row["FDR q-val"],
                    "gene_count": row.get("Tag %", ""),
                }
                for _, row in significant.head(20).iterrows()
            ],
            "gene_set_db": gene_set,
        }

    async def run_enrichr(
        self,
        gene_list: list[str],
        gene_sets: list[str] | None = None,
    ) -> dict[str, Any]:
        """
        Enrichr 스타일 over-representation 분석 (ORA)

        Args:
            gene_list: 유전자 심볼 리스트
            gene_sets: 사용할 유전자 세트 (기본: 여러 DB 동시 분석)

        Returns:
            농축 분석 결과 딕셔너리
        """
        if not HAS_GSEAPY:
            return {"error": "gseapy 패키지가 설치되지 않음", "install": "pip install gseapy"}

        if not gene_list:
            return {"error": "유전자 목록이 비어있음", "gene_count": 0}

        gene_set_names = gene_sets or [
            "KEGG_2021_Human",
            "GO_Biological_Process_2023",
        ]

        all_results: dict[str, Any] = {
            "gene_count": len(gene_list),
            "gene_sets_queried": gene_set_names,
            "significant_terms": [],
            "per_database": {},
        }

        for gs_name in gene_set_names:
            try:
                result = await asyncio.to_thread(
                    self._run_enrichr_sync, gene_list, gs_name
                )
                all_results["per_database"][gs_name] = result

                # significant terms 합산
                for term in result.get("top_terms", []):
                    term["database"] = gs_name
                    all_results["significant_terms"].append(term)

            except Exception as e:
                all_results["per_database"][gs_name] = {"error": str(e)}

        # 전체 significant terms를 p-value로 정렬
        all_results["significant_terms"].sort(
            key=lambda x: x.get("adjusted_p_value", 1.0)
        )
        all_results["significant_terms"] = all_results["significant_terms"][:30]

        return all_results

    def _run_enrichr_sync(
        self, gene_list: list[str], gene_set: str
    ) -> dict[str, Any]:
        """Enrichr 동기 실행"""
        enr = gp.enrichr(
            gene_list=gene_list,
            gene_sets=gene_set,
            organism=self.organism,
            outdir=self.output_dir,
            no_plot=True,
        )

        res_df = enr.results
        significant = res_df[res_df["Adjusted P-value"] < 0.05]

        return {
            "total_terms": len(res_df),
            "significant_count": len(significant),
            "top_terms": [
                {
                    "term": row["Term"],
                    "overlap": row["Overlap"],
                    "p_value": row["P-value"],
                    "adjusted_p_value": row["Adjusted P-value"],
                    "combined_score": row["Combined Score"],
                    "genes": row["Genes"].split(";") if isinstance(row["Genes"], str) else [],
                }
                for _, row in significant.head(15).iterrows()
            ],
        }

    def interpret_results(
        self, enrichment_results: dict[str, Any]
    ) -> dict[str, Any]:
        """
        농축 분석 결과 해석 요약

        Args:
            enrichment_results: run_gsea 또는 run_enrichr 결과

        Returns:
            해석된 요약 딕셔너리
        """
        significant_terms = enrichment_results.get("significant_terms", [])

        if not significant_terms:
            return {
                "summary": "유의한 농축 결과 없음",
                "category_counts": {},
                "top_pathway": None,
            }

        # 카테고리별 분류
        categories: dict[str, int] = {}
        for term in significant_terms:
            db = term.get("database", "unknown")
            categories[db] = categories.get(db, 0) + 1

        top = significant_terms[0]

        return {
            "summary": f"{len(significant_terms)}개 유의한 term 발견",
            "category_counts": categories,
            "top_pathway": {
                "name": top.get("term", ""),
                "p_value": top.get("adjusted_p_value", top.get("fdr", 1.0)),
                "database": top.get("database", ""),
            },
            "total_significant": len(significant_terms),
        }
