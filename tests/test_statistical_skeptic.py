"""Tests for Statistical Skeptic Agent"""

from datetime import datetime
from unittest.mock import AsyncMock, MagicMock

import pytest

from agents import AgentResponse, AgentRole
from agents.statistical_skeptic import StatisticalSkepticAgent
from backends.base import LLMResponse


@pytest.fixture
def mock_llm_router():
    router = MagicMock()
    router.generate = AsyncMock(return_value=LLMResponse(
        content='{"assessment": "통계 분석 적절", "score": 0.65, "confidence": 0.8, '
                '"key_points": ["p-value 보정 적절"], "concerns": ["샘플 크기 부족"], '
                '"questions": ["power analysis 수행?"], "rebuttal_to": null}',
        model="test-model",
        backend_name="test",
        success=True,
        latency_ms=100,
    ))
    return router


@pytest.fixture
def research_data():
    return {
        "paper_info": {"pmid": "12345", "title": "Test paper", "abstract": "..."},
        "sequencing_type": "bulk_rnaseq",
        "pipeline_info": {},
        "analysis_results": {},
    }


class TestStatisticalSkepticAgent:
    def test_role(self, mock_llm_router):
        agent = StatisticalSkepticAgent(mock_llm_router)
        assert agent.role == AgentRole.STATISTICAL_SKEPTIC

    def test_name(self, mock_llm_router):
        agent = StatisticalSkepticAgent(mock_llm_router)
        assert "통계" in agent.name
        assert "Statistical Skeptic" in agent.name

    def test_system_prompt(self, mock_llm_router):
        agent = StatisticalSkepticAgent(mock_llm_router)
        assert "통계" in agent.system_prompt or "biostatistics" in agent.system_prompt.lower()
        assert len(agent.system_prompt) > 100

    def test_system_prompt_keywords(self, mock_llm_router):
        agent = StatisticalSkepticAgent(mock_llm_router)
        prompt = agent.system_prompt.lower()
        assert "p-hacking" in prompt or "p-value" in prompt or "다중 비교" in prompt

    @pytest.mark.asyncio
    async def test_assess_success(self, mock_llm_router, research_data):
        agent = StatisticalSkepticAgent(mock_llm_router)
        response = await agent.assess(research_data, round_number=1)
        assert isinstance(response, AgentResponse)
        assert response.agent_role == AgentRole.STATISTICAL_SKEPTIC
        assert 0.0 <= response.score <= 1.0
        assert 0.0 <= response.confidence <= 1.0
        mock_llm_router.generate.assert_called_once()

    @pytest.mark.asyncio
    async def test_assess_round2(self, mock_llm_router, research_data):
        prev = [AgentResponse(
            agent_role=AgentRole.PHD_EXPERT, agent_name="PhD",
            assessment="Good", score=0.8, confidence=0.9,
            key_points=["Novel"], concerns=[], questions=["Stats ok?"],
            rebuttal_to=None, round_number=1,
            timestamp=datetime.now(), raw_llm_response="",
        )]
        agent = StatisticalSkepticAgent(mock_llm_router)
        response = await agent.assess(research_data, round_number=2, previous_responses=prev)
        assert response.round_number == 2

    @pytest.mark.asyncio
    async def test_assess_llm_failure(self, mock_llm_router, research_data):
        mock_llm_router.generate = AsyncMock(return_value=LLMResponse(
            content="", model="test", backend_name="test",
            success=False, latency_ms=0, error_message="timeout",
        ))
        agent = StatisticalSkepticAgent(mock_llm_router)
        response = await agent.assess(research_data)
        assert response.score == 0.5
        assert response.confidence == 0.0
        assert "오류" in response.concerns[0] or "error" in response.concerns[0].lower()

    @pytest.mark.asyncio
    async def test_assess_exception(self, mock_llm_router, research_data):
        mock_llm_router.generate = AsyncMock(side_effect=RuntimeError("LLM crash"))
        agent = StatisticalSkepticAgent(mock_llm_router)
        response = await agent.assess(research_data)
        assert response.score == 0.5
        assert response.confidence == 0.0

    def test_fallback_response(self, mock_llm_router):
        agent = StatisticalSkepticAgent(mock_llm_router)
        resp = agent._create_fallback_response(round_number=1, error_message="test err")
        assert resp.agent_role == AgentRole.STATISTICAL_SKEPTIC
        assert resp.score == 0.5
        assert "test err" in resp.concerns[0]
