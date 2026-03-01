"""
Sequencing Type Plugin Base
시퀀싱 타입 감지 플러그인의 추상 기본 클래스
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class SequencingCategory(Enum):
    SEQUENCING_CATEGORIES = "sequencing_categories"


@dataclass
class PipelineDefinition:
    nf_core_name: str
    timeout_hours: int
    required_params: list[str] = field(default_factory=list)
    optional_params: list[str] = field(default_factory=list)
    container_image: str = ""
    analysis_type: str = ""  # "deseq2", "seurat", "peak_diff", "variant"


@dataclass
class DetectionResult:
    sequencing_type: str
    confidence: float
    score: float
    evidence: list[str] = field(default_factory=list)
    sra_metadata_match: bool = False
    recommended_pipeline: PipelineDefinition | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


class SequencingTypePlugin(ABC):

    @property
    @abstractmethod
    def name(self) -> str:
        pass

    @property
    @abstractmethod
    def display_name(self) -> str:
        pass

    @property
    @abstractmethod
    def keywords(self) -> list[str]:
        pass

    @property
    @abstractmethod
    def sra_library_strategies(self) -> list[str]:
        pass

    @property
    @abstractmethod
    def pipeline(self) -> PipelineDefinition:
        pass

    @property
    def priority(self) -> int:
        return 50

    @property
    def exclude_keywords(self) -> list[str]:
        return []

    @abstractmethod
    def calculate_score(
        self,
        text: str,
        sra_metadata: dict[str, Any]
    ) -> tuple[float, list[str]]:
        pass

    def detect(
        self,
        pubmed_metadata: dict[str, Any],
        sra_metadata: dict[str, Any]
    ) -> DetectionResult:
        title = pubmed_metadata.get("title", "")
        abstract = pubmed_metadata.get("abstract", "")
        keywords = pubmed_metadata.get("keywords", [])

        combined_text = f"{title} {abstract} {' '.join(keywords)}".lower()

        has_exclusions = any(
            exc in combined_text for exc in self.exclude_keywords
        )

        if has_exclusions:
            return DetectionResult(
                sequencing_type=self.name,
                confidence=0.0,
                score=0.0,
                evidence=["Excluded by keyword filter"],
                sra_metadata_match=False
            )

        score, evidence = self.calculate_score(combined_text, sra_metadata)

        sra_match = self._check_sra_metadata(sra_metadata)
        if sra_match:
            score += 0.3
            evidence.append("SRA library strategy match")

        confidence = min(score, 1.0)

        return DetectionResult(
            sequencing_type=self.name,
            confidence=confidence,
            score=score,
            evidence=evidence,
            sra_metadata_match=sra_match,
            recommended_pipeline=self.pipeline,
            metadata={
                "display_name": self.display_name,
                "keywords_matched": [k for k in self.keywords if k in combined_text],
            }
        )

    def _check_sra_metadata(self, sra_metadata: dict[str, Any]) -> bool:
        for sra_id, meta in sra_metadata.items():
            strategy = meta.get("LibStrategy", "").upper()
            if strategy in [s.upper() for s in self.sra_library_strategies]:
                return True
        return False

    def __lt__(self, other):
        return self.priority < other.priority
