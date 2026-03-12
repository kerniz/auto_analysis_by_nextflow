"""
Core - 바이오인포매틱스 연구 자동화 핵심 오케스트레이션

하나의 주제를 넣으면 관련 논문·유전체 데이터 수집 → 모델링 → 어노테이션 →
토론 → 아이디어 검증까지 자동으로 해주는 올인원 시스템.
"""

from core.cli import cli
from core.pipeline import AsyncPipeline, PipelineConfig, PipelineStatus, PMIDResult

__all__ = [
    "AsyncPipeline",
    "PipelineConfig",
    "PipelineStatus",
    "PMIDResult",
    "cli",
]
