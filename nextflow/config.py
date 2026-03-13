"""
Nextflow Execution Configuration
Nextflow 파이프라인 실행 설정
"""

import re
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import ClassVar


class ContainerRuntime(Enum):
    DOCKER = "docker"
    SINGULARITY = "singularity"
    APPTAINER = "apptainer"
    PODMAN = "podman"
    CONDA = "conda"

# Whitelist pattern for Slurm string fields: alphanumeric, dash, underscore, colon, dot, slash, comma, equals, space
_SLURM_SAFE_PATTERN = re.compile(r'^[a-zA-Z0-9\-_:./,= ]*$')
_SLURM_TIME_PATTERN = re.compile(r'^\d{1,3}:\d{2}:\d{2}$')
_SLURM_MEMORY_PATTERN = re.compile(r'^\d+[KMGT]?[Bb]?$', re.IGNORECASE)


def _validate_slurm_field(value: str, field_name: str) -> str:
    """Validate a Slurm config string field against a safe character whitelist."""
    if not value:
        return value
    if not _SLURM_SAFE_PATTERN.match(value):
        raise ValueError(
            f"SlurmConfig.{field_name} contains unsafe characters: {value!r}. "
            f"Only alphanumeric, dash, underscore, colon, dot, slash, comma, equals, and space are allowed."
        )
    return value


