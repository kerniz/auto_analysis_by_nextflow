"""Pipeline Event System for TUI / Web UI real-time updates."""

import asyncio
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any


class EventType(Enum):
    """파이프라인 이벤트 유형"""
    PIPELINE_START = "pipeline_start"
    PIPELINE_COMPLETE = "pipeline_complete"
    PMID_START = "pmid_start"
    PMID_STAGE_START = "pmid_stage_start"
    PMID_STAGE_COMPLETE = "pmid_stage_complete"
    PMID_STAGE_ERROR = "pmid_stage_error"
    PMID_COMPLETE = "pmid_complete"
    LOG_MESSAGE = "log_message"


# Stage name constants
STAGE_PUBMED = "pubmed"
STAGE_SRA = "sra"
STAGE_SEQUENCING = "sequencing"
STAGE_FETCHNGS = "fetchngs"
STAGE_NFCORE = "nfcore"
STAGE_ANALYSIS = "analysis"
STAGE_DATA_AGGREGATION = "data_aggregation"
STAGE_ENRICHMENT = "enrichment"
STAGE_LLM = "llm_consensus"
STAGE_DEBATE = "debate"
STAGE_RES = "research_evaluation"
STAGE_META = "meta_agent"
STAGE_REPORT = "report"

ALL_STAGES = [
    STAGE_PUBMED, STAGE_SRA, STAGE_SEQUENCING,
    STAGE_DATA_AGGREGATION, STAGE_ENRICHMENT,
    STAGE_LLM, STAGE_DEBATE, STAGE_REPORT,
]

STAGE_LABELS = {
    STAGE_PUBMED: "PubMed Metadata",
    STAGE_SRA: "SRA Exploration",
    STAGE_SEQUENCING: "Sequencing Detection",
    STAGE_FETCHNGS: "SRA Download",
    STAGE_NFCORE: "nf-core Execution",
    STAGE_ANALYSIS: "Downstream Analysis",
    STAGE_DATA_AGGREGATION: "Data Aggregation",
    STAGE_ENRICHMENT: "Pathway Analysis",
    STAGE_LLM: "LLM Consensus Analysis",
    STAGE_DEBATE: "Multi-Agent Debate",
    STAGE_RES: "Research Evaluation (RES)",
    STAGE_META: "Meta Agent",
    STAGE_REPORT: "Report Generation",
}


def get_stage_label(stage: str) -> str:
    """Return the i18n stage label for the current locale."""
    from core.i18n import t
    key = f"stage.{stage}"
    result = t(key)
    # Fall back to static dict if no translation found
    return result if result != key else STAGE_LABELS.get(stage, stage)


@dataclass
class PipelineEvent:
    """파이프라인 이벤트 데이터"""
    event_type: EventType
    pmid: str = ""
    stage: str = ""
    data: dict[str, Any] = field(default_factory=dict)
    message: str = ""
    timestamp: datetime = field(default_factory=datetime.now)

    def to_dict(self) -> dict[str, Any]:
        return {
            "event_type": self.event_type.value,
            "pmid": self.pmid,
            "stage": self.stage,
            "data": self.data,
            "message": self.message,
            "timestamp": self.timestamp.isoformat(),
        }


class PipelineEventBus:
    """발행-구독 이벤트 버스"""

    def __init__(self):
        self._listeners: list[Callable] = []
        self._history: list[PipelineEvent] = []
        self._max_history: int = 500

    def subscribe(self, callback: Callable):
        """리스너 콜백 등록"""
        self._listeners.append(callback)

    def unsubscribe(self, callback: Callable):
        """리스너 콜백 제거"""
        self._listeners = [cb for cb in self._listeners if cb is not callback]

    def emit(self, event: PipelineEvent):
        """동기 이벤트 발행"""
        self._history.append(event)
        if len(self._history) > self._max_history:
            self._history = self._history[-self._max_history:]
        for listener in self._listeners:
            try:
                listener(event)
            except Exception:
                pass

    async def emit_async(self, event: PipelineEvent):
        """비동기 이벤트 발행 (async 리스너 지원)"""
        self._history.append(event)
        if len(self._history) > self._max_history:
            self._history = self._history[-self._max_history:]
        for listener in self._listeners:
            try:
                result = listener(event)
                if asyncio.iscoroutine(result):
                    await result
            except Exception:
                pass

    @property
    def history(self) -> list[PipelineEvent]:
        return list(self._history)

    @property
    def listener_count(self) -> int:
        return len(self._listeners)

    def clear_history(self):
        self._history.clear()
