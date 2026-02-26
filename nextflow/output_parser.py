"""
nf-core Output Parser
nf-core 파이프라인 출력 디렉토리 파싱
"""

import logging
from typing import Dict, List
from pathlib import Path

logger = logging.getLogger(__name__)


# Known output file patterns per nf-core pipeline
OUTPUT_PATTERNS: Dict[str, Dict[str, List[str]]] = {
    "nf-core/rnaseq": {
        "salmon_quant": [
            "star_salmon/*/quant.sf",
            "salmon/*/quant.sf",
        ],
        "counts_matrix": [
            "star_salmon/salmon.merged.gene_counts.tsv",
            "star_salmon/salmon.merged.gene_counts_length_scaled.tsv",
            "salmon/salmon.merged.gene_counts.tsv",
        ],
        "counts_rds": [
            "star_salmon/deseq2_qc/*.rds",
            "star_salmon/*.rds",
        ],
        "bam_files": [
            "star_salmon/*.bam",
            "star_salmon/*.sorted.bam",
        ],
        "multiqc_report": [
            "multiqc/star_salmon/multiqc_report.html",
            "multiqc/multiqc_report.html",
        ],
        "tx2gene": [
            "star_salmon/salmon_tx2gene.tsv",
            "salmon/salmon_tx2gene.tsv",
        ],
    },
    "nf-core/scrnaseq": {
        "cellranger_filtered": [
            "cellranger/*/outs/filtered_feature_bc_matrix/",
            "cellranger/*/outs/filtered_feature_bc_matrix.h5",
        ],
        "cellranger_raw": [
            "cellranger/*/outs/raw_feature_bc_matrix/",
            "cellranger/*/outs/raw_feature_bc_matrix.h5",
        ],
        "star_filtered": [
            "star/*/Solo.out/Gene/filtered/",
        ],
        "alevin_output": [
            "alevin/*/alevin/quants_mat.gz",
        ],
        "h5ad_files": [
            "*_filtered_matrix.h5ad",
            "combined_filtered_matrix.h5ad",
        ],
        "rds_files": [
            "*_filtered_matrix.rds",
            "combined_filtered_matrix.rds",
        ],
        "multiqc_report": [
            "multiqc/multiqc_report.html",
        ],
    },
    "nf-core/atacseq": {
        "narrow_peaks": [
            "bwa/mergedLibrary/macs2/narrowPeak/*.narrowPeak",
            "bwa/mergedLibrary/macs3/narrowPeak/*.narrowPeak",
            "*/mergedLibrary/macs*/narrowPeak/*.narrowPeak",
        ],
        "broad_peaks": [
            "bwa/mergedLibrary/macs2/broadPeak/*.broadPeak",
            "*/mergedLibrary/macs*/broadPeak/*.broadPeak",
        ],
        "consensus_peaks": [
            "bwa/mergedLibrary/macs2/consensus/*.bed",
            "*/mergedLibrary/macs*/consensus/*.bed",
        ],
        "consensus_counts": [
            "bwa/mergedLibrary/macs2/consensus/deseq2/*.tsv",
            "*/mergedLibrary/macs*/consensus/featureCounts/*.txt",
        ],
        "bigwig": [
            "bwa/mergedLibrary/bigwig/*.bigWig",
            "*/mergedLibrary/bigwig/*.bigWig",
        ],
        "multiqc_report": [
            "multiqc/multiqc_report.html",
        ],
    },
    "nf-core/chipseq": {
        "narrow_peaks": [
            "bwa/mergedLibrary/macs2/narrowPeak/*.narrowPeak",
            "*/mergedLibrary/macs*/narrowPeak/*.narrowPeak",
        ],
        "broad_peaks": [
            "bwa/mergedLibrary/macs2/broadPeak/*.broadPeak",
            "*/mergedLibrary/macs*/broadPeak/*.broadPeak",
        ],
        "consensus_peaks": [
            "bwa/mergedLibrary/macs2/consensus/*/*.bed",
            "*/mergedLibrary/macs*/consensus/*/*.bed",
        ],
        "consensus_counts": [
            "bwa/mergedLibrary/macs2/consensus/*/featureCounts/*.txt",
            "*/mergedLibrary/macs*/consensus/*/featureCounts/*.txt",
        ],
        "bigwig": [
            "bwa/mergedLibrary/bigwig/*.bigWig",
            "*/mergedLibrary/bigwig/*.bigWig",
        ],
        "peak_annotation": [
            "bwa/mergedLibrary/macs2/narrowPeak/*.annotatePeaks.txt",
            "*/mergedLibrary/macs*/narrowPeak/*.annotatePeaks.txt",
        ],
        "multiqc_report": [
            "multiqc/multiqc_report.html",
        ],
    },
}


class OutputParser:
    """Parses nf-core pipeline output directories to find key result files."""

    def get_supported_pipelines(self) -> List[str]:
        """Return list of pipelines with defined output patterns."""
        return list(OUTPUT_PATTERNS.keys())

    def find_outputs(
        self, pipeline_name: str, output_dir: Path
    ) -> Dict[str, List[str]]:
        """
        Scan the output directory for expected result files.

        Args:
            pipeline_name: nf-core pipeline name
            output_dir: Root output directory

        Returns:
            Dict mapping output category to list of found file paths
        """
        patterns = OUTPUT_PATTERNS.get(pipeline_name)
        if not patterns:
            logger.warning(f"No output patterns defined for {pipeline_name}")
            return {}

        results: Dict[str, List[str]] = {}

        for category, globs in patterns.items():
            found_files = []
            for glob_pattern in globs:
                matches = list(output_dir.rglob(glob_pattern.lstrip("*/")))
                if not matches:
                    matches = list(output_dir.glob(glob_pattern))
                found_files.extend(str(p) for p in matches if p.exists())

            if found_files:
                # Remove duplicates, keep order
                seen = set()
                unique = []
                for f in found_files:
                    if f not in seen:
                        seen.add(f)
                        unique.append(f)
                results[category] = unique

        return results

    def get_primary_output(
        self, pipeline_name: str, output_files: Dict[str, List[str]]
    ) -> Dict[str, str]:
        """
        Get the primary output file for downstream analysis.

        Returns dict with keys like 'counts_matrix', 'filtered_matrix', etc.
        Each mapped to the first matching file.
        """
        primary_keys = {
            "nf-core/rnaseq": ["counts_matrix", "salmon_quant", "tx2gene"],
            "nf-core/scrnaseq": [
                "cellranger_filtered", "star_filtered",
                "h5ad_files", "rds_files",
            ],
            "nf-core/atacseq": [
                "consensus_peaks", "consensus_counts",
                "narrow_peaks", "bigwig",
            ],
            "nf-core/chipseq": [
                "consensus_peaks", "consensus_counts",
                "narrow_peaks", "peak_annotation",
            ],
        }

        result = {}
        keys = primary_keys.get(pipeline_name, [])
        for key in keys:
            files = output_files.get(key, [])
            if files:
                result[key] = files[0]

        return result
