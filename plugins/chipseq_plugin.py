"""
ChIP-seq Plugin
ChIP sequencing 감지 플러그인
"""

import re
from typing import Dict, Any, Tuple, List

from .base import SequencingTypePlugin, DetectionResult, PipelineDefinition


class ChIPSeqPlugin(SequencingTypePlugin):
    
    @property
    def name(self) -> str:
        return "chip_seq"
    
    @property
    def display_name(self) -> str:
        return "ChIP-seq"
    
    @property
    def keywords(self) -> List[str]:
        return [
            "chip-seq", "chip seq", "chipseq",
            "chromatin immunoprecipitation",
            "histone modification", "histone mark",
            "transcription factor binding", "tf binding",
            "protein-dna interaction", "dna-protein interaction",
            "chip", "immunoprecipitation",
            "h3k4me3", "h3k27ac", "h3k4me1", "h3k27me3", "h3k36me3",
            "h3k9me3", "h3k9ac",
            "ctcf", "pol2", "rna polymerase",
            "epigenetic mark", "epigenomics",
            "antibody", "antibody-based",
        ]
    
    @property
    def sra_library_strategies(self) -> List[str]:
        return [
            "CHIP-SEQ",
            "CHIP SEQ",
            "CHROMATIN IMMUNOPRECIPITATION",
            "TF-SEQ",
        ]
    
    @property
    def pipeline(self) -> PipelineDefinition:
        return PipelineDefinition(
            nf_core_name="nf-core/chipseq",
            timeout_hours=2,
            required_params=["input", "outdir", "genome"],
            optional_params=[
                "skip_fastqc", "skip_multiqc",
                "narrow_peak", "broad_peak",
                "control"
            ],
            container_image="nfcore/chipseq:latest"
        )
    
    @property
    def priority(self) -> int:
        return 16
    
    @property
    def exclude_keywords(self) -> List[str]:
        return [
            "atac-seq", "rna-seq", "whole genome",
            "bisulfite", "cut&run", "cut&tag",
        ]
    
    def calculate_score(
        self, 
        text: str, 
        sra_metadata: Dict[str, Any]
    ) -> Tuple[float, List[str]]:
        score = 0.0
        evidence = []
        
        high_weight_keywords = [
            ("chip-seq", 0.45),
            ("chip seq", 0.45),
            ("chipseq", 0.45),
            ("chromatin immunoprecipitation", 0.5),
            ("transcription factor binding", 0.35),
            ("tf binding", 0.3),
        ]
        
        for keyword, weight in high_weight_keywords:
            if keyword in text:
                score += weight
                evidence.append(f"High-weight keyword: '{keyword}'")
        
        medium_weight_keywords = [
            ("histone modification", 0.25),
            ("histone mark", 0.25),
            ("protein-dna interaction", 0.2),
            ("dna-protein interaction", 0.2),
            ("epigenetic mark", 0.2),
            ("epigenomics", 0.15),
        ]
        
        for keyword, weight in medium_weight_keywords:
            if keyword in text:
                score += weight
                evidence.append(f"Medium-weight keyword: '{keyword}'")
        
        histone_marks = [
            "h3k4me3", "h3k27ac", "h3k4me1", "h3k27me3",
            "h3k36me3", "h3k9me3", "h3k9ac", "h3k14ac"
        ]
        
        for mark in histone_marks:
            if mark in text:
                score += 0.2
                evidence.append(f"Histone mark detected: '{mark}'")
        
        context_patterns = [
            (r'(peak|peak)\s+(calling|detection)', 0.2),
            (r'(transcription|tf)\s+factor\s+(binding|site)', 0.25),
            (r'(enhancer|promoter)\s+(region|element)', 0.15),
            (r'antibody\s+(against|for|targeting)', 0.2),
            (r'immunoprecipitation', 0.25),
        ]
        
        for pattern, weight in context_patterns:
            if re.search(pattern, text, re.IGNORECASE):
                score += weight
                evidence.append(f"Context pattern matched: '{pattern}'")
        
        return min(score, 1.0), evidence
