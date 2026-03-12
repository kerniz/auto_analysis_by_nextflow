"""Tests for Research Evaluation Score (RES) Module"""

import pytest

from agents.research_evaluation import (
    DEFAULT_DIMENSION_WEIGHTS,
    DEFAULT_QUANT_QUAL_RATIOS,
    DEFAULT_VERDICT_THRESHOLDS,
    DIMENSION_AGENT_MAP,
    DIMENSION_LABELS_KO,
    DimensionScore,
    ResearchEvaluationResult,
    ResearchEvaluationScorer,
)

# ── Fixtures ──

@pytest.fixture
def scorer():
    return ResearchEvaluationScorer()


@pytest.fixture
def agent_scores():
    return {
        "phd_expert": 0.75,
        "statistical_skeptic": 0.65,
        "biological_realist": 0.70,
        "experimental_critic": 0.60,
        "translation_evaluator": 0.55,
        "undergraduate": 0.68,
        "layperson": 0.72,
    }


@pytest.fixture
def research_data():
    return {
        "paper_info": {"pmid": "12345", "title": "Test", "abstract": "..."},
        "sra_metadata": {"total_reads": 30_000_000},
    }


@pytest.fixture
def enrichment_data():
    return {
        "top_pathways_count": 8,
        "novelty_score": 0.6,
    }


@pytest.fixture
def novelty_data():
    return {"score": 0.65}


@pytest.fixture
def aggregated_data():
    return {
        "citation_count": 50,
        "sources_succeeded": ["semantic_scholar", "europe_pmc"],
        "tcga_data": {"case_count": 200},
    }


# ── DimensionScore Tests ──

class TestDimensionScore:
    def test_create(self):
        ds = DimensionScore(
            dimension="data_support",
            quantitative_score=0.7,
            qualitative_score=0.6,
            combined_score=0.64,
            max_points=25,
            actual_points=16.0,
            explanation="test",
            label_ko="데이터 지원 강도",
        )
        assert ds.max_points == 25
        assert ds.actual_points == 16.0

    def test_to_dict(self):
        ds = DimensionScore(
            dimension="literature_redundancy",
            quantitative_score=0.65,
            qualitative_score=0.0,
            combined_score=0.65,
            max_points=20,
            actual_points=13.0,
            explanation="test",
        )
        d = ds.to_dict()
        assert d["dimension"] == "literature_redundancy"
        assert d["max_points"] == 20
        assert isinstance(d["quantitative_score"], float)


class TestResearchEvaluationResult:
    def test_create(self):
        result = ResearchEvaluationResult(
            total_score=72.5,
            dimensions=[],
            verdict="REVISE",
            confidence=0.8,
        )
        assert result.verdict == "REVISE"

    def test_to_dict(self):
        result = ResearchEvaluationResult(
            total_score=80.0,
            dimensions=[],
            verdict="GO",
            confidence=0.85,
        )
        d = result.to_dict()
        assert d["total_score"] == 80.0
        assert d["verdict"] == "GO"


# ── Constants Tests ──

class TestConstants:
    def test_dimension_weights_sum_100(self):
        total = sum(DEFAULT_DIMENSION_WEIGHTS.values())
        assert total == 100

    def test_quant_qual_ratios_valid(self):
        for dim, (q, ql) in DEFAULT_QUANT_QUAL_RATIOS.items():
            assert abs(q + ql - 1.0) < 0.001, f"{dim}: ratios don't sum to 1"

    def test_verdict_thresholds_ordered(self):
        assert DEFAULT_VERDICT_THRESHOLDS["go"] > DEFAULT_VERDICT_THRESHOLDS["revise"]
        assert DEFAULT_VERDICT_THRESHOLDS["revise"] > DEFAULT_VERDICT_THRESHOLDS["drop"]

    def test_agent_map_has_5_dims(self):
        # literature_redundancy는 매핑 없음 (100% 정량)
        assert len(DIMENSION_AGENT_MAP) == 5

    def test_ko_labels(self):
        assert len(DIMENSION_LABELS_KO) == 6
        assert "문헌" in DIMENSION_LABELS_KO["literature_redundancy"]


# ── ResearchEvaluationScorer Tests ──

