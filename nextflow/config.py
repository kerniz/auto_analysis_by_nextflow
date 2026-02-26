"""
Nextflow Execution Configuration
Nextflow 파이프라인 실행 설정
"""

from dataclasses import dataclass, field
from typing import Dict, Optional
from pathlib import Path
from enum import Enum


class ContainerRuntime(Enum):
    DOCKER = "docker"
    SINGULARITY = "singularity"
    APPTAINER = "apptainer"
    CONDA = "conda"


@dataclass
class NextflowExecutionConfig:
    """Configuration for Nextflow pipeline execution."""

    enabled: bool = False
    work_dir: Path = field(default_factory=lambda: Path("./nextflow_work"))
    outdir: Path = field(default_factory=lambda: Path("./results/nfcore"))
    container_runtime: ContainerRuntime = ContainerRuntime.DOCKER
    profile: str = "docker"
    genome: str = "GRCh38"
    max_memory: str = "16.GB"
    max_cpus: int = 4
    max_time: str = "24.h"
    resume: bool = True
    cache_dir: Optional[Path] = None

    # fetchngs
    fetchngs_enabled: bool = True
    fetchngs_download_method: str = "sratools"

    # R analysis
    r_executable: str = "Rscript"
    r_scripts_dir: Optional[Path] = None

    # Python analysis
    scanpy_enabled: bool = False

    # Pipeline-specific parameter overrides
    pipeline_params: Dict[str, Dict[str, str]] = field(default_factory=dict)

    # Analysis parameters
    analysis_params: Dict[str, Dict[str, str]] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, data: Dict) -> "NextflowExecutionConfig":
        """Load from config.json nextflow_execution + analysis sections."""
        nf = data.get("nextflow_execution", {})
        analysis = data.get("analysis", {})

        container_str = nf.get("container_runtime", "docker")
        try:
            container_runtime = ContainerRuntime(container_str)
        except ValueError:
            container_runtime = ContainerRuntime.DOCKER

        config = cls(
            enabled=nf.get("enabled", False),
            work_dir=Path(nf.get("work_dir", "./nextflow_work")),
            outdir=Path(nf.get("outdir", "./results/nfcore")),
            container_runtime=container_runtime,
            profile=nf.get("profile", container_str),
            genome=nf.get("genome", "GRCh38"),
            max_memory=nf.get("max_memory", "16.GB"),
            max_cpus=nf.get("max_cpus", 4),
            max_time=nf.get("max_time", "24.h"),
            resume=nf.get("resume", True),
            pipeline_params=nf.get("pipeline_params", {}),
        )

        fetchngs = nf.get("fetchngs", {})
        config.fetchngs_enabled = fetchngs.get("enabled", True)
        config.fetchngs_download_method = fetchngs.get("download_method", "sratools")

        config.r_executable = analysis.get("r_executable", "Rscript")
        config.scanpy_enabled = analysis.get("scanpy_enabled", False)
        config.analysis_params = {
            k: v for k, v in analysis.items()
            if isinstance(v, dict)
        }

        cache_dir = nf.get("cache_dir")
        if cache_dir:
            config.cache_dir = Path(cache_dir)

        r_scripts_dir = analysis.get("r_scripts_dir")
        if r_scripts_dir:
            config.r_scripts_dir = Path(r_scripts_dir)

        return config
