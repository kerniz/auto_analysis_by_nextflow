"""
Tests for Samplesheet Generator
Samplesheet 생성기 테스트
"""

import csv
import pytest
from pathlib import Path

from nextflow.samplesheet import SamplesheetGenerator, SAMPLESHEET_FORMATS


class TestSamplesheetFormats:
    def test_supported_pipelines(self):
        gen = SamplesheetGenerator()
        pipelines = gen.get_supported_pipelines()
        assert "nf-core/rnaseq" in pipelines
        assert "nf-core/scrnaseq" in pipelines
        assert "nf-core/atacseq" in pipelines
        assert "nf-core/chipseq" in pipelines
        assert "nf-core/sarek" in pipelines

    def test_rnaseq_columns(self):
        gen = SamplesheetGenerator()
        cols = gen.get_columns("nf-core/rnaseq")
        assert cols == ["sample", "fastq_1", "fastq_2", "strandedness"]

    def test_scrnaseq_columns(self):
        gen = SamplesheetGenerator()
        cols = gen.get_columns("nf-core/scrnaseq")
        assert cols == ["sample", "fastq_1", "fastq_2", "expected_cells"]

    def test_atacseq_columns(self):
        gen = SamplesheetGenerator()
        cols = gen.get_columns("nf-core/atacseq")
        assert cols == ["sample", "fastq_1", "fastq_2", "replicate"]

    def test_chipseq_columns(self):
        gen = SamplesheetGenerator()
        cols = gen.get_columns("nf-core/chipseq")
        assert cols == ["sample", "fastq_1", "fastq_2", "antibody", "control"]

    def test_sarek_columns(self):
        gen = SamplesheetGenerator()
        cols = gen.get_columns("nf-core/sarek")
        assert cols == ["patient", "sample", "lane", "fastq_1", "fastq_2", "status"]

    def test_unsupported_pipeline(self):
        gen = SamplesheetGenerator()
        with pytest.raises(ValueError, match="Unsupported"):
            gen.get_columns("nf-core/unknown")


