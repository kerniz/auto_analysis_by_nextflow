"""
Bulk RNA-seq Plugin
Bulk RNA sequencing 감지 플러그인
"""

import re
from typing import Dict, Any, Tuple, List

from .base import SequencingTypePlugin, DetectionResult, PipelineDefinition


class BulkRnaSeqPlugin(SequencingTypePlugin):
    
    @property
    def name(self) -> str:
        return "bulk_rna_seq"
    
    @property
    def display_name(self) -> str:
        return "Bulk RNA-seq"
    
    @property
    def keywords(self) -> List[str]:
        return [
            "bulk rna-seq", "bulk rna sequencing",
            "rna-seq", "rna sequencing",
            "transcriptome", "gene expression profiling",
            "polya", "poly-a selection", "poly(a)",
            "ribosomal depletion", "rrna depletion",
            "total rna", "whole transcriptome",
            "strand-specific", "directional",
            "mrna sequencing", "messenger rna",
            "differential expression", "gene expression analysis",
            "transcriptomic analysis", "transcriptome profiling",
        ]
    
    @property
    def sra_library_strategies(self) -> List[str]:
        return [
            "RNA-SEQ",
            "RNA SEQ",
            "TRANSCRIPTOME",
            "MRNA",
        ]
    
    @property
    def pipeline(self) -> PipelineDefinition:
        return PipelineDefinition(
            nf_core_name="nf-core/rnaseq",
            timeout_hours=3,
            required_params=["input", "outdir", "genome"],
            optional_params=[
                "skip_fastqc", "skip_multiqc",
                "trimmer", "aligner", "pseudo_aligner"
            ],
            container_image="nfcore/rnaseq:latest"
        )
    
    @property
    def priority(self) -> int:
        return 20
    
    @property
    def exclude_keywords(self) -> List[str]:
        return [
            "single-cell", "single cell", "scrna-seq",
            "10x genomics", "cell ranger", "droplet",
            "whole genome", "wgs", "chip-seq", "atac-seq",
        ]
    
    def calculate_score(
        self, 
        text: str, 
        sra_metadata: Dict[str, Any]
    ) -> Tuple[float, List[str]]:
        score = 0.0
        evidence = []
        
        high_weight_keywords = [
            ("bulk rna-seq", 0.4),
            ("bulk rna sequencing", 0.4),
            ("rna-seq", 0.25),
            ("rna sequencing", 0.25),
            ("transcriptome", 0.2),
        ]
        
        for keyword, weight in high_weight_keywords:
            if keyword in text:
                score += weight
                evidence.append(f"High-weight keyword: '{keyword}'")
        
        medium_weight_keywords = [
            ("polya", 0.15),
            ("poly-a", 0.15),
            ("ribosomal depletion", 0.2),
            ("rrna depletion", 0.2),
            ("total rna", 0.15),
            ("whole transcriptome", 0.2),
            ("strand-specific", 0.15),
            ("mrna", 0.1),
        ]
        
        for keyword, weight in medium_weight_keywords:
            if keyword in text:
                score += weight
                evidence.append(f"Medium-weight keyword: '{keyword}'")
        
        context_patterns = [
            (r'differential\s+gene\s+expression', 0.2),
            (r'gene\s+expression\s+(analysis|profiling)', 0.2),
            (r'transcript(?:ome|ic)\s+(analysis|profiling)', 0.2),
            (r'(up|down)[- ]regulated\s+gene[s]?', 0.15),
            (r'differentially\s+expressed', 0.2),
            (r'fold[- ]change', 0.1),
        ]
        
        for pattern, weight in context_patterns:
            if re.search(pattern, text, re.IGNORECASE):
                score += weight
                evidence.append(f"Context pattern matched: '{pattern}'")
        
        scrna_indicators = [
            "single-cell", "single cell", "10x", "cell ranger",
            "droplet", "umis", "barcode"
        ]
        
        has_scrna = any(ind in text for ind in scrna_indicators)
        
        if "rna-seq" in text or "rna sequencing" in text:
            if not has_scrna:
                score += 0.2
                evidence.append("RNA-seq without scRNA-seq indicators")
        
        return min(score, 1.0), evidence
