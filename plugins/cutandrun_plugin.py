"""
CUT&RUN Plugin
CUT&RUN / CUT&Tag 감지 플러그인
"""

import re
from typing import Any

from .base import PipelineDefinition, SequencingTypePlugin


class CutAndRunPlugin(SequencingTypePlugin):

    @property
    def name(self) -> str:
        return "cutandrun"

    @property
    def display_name(self) -> str:
        return "CUT&RUN / CUT&Tag"

    @property
    def keywords(self) -> list[str]:
        return [
            "cut&run", "cutandrun", "cut&tag", "cutandtag",
            "cleavage under targets",
            "protein-dna interaction", "chromatin profiling",
            "pa-mnase", "pa-tn5",
            "histone modification", "transcription factor binding",
            "low-input chromatin",
        ]

    @property
    def sra_library_strategies(self) -> list[str]:
        return [
            "CUT-AND-RUN",
            "CUT&RUN",
            "OTHER",
        ]

    @property
    def pipeline(self) -> PipelineDefinition:
        return PipelineDefinition(
            nf_core_name="nf-core/cutandrun",
            timeout_hours=3,
            required_params=["input", "outdir", "genome"],
            optional_params=[
                "skip_fastqc", "skip_multiqc",
                "peakcaller",
            ],
            container_image="nfcore/cutandrun:latest",
            analysis_type="peak_diff",
        )

    @property
    def priority(self) -> int:
        return 17

    @property
    def exclude_keywords(self) -> list[str]:
        return [
            "chip-seq", "atac-seq", "rna-seq", "bisulfite",
        ]

    def calculate_score(
        self,
        text: str,
        sra_metadata: dict[str, Any]
    ) -> tuple[float, list[str]]:
        score = 0.0
        evidence = []

        high_weight_keywords = [
            ("cut&run", 0.5),
            ("cutandrun", 0.5),
            ("cut&tag", 0.5),
            ("cutandtag", 0.5),
            ("cleavage under targets", 0.45),
        ]

        for keyword, weight in high_weight_keywords:
            if keyword in text:
                score += weight
                evidence.append(f"High-weight keyword: '{keyword}'")

        medium_weight_keywords = [
            ("protein-dna interaction", 0.2),
            ("chromatin profiling", 0.25),
            ("pa-mnase", 0.3),
            ("pa-tn5", 0.3),
        ]

        for keyword, weight in medium_weight_keywords:
            if keyword in text:
                score += weight
                evidence.append(f"Medium-weight keyword: '{keyword}'")

        context_patterns = [
            (r'histone\s+modification', 0.2),
            (r'transcription\s+factor\s+binding', 0.2),
            (r'low[- ]input\s+chromatin', 0.25),
        ]

        for pattern, weight in context_patterns:
            if re.search(pattern, text, re.IGNORECASE):
                score += weight
                evidence.append(f"Context pattern matched: '{pattern}'")

        return min(score, 1.0), evidence