@dataclass
class SlurmConfig:
    """Configuration for Slurm HPC executor."""

    enabled: bool = False
    queue: str = ""              # --partition
    account: str = ""            # --account
    qos: str = ""                # Quality of Service
    time_limit: str = "24:00:00" # --time
    memory: str = "16G"          # --mem
    cpus_per_task: int = 4       # --cpus-per-task
    nodes: int = 1               # --nodes
    extra_args: str = ""         # additional sbatch options
    submit_rate_limit: str = "50/2min"  # Nextflow submitRateLimit
    queue_size: int = 100        # Nextflow queueSize
    cluster_options: str = ""    # Nextflow clusterOptions

    def __post_init__(self):
        """Validate all string fields against injection."""
        for fname in ("queue", "account", "qos", "extra_args", "cluster_options"):
            _validate_slurm_field(getattr(self, fname), fname)
        if self.time_limit and not _SLURM_TIME_PATTERN.match(self.time_limit):
            raise ValueError(
                f"SlurmConfig.time_limit must be HH:MM:SS format, got: {self.time_limit!r}"
            )
        if self.memory and not _SLURM_MEMORY_PATTERN.match(self.memory):
            raise ValueError(
                f"SlurmConfig.memory must be like 16G, 4096M, etc., got: {self.memory!r}"
            )
        if self.cpus_per_task < 1 or self.cpus_per_task > 1024:
            raise ValueError(f"SlurmConfig.cpus_per_task out of range: {self.cpus_per_task}")
        if self.nodes < 1 or self.nodes > 1024:
            raise ValueError(f"SlurmConfig.nodes out of range: {self.nodes}")
        if self.queue_size < 1 or self.queue_size > 100000:
            raise ValueError(f"SlurmConfig.queue_size out of range: {self.queue_size}")

    @classmethod
    def from_dict(cls, data: dict) -> "SlurmConfig":
        """Load SlurmConfig from a dict."""
        return cls(
            enabled=data.get("enabled", False),
            queue=data.get("queue", ""),
            account=data.get("account", ""),
            qos=data.get("qos", ""),
            time_limit=data.get("time_limit", "24:00:00"),
            memory=data.get("memory", "16G"),
            cpus_per_task=data.get("cpus_per_task", 4),
            nodes=data.get("nodes", 1),
            extra_args=data.get("extra_args", ""),
            submit_rate_limit=data.get("submit_rate_limit", "50/2min"),
            queue_size=data.get("queue_size", 100),
            cluster_options=data.get("cluster_options", ""),
        )


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
    cache_dir: Path | None = None

    # fetchngs
    fetchngs_enabled: bool = True
    fetchngs_download_method: str = "sratools"

    # R analysis
    r_executable: str = "Rscript"
    r_scripts_dir: Path | None = None

    # Python analysis
    scanpy_enabled: bool = False

    # Slurm HPC executor
    slurm: SlurmConfig = field(default_factory=SlurmConfig)

    # Pipeline-specific parameter overrides
    pipeline_params: dict[str, dict[str, str]] = field(default_factory=dict)

    # Analysis parameters
    analysis_params: dict[str, dict[str, str]] = field(default_factory=dict)

    # Default pipeline-specific parameter presets
    DEFAULT_PIPELINE_PARAMS: ClassVar[dict[str, dict[str, object]]] = {
        "nf-core/rnaseq": {
            "aligner": "star_salmon",
            "pseudo_aligner": "salmon",
            "trimmer": "trimgalore",
            "skip_trimming": False,
            "skip_biotype_qc": False,
            "with_umi": False,
            "umitools_extract_method": "string",
            "min_mapped_reads": 5,
            "extra_salmon_quant_args": "",
        },
        "nf-core/scrnaseq": {
            "aligner": "cellranger",
            "protocol": "10XV3",
            "skip_emptydrops": False,
            "barcode_whitelist": None,
        },
        "nf-core/atacseq": {
            "narrow_peak": True,
            "broad_cutoff": 0.1,
            "macs_gsize": None,
            "min_reps_consensus": 1,
            "skip_consensus_peaks": False,
            "skip_diff_analysis": False,
            "read_length": 150,
        },
        "nf-core/chipseq": {
            "narrow_peak": True,
            "broad_cutoff": 0.1,
            "macs_gsize": None,
            "min_reps_consensus": 1,
            "skip_consensus_peaks": False,
            "skip_diff_analysis": False,
            "read_length": 150,
        },
        "nf-core/sarek": {
            "tools": "strelka,snpeff",
            "step": "mapping",
            "wes": False,
            "intervals": None,
            "joint_germline": False,
        },
        "nf-core/methylseq": {
            "aligner": "bismark",
            "comprehensive": True,
            "skip_deduplication": False,
            "rrbs": False,
            "em_seq": False,
        },
        "nf-core/cutandrun": {
            "peakcaller": "seacr",
            "use_control": True,
            "normalisation_mode": "CPM",
            "minimum_peak_overlap": 0.5,
        },
        "nf-core/rnafusion": {
            "tools": "arriba,starfusion",
            "all": False,
            "build_references": False,
        },
    }

    @classmethod
    def from_dict(cls, data: dict) -> "NextflowExecutionConfig":
        """Load from config.json nextflow_execution + analysis sections."""
        nf = data.get("nextflow_execution", {})
        analysis = data.get("analysis", {})

        container_str = nf.get("container_runtime", "docker")
        try:
            container_runtime = ContainerRuntime(container_str)
        except ValueError:
            container_runtime = ContainerRuntime.DOCKER

        # Merge default pipeline params with user-provided overrides
        user_pipeline_params = nf.get("pipeline_params", {})
        merged_pipeline_params: dict[str, dict[str, object]] = {}
        for pipeline, defaults in cls.DEFAULT_PIPELINE_PARAMS.items():
            merged = {k: v for k, v in defaults.items() if v is not None}
            if pipeline in user_pipeline_params:
                merged.update(user_pipeline_params[pipeline])
            merged_pipeline_params[pipeline] = merged
        # Include any user-specified pipelines not in defaults
        for pipeline, params in user_pipeline_params.items():
            if pipeline not in merged_pipeline_params:
                merged_pipeline_params[pipeline] = params

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
            pipeline_params=merged_pipeline_params,
        )

        slurm_data = nf.get("slurm", {})
        config.slurm = SlurmConfig.from_dict(slurm_data)

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
