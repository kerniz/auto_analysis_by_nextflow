"""
RNA Fusion Plugin
RNA fusion gene detection 감지 플러그인
"""

import re
from typing import Any

from .base import PipelineDefinition, SequencingTypePlugin


class RnaFusionPlugin(SequencingTypePlugin):

    @property
    def name(self) -> str:
        return "rnafusion"

    @property
    def display_name(self) -> str:
        return "RNA Fusion Gene Detection"

    @property
    def keywords(self) -> list[str]:
        return [
            "gene fusion", "fusion gene", "rna fusion",
            "chromosomal translocation", "chimeric transcript",
            "bcr-abl", "ews-fli1", "tmprss2-erg",
            "alk fusion", "ret fusion", "ntrk fusion",
            "breakpoint", "fusion detection",
            "structural rearrangement", "gene rearrangement",
            "oncogenic fusion",
        ]

    @property
    def sra_library_strategies(self) -> list[str]:
        return [
            "RNA-SEQ",
        ]

    @property
    def pipeline(self) -> PipelineDefinition:
        return PipelineDefinition(
            nf_core_name="nf-core/rnafusion",
            timeout_hours=4,
            required_params=["input", "outdir", "genome"],
            optional_params=[
                "skip_fastqc", "skip_multiqc",
                "tools", "all",
            ],
            container_image="nfcore/rnafusion:latest",
            analysis_type="fusion",
        )

    @property
    def priority(self) -> int:
        return 12

    @property
    def exclude_keywords(self) -> list[str]:
        return [
            "single-cell", "chip-seq", "atac-seq",
            "bisulfite", "wgs",
        ]

    def calculate_score(
        self,
        text: str,
        sra_metadata: dict[str, Any]
    ) -> tuple[float, list[str]]:
        score = 0.0
        evidence = []

        high_weight_keywords = [
            ("gene fusion", 0.5),
            ("fusion gene", 0.5),
            ("rna fusion", 0.5),
            ("chromosomal translocation", 0.45),
            ("chimeric transcript", 0.45),
        ]

        for keyword, weight in high_weight_keywords:
            if keyword in text:
                score += weight
                evidence.append(f"High-weight keyword: '{keyword}'")

        medium_weight_keywords = [
            ("bcr-abl", 0.3),
            ("ews-fli1", 0.3),
            ("tmprss2-erg", 0.3),
            ("alk fusion", 0.3),
            ("ret fusion", 0.3),
            ("ntrk fusion", 0.3),
            ("breakpoint", 0.2),
        ]

        for keyword, weight in medium_weight_keywords:
            if keyword in text:
                score += weight
                evidence.append(f"Medium-weight keyword: '{keyword}'")

        context_patterns = [
            (r'fusion\s+(detection|discovery|analysis)', 0.25),
            (r'structural\s+rearrangement', 0.25),
            (r'gene\s+rearrangement', 0.25),
            (r'oncogenic\s+fusion', 0.3),
        ]

        for pattern, weight in context_patterns:
            if re.search(pattern, text, re.IGNORECASE):
                score += weight
                evidence.append(f"Context pattern matched: '{pattern}'")

        return min(score, 1.0), evidence