class TestResearchEvaluationScorer:
    def test_init_defaults(self, scorer):
        assert sum(scorer.dimension_weights.values()) == 100
        assert scorer.verdict_thresholds["go"] == 75

    def test_init_custom(self):
        custom = ResearchEvaluationScorer(
            dimension_weights={"dim1": 50, "dim2": 50},
            verdict_thresholds={"go": 80, "revise": 50, "drop": 0},
        )
        assert custom.verdict_thresholds["go"] == 80

    def test_evaluate_returns_result(
        self, scorer, research_data, agent_scores, enrichment_data, novelty_data, aggregated_data
    ):
        result = scorer.evaluate(
            research_data=research_data,
            agent_scores=agent_scores,
            enrichment_data=enrichment_data,
            novelty_data=novelty_data,
            aggregated_data=aggregated_data,
        )
        assert isinstance(result, ResearchEvaluationResult)
        assert 0 <= result.total_score <= 100
        assert result.verdict in ("GO", "REVISE", "DROP")
        assert len(result.dimensions) == 6

    def test_evaluate_go_verdict(self, scorer, research_data, enrichment_data, aggregated_data):
        high_scores = {k: 0.95 for k in [
            "phd_expert", "statistical_skeptic", "biological_realist",
            "experimental_critic", "translation_evaluator",
            "undergraduate", "layperson",
        ]}
        result = scorer.evaluate(
            research_data=research_data,
            agent_scores=high_scores,
            enrichment_data=enrichment_data,
            novelty_data={"score": 0.95},
            aggregated_data=aggregated_data,
        )
        assert result.verdict == "GO"
        assert result.total_score >= 75

    def test_evaluate_drop_verdict(self, scorer, research_data):
        low_scores = {k: 0.1 for k in [
            "phd_expert", "statistical_skeptic", "biological_realist",
            "experimental_critic", "translation_evaluator",
        ]}
        result = scorer.evaluate(
            research_data=research_data,
            agent_scores=low_scores,
            novelty_data={"score": 0.1},
        )
        assert result.verdict == "DROP"
        assert result.total_score < 45

    def test_evaluate_revise_verdict(self, scorer, research_data, enrichment_data, aggregated_data):
        mid_scores = {k: 0.55 for k in [
            "phd_expert", "statistical_skeptic", "biological_realist",
            "experimental_critic", "translation_evaluator",
        ]}
        result = scorer.evaluate(
            research_data=research_data,
            agent_scores=mid_scores,
            enrichment_data=enrichment_data,
            novelty_data={"score": 0.5},
            aggregated_data=aggregated_data,
        )
        assert result.verdict in ("REVISE", "GO")

    def test_single_pmid_cross_dataset(self, scorer, research_data, agent_scores):
        result = scorer.evaluate(
            research_data=research_data,
            agent_scores=agent_scores,
            multi_pmid=False,
        )
        # 단일 PMID: cross_dataset은 정성 100%
        cd_dim = next(
            d for d in result.dimensions
            if d.dimension == "cross_dataset_reproducibility"
        )
        assert cd_dim.quantitative_score == 0.0

    def test_multi_pmid_cross_dataset(self, scorer, research_data, agent_scores, enrichment_data):
        enrichment_data["deg_overlap_jaccard"] = 0.4
        result = scorer.evaluate(
            research_data=research_data,
            agent_scores=agent_scores,
            enrichment_data=enrichment_data,
            multi_pmid=True,
        )
        cd_dim = next(
            d for d in result.dimensions
            if d.dimension == "cross_dataset_reproducibility"
        )
        assert cd_dim.quantitative_score == 0.4

    def test_empty_agent_scores(self, scorer, research_data):
        result = scorer.evaluate(
            research_data=research_data,
            agent_scores={},
        )
        assert isinstance(result, ResearchEvaluationResult)
        assert result.confidence == 0.5  # fallback

    def test_confidence_calculation(self, scorer, research_data):
        # 동일한 점수 → 높은 확신도
        same_scores = {k: 0.7 for k in [
            "phd_expert", "statistical_skeptic", "biological_realist",
        ]}
        result = scorer.evaluate(research_data=research_data, agent_scores=same_scores)
        assert result.confidence >= 0.8

    def test_confidence_low_variance(self, scorer, research_data):
        # 분산 큰 점수 → 낮은 확신도
        varied_scores = {
            "phd_expert": 0.9,
            "statistical_skeptic": 0.1,
            "biological_realist": 0.5,
        }
        result = scorer.evaluate(research_data=research_data, agent_scores=varied_scores)
        assert result.confidence < 0.8

    def test_dimension_labels_present(
        self, scorer, research_data, agent_scores
    ):
        result = scorer.evaluate(
            research_data=research_data,
            agent_scores=agent_scores,
        )
        for dim in result.dimensions:
            assert dim.label_ko != ""

    def test_dimension_points_bounded(
        self, scorer, research_data, agent_scores
    ):
        result = scorer.evaluate(
            research_data=research_data,
            agent_scores=agent_scores,
        )
        for dim in result.dimensions:
            assert 0 <= dim.actual_points <= dim.max_points
            assert 0 <= dim.combined_score <= 1.0

    def test_total_score_bounded(self, scorer, research_data, agent_scores):
        result = scorer.evaluate(
            research_data=research_data,
            agent_scores=agent_scores,
        )
        assert 0 <= result.total_score <= 100

    def test_metadata(self, scorer, research_data, agent_scores):
        result = scorer.evaluate(
            research_data=research_data,
            agent_scores=agent_scores,
        )
        assert result.evaluation_metadata["dimension_count"] == 6


