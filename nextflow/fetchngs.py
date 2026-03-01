"""
nf-core/fetchngs Runner
SRA 데이터 다운로드 (nf-core/fetchngs 래퍼)
"""

import asyncio
import logging
import time
from dataclasses import dataclass, field
from pathlib import Path

from .config import NextflowExecutionConfig

logger = logging.getLogger(__name__)


@dataclass
class FetchNGSResult:
    """Result from nf-core/fetchngs execution."""

    success: bool
    output_dir: Path
    fastq_dir: Path | None = None
    samplesheet_path: Path | None = None
    accessions_processed: list[str] = field(default_factory=list)
    accessions_failed: list[str] = field(default_factory=list)
    log_file: Path | None = None
    execution_time_seconds: float = 0.0
    error: str = ""

    def to_dict(self) -> dict:
        return {
            "success": self.success,
            "fastq_dir": str(self.fastq_dir) if self.fastq_dir else None,
            "samplesheet_path": str(self.samplesheet_path) if self.samplesheet_path else None,
            "accessions_processed": self.accessions_processed,
            "accessions_failed": self.accessions_failed,
            "execution_time_seconds": self.execution_time_seconds,
            "error": self.error,
        }


class FetchNGSRunner:
    """Runs nf-core/fetchngs to download SRA data as FASTQ files."""

    def __init__(self, config: NextflowExecutionConfig):
        self.config = config

    async def run(
        self,
        srr_accessions: list[str],
        output_dir: Path,
        pmid: str = "",
    ) -> FetchNGSResult:
        """
        Download SRA data using nf-core/fetchngs.

        Args:
            srr_accessions: List of SRR accession IDs
            output_dir: Output directory for downloaded data
            pmid: Associated PMID (for logging)

        Returns:
            FetchNGSResult with paths to downloaded files
        """
        if not srr_accessions:
            return FetchNGSResult(
                success=False,
                output_dir=output_dir,
                error="No SRR accessions provided",
            )

        output_dir.mkdir(parents=True, exist_ok=True)

        # Create accession file
        accession_file = self._create_accession_file(srr_accessions, output_dir)
        log_file = output_dir / "fetchngs.log"

        # Build command
        cmd = self._build_command(accession_file, output_dir)

        logger.info(
            f"Starting fetchngs for PMID {pmid}: "
            f"{len(srr_accessions)} accessions"
        )

        start_time = time.time()

        try:
            exit_code, duration = await self._execute_nextflow(
                cmd, log_file,
                timeout_seconds=self.config.pipeline_params.get(
                    "fetchngs", {}
                ).get("timeout", 7200),
            )

            elapsed = time.time() - start_time

            # Check outputs
            fastq_dir = self._find_fastq_dir(output_dir)
            samplesheet_path = self._find_samplesheet(output_dir)

            if exit_code == 0 and fastq_dir:
                processed = self._find_processed_accessions(
                    fastq_dir, srr_accessions
                )
                failed = [a for a in srr_accessions if a not in processed]
                return FetchNGSResult(
                    success=True,
                    output_dir=output_dir,
                    fastq_dir=fastq_dir,
                    samplesheet_path=samplesheet_path,
                    accessions_processed=processed,
                    accessions_failed=failed,
                    log_file=log_file,
                    execution_time_seconds=elapsed,
                )
            else:
                return FetchNGSResult(
                    success=False,
                    output_dir=output_dir,
                    log_file=log_file,
                    accessions_failed=srr_accessions,
                    execution_time_seconds=elapsed,
                    error=f"fetchngs exited with code {exit_code}",
                )

        except asyncio.TimeoutError:
            elapsed = time.time() - start_time
            return FetchNGSResult(
                success=False,
                output_dir=output_dir,
                log_file=log_file,
                accessions_failed=srr_accessions,
                execution_time_seconds=elapsed,
                error="fetchngs timed out",
            )
        except Exception as e:
            elapsed = time.time() - start_time
            return FetchNGSResult(
                success=False,
                output_dir=output_dir,
                log_file=log_file,
                accessions_failed=srr_accessions,
                execution_time_seconds=elapsed,
                error=str(e),
            )

    def _create_accession_file(
        self, accessions: list[str], output_dir: Path
    ) -> Path:
        """Write accession IDs to a text file for fetchngs input."""
        accession_file = output_dir / "accessions.csv"
        with open(accession_file, "w") as f:
            for acc in accessions:
                f.write(f"{acc}\n")
        return accession_file

    def _build_command(
        self, accession_file: Path, output_dir: Path
    ) -> list[str]:
        """Construct the nextflow run command for fetchngs."""
        cmd = [
            "nextflow", "run", "nf-core/fetchngs",
            "--input", str(accession_file),
            "--outdir", str(output_dir),
            "--download_method", self.config.fetchngs_download_method,
            "-profile", self.config.profile,
        ]

        if self.config.resume:
            cmd.append("-resume")

        work_dir = self.config.work_dir / "fetchngs"
        cmd.extend(["-w", str(work_dir)])

        return cmd

    async def _execute_nextflow(
        self, cmd: list[str], log_file: Path, timeout_seconds: int = 7200
    ) -> tuple:
        """Run nextflow as an async subprocess."""
        logger.info(f"Executing: {' '.join(cmd)}")

        with open(log_file, "w") as log_f:
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=log_f,
                stderr=asyncio.subprocess.STDOUT,
            )

            start = time.time()
            try:
                await asyncio.wait_for(
                    process.wait(), timeout=timeout_seconds
                )
            except asyncio.TimeoutError:
                process.kill()
                raise

            duration = time.time() - start

        return process.returncode, duration

    def _find_fastq_dir(self, output_dir: Path) -> Path | None:
        """Find the FASTQ output directory from fetchngs."""
        candidates = [
            output_dir / "fastq",
            output_dir / "fastqs",
            output_dir / "sra",
        ]
        for d in candidates:
            if d.is_dir():
                return d
        return output_dir if any(output_dir.glob("**/*.fastq.gz")) else None

    def _find_samplesheet(self, output_dir: Path) -> Path | None:
        """Find the auto-generated samplesheet from fetchngs."""
        candidates = [
            output_dir / "samplesheet" / "samplesheet.csv",
            output_dir / "samplesheet.csv",
        ]
        for f in candidates:
            if f.exists():
                return f
        return None

    def _find_processed_accessions(
        self, fastq_dir: Path, expected: list[str]
    ) -> list[str]:
        """Check which accessions have FASTQ files downloaded."""
        found = []
        for acc in expected:
            patterns = [
                f"{acc}*.fastq.gz",
                f"{acc}*.fq.gz",
            ]
            for pattern in patterns:
                if list(fastq_dir.rglob(pattern)):
                    found.append(acc)
                    break
        return found
