"""Tests for Translation Evaluator Agent"""

from datetime import datetime
from unittest.mock import AsyncMock, MagicMock

import pytest

from agents import AgentResponse, AgentRole
from agents.translation_evaluator import TranslationEvaluatorAgent
from backends.base import LLMResponse


@pytest.fixture
def mock_llm_router():
    router = MagicMock()
    router.generate = AsyncMock(return_value=LLMResponse(
        content='{"assessment": "임상 전환 가능성 중간", "score": 0.55, "confidence": 0.7, '
                '"key_points": ["바이오마커 잠재력"], "concerns": ["FDA 경로 불명확"], '
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


class TestTranslationEvaluatorAgent:
    def test_role(self, mock_llm_router):
        agent = TranslationEvaluatorAgent(mock_llm_router)
        assert agent.role == AgentRole.TRANSLATION_EVALUATOR

    def test_name(self, mock_llm_router):
        agent = TranslationEvaluatorAgent(mock_llm_router)
        assert "번역" in agent.name
        assert "Translation Evaluator" in agent.name

    def test_system_prompt(self, mock_llm_router):
        agent = TranslationEvaluatorAgent(mock_llm_router)
        prompt = agent.system_prompt.lower()
        assert "clinical" in prompt or "임상" in agent.system_prompt
        assert len(agent.system_prompt) > 100

    def test_system_prompt_keywords(self, mock_llm_router):
        agent = TranslationEvaluatorAgent(mock_llm_router)
        prompt = agent.system_prompt.lower()
        assert "fda" in prompt or "patent" in prompt or "특허" in agent.system_prompt

    @pytest.mark.asyncio
    async def test_assess_success(self, mock_llm_router, research_data):
        agent = TranslationEvaluatorAgent(mock_llm_router)
        response = await agent.assess(research_data, round_number=1)
        assert isinstance(response, AgentResponse)
        assert response.agent_role == AgentRole.TRANSLATION_EVALUATOR
        assert 0.0 <= response.score <= 1.0

    @pytest.mark.asyncio
    async def test_assess_round2(self, mock_llm_router, research_data):
        prev = [AgentResponse(
            agent_role=AgentRole.BIOLOGICAL_REALIST, agent_name="BR",
            assessment="Bio ok", score=0.7, confidence=0.8,
            key_points=[], concerns=[], questions=["Market size?"],
            rebuttal_to=None, round_number=1,
            timestamp=datetime.now(), raw_llm_response="",
        )]
        agent = TranslationEvaluatorAgent(mock_llm_router)
        response = await agent.assess(research_data, round_number=2, previous_responses=prev)
        assert response.round_number == 2

    @pytest.mark.asyncio
    async def test_assess_llm_failure(self, mock_llm_router, research_data):
        mock_llm_router.generate = AsyncMock(return_value=LLMResponse(
            content="", model="test", backend_name="test",
            success=False, latency_ms=0, error_message="timeout",
        ))
        agent = TranslationEvaluatorAgent(mock_llm_router)
        response = await agent.assess(research_data)
        assert response.score == 0.5
        assert response.confidence == 0.0

    @pytest.mark.asyncio
    async def test_assess_exception(self, mock_llm_router, research_data):
        mock_llm_router.generate = AsyncMock(side_effect=RuntimeError("crash"))
        agent = TranslationEvaluatorAgent(mock_llm_router)
        response = await agent.assess(research_data)
        assert response.score == 0.5

    def test_fallback_response(self, mock_llm_router):
        agent = TranslationEvaluatorAgent(mock_llm_router)
        resp = agent._create_fallback_response(round_number=1, error_message="err")
        assert resp.agent_role == AgentRole.TRANSLATION_EVALUATOR
        assert resp.score == 0.5
