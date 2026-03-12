"""Tests for Experimental Critic Agent"""

from datetime import datetime
from unittest.mock import AsyncMock, MagicMock

import pytest

from agents import AgentResponse, AgentRole
from agents.experimental_critic import ExperimentalCriticAgent
from backends.base import LLMResponse


@pytest.fixture
def mock_llm_router():
    router = MagicMock()
    router.generate = AsyncMock(return_value=LLMResponse(
        content='{"assessment": "실험 설계 적절", "score": 0.68, "confidence": 0.75, '
                '"key_points": ["대조군 설정 양호"], "concerns": ["batch effect 미보정"], '
                '"questions": ["시퀀싱 깊이?"], "rebuttal_to": null}',
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


class TestExperimentalCriticAgent:
    def test_role(self, mock_llm_router):
        agent = ExperimentalCriticAgent(mock_llm_router)
        assert agent.role == AgentRole.EXPERIMENTAL_CRITIC

    def test_name(self, mock_llm_router):
        agent = ExperimentalCriticAgent(mock_llm_router)
        assert "실험" in agent.name
        assert "Experimental Critic" in agent.name

    def test_system_prompt(self, mock_llm_router):
        agent = ExperimentalCriticAgent(mock_llm_router)
        prompt = agent.system_prompt.lower()
        assert "wet-lab" in prompt or "실험" in agent.system_prompt
        assert len(agent.system_prompt) > 100

    def test_system_prompt_keywords(self, mock_llm_router):
        agent = ExperimentalCriticAgent(mock_llm_router)
        prompt = agent.system_prompt.lower()
        assert "batch" in prompt or "재현" in agent.system_prompt

    @pytest.mark.asyncio
    async def test_assess_success(self, mock_llm_router, research_data):
        agent = ExperimentalCriticAgent(mock_llm_router)
        response = await agent.assess(research_data, round_number=1)
        assert isinstance(response, AgentResponse)
        assert response.agent_role == AgentRole.EXPERIMENTAL_CRITIC
        assert 0.0 <= response.score <= 1.0

    @pytest.mark.asyncio
    async def test_assess_round2(self, mock_llm_router, research_data):
        prev = [AgentResponse(
            agent_role=AgentRole.PHD_EXPERT, agent_name="PhD",
            assessment="Needs validation", score=0.7, confidence=0.8,
            key_points=[], concerns=[], questions=["Validation plan?"],
            rebuttal_to=None, round_number=1,
            timestamp=datetime.now(), raw_llm_response="",
        )]
        agent = ExperimentalCriticAgent(mock_llm_router)
        response = await agent.assess(research_data, round_number=2, previous_responses=prev)
        assert response.round_number == 2

    @pytest.mark.asyncio
    async def test_assess_llm_failure(self, mock_llm_router, research_data):
        mock_llm_router.generate = AsyncMock(return_value=LLMResponse(
            content="", model="test", backend_name="test",
            success=False, latency_ms=0, error_message="timeout",
        ))
        agent = ExperimentalCriticAgent(mock_llm_router)
        response = await agent.assess(research_data)
        assert response.score == 0.5
        assert response.confidence == 0.0

    @pytest.mark.asyncio
    async def test_assess_exception(self, mock_llm_router, research_data):
        mock_llm_router.generate = AsyncMock(side_effect=RuntimeError("crash"))
        agent = ExperimentalCriticAgent(mock_llm_router)
        response = await agent.assess(research_data)
        assert response.score == 0.5

    def test_fallback_response(self, mock_llm_router):
        agent = ExperimentalCriticAgent(mock_llm_router)
        resp = agent._create_fallback_response(round_number=1, error_message="err")
        assert resp.agent_role == AgentRole.EXPERIMENTAL_CRITIC
        assert resp.score == 0.5
