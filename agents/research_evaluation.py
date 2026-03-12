"""
Research Evaluation Score (RES) Module
연구 평가 점수 모듈 — 100점 만점 6차원 하이브리드 평가 시스템

정량적 메트릭(인용수, 샘플 크기, Jaccard 유사도 등)과
정성적 에이전트 평가(LLM 토론 점수)를 결합하여
100점 만점의 종합 연구 평가 점수를 산출합니다.
"""

import logging
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)


# 차원별 정량:정성 비율 기본값
DEFAULT_QUANT_QUAL_RATIOS: dict[str, tuple[float, float]] = {
    "literature_redundancy": (1.0, 0.0),       # 100% 정량
    "data_support": (0.4, 0.6),                # 40:60
    "cross_dataset_reproducibility": (0.6, 0.4),  # 60:40 (단일 PMID면 0:100)
    "biological_plausibility": (0.3, 0.7),     # 30:70
    "technical_feasibility": (0.2, 0.8),       # 20:80
    "clinical_industrial_impact": (0.1, 0.9),  # 10:90
}

# 차원별 기본 배점 (합계 100)
DEFAULT_DIMENSION_WEIGHTS: dict[str, int] = {
    "literature_redundancy": 20,
    "data_support": 25,
    "cross_dataset_reproducibility": 20,
    "biological_plausibility": 15,
    "technical_feasibility": 10,
    "clinical_industrial_impact": 10,
}

# 판정 기준
DEFAULT_VERDICT_THRESHOLDS: dict[str, int] = {
    "go": 75,
    "revise": 45,
    "drop": 0,
}

# 차원별 전문가 에이전트 매핑 (정성 점수 소스)
DIMENSION_AGENT_MAP: dict[str, str] = {
    "data_support": "statistical_skeptic",
    "cross_dataset_reproducibility": "phd_expert",
    "biological_plausibility": "biological_realist",
    "technical_feasibility": "experimental_critic",
    "clinical_industrial_impact": "translation_evaluator",
}

# 차원 한국어 라벨
DIMENSION_LABELS_KO: dict[str, str] = {
    "literature_redundancy": "문헌 중복도",
    "data_support": "데이터 지원 강도",
    "cross_dataset_reproducibility": "교차 데이터셋 재현성",
    "biological_plausibility": "생물학적 타당성",
    "technical_feasibility": "기술적 실현가능성",
    "clinical_industrial_impact": "임상/산업적 영향",
}


@dataclass
class DimensionScore:
    """단일 차원 평가 결과"""
    dimension: str
    quantitative_score: float  # 0.0-1.0
    qualitative_score: float   # 0.0-1.0
    combined_score: float      # 가중 결합 0.0-1.0
    max_points: int            # 배점 (20/25/20/15/10/10)
    actual_points: float       # combined_score * max_points
    explanation: str
    label_ko: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "dimension": self.dimension,
            "label_ko": self.label_ko,
            "quantitative_score": round(self.quantitative_score, 3),
            "qualitative_score": round(self.qualitative_score, 3),
            "combined_score": round(self.combined_score, 3),
            "max_points": self.max_points,
            "actual_points": round(self.actual_points, 2),
            "explanation": self.explanation,
        }


@dataclass
class ResearchEvaluationResult:
    """연구 평가 종합 결과"""
    total_score: float              # 0-100
    dimensions: list[DimensionScore]
    verdict: str                    # "GO" / "REVISE" / "DROP"
    confidence: float               # 0.0-1.0
    evaluation_metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "total_score": round(self.total_score, 2),
            "dimensions": [d.to_dict() for d in self.dimensions],
            "verdict": self.verdict,
            "confidence": round(self.confidence, 3),
            "evaluation_metadata": self.evaluation_metadata,
        }


