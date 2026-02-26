"""
Tests for Nextflow Execution Layer
Nextflow 실행 레이어 테스트
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from pathlib import Path

from nextflow.config import NextflowExecutionConfig, ContainerRuntime
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
