"""
Nextflow Pipeline Executor
nf-core 파이프라인 실행기
"""

import asyncio
import logging
import shutil
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from plugins.base import PipelineDefinition

from .config import NextflowExecutionConfig
from .monitor import PipelineMonitor
from .output_parser import OutputParser
from .samplesheet import SamplesheetGenerator

logger = logging.getLogger(__name__)


@dataclass
class PipelineExecutionResult:
    """Result from a nf-core pipeline execution."""

    pipeline_name: str
    status: str  # "completed", "failed", "timeout"
    exit_code: int | None = None
    output_dir: Path | None = None
    execution_time_seconds: float = 0.0
    log_file: Path | None = None
    output_files: dict[str, list[str]] = field(default_factory=dict)
    trace_summary: dict[str, Any] = field(default_factory=dict)
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

    async def check_prerequisites(self) -> dict[str, bool]:
        """Check system prerequisites for pipeline execution."""
        results = {}

        # Check nextflow
        results["nextflow"] = shutil.which("nextflow") is not None

        # Check container runtime
        runtime = self.config.container_runtime.value
        results[runtime] = shutil.which(runtime) is not None

        # Check java (required by nextflow)
        results["java"] = shutil.which("java") is not None

        # Check Slurm tools if Slurm is enabled
        if self.config.slurm.enabled:
            for tool in ("sbatch", "squeue", "sinfo"):
                results[tool] = shutil.which(tool) is not None
            if not results.get("sbatch"):
                logger.warning(
                    "Slurm enabled but sbatch not found; "
                    "pipeline will fall back to local executor"
                )

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
        extra_params: dict[str, str] | None = None,
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

        # Generate dynamic Slurm config if enabled
        slurm_config_path = self._generate_slurm_config(output_dir)

        cmd = self._build_command(
            pipeline_def, samplesheet_path, output_dir, extra_params
        )

        # Include generated Slurm config file
        if slurm_config_path:
            cmd.extend(["-c", str(slurm_config_path)])

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
        extra_params: dict[str, str] | None = None,
    ) -> list[str]:
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

    @staticmethod
    def _escape_groovy_string(value: str) -> str:
        """Escape a string for safe inclusion in a Groovy/Nextflow config."""
        return value.replace("\\", "\\\\").replace("'", "\\'")

    def _generate_slurm_config(self, output_dir: Path) -> Path | None:
        """Generate a dynamic nextflow.config with Slurm settings.

        Returns the path to the generated config file, or None if Slurm
        is not enabled. All string values are validated at SlurmConfig
        creation time and escaped here for safe Groovy string inclusion.
        """
        slurm = self.config.slurm
        if not slurm.enabled:
            return None

        esc = self._escape_groovy_string

        lines = [
            "// Auto-generated Slurm configuration",
            "process {",
            "    executor = 'slurm'",
        ]

        if slurm.queue:
            lines.append(f"    queue = '{esc(slurm.queue)}'")
        if slurm.time_limit:
            lines.append(f"    time = '{esc(slurm.time_limit)}'")
        if slurm.memory:
            lines.append(f"    memory = '{esc(slurm.memory)}'")
        lines.append(f"    cpus = {slurm.cpus_per_task}")

        # Build clusterOptions combining account, qos, nodes, extra_args
        cluster_parts = []
        if slurm.account:
            cluster_parts.append(f"--account={esc(slurm.account)}")
        if slurm.qos:
            cluster_parts.append(f"--qos={esc(slurm.qos)}")
        if slurm.nodes > 1:
            cluster_parts.append(f"--nodes={slurm.nodes}")
        if slurm.extra_args:
            cluster_parts.append(esc(slurm.extra_args))
        if slurm.cluster_options:
            cluster_parts.append(esc(slurm.cluster_options))

        if cluster_parts:
            combined = " ".join(cluster_parts)
            lines.append(f"    clusterOptions = '{combined}'")

        lines.append("}")
        lines.append("")

        # Executor-level settings
        lines.append("executor {")
        lines.append(f"    submitRateLimit = '{esc(slurm.submit_rate_limit)}'")
        lines.append(f"    queueSize = {slurm.queue_size}")
        lines.append("}")
        lines.append("")

        config_path = output_dir / "slurm.config"
        config_path.write_text("\n".join(lines))
        logger.info(f"Generated Slurm config: {config_path}")
        return config_path