# ── Quantitative Score Methods ──

class TestQuantitativeMethods:
    def test_literature_redundancy_high_novelty(self, scorer):
        score = scorer._quant_literature_redundancy({"score": 0.9})
        assert score == 0.9

    def test_literature_redundancy_no_data(self, scorer):
        score = scorer._quant_literature_redundancy({})
        assert score == 0.5

    def test_data_support_high_citations(self, scorer):
        score = scorer._quant_data_support(
            {}, {"citation_count": 200, "sources_succeeded": ["a", "b"]}
        )
        assert score > 0.8

    def test_data_support_no_data(self, scorer):
        score = scorer._quant_data_support({}, {})
        assert 0.0 <= score <= 1.0  # 기본값 (citation 0 → 0.3)

    def test_cross_dataset_single(self, scorer):
        score = scorer._quant_cross_dataset({}, multi_pmid=False)
        assert score == 0.0

    def test_cross_dataset_multi(self, scorer):
        score = scorer._quant_cross_dataset(
            {"deg_overlap_jaccard": 0.6}, multi_pmid=True
        )
        assert score == 0.6

    def test_biological_plausibility(self, scorer):
        score = scorer._quant_biological_plausibility({"top_pathways_count": 10})
        assert score == 1.0

    def test_technical_feasibility(self, scorer):
        score = scorer._quant_technical_feasibility(
            {"sra_metadata": {"total_reads": 25_000_000}}
        )
        assert score == 0.5

    def test_clinical_impact_with_tcga(self, scorer):
        score = scorer._quant_clinical_impact(
            {"tcga_data": {"case_count": 500}}
        )
        assert score > 0.6

    def test_clinical_impact_no_tcga(self, scorer):
        score = scorer._quant_clinical_impact({})
        assert score == 0.3

    def test_determine_verdict_go(self, scorer):
        assert scorer._determine_verdict(80) == "GO"

    def test_determine_verdict_revise(self, scorer):
        assert scorer._determine_verdict(60) == "REVISE"

    def test_determine_verdict_drop(self, scorer):
        assert scorer._determine_verdict(30) == "DROP"

    def test_determine_verdict_boundary_go(self, scorer):
        assert scorer._determine_verdict(75) == "GO"

    def test_determine_verdict_boundary_revise(self, scorer):
        assert scorer._determine_verdict(45) == "REVISE"

    def test_get_qualitative_mapped(self, scorer):
        scores = {"statistical_skeptic": 0.7}
        score = scorer._get_qualitative_score("data_support", scores)
        assert score == 0.7

    def test_get_qualitative_unmapped(self, scorer):
        scores = {"phd_expert": 0.8, "statistical_skeptic": 0.6}
        score = scorer._get_qualitative_score("literature_redundancy", scores)
        assert score == 0.7  # average
