"""
Pathway Analyzer
KEGG/Reactome 경로 분석기

annotation_client를 활용하여 유전자 목록에 대한
경로 농축 분석을 수행합니다.
"""

import asyncio
from collections import Counter
from typing import Any


class PathwayAnalyzer:
    """
    경로 분석기

    KEGG 및 Reactome 경로 농축 분석을 수행하고
    핵심 경로를 식별합니다.
    """

    def __init__(self, annotation_client=None):
        """
        Args:
            annotation_client: AnnotationClient 인스턴스 (optional)
        """
        self.annotation_client = annotation_client

    async def analyze_pathways(
        self,
        gene_list: list[str],
        organism: str = "hsa",
    ) -> dict[str, Any]:
        """
        유전자 목록에 대한 경로 농축 분석 실행

        Args:
            gene_list: 유전자 심볼 리스트
            organism: KEGG organism 코드 (기본: hsa = Homo sapiens)

        Returns:
            경로 분석 결과
        """
        if not gene_list:
            return {"error": "유전자 목록이 비어있음", "gene_count": 0}

        results: dict[str, Any] = {
            "gene_count": len(gene_list),
            "kegg": {},
            "go": {},
            "summary": {},
        }

        # KEGG 분석
        kegg_result = await self.get_kegg_enrichment(gene_list, organism)
        results["kegg"] = kegg_result

        # GO 분석 (annotation_client 사용 가능 시)
        if self.annotation_client:
            go_result = await self._get_go_enrichment(gene_list)
            results["go"] = go_result

        # 요약 생성
        results["summary"] = self._generate_summary(results)

        return results

    async def get_kegg_enrichment(
        self,
        gene_list: list[str],
        organism: str = "hsa",
    ) -> dict[str, Any]:
        """
        KEGG 경로 농축 분석

        annotation_client가 있으면 API를 사용하고,
        없으면 gseapy의 Enrichr를 사용합니다.
        """
        # annotation_client가 있으면 직접 KEGG API 사용
        if self.annotation_client:
            return await self._kegg_via_annotation_client(gene_list, organism)

        # gseapy Enrichr 폴백
        try:
            import gseapy as gp

            enr = await asyncio.to_thread(
                gp.enrichr,
                gene_list=gene_list,
                gene_sets="KEGG_2021_Human",
                organism="human",
                outdir=None,
                no_plot=True,
            )

            res_df = enr.results
            significant = res_df[res_df["Adjusted P-value"] < 0.05]

            return {
                "source": "enrichr",
                "total_pathways": len(res_df),
                "significant_count": len(significant),
                "pathways": [
                    {
                        "pathway": row["Term"],
                        "p_value": row["P-value"],
                        "adjusted_p_value": row["Adjusted P-value"],
                        "combined_score": row["Combined Score"],
                        "genes": row["Genes"].split(";") if isinstance(row["Genes"], str) else [],
                        "overlap": row["Overlap"],
                    }
                    for _, row in significant.head(20).iterrows()
                ],
            }

        except ImportError:
            return {"error": "gseapy 패키지 필요 (pip install gseapy)"}
        except Exception as e:
            return {"error": f"KEGG 분석 실패: {str(e)}"}

    async def _kegg_via_annotation_client(
        self,
        gene_list: list[str],
        organism: str,
    ) -> dict[str, Any]:
        """annotation_client를 통한 KEGG 경로 조회"""
        pathway_counts: Counter = Counter()
        gene_pathway_map: dict[str, list[str]] = {}

        # 유전자별 KEGG 경로 조회 (동시 실행, rate limit 고려)
        semaphore = asyncio.Semaphore(5)

        async def query_gene(gene: str):
            async with semaphore:
                try:
                    result = await self.annotation_client.get_kegg_pathways(
                        gene, organism
                    )
                    if result.success:
                        pathways = result.data.get("pathways", [])
                        for pw in pathways:
                            pathway_counts[pw] += 1
                            gene_pathway_map.setdefault(pw, []).append(gene)
                except Exception:
                    pass

        await asyncio.gather(*[query_gene(g) for g in gene_list[:100]])

        # 가장 많은 유전자가 속한 경로 순으로 정렬
        sorted_pathways = pathway_counts.most_common(20)

        return {
            "source": "kegg_api",
            "total_pathways": len(pathway_counts),
            "pathways": [
                {
                    "pathway": pw,
                    "gene_count": count,
                    "genes": gene_pathway_map.get(pw, []),
                    "enrichment_ratio": count / max(len(gene_list), 1),
                }
                for pw, count in sorted_pathways
            ],
        }

    async def get_reactome_enrichment(
        self, gene_list: list[str]
    ) -> dict[str, Any]:
        """
        Reactome 경로 농축 분석

        gseapy의 Enrichr Reactome 데이터베이스를 사용합니다.
        """
        try:
            import gseapy as gp

            enr = await asyncio.to_thread(
                gp.enrichr,
                gene_list=gene_list,
                gene_sets="Reactome_2022",
                organism="human",
                outdir=None,
                no_plot=True,
            )

            res_df = enr.results
            significant = res_df[res_df["Adjusted P-value"] < 0.05]

            return {
                "source": "enrichr_reactome",
                "total_pathways": len(res_df),
                "significant_count": len(significant),
                "pathways": [
                    {
                        "pathway": row["Term"],
                        "p_value": row["P-value"],
                        "adjusted_p_value": row["Adjusted P-value"],
                        "combined_score": row["Combined Score"],
                        "overlap": row["Overlap"],
                    }
                    for _, row in significant.head(20).iterrows()
                ],
            }

        except ImportError:
            return {"error": "gseapy 패키지 필요"}
        except Exception as e:
            return {"error": f"Reactome 분석 실패: {str(e)}"}

    async def _get_go_enrichment(
        self, gene_list: list[str]
    ) -> dict[str, Any]:
        """annotation_client를 통한 GO enrichment"""
        if not self.annotation_client:
            return {"error": "annotation_client 필요"}

        try:
            result = await self.annotation_client.get_go_enrichment(gene_list)
            if result.success:
                return result.data
            return {"error": result.error_message}
        except Exception as e:
            return {"error": str(e)}

    def identify_key_pathways(
        self,
        enrichment_results: dict[str, Any],
        top_n: int = 10,
    ) -> list[dict[str, Any]]:
        """
        가장 유의한 경로 식별

        KEGG와 Reactome 결과를 합쳐서 상위 N개 경로를 반환합니다.
        """
        all_pathways = []

        # KEGG 결과
        kegg = enrichment_results.get("kegg", {})
        for pw in kegg.get("pathways", []):
            pw["source"] = "KEGG"
            all_pathways.append(pw)

        # Reactome 결과
        reactome = enrichment_results.get("reactome", {})
        for pw in reactome.get("pathways", []):
            pw["source"] = "Reactome"
            all_pathways.append(pw)

        # p-value 기준 정렬 (있는 경우)
        all_pathways.sort(
            key=lambda x: x.get("adjusted_p_value", x.get("p_value", 1.0))
        )

        return all_pathways[:top_n]

    def _generate_summary(
        self, results: dict[str, Any]
    ) -> dict[str, Any]:
        """경로 분석 결과 요약"""
        kegg_count = results.get("kegg", {}).get("significant_count", 0)
        go_count = len(results.get("go", {}).get("terms", []))

        kegg_pathways = results.get("kegg", {}).get("pathways", [])
        top_pathway = kegg_pathways[0] if kegg_pathways else None

        return {
            "kegg_significant": kegg_count,
            "go_terms": go_count,
            "top_pathway": top_pathway.get("pathway", "N/A") if top_pathway else "N/A",
            "total_pathways_found": kegg_count + go_count,
        }
