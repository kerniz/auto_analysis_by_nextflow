"""
Tests for nf-core Output Parser
출력 파서 테스트
"""

import pytest
from pathlib import Path

from nextflow.output_parser import OutputParser


class TestOutputParser:
    def test_supported_pipelines(self):
        parser = OutputParser()
        pipelines = parser.get_supported_pipelines()
        assert "nf-core/rnaseq" in pipelines
        assert "nf-core/scrnaseq" in pipelines
        assert "nf-core/atacseq" in pipelines
        assert "nf-core/chipseq" in pipelines

    def test_unsupported_pipeline(self):
        parser = OutputParser()
        results = parser.find_outputs("nf-core/unknown", Path("/tmp"))
        assert results == {}

    def test_find_rnaseq_outputs(self, tmp_path):
        """Mock nf-core/rnaseq output structure."""
        # Create mock files
        salmon_dir = tmp_path / "star_salmon" / "sample1"
        salmon_dir.mkdir(parents=True)
        (salmon_dir / "quant.sf").touch()

        counts = tmp_path / "star_salmon"
        (counts / "salmon.merged.gene_counts.tsv").touch()

        mqc_dir = tmp_path / "multiqc" / "star_salmon"
        mqc_dir.mkdir(parents=True)
        (mqc_dir / "multiqc_report.html").touch()

        parser = OutputParser()
        outputs = parser.find_outputs("nf-core/rnaseq", tmp_path)

        assert "salmon_quant" in outputs
        assert "counts_matrix" in outputs
        assert "multiqc_report" in outputs

    def test_find_scrnaseq_outputs(self, tmp_path):
        """Mock nf-core/scrnaseq output structure."""
        cr_dir = tmp_path / "cellranger" / "sample1" / "outs" / "filtered_feature_bc_matrix"
        cr_dir.mkdir(parents=True)
        (cr_dir / "matrix.mtx.gz").touch()

        rds = tmp_path / "sample1_filtered_matrix.rds"
        rds.touch()

        parser = OutputParser()
        outputs = parser.find_outputs("nf-core/scrnaseq", tmp_path)

        assert "cellranger_filtered" in outputs
        assert "rds_files" in outputs

    def test_find_atacseq_outputs(self, tmp_path):
        """Mock nf-core/atacseq output structure."""
        peaks_dir = tmp_path / "bwa" / "mergedLibrary" / "macs2" / "narrowPeak"
        peaks_dir.mkdir(parents=True)
        (peaks_dir / "sample1.narrowPeak").touch()

        bw_dir = tmp_path / "bwa" / "mergedLibrary" / "bigwig"
        bw_dir.mkdir(parents=True)
        (bw_dir / "sample1.bigWig").touch()

        parser = OutputParser()
        outputs = parser.find_outputs("nf-core/atacseq", tmp_path)

        assert "narrow_peaks" in outputs
        assert "bigwig" in outputs

    def test_find_empty_dir(self, tmp_path):
        parser = OutputParser()
        outputs = parser.find_outputs("nf-core/rnaseq", tmp_path)
        assert outputs == {}

    def test_get_primary_output(self):
        parser = OutputParser()
        output_files = {
            "counts_matrix": ["/data/counts.tsv"],
            "salmon_quant": ["/data/s1/quant.sf", "/data/s2/quant.sf"],
            "multiqc_report": ["/data/multiqc.html"],
        }
        primary = parser.get_primary_output("nf-core/rnaseq", output_files)
        assert primary["counts_matrix"] == "/data/counts.tsv"
        assert primary["salmon_quant"] == "/data/s1/quant.sf"

    def test_get_primary_output_empty(self):
        parser = OutputParser()
        primary = parser.get_primary_output("nf-core/rnaseq", {})
        assert primary == {}

    def test_dedup_results(self, tmp_path):
        """Ensure no duplicate paths in results."""
        salmon_dir = tmp_path / "star_salmon" / "s1"
        salmon_dir.mkdir(parents=True)
        (salmon_dir / "quant.sf").touch()

        parser = OutputParser()
        outputs = parser.find_outputs("nf-core/rnaseq", tmp_path)
        if "salmon_quant" in outputs:
            assert len(outputs["salmon_quant"]) == len(set(outputs["salmon_quant"]))
