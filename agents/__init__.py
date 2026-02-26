"""
Multi-Agent Debate System
다중 에이전트 토론 시스템

연구 논문의 품질을 다양한 관점(일반인, 학사전공, 박사급)에서
평가하는 다중 에이전트 토론 시스템입니다.

A multi-agent debate system that evaluates research paper quality
from multiple perspectives (Layperson, Undergraduate, PhD Expert).
"""

from .base import (
    AgentRole,
    AgentResponse,
    DebateRound,
    DebateAgent,
)
from .layperson import LaypersonAgent
from .undergraduate import UndergraduateAgent
from .phd_expert import PhDExpertAgent
from .debate_manager import (
    DebateConfig,
    DebateResult,
    DebateManager,
)
from .report import (
    DebateReport,
    DebateReportGenerator,
)

__all__ = [
    # Base classes and data structures
    "AgentRole",
    "AgentResponse",
    "DebateRound",
    "DebateAgent",
    # Agent implementations
    "LaypersonAgent",
    "UndergraduateAgent",
    "PhDExpertAgent",
    # Debate management
    "DebateConfig",
    "DebateResult",
    "DebateManager",
    # Report generation
    "DebateReport",
    "DebateReportGenerator",
]
