"""
Sarek Plugin
WGS/WES variant calling 감지 플러그인
"""

import re
from typing import Any

from .base import PipelineDefinition, SequencingTypePlugin


class SarekPlugin(SequencingTypePlugin):

    @property
    def name(self) -> str:
        return "wgs_wes"

    @property
    def display_name(self) -> str:
        return "WGS/WES Variant Calling"

    @property
    def keywords(self) -> list[str]:
        return [
            "whole genome sequencing", "wgs",
            "whole exome sequencing", "wes",
            "variant calling", "somatic mutation", "germline variant",
            "snp", "indel", "copy number variation", "cnv",
            "structural variant", "targeted sequencing", "exome capture",
            "variant detection", "mutation analysis",
            "tumor-normal", "cancer genomics",
        ]

    @property
    def sra_library_strategies(self) -> list[str]:
        return [
            "WGS",
            "WXS",
            "TARGETED CAPTURE",
            "WHOLE GENOME",
        ]

    @property
    def pipeline(self) -> PipelineDefinition:
        return PipelineDefinition(
            nf_core_name="nf-core/sarek",
            timeout_hours=6,
            required_params=["input", "outdir", "genome"],
            optional_params=[
                "skip_fastqc", "skip_multiqc",
                "tools", "step", "joint_germline",
            ],
            container_image="nfcore/sarek:latest",
            analysis_type="variant",
        )

    @property
    def priority(self) -> int:
        return 25

    @property
    def exclude_keywords(self) -> list[str]:
        return [
            "rna-seq", "chip-seq", "atac-seq", "bisulfite",
        ]

    def calculate_score(
        self,
        text: str,
        sra_metadata: dict[str, Any]
    ) -> tuple[float, list[str]]:
        score = 0.0
        evidence = []

        high_weight_keywords = [
            ("whole genome sequencing", 0.5),
            ("wgs", 0.45),
            ("whole exome sequencing", 0.5),
            ("wes", 0.4),
            ("variant calling", 0.45),
            ("somatic mutation", 0.4),
            ("germline variant", 0.4),
        ]

        for keyword, weight in high_weight_keywords:
            if keyword in text:
                score += weight
                evidence.append(f"High-weight keyword: '{keyword}'")

        medium_weight_keywords = [
            ("snp", 0.2),
            ("indel", 0.2),
            ("copy number variation", 0.25),
            ("cnv", 0.2),
            ("structural variant", 0.25),
            ("targeted sequencing", 0.2),
            ("exome capture", 0.25),
        ]

        for keyword, weight in medium_weight_keywords:
            if keyword in text:
                score += weight
                evidence.append(f"Medium-weight keyword: '{keyword}'")

        context_patterns = [
            (r'variant\s+(detection|discovery|analysis)', 0.25),
            (r'mutation\s+(analysis|detection|calling)', 0.25),
            (r'tumor[- ]normal\s+(pair|matched)', 0.3),
            (r'cancer\s+genomics?', 0.2),
        ]

        for pattern, weight in context_patterns:
            if re.search(pattern, text, re.IGNORECASE):
                score += weight
                evidence.append(f"Context pattern matched: '{pattern}'")

        return min(score, 1.0), evidence
