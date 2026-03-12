"""Tests for Biological Realist Agent"""

from datetime import datetime
from unittest.mock import AsyncMock, MagicMock

import pytest

from agents import AgentResponse, AgentRole
from agents.biological_realist import BiologicalRealistAgent
from backends.base import LLMResponse


@pytest.fixture
def mock_llm_router():
    router = MagicMock()
    router.generate = AsyncMock(return_value=LLMResponse(
        content='{"assessment": "생물학적으로 타당", "score": 0.72, "confidence": 0.85, '
                '"key_points": ["경로 일관성"], "concerns": ["종간 보존성 미확인"], '
                '"questions": [], "rebuttal_to": null}',
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
        "sequencing_type": "scrna_seq",
        "pipeline_info": {},
        "analysis_results": {},
    }


class TestBiologicalRealistAgent:
    def test_role(self, mock_llm_router):
        agent = BiologicalRealistAgent(mock_llm_router)
        assert agent.role == AgentRole.BIOLOGICAL_REALIST

    def test_name(self, mock_llm_router):
        agent = BiologicalRealistAgent(mock_llm_router)
        assert "생물" in agent.name
        assert "Biological Realist" in agent.name

    def test_system_prompt(self, mock_llm_router):
        agent = BiologicalRealistAgent(mock_llm_router)
        prompt = agent.system_prompt.lower()
        assert "pathway" in prompt or "경로" in agent.system_prompt
        assert len(agent.system_prompt) > 100

    def test_system_prompt_keywords(self, mock_llm_router):
        agent = BiologicalRealistAgent(mock_llm_router)
        prompt = agent.system_prompt.lower()
        assert "cell type" in prompt or "세포 유형" in agent.system_prompt

    @pytest.mark.asyncio
    async def test_assess_success(self, mock_llm_router, research_data):
        agent = BiologicalRealistAgent(mock_llm_router)
        response = await agent.assess(research_data, round_number=1)
        assert isinstance(response, AgentResponse)
        assert response.agent_role == AgentRole.BIOLOGICAL_REALIST
        assert 0.0 <= response.score <= 1.0

    @pytest.mark.asyncio
    async def test_assess_round2(self, mock_llm_router, research_data):
        prev = [AgentResponse(
            agent_role=AgentRole.LAYPERSON, agent_name="LP",
            assessment="Seems ok", score=0.6, confidence=0.5,
            key_points=[], concerns=[], questions=[],
            rebuttal_to=None, round_number=1,
            timestamp=datetime.now(), raw_llm_response="",
        )]
        agent = BiologicalRealistAgent(mock_llm_router)
        response = await agent.assess(research_data, round_number=2, previous_responses=prev)
        assert response.round_number == 2

    @pytest.mark.asyncio
    async def test_assess_llm_failure(self, mock_llm_router, research_data):
        mock_llm_router.generate = AsyncMock(return_value=LLMResponse(
            content="", model="test", backend_name="test",
            success=False, latency_ms=0, error_message="timeout",
        ))
        agent = BiologicalRealistAgent(mock_llm_router)
        response = await agent.assess(research_data)
        assert response.score == 0.5
        assert response.confidence == 0.0

    @pytest.mark.asyncio
    async def test_assess_exception(self, mock_llm_router, research_data):
        mock_llm_router.generate = AsyncMock(side_effect=RuntimeError("crash"))
        agent = BiologicalRealistAgent(mock_llm_router)
        response = await agent.assess(research_data)
        assert response.score == 0.5

    def test_fallback_response(self, mock_llm_router):
        agent = BiologicalRealistAgent(mock_llm_router)
        resp = agent._create_fallback_response(round_number=1, error_message="err")
        assert resp.agent_role == AgentRole.BIOLOGICAL_REALIST
        assert resp.score == 0.5