class ResearchEvaluationScorer:
    """
    100점 만점 6차원 하이브리드 연구 평가 시스템

    정량 메트릭 + LLM 에이전트 정성 점수 결합.
    """

    def __init__(
        self,
        dimension_weights: dict[str, int] | None = None,
        verdict_thresholds: dict[str, int] | None = None,
        quant_qual_ratios: dict[str, tuple[float, float]] | None = None,
    ):
        self.dimension_weights = dimension_weights or dict(DEFAULT_DIMENSION_WEIGHTS)
        self.verdict_thresholds = verdict_thresholds or dict(DEFAULT_VERDICT_THRESHOLDS)
        self.quant_qual_ratios = quant_qual_ratios or dict(DEFAULT_QUANT_QUAL_RATIOS)

    def evaluate(
        self,
        research_data: dict[str, Any],
        agent_scores: dict[str, float],
        enrichment_data: dict[str, Any] | None = None,
        novelty_data: dict[str, Any] | None = None,
        aggregated_data: dict[str, Any] | None = None,
        multi_pmid: bool = False,
    ) -> ResearchEvaluationResult:
        """
        종합 연구 평가 점수 산출.

        Args:
            research_data: 논문 정보 + SRA 메타데이터
            agent_scores: 에이전트별 점수 {role_value: score}
            enrichment_data: 경로 분석/GSEA 결과
            novelty_data: novelty_scorer 결과
            aggregated_data: 데이터 통합 결과
            multi_pmid: 다중 PMID 분석 여부

        Returns:
            ResearchEvaluationResult
        """
        enrichment_data = enrichment_data or {}
        novelty_data = novelty_data or {}
        aggregated_data = aggregated_data or {}

        dimensions: list[DimensionScore] = []

        for dim_name, max_points in self.dimension_weights.items():
            quant_ratio, qual_ratio = self.quant_qual_ratios.get(
                dim_name, (0.5, 0.5)
            )

            # 정량 점수 계산
            quant_score = self._compute_quantitative(
                dim_name, research_data, enrichment_data,
                novelty_data, aggregated_data, multi_pmid,
            )

            # 정성 점수 (에이전트 점수)
            qual_score = self._get_qualitative_score(dim_name, agent_scores)

            # 교차 데이터셋 재현성: 단일 PMID면 정성 100%
            if dim_name == "cross_dataset_reproducibility" and not multi_pmid:
                quant_ratio, qual_ratio = 0.0, 1.0

            # 결합
            combined = quant_ratio * quant_score + qual_ratio * qual_score
            combined = max(0.0, min(1.0, combined))

            actual_pts = combined * max_points
            explanation = self._explain_dimension(
                dim_name, quant_score, qual_score, quant_ratio, qual_ratio
            )

            dimensions.append(DimensionScore(
                dimension=dim_name,
                quantitative_score=quant_score,
                qualitative_score=qual_score,
                combined_score=combined,
                max_points=max_points,
                actual_points=actual_pts,
                explanation=explanation,
                label_ko=DIMENSION_LABELS_KO.get(dim_name, dim_name),
            ))

        total_score = sum(d.actual_points for d in dimensions)
        verdict = self._determine_verdict(total_score)

        # 확신도: 에이전트 점수 표준편차의 역수 기반
        agent_vals = [v for v in agent_scores.values() if v > 0]
        if len(agent_vals) >= 2:
            mean_s = sum(agent_vals) / len(agent_vals)
            variance = sum((v - mean_s) ** 2 for v in agent_vals) / len(agent_vals)
            std_dev = variance ** 0.5
            confidence = max(0.3, min(1.0, 1.0 - std_dev))
        else:
            confidence = 0.5

        return ResearchEvaluationResult(
            total_score=total_score,
            dimensions=dimensions,
            verdict=verdict,
            confidence=confidence,
            evaluation_metadata={
                "num_agents": len(agent_scores),
                "multi_pmid": multi_pmid,
                "dimension_count": len(dimensions),
            },
        )

    def _compute_quantitative(
        self,
        dimension: str,
        research_data: dict[str, Any],
        enrichment_data: dict[str, Any],
        novelty_data: dict[str, Any],
        aggregated_data: dict[str, Any],
        multi_pmid: bool,
    ) -> float:
        """차원별 정량 점수 산출 (0.0-1.0)"""
        if dimension == "literature_redundancy":
            return self._quant_literature_redundancy(novelty_data)
        elif dimension == "data_support":
            return self._quant_data_support(research_data, aggregated_data)
        elif dimension == "cross_dataset_reproducibility":
            return self._quant_cross_dataset(enrichment_data, multi_pmid)
        elif dimension == "biological_plausibility":
            return self._quant_biological_plausibility(enrichment_data)
        elif dimension == "technical_feasibility":
            return self._quant_technical_feasibility(research_data)
        elif dimension == "clinical_industrial_impact":
            return self._quant_clinical_impact(aggregated_data)
        return 0.5

    def _quant_literature_redundancy(self, novelty_data: dict[str, Any]) -> float:
        """NoveltyScorer 결과를 활용한 문헌 중복도 (= 1 - novelty)"""
        novelty_score = novelty_data.get("score", 0.5)
        # novelty_score가 높을수록 신규 = 중복 낮음 = 점수 높음
        return max(0.0, min(1.0, float(novelty_score)))

    def _quant_data_support(
        self, research_data: dict[str, Any], aggregated_data: dict[str, Any]
    ) -> float:
        """인용수, 샘플 크기, 데이터 소스 수 기반"""
        score = 0.5
        # 인용수 반영 (100+ → 1.0, 0 → 0.3)
        citations = aggregated_data.get("citation_count", 0)
        if isinstance(citations, (int, float)):
            citation_score = min(1.0, 0.3 + 0.7 * (citations / 100))
            score = citation_score
        # 데이터 소스 수 보정
        sources = aggregated_data.get("sources_succeeded", [])
        if isinstance(sources, list) and len(sources) > 1:
            score = min(1.0, score + 0.1 * (len(sources) - 1))
        return max(0.0, min(1.0, score))

    def _quant_cross_dataset(
        self, enrichment_data: dict[str, Any], multi_pmid: bool
    ) -> float:
        """DEG overlap Jaccard 기반 (다중 PMID)"""
        if not multi_pmid:
            return 0.0  # 단일 PMID면 정량 점수 사용 안 함
        jaccard = enrichment_data.get("deg_overlap_jaccard", 0.0)
        return max(0.0, min(1.0, float(jaccard)))

    def _quant_biological_plausibility(
        self, enrichment_data: dict[str, Any]
    ) -> float:
        """pathway 연결성 비율"""
        pathways = enrichment_data.get("top_pathways_count", 0)
        if isinstance(pathways, (int, float)) and pathways > 0:
            # 경로 수가 5-15 범위면 정상
            return min(1.0, pathways / 10)
        return 0.5

    def _quant_technical_feasibility(
        self, research_data: dict[str, Any]
    ) -> float:
        """시퀀싱 깊이 적정성"""
        sra = research_data.get("sra_metadata", {})
        if isinstance(sra, dict):
            total_reads = sra.get("total_reads", 0)
            if isinstance(total_reads, (int, float)) and total_reads > 0:
                # 10M reads → 0.5, 50M+ → 1.0
                return min(1.0, total_reads / 50_000_000)
        return 0.5

    def _quant_clinical_impact(self, aggregated_data: dict[str, Any]) -> float:
        """TCGA overlap 기반"""
        tcga = aggregated_data.get("tcga_data", {})
        if isinstance(tcga, dict) and tcga:
            # TCGA 데이터가 있으면 기본 0.6+
            case_count = tcga.get("case_count", 0)
            if isinstance(case_count, (int, float)):
                return min(1.0, 0.6 + 0.4 * (case_count / 1000))
            return 0.6
        return 0.3

    def _get_qualitative_score(
        self, dimension: str, agent_scores: dict[str, float]
    ) -> float:
        """차원에 매핑된 에이전트의 점수 반환"""
        agent_role = DIMENSION_AGENT_MAP.get(dimension)
        if agent_role and agent_role in agent_scores:
            return agent_scores[agent_role]
        # 매핑 없는 차원(literature_redundancy)은 전체 평균 사용
        if agent_scores:
            return sum(agent_scores.values()) / len(agent_scores)
        return 0.5

    def _determine_verdict(self, total_score: float) -> str:
        """총점 기반 판정"""
        go_threshold = self.verdict_thresholds.get("go", 75)
        revise_threshold = self.verdict_thresholds.get("revise", 45)
        if total_score >= go_threshold:
            return "GO"
        elif total_score >= revise_threshold:
            return "REVISE"
        return "DROP"

    def _explain_dimension(
        self,
        dim_name: str,
        quant: float,
        qual: float,
        quant_ratio: float,
        qual_ratio: float,
    ) -> str:
        """차원별 설명 텍스트 생성"""
        label = DIMENSION_LABELS_KO.get(dim_name, dim_name)
        parts = []
        if quant_ratio > 0:
            parts.append(f"정량 {quant:.2f}×{quant_ratio:.0%}")
        if qual_ratio > 0:
            parts.append(f"정성 {qual:.2f}×{qual_ratio:.0%}")
        return f"{label}: {' + '.join(parts)}"
