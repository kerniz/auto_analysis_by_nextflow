"""
scRNA-seq Plugin
Single-cell RNA sequencing 감지 플러그인
"""

import re
from typing import Dict, Any, Tuple, List

from .base import SequencingTypePlugin, DetectionResult, PipelineDefinition


class ScRnaSeqPlugin(SequencingTypePlugin):
    
    @property
    def name(self) -> str:
        return "scrna_seq"
    
    @property
    def display_name(self) -> str:
        return "scRNA-seq"
    
    @property
    def keywords(self) -> List[str]:
        return [
            "single-cell", "single cell", "singlecell",
            "scrna-seq", "single-cell rna sequencing",
            "10x genomics", "drop-seq", "smart-seq", "smart-seq2",
            "cell ranger", "cellranger",
            "droplet", "microfluidic", "cell barcoding",
            "umis", "unique molecular identifiers",
            "cell capture", "cell isolation",
            "single nucleus", "snrna-seq",
            "c1", "fluidigm", "in-drop", "seq-well",
            "massively parallel", "cell hashing",
        ]
    
    @property
    def sra_library_strategies(self) -> List[str]:
        return [
            "SINGLE_CELL",
            "SCRNA-SEQ",
            "SINGLE CELL",
            "RNA-SEQ",  # Sometimes SRA uses generic strategy
        ]
    
    @property
    def pipeline(self) -> PipelineDefinition:
        return PipelineDefinition(
            nf_core_name="nf-core/scrnaseq",
            timeout_hours=4,
            required_params=["input", "outdir"],
            optional_params=[
                "skip_fastqc", "skip_multiqc", 
                "barcode_whitelist", "genome"
            ],
            container_image="nfcore/scrnaseq:latest"
        )
    
    @property
    def priority(self) -> int:
        return 10  # Higher priority
    
    @property
    def exclude_keywords(self) -> List[str]:
        return [
            "bulk rna-seq", "bulk sequencing",
            "whole genome", "dna-seq", "chip-seq", "atac-seq",
        ]
    
    def calculate_score(
        self, 
        text: str, 
        sra_metadata: Dict[str, Any]
    ) -> Tuple[float, List[str]]:
        score = 0.0
        evidence = []
        
        high_weight_keywords = [
            ("single-cell", 0.35),
            ("single cell", 0.35),
            ("scrna-seq", 0.4),
            ("10x genomics", 0.3),
            ("cell ranger", 0.3),
            ("cellranger", 0.3),
            ("drop-seq", 0.25),
            ("smart-seq", 0.25),
        ]
        
        for keyword, weight in high_weight_keywords:
            if keyword in text:
                score += weight
                evidence.append(f"High-weight keyword: '{keyword}'")
        
        medium_weight_keywords = [
            ("umis", 0.2),
            ("droplet", 0.15),
            ("microfluidic", 0.15),
            ("cell barcoding", 0.2),
            ("single nucleus", 0.25),
            ("snrna-seq", 0.3),
        ]
        
        for keyword, weight in medium_weight_keywords:
            if keyword in text:
                score += weight
                evidence.append(f"Medium-weight keyword: '{keyword}'")
        
        context_patterns = [
            (r'cell\s+type[s]?\s+(identification|classification|annotation)', 0.2),
            (r'(distinct|unique)\s+cell\s+population[s]?', 0.2),
            (r'cellular\s+heterogeneity', 0.2),
            (r'single[- ]cell\s+resolution', 0.25),
            (r'(count|number)\s+of\s+cells', 0.15),
            (r'barcode[d]?\s+(read|sequenc)', 0.2),
        ]
        
        for pattern, weight in context_patterns:
            if re.search(pattern, text, re.IGNORECASE):
                score += weight
                evidence.append(f"Context pattern matched: '{pattern}'")
        
        return min(score, 1.0), evidence
