"""
Multi-Agent Debate System
다중 에이전트 토론 시스템

연구 논문의 품질을 다양한 관점(7인 패널 + 메타 에이전트)에서
평가하는 다중 에이전트 토론 시스템입니다.

A multi-agent debate system that evaluates research paper quality
from multiple perspectives (7-agent panel + Meta-Agent).
"""

from .base import (
    AgentResponse,
    AgentRole,
    DebateAgent,
    DebateRound,
)
from .biological_realist import BiologicalRealistAgent
from .debate_manager import (
    DebateConfig,
    DebateManager,
    DebateResult,
)
from .experimental_critic import ExperimentalCriticAgent
from .layperson import LaypersonAgent
from .phd_expert import PhDExpertAgent
from .report import (
    DebateReport,
    DebateReportGenerator,
)
from .statistical_skeptic import StatisticalSkepticAgent
from .translation_evaluator import TranslationEvaluatorAgent
from .undergraduate import UndergraduateAgent

__all__ = [
    # Base classes and data structures
    "AgentRole",
    "AgentResponse",
    "DebateRound",
    "DebateAgent",
    # Core agent implementations (3인)
    "LaypersonAgent",
    "UndergraduateAgent",
    "PhDExpertAgent",
    # Specialist agent implementations (4인)
    "StatisticalSkepticAgent",
    "BiologicalRealistAgent",
    "ExperimentalCriticAgent",
    "TranslationEvaluatorAgent",
    # Debate management
    "DebateConfig",
    "DebateResult",
    "DebateManager",
    # Report generation
    "DebateReport",
    "DebateReportGenerator",
]
