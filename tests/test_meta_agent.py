"""Tests for Meta-Agent"""

from unittest.mock import AsyncMock, MagicMock

import pytest

from agents.meta_agent import MetaAgent, MetaAgentVerdict
from backends.base import LLMResponse


@pytest.fixture
def mock_llm_router():
    router = MagicMock()
    router.generate = AsyncMock(return_value=LLMResponse(
        content='{"verdict": "GO", "confidence": 0.85, '
                '"narrative": "이 연구는 전반적으로 우수합니다.", '
                '"key_recommendations": ["후속 실험 권장"], '
                '"risk_factors": ["샘플 크기 제한"]}',
        model="test-model",
        backend_name="test",
        success=True,
        latency_ms=100,
    ))
    return router


@pytest.fixture
def research_data():
    return {
        "paper_info": {"pmid": "12345", "title": "Test paper", "abstract": "Test abstract"},
    }


@pytest.fixture
def debate_result():
    return {
        "overall_score": 0.72,
        "overall_verdict": "PASS",
        "per_agent_scores": {
            "phd_expert": 0.75,
            "statistical_skeptic": 0.65,
        },
        "dissenting_opinions": ["통계 검정력 우려"],
    }


@pytest.fixture
def res_result():
    return {
        "total_score": 78.5,
        "verdict": "GO",
        "dimensions": [
            {"dimension": "literature_redundancy", "label_ko": "문헌 중복도",
             "actual_points": 15.0, "max_points": 20},
            {"dimension": "data_support", "label_ko": "데이터 지원 강도",
             "actual_points": 20.0, "max_points": 25},
        ],
    }


# ── MetaAgentVerdict Tests ──

class TestMetaAgentVerdict:
    def test_create(self):
        v = MetaAgentVerdict(
            verdict="GO",
            confidence=0.85,
            narrative="Good research",
            key_recommendations=["Follow-up"],
            risk_factors=["Sample size"],
            res_score=80.0,
            debate_score=0.75,
        )
        assert v.verdict == "GO"
        assert v.res_score == 80.0

    def test_to_dict(self):
        v = MetaAgentVerdict(
            verdict="REVISE",
            confidence=0.7,
            narrative="Needs work",
            key_recommendations=["Add controls"],
            risk_factors=["Low power"],
            res_score=55.0,
            debate_score=0.6,
        )
        d = v.to_dict()
        assert d["verdict"] == "REVISE"
        assert d["res_score"] == 55.0
        assert "timestamp" in d
        assert len(d["key_recommendations"]) == 1


# ── MetaAgent Tests ──

