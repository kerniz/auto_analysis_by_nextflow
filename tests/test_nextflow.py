"""
Tests for Nextflow Execution Layer
Nextflow 실행 레이어 테스트
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from pathlib import Path

from nextflow.config import NextflowExecutionConfig, ContainerRuntime, SlurmConfig
from nextflow.fetchngs import FetchNGSRunner
from nextflow.executor import NextflowExecutor
from nextflow.monitor import PipelineMonitor, PipelineProgress
from plugins.base import PipelineDefinition


class TestNextflowConfig:
    def test_defaults(self):
        config = NextflowExecutionConfig()
        assert config.enabled is False
        assert config.genome == "GRCh38"
        assert config.container_runtime == ContainerRuntime.DOCKER
        assert config.max_cpus == 4

    def test_from_dict(self):
        data = {
            "nextflow_execution": {
                "enabled": True,
                "genome": "mm10",
                "container_runtime": "singularity",
                "max_cpus": 8,
                "max_memory": "32.GB",
                "fetchngs": {"enabled": True, "download_method": "aspera"},
                "pipeline_params": {
                    "nf-core/rnaseq": {"pseudo_aligner": "salmon"}
                },
            },
            "analysis": {
                "r_executable": "/usr/bin/Rscript",
                "scanpy_enabled": True,
                "deseq2": {"fc_threshold": "2.0"},
            },
        }
        config = NextflowExecutionConfig.from_dict(data)
        assert config.enabled is True
        assert config.genome == "mm10"
        assert config.container_runtime == ContainerRuntime.SINGULARITY
        assert config.max_cpus == 8
        assert config.fetchngs_download_method == "aspera"
        assert config.r_executable == "/usr/bin/Rscript"
        assert config.scanpy_enabled is True
        assert config.analysis_params["deseq2"]["fc_threshold"] == "2.0"

    def test_from_dict_empty(self):
        config = NextflowExecutionConfig.from_dict({})
        assert config.enabled is False
        assert config.genome == "GRCh38"

    def test_container_runtime_enum(self):
        assert ContainerRuntime.DOCKER.value == "docker"
        assert ContainerRuntime.SINGULARITY.value == "singularity"
        assert ContainerRuntime.APPTAINER.value == "apptainer"


class TestFetchNGSRunner:
    def test_init(self):
        config = NextflowExecutionConfig()
        runner = FetchNGSRunner(config)
        assert runner.config == config

    @pytest.mark.asyncio
    async def test_empty_accessions(self):
        config = NextflowExecutionConfig()
        runner = FetchNGSRunner(config)
        result = await runner.run([], Path("/tmp/out"))
        assert result.success is False
        assert "No SRR accessions" in result.error

    def test_create_accession_file(self, tmp_path):
        config = NextflowExecutionConfig()
        runner = FetchNGSRunner(config)
        acc_file = runner._create_accession_file(
            ["SRR111", "SRR222"], tmp_path
        )
        assert acc_file.exists()
        content = acc_file.read_text()
        assert "SRR111" in content
        assert "SRR222" in content

    def test_build_command(self, tmp_path):
        config = NextflowExecutionConfig(profile="docker")
        runner = FetchNGSRunner(config)
        cmd = runner._build_command(
            tmp_path / "accessions.csv", tmp_path / "output"
        )
        assert "nextflow" in cmd
        assert "nf-core/fetchngs" in cmd
        assert "-profile" in cmd
        assert "docker" in cmd
        assert "-resume" in cmd

    def test_find_fastq_dir(self, tmp_path):
        config = NextflowExecutionConfig()
        runner = FetchNGSRunner(config)
        # Create fastq dir
        fq_dir = tmp_path / "fastq"
        fq_dir.mkdir()
        assert runner._find_fastq_dir(tmp_path) == fq_dir

    def test_find_fastq_dir_none(self, tmp_path):
        config = NextflowExecutionConfig()
        runner = FetchNGSRunner(config)
        assert runner._find_fastq_dir(tmp_path) is None

    def test_find_samplesheet(self, tmp_path):
        config = NextflowExecutionConfig()
        runner = FetchNGSRunner(config)
        ss_dir = tmp_path / "samplesheet"
        ss_dir.mkdir()
        ss_file = ss_dir / "samplesheet.csv"
        ss_file.touch()
        assert runner._find_samplesheet(tmp_path) == ss_file


class TestNextflowExecutor:
    def test_build_command(self):
        config = NextflowExecutionConfig(
            genome="GRCh38", profile="docker",
            max_memory="16.GB", max_cpus=4,
        )
        executor = NextflowExecutor(config)
        pipeline_def = PipelineDefinition(
            nf_core_name="nf-core/rnaseq",
            timeout_hours=3,
            analysis_type="deseq2",
        )
        cmd = executor._build_command(
            pipeline_def, Path("/tmp/ss.csv"), Path("/tmp/out")
        )
        assert "nextflow" in cmd
        assert "nf-core/rnaseq" in cmd
        assert "--genome" in cmd
        assert "GRCh38" in cmd
        assert "--max_cpus" in cmd
        assert "4" in cmd
        assert "-resume" in cmd

    def test_build_command_with_extra_params(self):
        config = NextflowExecutionConfig()
        executor = NextflowExecutor(config)
        pipeline_def = PipelineDefinition(
            nf_core_name="nf-core/scrnaseq", timeout_hours=4,
        )
        cmd = executor._build_command(
            pipeline_def, Path("/ss.csv"), Path("/out"),
            extra_params={"protocol": "10XV3"},
        )
        assert "--protocol" in cmd
        assert "10XV3" in cmd

    @pytest.mark.asyncio
    @patch("shutil.which")
    async def test_check_prerequisites(self, mock_which):
        mock_which.side_effect = lambda x: (
            "/usr/bin/nextflow" if x == "nextflow"
            else "/usr/bin/docker" if x == "docker"
            else "/usr/bin/java" if x == "java"
            else None
        )
        config = NextflowExecutionConfig()
        executor = NextflowExecutor(config)
        results = await executor.check_prerequisites()
        assert results["nextflow"] is True
        assert results["docker"] is True
        assert results["java"] is True


class TestPipelineMonitor:
    def test_parse_empty_log(self, tmp_path):
        monitor = PipelineMonitor(tmp_path)
        log_file = tmp_path / "nonexistent.log"
        progress = monitor.parse_log_progress(log_file)
        assert progress.status == "not_started"

    def test_parse_completed_log(self, tmp_path):
        log_file = tmp_path / "pipeline.log"
        log_file.write_text("""
