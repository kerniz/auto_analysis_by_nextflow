"""
Samplesheet Generator
nf-core 파이프라인별 samplesheet CSV 생성기
"""

import csv
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple
from pathlib import Path


@dataclass
class SamplesheetColumn:
    name: str
    required: bool = True
    default: Optional[str] = None


# nf-core pipeline samplesheet format definitions
SAMPLESHEET_FORMATS: Dict[str, List[SamplesheetColumn]] = {
    "nf-core/rnaseq": [
        SamplesheetColumn("sample"),
        SamplesheetColumn("fastq_1"),
        SamplesheetColumn("fastq_2", required=False, default=""),
        SamplesheetColumn("strandedness", required=False, default="auto"),
    ],
    "nf-core/scrnaseq": [
        SamplesheetColumn("sample"),
        SamplesheetColumn("fastq_1"),
        SamplesheetColumn("fastq_2", required=False, default=""),
        SamplesheetColumn("expected_cells", required=False, default="3000"),
    ],
    "nf-core/atacseq": [
        SamplesheetColumn("sample"),
        SamplesheetColumn("fastq_1"),
        SamplesheetColumn("fastq_2", required=False, default=""),
        SamplesheetColumn("replicate", required=False, default="1"),
    ],
    "nf-core/chipseq": [
        SamplesheetColumn("sample"),
        SamplesheetColumn("fastq_1"),
        SamplesheetColumn("fastq_2", required=False, default=""),
        SamplesheetColumn("antibody", required=False, default=""),
        SamplesheetColumn("control", required=False, default=""),
    ],
    "nf-core/sarek": [
        SamplesheetColumn("patient"),
        SamplesheetColumn("sample"),
        SamplesheetColumn("lane", required=False, default="lane_1"),
        SamplesheetColumn("fastq_1"),
        SamplesheetColumn("fastq_2", required=False, default=""),
        SamplesheetColumn("status", required=False, default="0"),
    ],
}


class SamplesheetGenerator:
    """Generates pipeline-specific samplesheet CSVs from SRA accession data."""

    def get_supported_pipelines(self) -> List[str]:
        """Return list of supported pipeline names."""
        return list(SAMPLESHEET_FORMATS.keys())

    def get_columns(self, pipeline_name: str) -> List[str]:
        """Return column names for a given pipeline."""
        fmt = SAMPLESHEET_FORMATS.get(pipeline_name)
        if not fmt:
            raise ValueError(f"Unsupported pipeline: {pipeline_name}")
        return [col.name for col in fmt]

    def generate(
        self,
        pipeline_name: str,
        srr_accessions: List[str],
        fastq_dir: Path,
        output_path: Path,
        metadata: Optional[Dict[str, Dict[str, str]]] = None,
    ) -> Path:
        """
        Generate a samplesheet CSV for the specified nf-core pipeline.

        Args:
            pipeline_name: nf-core pipeline name (e.g., "nf-core/rnaseq")
            srr_accessions: List of SRR accession IDs
            fastq_dir: Directory containing FASTQ files
            output_path: Where to write the CSV
            metadata: Optional per-sample metadata overrides
                      {srr_id: {column_name: value}}

        Returns:
            Path to the generated samplesheet CSV
        """
        fmt = SAMPLESHEET_FORMATS.get(pipeline_name)
        if not fmt:
            raise ValueError(
                f"Unsupported pipeline: {pipeline_name}. "
                f"Supported: {list(SAMPLESHEET_FORMATS.keys())}"
            )

        metadata = metadata or {}
        output_path.parent.mkdir(parents=True, exist_ok=True)

        headers = [col.name for col in fmt]
        rows = []

        for srr_id in srr_accessions:
            fastq_1, fastq_2 = self._resolve_fastq_paths(srr_id, fastq_dir)
            if fastq_1 is None:
                continue

            row = self._build_row(
                pipeline_name, fmt, srr_id, fastq_1, fastq_2,
                metadata.get(srr_id, {}),
            )
            rows.append(row)

        with open(output_path, "w", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(headers)
            writer.writerows(rows)

        return output_path

    def generate_from_fastq_pairs(
        self,
        pipeline_name: str,
        fastq_pairs: List[Tuple[str, Path, Optional[Path]]],
        output_path: Path,
        metadata: Optional[Dict[str, Dict[str, str]]] = None,
    ) -> Path:
        """
        Generate samplesheet from explicit (sample_name, fastq_1, fastq_2) tuples.
        Useful when FASTQ paths are already known.
        """
        fmt = SAMPLESHEET_FORMATS.get(pipeline_name)
        if not fmt:
            raise ValueError(f"Unsupported pipeline: {pipeline_name}")

        metadata = metadata or {}
        output_path.parent.mkdir(parents=True, exist_ok=True)

        headers = [col.name for col in fmt]
        rows = []

        for sample_name, fq1, fq2 in fastq_pairs:
            row = self._build_row(
                pipeline_name, fmt, sample_name, fq1, fq2,
                metadata.get(sample_name, {}),
            )
            rows.append(row)

        with open(output_path, "w", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(headers)
            writer.writerows(rows)

        return output_path

    def _resolve_fastq_paths(
        self, srr_id: str, fastq_dir: Path
    ) -> Tuple[Optional[Path], Optional[Path]]:
        """Find fastq_1 and fastq_2 for an SRR accession in the given directory."""
        # Common naming conventions from fetchngs / sra-tools
        patterns_r1 = [
            f"{srr_id}_1.fastq.gz",
            f"{srr_id}_R1.fastq.gz",
            f"{srr_id}_1.fq.gz",
            f"{srr_id}.fastq.gz",  # single-end
        ]
        patterns_r2 = [
            f"{srr_id}_2.fastq.gz",
            f"{srr_id}_R2.fastq.gz",
            f"{srr_id}_2.fq.gz",
        ]

        fastq_1 = None
        fastq_2 = None

        for pattern in patterns_r1:
            candidate = fastq_dir / pattern
            if candidate.exists():
                fastq_1 = candidate
                break

        if fastq_1 is None:
            # Try subdirectory: fastq_dir/srr_id/
            sub_dir = fastq_dir / srr_id
            if sub_dir.is_dir():
                for pattern in patterns_r1:
                    candidate = sub_dir / pattern
                    if candidate.exists():
                        fastq_1 = candidate
                        break

        if fastq_1 is None:
            return None, None

        for pattern in patterns_r2:
            candidate = fastq_1.parent / pattern
            if candidate.exists():
                fastq_2 = candidate
                break

        return fastq_1, fastq_2

    def _build_row(
        self,
        pipeline_name: str,
        fmt: List[SamplesheetColumn],
        sample_id: str,
        fastq_1: Optional[Path],
        fastq_2: Optional[Path],
        extra_metadata: Dict[str, str],
    ) -> List[str]:
        """Build a single row for the samplesheet."""
        row = []
        for col in fmt:
            if col.name in extra_metadata:
                row.append(extra_metadata[col.name])
            elif col.name == "sample":
                row.append(sample_id)
            elif col.name == "patient":
                row.append(sample_id)
            elif col.name == "fastq_1":
                row.append(str(fastq_1) if fastq_1 else "")
            elif col.name == "fastq_2":
                row.append(str(fastq_2) if fastq_2 else "")
            elif col.default is not None:
                row.append(col.default)
            else:
                row.append("")
        return row