class TestSamplesheetGeneration:
    @pytest.fixture
    def fastq_dir(self, tmp_path):
        """Create mock FASTQ files."""
        fq_dir = tmp_path / "fastq"
        fq_dir.mkdir()
        # SRR111
        (fq_dir / "SRR111_1.fastq.gz").touch()
        (fq_dir / "SRR111_2.fastq.gz").touch()
        # SRR222
        (fq_dir / "SRR222_1.fastq.gz").touch()
        (fq_dir / "SRR222_2.fastq.gz").touch()
        # SRR333 (single-end)
        (fq_dir / "SRR333.fastq.gz").touch()
        return fq_dir

    def test_generate_rnaseq(self, tmp_path, fastq_dir):
        gen = SamplesheetGenerator()
        output = tmp_path / "samplesheet.csv"
        gen.generate(
            pipeline_name="nf-core/rnaseq",
            srr_accessions=["SRR111", "SRR222"],
            fastq_dir=fastq_dir,
            output_path=output,
        )
        assert output.exists()
        with open(output) as f:
            reader = csv.DictReader(f)
            rows = list(reader)
        assert len(rows) == 2
        assert rows[0]["sample"] == "SRR111"
        assert rows[0]["strandedness"] == "auto"
        assert "SRR111_1.fastq.gz" in rows[0]["fastq_1"]

    def test_generate_scrnaseq(self, tmp_path, fastq_dir):
        gen = SamplesheetGenerator()
        output = tmp_path / "ss.csv"
        gen.generate(
            pipeline_name="nf-core/scrnaseq",
            srr_accessions=["SRR111"],
            fastq_dir=fastq_dir,
            output_path=output,
        )
        with open(output) as f:
            reader = csv.DictReader(f)
            rows = list(reader)
        assert rows[0]["expected_cells"] == "3000"

    def test_generate_atacseq(self, tmp_path, fastq_dir):
        gen = SamplesheetGenerator()
        output = tmp_path / "ss.csv"
        gen.generate(
            pipeline_name="nf-core/atacseq",
            srr_accessions=["SRR111"],
            fastq_dir=fastq_dir,
            output_path=output,
        )
        with open(output) as f:
            reader = csv.DictReader(f)
            rows = list(reader)
        assert rows[0]["replicate"] == "1"

    def test_generate_chipseq(self, tmp_path, fastq_dir):
        gen = SamplesheetGenerator()
        output = tmp_path / "ss.csv"
        gen.generate(
            pipeline_name="nf-core/chipseq",
            srr_accessions=["SRR111"],
            fastq_dir=fastq_dir,
            output_path=output,
        )
        with open(output) as f:
            reader = csv.DictReader(f)
            rows = list(reader)
        assert "antibody" in rows[0]
        assert "control" in rows[0]

    def test_single_end(self, tmp_path, fastq_dir):
        gen = SamplesheetGenerator()
        output = tmp_path / "ss.csv"
        gen.generate(
            pipeline_name="nf-core/rnaseq",
            srr_accessions=["SRR333"],
            fastq_dir=fastq_dir,
            output_path=output,
        )
        with open(output) as f:
            reader = csv.DictReader(f)
            rows = list(reader)
        assert len(rows) == 1
        assert rows[0]["fastq_2"] == ""

    def test_missing_accession_skipped(self, tmp_path, fastq_dir):
        gen = SamplesheetGenerator()
        output = tmp_path / "ss.csv"
        gen.generate(
            pipeline_name="nf-core/rnaseq",
            srr_accessions=["SRR111", "SRR_NONEXIST"],
            fastq_dir=fastq_dir,
            output_path=output,
        )
        with open(output) as f:
            reader = csv.DictReader(f)
            rows = list(reader)
        assert len(rows) == 1  # only SRR111

    def test_metadata_override(self, tmp_path, fastq_dir):
        gen = SamplesheetGenerator()
        output = tmp_path / "ss.csv"
        gen.generate(
            pipeline_name="nf-core/rnaseq",
            srr_accessions=["SRR111"],
            fastq_dir=fastq_dir,
            output_path=output,
            metadata={"SRR111": {"strandedness": "reverse"}},
        )
        with open(output) as f:
            reader = csv.DictReader(f)
            rows = list(reader)
        assert rows[0]["strandedness"] == "reverse"

    def test_subdirectory_resolution(self, tmp_path):
        """Test FASTQ resolution in per-accession subdirectories."""
        fq_dir = tmp_path / "fastq"
        sub = fq_dir / "SRR999"
        sub.mkdir(parents=True)
        (sub / "SRR999_1.fastq.gz").touch()
        (sub / "SRR999_2.fastq.gz").touch()

        gen = SamplesheetGenerator()
        output = tmp_path / "ss.csv"
        gen.generate(
            pipeline_name="nf-core/rnaseq",
            srr_accessions=["SRR999"],
            fastq_dir=fq_dir,
            output_path=output,
        )
        with open(output) as f:
            reader = csv.DictReader(f)
            rows = list(reader)
        assert len(rows) == 1
        assert "SRR999_1.fastq.gz" in rows[0]["fastq_1"]

    def test_generate_from_fastq_pairs(self, tmp_path):
        gen = SamplesheetGenerator()
        output = tmp_path / "ss.csv"
        pairs = [
            ("sample1", Path("/data/s1_R1.fq.gz"), Path("/data/s1_R2.fq.gz")),
            ("sample2", Path("/data/s2_R1.fq.gz"), None),
        ]
        gen.generate_from_fastq_pairs(
            pipeline_name="nf-core/rnaseq",
            fastq_pairs=pairs,
            output_path=output,
        )
        with open(output) as f:
            reader = csv.DictReader(f)
            rows = list(reader)
        assert len(rows) == 2
        assert rows[0]["sample"] == "sample1"
        assert rows[1]["fastq_2"] == ""