class TestMetaAgent:
    def test_init(self, mock_llm_router):
        agent = MetaAgent(mock_llm_router)
        assert agent.llm_router is mock_llm_router

    @pytest.mark.asyncio
    async def test_synthesize_go(self, mock_llm_router, research_data, debate_result, res_result):
        agent = MetaAgent(mock_llm_router)
        verdict = await agent.synthesize(research_data, debate_result, res_result)
        assert isinstance(verdict, MetaAgentVerdict)
        assert verdict.verdict == "GO"
        assert verdict.confidence == 0.85
        assert verdict.debate_score == 0.72
        assert verdict.res_score == 78.5

    @pytest.mark.asyncio
    async def test_synthesize_revise(self, mock_llm_router, research_data, debate_result):
        mock_llm_router.generate = AsyncMock(return_value=LLMResponse(
            content='{"verdict": "REVISE", "confidence": 0.7, '
                    '"narrative": "보완 필요", "key_recommendations": ["추가 실험"], '
                    '"risk_factors": ["재현성 부족"]}',
            model="test", backend_name="test", success=True, latency_ms=100,
        ))
        agent = MetaAgent(mock_llm_router)
        verdict = await agent.synthesize(research_data, debate_result)
        assert verdict.verdict == "REVISE"

    @pytest.mark.asyncio
    async def test_synthesize_drop(self, mock_llm_router, research_data, debate_result):
        mock_llm_router.generate = AsyncMock(return_value=LLMResponse(
            content='{"verdict": "DROP", "confidence": 0.9, '
                    '"narrative": "가치 없음", "key_recommendations": [], '
                    '"risk_factors": ["심각한 결함"]}',
            model="test", backend_name="test", success=True, latency_ms=100,
        ))
        agent = MetaAgent(mock_llm_router)
        verdict = await agent.synthesize(research_data, debate_result)
        assert verdict.verdict == "DROP"

    @pytest.mark.asyncio
    async def test_synthesize_llm_failure(
        self, mock_llm_router, research_data, debate_result, res_result
    ):
        mock_llm_router.generate = AsyncMock(return_value=LLMResponse(
            content="", model="test", backend_name="test",
            success=False, latency_ms=0, error_message="timeout",
        ))
        agent = MetaAgent(mock_llm_router)
        verdict = await agent.synthesize(research_data, debate_result, res_result)
        assert verdict.confidence == 0.3  # fallback
        assert verdict.verdict == "GO"  # res_score=78.5 >= 75

    @pytest.mark.asyncio
    async def test_synthesize_exception(self, mock_llm_router, research_data, debate_result):
        mock_llm_router.generate = AsyncMock(side_effect=RuntimeError("crash"))
        agent = MetaAgent(mock_llm_router)
        verdict = await agent.synthesize(research_data, debate_result)
        assert verdict.confidence == 0.3  # fallback

    @pytest.mark.asyncio
    async def test_synthesize_parse_failure(self, mock_llm_router, research_data, debate_result):
        mock_llm_router.generate = AsyncMock(return_value=LLMResponse(
            content="This is not JSON at all",
            model="test", backend_name="test", success=True, latency_ms=100,
        ))
        agent = MetaAgent(mock_llm_router)
        verdict = await agent.synthesize(research_data, debate_result)
        assert verdict.confidence == 0.3  # fallback

    @pytest.mark.asyncio
    async def test_synthesize_invalid_verdict_string(
        self, mock_llm_router, research_data, debate_result
    ):
        mock_llm_router.generate = AsyncMock(return_value=LLMResponse(
            content='{"verdict": "MAYBE", "confidence": 0.5, '
                    '"narrative": "ambiguous", "key_recommendations": [], '
                    '"risk_factors": []}',
            model="test", backend_name="test", success=True, latency_ms=100,
        ))
        agent = MetaAgent(mock_llm_router)
        verdict = await agent.synthesize(research_data, debate_result)
        assert verdict.verdict == "REVISE"  # invalid → default REVISE

    @pytest.mark.asyncio
    async def test_synthesize_no_res_result(
        self, mock_llm_router, research_data, debate_result
    ):
        agent = MetaAgent(mock_llm_router)
        verdict = await agent.synthesize(research_data, debate_result, res_result=None)
        assert isinstance(verdict, MetaAgentVerdict)
        assert verdict.res_score == 0.0

    def test_fallback_verdict_go(self, mock_llm_router):
        agent = MetaAgent(mock_llm_router)
        v = agent._create_fallback_verdict(
            {"overall_score": 0.8}, {"total_score": 80}, "test"
        )
        assert v.verdict == "GO"

    def test_fallback_verdict_revise(self, mock_llm_router):
        agent = MetaAgent(mock_llm_router)
        v = agent._create_fallback_verdict(
            {"overall_score": 0.6}, {"total_score": 60}, "test"
        )
        assert v.verdict == "REVISE"

    def test_fallback_verdict_drop(self, mock_llm_router):
        agent = MetaAgent(mock_llm_router)
        v = agent._create_fallback_verdict(
            {"overall_score": 0.3}, {"total_score": 30}, "test"
        )
        assert v.verdict == "DROP"

    def test_fallback_verdict_no_res(self, mock_llm_router):
        agent = MetaAgent(mock_llm_router)
        v = agent._create_fallback_verdict(
            {"overall_score": 0.5}, None, "test"
        )
        assert v.verdict == "REVISE"  # no res_score → REVISE default

    def test_build_synthesis_prompt(self, mock_llm_router, research_data, debate_result, res_result):
        agent = MetaAgent(mock_llm_router)
        prompt = agent._build_synthesis_prompt(research_data, debate_result, res_result)
        assert "메타 에이전트" in prompt
        assert "12345" in prompt
        assert "/no_think" in prompt

    def test_ensure_str_list(self, mock_llm_router):
        assert MetaAgent._ensure_str_list(["a", "b"]) == ["a", "b"]
        assert MetaAgent._ensure_str_list("single") == ["single"]
        assert MetaAgent._ensure_str_list(None) == []
        assert MetaAgent._ensure_str_list(123) == []
