"""
Nextflow Pipeline Executor
nf-core 파이프라인 실행기
"""

import asyncio
import logging
import shutil
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional
from pathlib import Path

from plugins.base import PipelineDefinition
from .config import NextflowExecutionConfig
from .samplesheet import SamplesheetGenerator
from .monitor import PipelineMonitor
from .output_parser import OutputParser

logger = logging.getLogger(__name__)


@dataclass
class PipelineExecutionResult:
    """Result from a nf-core pipeline execution."""

    pipeline_name: str
    status: str  # "completed", "failed", "timeout"
    exit_code: Optional[int] = None
    output_dir: Optional[Path] = None
    execution_time_seconds: float = 0.0
    log_file: Optional[Path] = None
    output_files: Dict[str, List[str]] = field(default_factory=dict)
    trace_summary: Dict[str, Any] = field(default_factory=dict)
    error: str = ""

    def to_dict(self) -> dict:
        return {
            "pipeline_name": self.pipeline_name,
            "status": self.status,
            "exit_code": self.exit_code,
            "output_dir": str(self.output_dir) if self.output_dir else None,
            "execution_time_seconds": self.execution_time_seconds,
            "output_files": {
                k: [str(p) for p in v]
                for k, v in self.output_files.items()
            },
            "error": self.error,
        }


class NextflowExecutor:
    """Executes nf-core pipelines with proper configuration."""

    def __init__(self, config: NextflowExecutionConfig):
        self.config = config
        self.samplesheet_gen = SamplesheetGenerator()
        self.output_parser = OutputParser()

    async def check_prerequisites(self) -> Dict[str, bool]:
        """Check system prerequisites for pipeline execution."""
        results = {}

        # Check nextflow
        results["nextflow"] = shutil.which("nextflow") is not None

        # Check container runtime
        runtime = self.config.container_runtime.value
        results[runtime] = shutil.which(runtime) is not None

        # Check java (required by nextflow)
        results["java"] = shutil.which("java") is not None

        # Check disk space (basic check)
        try:
            import os
            stat = os.statvfs(str(self.config.outdir.parent))
            free_gb = (stat.f_bavail * stat.f_frsize) / (1024**3)
            results["disk_space_gb"] = round(free_gb, 1)
            results["sufficient_disk"] = free_gb > 10
        except Exception:
            results["sufficient_disk"] = True

        return results

    async def execute_pipeline(
        self,
        pipeline_def: PipelineDefinition,
        samplesheet_path: Path,
        output_dir: Path,
        extra_params: Optional[Dict[str, str]] = None,
    ) -> PipelineExecutionResult:
        """
        Execute an nf-core pipeline.

        Args:
            pipeline_def: Pipeline definition from sequencing plugin
            samplesheet_path: Path to generated samplesheet CSV
            output_dir: Output directory for results
            extra_params: Additional Nextflow parameters

        Returns:
            PipelineExecutionResult with status and output paths
        """
        output_dir.mkdir(parents=True, exist_ok=True)
        log_file = output_dir / "pipeline.log"

        cmd = self._build_command(
            pipeline_def, samplesheet_path, output_dir, extra_params
        )

        logger.info(
            f"Executing {pipeline_def.nf_core_name}: {' '.join(cmd)}"
        )

        start_time = time.time()
        timeout = pipeline_def.timeout_hours * 3600

        try:
            with open(log_file, "w") as log_f:
                process = await asyncio.create_subprocess_exec(
                    *cmd,
                    stdout=log_f,
                    stderr=asyncio.subprocess.STDOUT,
                )

                try:
                    await asyncio.wait_for(
                        process.wait(), timeout=timeout
                    )
                except asyncio.TimeoutError:
                    process.kill()
                    elapsed = time.time() - start_time
                    return PipelineExecutionResult(
                        pipeline_name=pipeline_def.nf_core_name,
                        status="timeout",
                        output_dir=output_dir,
                        log_file=log_file,
                        execution_time_seconds=elapsed,
                        error=f"Pipeline timed out after {pipeline_def.timeout_hours}h",
                    )

            elapsed = time.time() - start_time

            if process.returncode == 0:
                # Parse outputs
                output_files = self.output_parser.find_outputs(
                    pipeline_def.nf_core_name, output_dir
                )

                # Parse trace
                trace_file = output_dir / "pipeline_info" / "execution_trace.txt"
                monitor = PipelineMonitor(self.config.work_dir)
                trace_summary = monitor.parse_trace_file(trace_file)

                return PipelineExecutionResult(
                    pipeline_name=pipeline_def.nf_core_name,
                    status="completed",
                    exit_code=0,
                    output_dir=output_dir,
                    execution_time_seconds=elapsed,
                    log_file=log_file,
                    output_files=output_files,
                    trace_summary=trace_summary,
                )
            else:
                return PipelineExecutionResult(
                    pipeline_name=pipeline_def.nf_core_name,
                    status="failed",
                    exit_code=process.returncode,
                    output_dir=output_dir,
                    execution_time_seconds=elapsed,
                    log_file=log_file,
                    error=f"Pipeline exited with code {process.returncode}",
                )

        except Exception as e:
            elapsed = time.time() - start_time
            return PipelineExecutionResult(
                pipeline_name=pipeline_def.nf_core_name,
                status="failed",
                output_dir=output_dir,
                execution_time_seconds=elapsed,
                log_file=log_file,
                error=str(e),
            )

    def _build_command(
        self,
        pipeline_def: PipelineDefinition,
        samplesheet_path: Path,
        output_dir: Path,
        extra_params: Optional[Dict[str, str]] = None,
    ) -> List[str]:
        """Construct the nextflow run command."""
        cmd = [
            "nextflow", "run", pipeline_def.nf_core_name,
            "--input", str(samplesheet_path),
            "--outdir", str(output_dir),
            "--genome", self.config.genome,
            "-profile", self.config.profile,
            "--max_memory", self.config.max_memory,
            "--max_cpus", str(self.config.max_cpus),
            "--max_time", self.config.max_time,
        ]

        if self.config.resume:
            cmd.append("-resume")

        # Work directory
        work_dir = self.config.work_dir / pipeline_def.nf_core_name.replace("/", "_")
        cmd.extend(["-w", str(work_dir)])

        # Pipeline-specific params from config
        pipeline_params = self.config.pipeline_params.get(
            pipeline_def.nf_core_name, {}
        )
        for key, val in pipeline_params.items():
            cmd.extend([f"--{key}", str(val)])

        # Extra params
        if extra_params:
            for key, val in extra_params.items():
                cmd.extend([f"--{key}", str(val)])

        return cmd