[ab/123456] process > NFCORE_RNASEQ:FASTQC (1) [100%] 2 of 2 ✔
[cd/789012] process > NFCORE_RNASEQ:TRIMGALORE (1) [100%] 2 of 2 ✔
Execution complete -- Goodbye
Duration : 1h 23m 45s
""")
        monitor = PipelineMonitor(tmp_path)
        progress = monitor.parse_log_progress(log_file)
        assert progress.status == "completed"
        assert progress.percent_complete == 100.0

    def test_parse_failed_log(self, tmp_path):
        log_file = tmp_path / "pipeline.log"
        log_file.write_text("""
[ab/123456] process > NFCORE_RNASEQ:FASTQC (1) [100%] 2 of 2 ✔
Error executing process > 'NFCORE_RNASEQ:ALIGN'
""")
        monitor = PipelineMonitor(tmp_path)
        progress = monitor.parse_log_progress(log_file)
        assert progress.status == "failed"

    def test_parse_trace_file(self, tmp_path):
        trace = tmp_path / "trace.txt"
        trace.write_text("task_id\tname\tstatus\trealtime\t%cpu\tpeak_rss\n"
                         "1\tFASTQC\tCOMPLETED\t5m 30s\t150.0\t1.2 GB\n"
                         "2\tSTAR\tCOMPLETED\t25m 10s\t400.0\t8.5 GB\n")
        monitor = PipelineMonitor(tmp_path)
        result = monitor.parse_trace_file(trace)
        assert "FASTQC" in result
        assert result["FASTQC"]["status"] == "COMPLETED"

    def test_parse_trace_file_missing(self, tmp_path):
        monitor = PipelineMonitor(tmp_path)
        assert monitor.parse_trace_file(tmp_path / "nope.txt") == {}


class TestSlurmConfig:
    def test_defaults(self):
        cfg = SlurmConfig()
        assert cfg.enabled is False
        assert cfg.queue == ""
        assert cfg.account == ""
        assert cfg.qos == ""
        assert cfg.time_limit == "24:00:00"
        assert cfg.memory == "16G"
        assert cfg.cpus_per_task == 4
        assert cfg.nodes == 1
        assert cfg.extra_args == ""
        assert cfg.submit_rate_limit == "50/2min"
        assert cfg.queue_size == 100
        assert cfg.cluster_options == ""

    def test_from_dict(self):
        data = {
            "enabled": True,
            "queue": "gpu",
            "account": "mylab",
            "qos": "high",
            "time_limit": "48:00:00",
            "memory": "64G",
            "cpus_per_task": 16,
            "nodes": 2,
            "extra_args": "--gres=gpu:1",
            "submit_rate_limit": "100/5min",
            "queue_size": 200,
            "cluster_options": "--constraint=fast",
        }
        cfg = SlurmConfig.from_dict(data)
        assert cfg.enabled is True
        assert cfg.queue == "gpu"
        assert cfg.account == "mylab"
        assert cfg.qos == "high"
        assert cfg.time_limit == "48:00:00"
        assert cfg.memory == "64G"
        assert cfg.cpus_per_task == 16
        assert cfg.nodes == 2
        assert cfg.extra_args == "--gres=gpu:1"
        assert cfg.submit_rate_limit == "100/5min"
        assert cfg.queue_size == 200
        assert cfg.cluster_options == "--constraint=fast"

    def test_from_dict_partial(self):
        data = {"enabled": True, "queue": "batch"}
        cfg = SlurmConfig.from_dict(data)
        assert cfg.enabled is True
        assert cfg.queue == "batch"
        assert cfg.memory == "16G"  # default preserved

    def test_from_dict_empty(self):
        cfg = SlurmConfig.from_dict({})
        assert cfg.enabled is False
        assert cfg.queue == ""

    def test_disabled_by_default(self):
        nf_config = NextflowExecutionConfig()
        assert nf_config.slurm.enabled is False

    def test_from_dict_in_nextflow_config(self):
        data = {
            "nextflow_execution": {
                "enabled": True,
                "slurm": {
                    "enabled": True,
                    "queue": "compute",
                    "account": "proj123",
                },
            }
        }
        config = NextflowExecutionConfig.from_dict(data)
        assert config.slurm.enabled is True
        assert config.slurm.queue == "compute"
        assert config.slurm.account == "proj123"

    def test_from_dict_no_slurm_section(self):
        data = {"nextflow_execution": {"enabled": True}}
        config = NextflowExecutionConfig.from_dict(data)
        assert config.slurm.enabled is False


class TestSlurmValidation:
    def test_unsafe_queue_rejected(self):
        with pytest.raises(ValueError, match="unsafe characters"):
            SlurmConfig(enabled=True, queue="batch'; rm -rf /")

    def test_unsafe_account_rejected(self):
        with pytest.raises(ValueError, match="unsafe characters"):
            SlurmConfig(enabled=True, account="lab\nmalicious")

    def test_unsafe_extra_args_rejected(self):
        with pytest.raises(ValueError, match="unsafe characters"):
            SlurmConfig(enabled=True, extra_args="--gres=gpu:1; echo pwned")

    def test_unsafe_cluster_options_rejected(self):
        with pytest.raises(ValueError, match="unsafe characters"):
            SlurmConfig(enabled=True, cluster_options="'; cat /etc/passwd; '")

    def test_invalid_time_format(self):
        with pytest.raises(ValueError, match="HH:MM:SS"):
            SlurmConfig(enabled=True, time_limit="forever")

    def test_invalid_memory_format(self):
        with pytest.raises(ValueError, match="memory"):
            SlurmConfig(enabled=True, memory="lots")

    def test_cpus_out_of_range(self):
        with pytest.raises(ValueError, match="cpus_per_task"):
            SlurmConfig(enabled=True, cpus_per_task=0)

    def test_nodes_out_of_range(self):
        with pytest.raises(ValueError, match="nodes"):
            SlurmConfig(enabled=True, nodes=-1)

    def test_valid_complex_values(self):
        cfg = SlurmConfig(
            enabled=True,
            queue="gpu-a100",
            account="my_lab_123",
            extra_args="--gres=gpu:2 --exclusive",
            cluster_options="--constraint=v100",
        )
        assert cfg.queue == "gpu-a100"
        assert cfg.extra_args == "--gres=gpu:2 --exclusive"


class TestSlurmExecutor:
    def test_build_command_slurm_no_inline_params(self):
        """Slurm params are in generated config, not in command line."""
        slurm = SlurmConfig(
            enabled=True,
            queue="batch",
            time_limit="12:00:00",
            memory="32G",
            cpus_per_task=8,
        )
        config = NextflowExecutionConfig(
            genome="GRCh38", profile="singularity",
            max_memory="16.GB", max_cpus=4,
            slurm=slurm,
        )
        executor = NextflowExecutor(config)
        pipeline_def = PipelineDefinition(
            nf_core_name="nf-core/rnaseq",
            timeout_hours=3,
            analysis_type="deseq2",
        )
        cmd = executor._build_command(
            pipeline_def, Path("/tmp/ss.csv"), Path("/tmp/out")
        )
        # Slurm params should NOT be in command line (they go via -c slurm.config)
        assert "--slurm_queue" not in cmd
        assert "--slurm_time" not in cmd
        assert "--slurm_memory" not in cmd
        assert "--slurm_cpus" not in cmd
        # Standard params should still be there
        assert "nf-core/rnaseq" in cmd
        assert "--genome" in cmd

    def test_build_command_slurm_disabled_no_slurm_params(self):
        config = NextflowExecutionConfig(
            genome="GRCh38", profile="docker",
        )
        executor = NextflowExecutor(config)
        pipeline_def = PipelineDefinition(
            nf_core_name="nf-core/rnaseq",
            timeout_hours=3,
        )
        cmd = executor._build_command(
            pipeline_def, Path("/tmp/ss.csv"), Path("/tmp/out")
        )
        assert "--slurm_queue" not in cmd
        assert "--slurm_time" not in cmd

    def test_build_command_standard_params_preserved(self):
        slurm = SlurmConfig(
            enabled=True,
            queue="gpu",
            cluster_options="--constraint=v100",
        )
        config = NextflowExecutionConfig(slurm=slurm)
        executor = NextflowExecutor(config)
        pipeline_def = PipelineDefinition(
            nf_core_name="nf-core/sarek", timeout_hours=6,
        )
        cmd = executor._build_command(
            pipeline_def, Path("/ss.csv"), Path("/out")
        )
        assert "nf-core/sarek" in cmd
        assert "--genome" in cmd

    @pytest.mark.asyncio
    @patch("shutil.which")
    async def test_check_prerequisites_slurm_enabled(self, mock_which):
        def which_side_effect(name):
            binaries = {
                "nextflow": "/usr/bin/nextflow",
                "docker": "/usr/bin/docker",
                "java": "/usr/bin/java",
                "sbatch": "/usr/bin/sbatch",
                "squeue": "/usr/bin/squeue",
                "sinfo": "/usr/bin/sinfo",
            }
            return binaries.get(name)

        mock_which.side_effect = which_side_effect
        slurm = SlurmConfig(enabled=True, queue="batch")
        config = NextflowExecutionConfig(slurm=slurm)
        executor = NextflowExecutor(config)
        results = await executor.check_prerequisites()
        assert results["nextflow"] is True
        assert results["docker"] is True
        assert results["java"] is True
        assert results["sbatch"] is True
        assert results["squeue"] is True
        assert results["sinfo"] is True

    @pytest.mark.asyncio
    @patch("shutil.which")
    async def test_check_prerequisites_slurm_missing_tools(self, mock_which):
        def which_side_effect(name):
            binaries = {
                "nextflow": "/usr/bin/nextflow",
                "docker": "/usr/bin/docker",
                "java": "/usr/bin/java",
            }
            return binaries.get(name)

        mock_which.side_effect = which_side_effect
        slurm = SlurmConfig(enabled=True)
        config = NextflowExecutionConfig(slurm=slurm)
        executor = NextflowExecutor(config)
        results = await executor.check_prerequisites()
        assert results["sbatch"] is False
        assert results["squeue"] is False
        assert results["sinfo"] is False

    @pytest.mark.asyncio
    @patch("shutil.which")
    async def test_check_prerequisites_slurm_disabled_no_check(self, mock_which):
        mock_which.side_effect = lambda x: (
            "/usr/bin/nextflow" if x == "nextflow"
            else "/usr/bin/docker" if x == "docker"
            else "/usr/bin/java" if x == "java"
            else None
        )
        config = NextflowExecutionConfig()  # slurm disabled by default
        executor = NextflowExecutor(config)
        results = await executor.check_prerequisites()
        assert "sbatch" not in results
        assert "squeue" not in results
        assert "sinfo" not in results

    def test_generate_slurm_config_disabled(self, tmp_path):
        config = NextflowExecutionConfig()
        executor = NextflowExecutor(config)
        result = executor._generate_slurm_config(tmp_path)
        assert result is None

    def test_generate_slurm_config_basic(self, tmp_path):
        slurm = SlurmConfig(
            enabled=True,
            queue="compute",
            time_limit="12:00:00",
            memory="32G",
            cpus_per_task=8,
        )
        config = NextflowExecutionConfig(slurm=slurm)
        executor = NextflowExecutor(config)
        result = executor._generate_slurm_config(tmp_path)
        assert result is not None
        assert result == tmp_path / "slurm.config"
        assert result.exists()
        content = result.read_text()
        assert "executor = 'slurm'" in content
        assert "queue = 'compute'" in content
        assert "time = '12:00:00'" in content
        assert "memory = '32G'" in content
        assert "cpus = 8" in content
        assert "submitRateLimit = '50/2min'" in content
        assert "queueSize = 100" in content

    def test_generate_slurm_config_with_account_and_qos(self, tmp_path):
        slurm = SlurmConfig(
            enabled=True,
            queue="batch",
            account="lab_account",
            qos="high",
            cpus_per_task=4,
        )
        config = NextflowExecutionConfig(slurm=slurm)
        executor = NextflowExecutor(config)
        result = executor._generate_slurm_config(tmp_path)
        content = result.read_text()
        assert "--account=lab_account" in content
        assert "--qos=high" in content

    def test_generate_slurm_config_multinode(self, tmp_path):
        slurm = SlurmConfig(
            enabled=True,
            nodes=4,
            cpus_per_task=16,
        )
        config = NextflowExecutionConfig(slurm=slurm)
        executor = NextflowExecutor(config)
        result = executor._generate_slurm_config(tmp_path)
        content = result.read_text()
        assert "--nodes=4" in content

    def test_generate_slurm_config_extra_args(self, tmp_path):
        slurm = SlurmConfig(
            enabled=True,
            extra_args="--gres=gpu:2 --exclusive",
            cluster_options="--constraint=v100",
            cpus_per_task=4,
        )
        config = NextflowExecutionConfig(slurm=slurm)
        executor = NextflowExecutor(config)
        result = executor._generate_slurm_config(tmp_path)
        content = result.read_text()
        assert "--gres=gpu:2 --exclusive" in content
        assert "--constraint=v100" in content

    def test_escape_groovy_string(self):
        assert NextflowExecutor._escape_groovy_string("hello") == "hello"
        assert NextflowExecutor._escape_groovy_string("it's") == "it\\'s"
        assert NextflowExecutor._escape_groovy_string("a\\b") == "a\\\\b"

    def test_generate_slurm_config_no_duplicate_cluster_options(self, tmp_path):
        """clusterOptions should appear exactly once."""
        slurm = SlurmConfig(
            enabled=True,
            account="mylab",
            qos="high",
            cpus_per_task=4,
        )
        config = NextflowExecutionConfig(slurm=slurm)
        executor = NextflowExecutor(config)
        result = executor._generate_slurm_config(tmp_path)
        content = result.read_text()
        assert content.count("clusterOptions") == 1
        assert "--account=mylab" in content
        assert "--qos=high" in content
