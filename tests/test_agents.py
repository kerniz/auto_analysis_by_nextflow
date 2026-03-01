"""
Tests for Multi-Agent Debate System
멀티 에이전트 토론 시스템 테스트
"""

from datetime import datetime
from unittest.mock import AsyncMock, MagicMock

import pytest

from agents import (
    AgentResponse,
    AgentRole,
    DebateConfig,
    DebateManager,
    DebateRound,
    LaypersonAgent,
    PhDExpertAgent,
    UndergraduateAgent,
)
from agents.debate_manager import DebateResult
from backends.base import LLMResponse


@pytest.fixture
def mock_llm_router():
    router = MagicMock()
    router.generate = AsyncMock(return_value=LLMResponse(
        content='{"assessment": "Test assessment", "score": 0.7, "confidence": 0.8, '
                '"key_points": ["Point 1"], "concerns": ["Concern 1"], "questions": ["Q1"]}',
        model="test-model",
        backend_name="test-backend",
        success=True,
        latency_ms=100,
    ))
    router.backends = {}
    return router


@pytest.fixture
def sample_research_data():
    return {
        "paper": {
            "pmid": "40315330",
            "title": "Single-cell RNA sequencing reveals cellular heterogeneity",
            "abstract": "We performed single-cell RNA sequencing...",
        },
        "sequencing": {
            "sequencing_type": "scrna_seq",
            "confidence": 0.85,
        },
        "aggregated": {},
        "enrichment": {},
        "llm_analysis": {"consistency_rating": "PASS"},
    }


class TestAgentRole:
    def test_roles(self):
        assert AgentRole.LAYPERSON.value == "layperson"
        assert AgentRole.UNDERGRADUATE.value == "undergraduate"
        assert AgentRole.PHD_EXPERT.value == "phd_expert"


class TestAgentResponse:
    def test_create(self):
        resp = AgentResponse(
            agent_role=AgentRole.LAYPERSON,
            agent_name="Test Agent",
            assessment="Good paper",
            score=0.7,
            confidence=0.8,
            key_points=["Point 1"],
            concerns=["Concern 1"],
            questions=["Q1"],
            rebuttal_to=None,
            round_number=1,
            timestamp=datetime.now(),
            raw_llm_response="raw",
        )
        assert resp.score == 0.7
        assert resp.confidence == 0.8

    def test_to_dict(self):
        resp = AgentResponse(
            agent_role=AgentRole.PHD_EXPERT,
            agent_name="PhD",
            assessment="Assessment text",
            score=0.85,
            confidence=0.9,
            key_points=["Novel approach"],
            concerns=["Small sample"],
            questions=["Q1"],
            rebuttal_to=None,
            round_number=2,
            timestamp=datetime.now(),
            raw_llm_response="raw",
        )
        d = resp.to_dict()
        assert d["agent_role"] == "phd_expert"
        assert d["score"] == 0.85
        assert len(d["key_points"]) == 1


class TestDebateRound:
    def test_create(self):
        round_data = DebateRound(round_number=1, responses=[])
        assert round_data.round_number == 1
        assert round_data.responses == []
        assert round_data.consensus_score is None

    def test_to_dict(self):
        resp = AgentResponse(
            agent_role=AgentRole.LAYPERSON,
            agent_name="Test",
            assessment="Ok",
            score=0.7,
            confidence=0.8,
            key_points=[],
            concerns=[],
            questions=[],
            rebuttal_to=None,
            round_number=1,
            timestamp=datetime.now(),
            raw_llm_response="raw",
        )
        round_data = DebateRound(round_number=1, responses=[resp])
        d = round_data.to_dict()
        assert d["round_number"] == 1
        assert len(d["responses"]) == 1


class TestLaypersonAgent:
    def test_properties(self, mock_llm_router):
        agent = LaypersonAgent(mock_llm_router)
        assert agent.role == AgentRole.LAYPERSON
        assert "일반인" in agent.name
        assert len(agent.system_prompt) > 0

    @pytest.mark.asyncio
    async def test_assess(self, mock_llm_router, sample_research_data):
        agent = LaypersonAgent(mock_llm_router)
        response = await agent.assess(sample_research_data, round_number=1)
        assert isinstance(response, AgentResponse)
        assert response.agent_role == AgentRole.LAYPERSON
        assert 0.0 <= response.score <= 1.0
        mock_llm_router.generate.assert_called_once()


class TestUndergraduateAgent:
    def test_properties(self, mock_llm_router):
        agent = UndergraduateAgent(mock_llm_router)
        assert agent.role == AgentRole.UNDERGRADUATE
        assert "학사전공" in agent.name

    @pytest.mark.asyncio
    async def test_assess(self, mock_llm_router, sample_research_data):
        agent = UndergraduateAgent(mock_llm_router)
        response = await agent.assess(sample_research_data, round_number=1)
        assert isinstance(response, AgentResponse)
        assert response.agent_role == AgentRole.UNDERGRADUATE


class TestPhDExpertAgent:
    def test_properties(self, mock_llm_router):
        agent = PhDExpertAgent(mock_llm_router)
        assert agent.role == AgentRole.PHD_EXPERT
        assert "박사급" in agent.name

    @pytest.mark.asyncio
    async def test_assess(self, mock_llm_router, sample_research_data):
        agent = PhDExpertAgent(mock_llm_router)
        response = await agent.assess(sample_research_data, round_number=1)
        assert isinstance(response, AgentResponse)
        assert response.agent_role == AgentRole.PHD_EXPERT


class TestDebateConfig:
    def test_defaults(self):
        config = DebateConfig()
        assert config.num_rounds == 3
        assert config.consensus_threshold == 0.7
        assert config.parallel_assessment is True


class TestDebateManager:
    def test_create_default_panel(self, mock_llm_router):
        manager = DebateManager.create_default_panel(mock_llm_router)
        assert len(manager.agents) == 3
        roles = [a.role for a in manager.agents]
        assert AgentRole.LAYPERSON in roles
        assert AgentRole.UNDERGRADUATE in roles
        assert AgentRole.PHD_EXPERT in roles

    @pytest.mark.asyncio
    async def test_run_debate(self, mock_llm_router, sample_research_data):
        config = DebateConfig(num_rounds=2)
        manager = DebateManager.create_default_panel(mock_llm_router, config=config)
        result = await manager.run_debate(sample_research_data)

        assert isinstance(result, DebateResult)
        assert len(result.rounds) >= 1
        assert result.overall_verdict in ("PASS", "WARN", "FAIL")
        assert 0.0 <= result.overall_score <= 1.0

    def test_determine_verdict(self, mock_llm_router):
        manager = DebateManager.create_default_panel(mock_llm_router)
        assert manager._determine_verdict(0.9) == "PASS"
        assert manager._determine_verdict(0.6) == "WARN"
        assert manager._determine_verdict(0.3) == "FAIL"

    def test_weighted_scoring(self, mock_llm_router):
        manager = DebateManager.create_default_panel(mock_llm_router)
        scores = {
            AgentRole.PHD_EXPERT.value: 0.8,
            AgentRole.UNDERGRADUATE.value: 0.6,
            AgentRole.LAYPERSON.value: 0.7,
        }
        overall = manager._calculate_overall_score(scores)
        # PhD=0.5, Undergrad=0.3, Layperson=0.2
        expected = 0.8 * 0.5 + 0.6 * 0.3 + 0.7 * 0.2
        assert abs(overall - expected) < 0.05
