"""
ATAC-seq Plugin
ATAC sequencing 감지 플러그인
"""

import re
from typing import Dict, Any, Tuple, List

from .base import SequencingTypePlugin, DetectionResult, PipelineDefinition


class AtacSeqPlugin(SequencingTypePlugin):
    
    @property
    def name(self) -> str:
        return "atac_seq"
    
    @property
    def display_name(self) -> str:
        return "ATAC-seq"
    
    @property
    def keywords(self) -> List[str]:
        return [
            "atac-seq", "atac seq", "atacseq",
            "assay for transposase-accessible chromatin",
            "chromatin accessibility", "open chromatin",
            "transposase-accessible", "tn5 transposase",
            "chromatin landscape", "accessible chromatin",
            "atac", "transposition",
            "single-cell atac", "scatac-seq",
            "multiome", "10x multiome",
        ]
    
    @property
    def sra_library_strategies(self) -> List[str]:
        return [
            "ATAC-SEQ",
            "ATAC SEQ",
            "DNASE-SEQ",  # Related assay
            "CHROMATIN",
        ]
    
    @property
    def pipeline(self) -> PipelineDefinition:
        return PipelineDefinition(
            nf_core_name="nf-core/atacseq",
            timeout_hours=2,
            required_params=["input", "outdir", "genome"],
            optional_params=[
                "skip_fastqc", "skip_multiqc",
                "narrow_peak", "broad_peak"
            ],
            container_image="nfcore/atacseq:latest"
        )
    
    @property
    def priority(self) -> int:
        return 15
    
    @property
    def exclude_keywords(self) -> List[str]:
        return [
            "chip-seq", "rna-seq", "whole genome",
            "bisulfite", "methylation",
        ]
    
    def calculate_score(
        self, 
        text: str, 
        sra_metadata: Dict[str, Any]
    ) -> Tuple[float, List[str]]:
        score = 0.0
        evidence = []
        
        high_weight_keywords = [
            ("atac-seq", 0.45),
            ("atac seq", 0.45),
            ("atacseq", 0.45),
            ("assay for transposase-accessible chromatin", 0.5),
            ("chromatin accessibility", 0.35),
            ("open chromatin", 0.3),
        ]
        
        for keyword, weight in high_weight_keywords:
            if keyword in text:
                score += weight
                evidence.append(f"High-weight keyword: '{keyword}'")
        
        medium_weight_keywords = [
            ("transposase-accessible", 0.25),
            ("tn5 transposase", 0.25),
            ("chromatin landscape", 0.2),
            ("accessible chromatin", 0.25),
            ("transposition", 0.15),
        ]
        
        for keyword, weight in medium_weight_keywords:
            if keyword in text:
                score += weight
                evidence.append(f"Medium-weight keyword: '{keyword}'")
        
        context_patterns = [
            (r'(peak|peak)\s+(calling|detection)', 0.2),
            (r'(chromatin|accessibility)\s+(profile|map|landscape)', 0.2),
            (r'(regulatory|enhancer|promoter)\s+(element|region)', 0.15),
            (r'single[- ]cell\s+atac', 0.3),
            (r'scatac', 0.3),
            (r'multiome', 0.25),
        ]
        
        for pattern, weight in context_patterns:
            if re.search(pattern, text, re.IGNORECASE):
                score += weight
                evidence.append(f"Context pattern matched: '{pattern}'")
        
        return min(score, 1.0), evidence
