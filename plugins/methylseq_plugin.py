"""
MethylSeq Plugin
DNA methylation (bisulfite sequencing) 감지 플러그인
"""

import re
from typing import Any

from .base import PipelineDefinition, SequencingTypePlugin


class MethylSeqPlugin(SequencingTypePlugin):

    @property
    def name(self) -> str:
        return "methylseq"

    @property
    def display_name(self) -> str:
        return "DNA Methylation (Bisulfite-seq)"

    @property
    def keywords(self) -> list[str]:
        return [
            "bisulfite sequencing", "methylation", "wgbs", "rrbs",
            "dna methylation", "methylseq",
            "cpg island", "epigenetic", "5-methylcytosine",
            "methyl-seq", "em-seq", "epigenome",
            "differentially methylated", "dmr",
        ]

    @property
    def sra_library_strategies(self) -> list[str]:
        return [
            "BISULFITE-SEQ",
            "METHYLATION",
            "RRBS",
        ]

    @property
    def pipeline(self) -> PipelineDefinition:
        return PipelineDefinition(
            nf_core_name="nf-core/methylseq",
            timeout_hours=4,
            required_params=["input", "outdir", "genome"],
            optional_params=[
                "skip_fastqc", "skip_multiqc",
                "aligner", "rrbs",
            ],
            container_image="nfcore/methylseq:latest",
            analysis_type="methylation",
        )

    @property
    def priority(self) -> int:
        return 18

    @property
    def exclude_keywords(self) -> list[str]:
        return [
            "rna-seq", "chip-seq", "atac-seq",
        ]

    def calculate_score(
        self,
        text: str,
        sra_metadata: dict[str, Any]
    ) -> tuple[float, list[str]]:
        score = 0.0
        evidence = []

        high_weight_keywords = [
            ("bisulfite sequencing", 0.5),
            ("methylation", 0.4),
            ("wgbs", 0.45),
            ("rrbs", 0.45),
            ("dna methylation", 0.5),
            ("methylseq", 0.45),
        ]

        for keyword, weight in high_weight_keywords:
            if keyword in text:
                score += weight
                evidence.append(f"High-weight keyword: '{keyword}'")

        medium_weight_keywords = [
            ("cpg island", 0.25),
            ("epigenetic", 0.2),
            ("5-methylcytosine", 0.25),
            ("methyl-seq", 0.25),
            ("em-seq", 0.25),
            ("epigenome", 0.15),
        ]

        for keyword, weight in medium_weight_keywords:
            if keyword in text:
                score += weight
                evidence.append(f"Medium-weight keyword: '{keyword}'")

        context_patterns = [
            (r'methylation\s+(level|profile|pattern)', 0.25),
            (r'cpg\s+(site|dinucleotide|methylation)', 0.25),
            (r'differentially\s+methylated\s+(region|site)', 0.3),
            (r'\bdmr\b', 0.2),
        ]

        for pattern, weight in context_patterns:
            if re.search(pattern, text, re.IGNORECASE):
                score += weight
                evidence.append(f"Context pattern matched: '{pattern}'")

        return min(score, 1.0), evidence
