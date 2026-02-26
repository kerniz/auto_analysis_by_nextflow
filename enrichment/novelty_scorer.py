"""
Novelty Scorer
기존 문헌 대비 신규성 평가

Semantic Scholar, Europe PMC 데이터를 활용하여
연구의 신규성을 다차원적으로 평가합니다.
"""

import asyncio
import re
from typing import Dict, List, Optional, Any
from datetime import datetime


class NoveltyScorer:
    """
    신규성 평가기

    연구 결과의 신규성을 기존 문헌과 비교하여 평가합니다.
    토픽, 방법론, 발견의 신규성을 각각 점수화합니다.

    Scoring dimensions:
    - Topic novelty: 연구 주제가 얼마나 새로운가
    - Methodology novelty: 사용된 방법론이 얼마나 새로운가
    - Finding novelty: 발견이 얼마나 새로운가
    """

    def __init__(
        self,
        semantic_scholar_client=None,
        europe_pmc_client=None,
    ):
        self.ss_client = semantic_scholar_client
        self.epmc_client = europe_pmc_client

    async def score_novelty(
        self,
        paper_metadata: Dict[str, Any],
        enrichment_results: Dict[str, Any],
        aggregated_data: Any,
    ) -> Dict[str, Any]:
        """
        전체 신규성 점수 계산

        Args:
            paper_metadata: 논문 메타데이터
            enrichment_results: 농축 분석 결과
            aggregated_data: 통합 데이터 결과 (AggregatedResult or dict)

        Returns:
            {score: 0.0-1.0, factors: {...}, explanation: str}
        """
        title = paper_metadata.get("title", "")
        abstract = paper_metadata.get("abstract", "")

        # 각 차원별 신규성 평가 (병렬)
        topic_task = self._assess_topic_novelty(title, abstract, aggregated_data)
        method_task = self._assess_methodology_novelty(paper_metadata)
        finding_task = self._assess_finding_novelty(
            enrichment_results, aggregated_data
        )

        topic_score, method_score, finding_score = await asyncio.gather(
            topic_task, method_task, finding_task
        )

        # 가중 종합 점수 (발견 > 방법론 > 주제)
        weights = {"topic": 0.25, "methodology": 0.30, "finding": 0.45}
        overall_score = (
            topic_score * weights["topic"]
            + method_score * weights["methodology"]
            + finding_score * weights["finding"]
        )

        # 등급 결정
        if overall_score >= 0.8:
            rating = "HIGHLY_NOVEL"
        elif overall_score >= 0.6:
            rating = "MODERATELY_NOVEL"
        elif overall_score >= 0.4:
            rating = "INCREMENTAL"
        else:
            rating = "LOW_NOVELTY"

        return {
            "score": round(overall_score, 3),
            "rating": rating,
            "factors": {
                "topic_novelty": round(topic_score, 3),
                "methodology_novelty": round(method_score, 3),
                "finding_novelty": round(finding_score, 3),
            },
            "weights": weights,
            "explanation": self._generate_explanation(
                overall_score, topic_score, method_score, finding_score, rating
            ),
        }

    async def _assess_topic_novelty(
        self,
        title: str,
        abstract: str,
        aggregated_data: Any,
    ) -> float:
        """
        연구 주제 신규성 평가

        유사 논문 수, 발행 연도 트렌드, 인용 네트워크 크기를 기반으로 평가합니다.
        """
        score = 0.5  # 기본값 (데이터 없을 때)

        # aggregated_data에서 관련 논문 정보 추출
        if isinstance(aggregated_data, dict):
            agg = aggregated_data
        elif hasattr(aggregated_data, "to_dict"):
            agg = aggregated_data.to_dict()
        else:
            agg = {}

        # 관련 논문 수 기반 점수
        related_papers = agg.get("related_papers", [])
        citation_count = agg.get("citation_count", 0)

        if related_papers:
            num_related = len(related_papers)
            # 관련 논문이 적을수록 주제가 새로움
            if num_related <= 5:
                score = 0.9
            elif num_related <= 20:
                score = 0.7
            elif num_related <= 50:
                score = 0.5
            elif num_related <= 100:
                score = 0.3
            else:
                score = 0.2

        # 인용 수가 매우 적으면 너무 새로운 주제일 수 있음
        if citation_count == 0:
            score = min(score + 0.1, 1.0)

        # Semantic Scholar 데이터로 보완
        if self.ss_client:
            try:
                search_result = await self.ss_client.search(title[:100], limit=10)
                if search_result.success:
                    similar_papers = search_result.data.get("data", [])
                    if len(similar_papers) <= 3:
                        score = min(score + 0.15, 1.0)
                    elif len(similar_papers) >= 8:
                        score = max(score - 0.1, 0.0)
            except Exception:
                pass

        return min(max(score, 0.0), 1.0)

    async def _assess_methodology_novelty(
        self,
        paper_metadata: Dict[str, Any],
    ) -> float:
        """
        방법론 신규성 평가

        사용된 분석 기법, 도구, 접근법의 최신성을 평가합니다.
        """
        abstract = paper_metadata.get("abstract", "").lower()
        title = paper_metadata.get("title", "").lower()
        text = f"{title} {abstract}"

        score = 0.5

        # 최신 방법론 키워드 (높은 신규성)
        novel_methods = [
            "single-cell multiome", "spatial transcriptomics",
            "long-read sequencing", "nanopore", "pacbio",
            "crispr screen", "perturb-seq",
            "foundation model", "large language model",
            "graph neural network", "transformer",
            "multi-omics integration", "single-cell atac",
            "visium", "slide-seq", "merfish", "seqfish",
        ]

        # 표준 방법론 키워드 (보통 신규성)
        standard_methods = [
            "rna-seq", "chip-seq", "atac-seq",
            "deseq2", "edger", "limma",
            "gsea", "gene ontology", "kegg",
            "seurat", "scanpy", "cellranger",
        ]

        # 오래된 방법론 (낮은 신규성)
        old_methods = [
            "microarray", "rt-pcr", "northern blot",
            "sage", "est", "hybridization",
        ]

        novel_count = sum(1 for m in novel_methods if m in text)
        standard_count = sum(1 for m in standard_methods if m in text)
        old_count = sum(1 for m in old_methods if m in text)

        if novel_count >= 2:
            score = 0.9
        elif novel_count == 1:
            score = 0.75
        elif standard_count >= 1 and old_count == 0:
            score = 0.5
        elif old_count >= 1:
            score = 0.25

        # 최신 도구 조합 보너스
        if novel_count >= 1 and standard_count >= 1:
            score = min(score + 0.1, 1.0)

        return min(max(score, 0.0), 1.0)

    async def _assess_finding_novelty(
        self,
        enrichment_results: Dict[str, Any],
        aggregated_data: Any,
    ) -> float:
        """
        연구 발견 신규성 평가

        발견된 경로/유전자가 해당 분야에서 얼마나 잘 알려져 있는지 평가합니다.
        """
        score = 0.5

        if not enrichment_results or enrichment_results.get("error"):
            return score

        # 유의한 경로의 수
        significant_terms = enrichment_results.get("significant_terms", [])
        top_genes_count = enrichment_results.get("top_genes_count", 0)

        # 잘 알려진 경로 목록 (낮은 신규성)
        well_known_pathways = [
            "cell cycle", "apoptosis", "p53 signaling",
            "mapk signaling", "pi3k-akt", "wnt signaling",
            "nf-kappa b", "jak-stat", "notch signaling",
            "tgf-beta", "hedgehog", "hippo signaling",
        ]

        # 잘 알려진 유전자
        well_known_genes = [
            "tp53", "kras", "egfr", "braf", "pik3ca",
            "myc", "rb1", "apc", "pten", "brca1",
        ]

        known_pathway_count = 0
        novel_pathway_count = 0

        for term in significant_terms:
            term_name = term.get("term", "").lower()
            is_known = any(pw in term_name for pw in well_known_pathways)
            if is_known:
                known_pathway_count += 1
            else:
                novel_pathway_count += 1

        total_pathways = known_pathway_count + novel_pathway_count

        if total_pathways > 0:
            novelty_ratio = novel_pathway_count / total_pathways
            score = 0.3 + (novelty_ratio * 0.5)

        # Europe PMC text-mined terms로 보완
        if isinstance(aggregated_data, dict):
            epmc_data = aggregated_data.get("europe_pmc_data", {})
            text_mined = epmc_data.get("text_mined_terms", [])
            if text_mined:
                gene_terms = [t for t in text_mined if t.get("type") == "Gene"]
                known_gene_count = sum(
                    1 for g in gene_terms
                    if g.get("name", "").lower() in well_known_genes
                )
                if known_gene_count > len(gene_terms) * 0.5:
                    score = max(score - 0.15, 0.0)
                elif known_gene_count == 0 and gene_terms:
                    score = min(score + 0.15, 1.0)

        return min(max(score, 0.0), 1.0)

    def _generate_explanation(
        self,
        overall: float,
        topic: float,
        methodology: float,
        finding: float,
        rating: str,
    ) -> str:
        """신규성 평가 설명 생성"""
        parts = []

        parts.append(f"Overall novelty: {rating} ({overall:.2f})")

        if topic >= 0.7:
            parts.append("Topic is relatively unexplored in existing literature.")
        elif topic <= 0.3:
            parts.append("Topic is well-covered in existing literature.")

        if methodology >= 0.7:
            parts.append("Methodology uses cutting-edge approaches.")
        elif methodology <= 0.3:
            parts.append("Methodology relies on well-established techniques.")

        if finding >= 0.7:
            parts.append("Findings reveal potentially novel biological insights.")
        elif finding <= 0.3:
            parts.append("Findings primarily confirm known biological relationships.")

        return " ".join(parts)
