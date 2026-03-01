"""
Tests for Analysis Orchestrator and Script Runners
분석 오케스트레이터 및 스크립트 러너 테스트
"""

import asyncio
import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from analysis.orchestrator import (
    ANALYSIS_ROUTES,
    OUTPUT_TO_ARGS_MAP,
    AnalysisOrchestrator,
    AnalysisResult,
)
from analysis.script_runner import PythonScriptRunner, RScriptRunner


class TestAnalysisRoutes:
    def test_all_routes_defined(self):
        assert "deseq2" in ANALYSIS_ROUTES
        assert "seurat" in ANALYSIS_ROUTES
        assert "scanpy" in ANALYSIS_ROUTES
        assert "peak_diff" in ANALYSIS_ROUTES

    def test_route_structure(self):
        for name, route in ANALYSIS_ROUTES.items():
            assert "script" in route
            assert "runner" in route
            assert route["runner"] in ("r", "python")

    def test_output_mapping_exists(self):
        for analysis_type in ANALYSIS_ROUTES:
            assert analysis_type in OUTPUT_TO_ARGS_MAP


class TestAnalysisResult:
    def test_to_dict(self):
        result = AnalysisResult(
            analysis_type="deseq2",
            success=True,
            output_dir=Path("/tmp/out"),
            summary={"significant_degs": 150},
            key_files={"results": "/tmp/out/deseq2_results.csv"},
            execution_time_seconds=45.3,
        )
        d = result.to_dict()
        assert d["analysis_type"] == "deseq2"
        assert d["success"] is True
        assert d["summary"]["significant_degs"] == 150

    def test_to_dict_error(self):
        result = AnalysisResult(
            analysis_type="seurat",
            success=False,
            error="R not installed",
        )
        d = result.to_dict()
        assert d["success"] is False
        assert "R not installed" in d["error"]


class TestAnalysisOrchestrator:
    def test_init(self):
        orch = AnalysisOrchestrator()
        assert orch.r_runner is not None
        assert orch.py_runner is not None
        assert orch.scanpy_enabled is False

    @pytest.mark.asyncio
    async def test_unknown_analysis_type(self):
        orch = AnalysisOrchestrator()
        result = await orch.run_analysis(
            analysis_type="unknown_type",
            pipeline_outputs={},
            output_dir=Path("/tmp/test"),
        )
        assert result.success is False
        assert "Unknown" in result.error

    @pytest.mark.asyncio
    async def test_script_not_found(self, tmp_path):
        orch = AnalysisOrchestrator(scripts_dir=tmp_path)
        result = await orch.run_analysis(
            analysis_type="deseq2",
            pipeline_outputs={"counts_matrix": ["/data/counts.tsv"]},
            output_dir=tmp_path / "out",
        )
        assert result.success is False
        assert "not found" in result.error

    def test_map_outputs_deseq2(self):
        orch = AnalysisOrchestrator()
        args = orch._map_outputs_to_args("deseq2", {
            "counts_matrix": ["/data/counts.tsv"],
            "tx2gene": ["/data/tx2gene.tsv"],
        })
        assert args["counts_matrix"] == "/data/counts.tsv"
        assert args["tx2gene"] == "/data/tx2gene.tsv"

    def test_map_outputs_seurat(self):
        orch = AnalysisOrchestrator()
        args = orch._map_outputs_to_args("seurat", {
            "cellranger_filtered": ["/data/filtered/"],
        })
        assert args["input_dir"] == "/data/filtered/"

    def test_map_outputs_scanpy(self):
        orch = AnalysisOrchestrator()
        args = orch._map_outputs_to_args("scanpy", {
            "h5ad_files": ["/data/combined.h5ad"],
        })
        assert args["input_h5ad"] == "/data/combined.h5ad"

    def test_map_outputs_peak_diff(self):
        orch = AnalysisOrchestrator()
        args = orch._map_outputs_to_args("peak_diff", {
            "consensus_counts": ["/data/featurecounts.txt"],
            "consensus_peaks": ["/data/peaks.bed"],
        })
        assert args["counts_matrix"] == "/data/featurecounts.txt"
        assert args["peaks_bed"] == "/data/peaks.bed"

    def test_find_key_files(self, tmp_path):
        orch = AnalysisOrchestrator()
        # Create mock output files
        (tmp_path / "deseq2_results.csv").touch()
        (tmp_path / "significant_degs.csv").touch()
        (tmp_path / "summary.json").write_text('{"success": true}')

        found = orch._find_key_files("deseq2", tmp_path)
        assert "results" in found
        assert "significant_degs" in found
        assert "summary" in found

    def test_find_key_files_empty(self, tmp_path):
        orch = AnalysisOrchestrator()
        found = orch._find_key_files("deseq2", tmp_path)
        assert found == {}

    @pytest.mark.asyncio
    async def test_run_with_summary_json(self, tmp_path):
        """Test that summary.json is parsed correctly."""
        # Create mock script and summary
        scripts_dir = tmp_path / "scripts"
        r_scripts = scripts_dir / "r_scripts"
        r_scripts.mkdir(parents=True)
        script = r_scripts / "deseq2_analysis.R"
        script.write_text("# mock")

        out_dir = tmp_path / "out"
        out_dir.mkdir()
        summary_data = {
            "success": True,
            "significant_degs": 42,
            "upregulated": 20,
            "downregulated": 22,
        }
        (out_dir / "summary.json").write_text(json.dumps(summary_data))

        orch = AnalysisOrchestrator(scripts_dir=scripts_dir)

        # Mock the R runner
        orch.r_runner.run = AsyncMock(return_value=(True, "", ""))

        result = await orch.run_analysis(
            analysis_type="deseq2",
            pipeline_outputs={"counts_matrix": ["/data/counts.tsv"]},
            output_dir=out_dir,
        )
        assert result.success is True
        assert result.summary["significant_degs"] == 42

    @pytest.mark.asyncio
    async def test_run_script_fails(self, tmp_path):
        """Test when the script runner returns failure."""
        scripts_dir = tmp_path / "scripts"
        r_scripts = scripts_dir / "r_scripts"
        r_scripts.mkdir(parents=True)
        script = r_scripts / "deseq2_analysis.R"
        script.write_text("# mock")

        out_dir = tmp_path / "out"
        out_dir.mkdir()

        orch = AnalysisOrchestrator(scripts_dir=scripts_dir)
        orch.r_runner.run = AsyncMock(return_value=(False, "", "Error: library not found"))

        result = await orch.run_analysis(
            analysis_type="deseq2",
            pipeline_outputs={"counts_matrix": ["/data/counts.tsv"]},
            output_dir=out_dir,
        )
        assert result.success is False


class TestRScriptRunner:
    def test_init(self):
        runner = RScriptRunner()
        assert runner.r_executable == "Rscript"

    def test_init_custom(self):
        runner = RScriptRunner("/usr/local/bin/Rscript")
        assert runner.r_executable == "/usr/local/bin/Rscript"

    @pytest.mark.asyncio
    @patch("shutil.which", return_value="/usr/bin/Rscript")
    async def test_check_installation_yes(self, mock_which):
        runner = RScriptRunner()
        assert await runner.check_installation() is True

    @pytest.mark.asyncio
    @patch("shutil.which", return_value=None)
    async def test_check_installation_no(self, mock_which):
        runner = RScriptRunner()
        assert await runner.check_installation() is False

    @pytest.mark.asyncio
    async def test_check_packages_success(self):
        runner = RScriptRunner()

        mock_proc = AsyncMock()
        mock_proc.communicate = AsyncMock(return_value=(b"TRUE", b""))
        mock_proc.returncode = 0

        with patch("asyncio.create_subprocess_exec", return_value=mock_proc):
            results = await runner.check_packages(["ggplot2"])
            assert results["ggplot2"] is True

    @pytest.mark.asyncio
    async def test_check_packages_not_installed(self):
        runner = RScriptRunner()

        mock_proc = AsyncMock()
        mock_proc.communicate = AsyncMock(return_value=(b"FALSE", b""))
        mock_proc.returncode = 0

        with patch("asyncio.create_subprocess_exec", return_value=mock_proc):
            results = await runner.check_packages(["nonexistent_pkg"])
            assert results["nonexistent_pkg"] is False

    @pytest.mark.asyncio
    async def test_check_packages_exception(self):
        runner = RScriptRunner()

        with patch("asyncio.create_subprocess_exec", side_effect=FileNotFoundError("Rscript not found")):
            results = await runner.check_packages(["ggplot2"])
            assert results["ggplot2"] is False

    @pytest.mark.asyncio
    async def test_check_packages_multiple(self):
        runner = RScriptRunner()

        call_count = 0
        async def mock_communicate():
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return (b"TRUE", b"")
            return (b"FALSE", b"")

        mock_proc = AsyncMock()
        mock_proc.communicate = mock_communicate
        mock_proc.returncode = 0

        with patch("asyncio.create_subprocess_exec", return_value=mock_proc):
            results = await runner.check_packages(["pkg1", "pkg2"])
            assert results["pkg1"] is True
            assert results["pkg2"] is False

    @pytest.mark.asyncio
    async def test_run_success(self):
        runner = RScriptRunner()

        mock_proc = AsyncMock()
        mock_proc.communicate = AsyncMock(return_value=(b"output data\n", b""))
        mock_proc.returncode = 0

        with patch("asyncio.create_subprocess_exec", return_value=mock_proc):
            success, stdout, stderr = await runner.run(
                Path("/scripts/analysis.R"),
                {"input": "data.csv", "output": "results.csv"},
            )
            assert success is True
            assert "output data" in stdout
            assert stderr == ""

    @pytest.mark.asyncio
    async def test_run_failure(self):
        runner = RScriptRunner()

        mock_proc = AsyncMock()
        mock_proc.communicate = AsyncMock(return_value=(b"", b"Error in library: not found"))
        mock_proc.returncode = 1

        with patch("asyncio.create_subprocess_exec", return_value=mock_proc):
            success, stdout, stderr = await runner.run(
                Path("/scripts/analysis.R"),
                {"input": "data.csv"},
            )
            assert success is False
            assert "Error" in stderr

    @pytest.mark.asyncio
    async def test_run_timeout(self):
        runner = RScriptRunner()

        mock_proc = AsyncMock()
        mock_proc.communicate = AsyncMock(side_effect=asyncio.TimeoutError())
        mock_proc.kill = MagicMock()

        with patch("asyncio.create_subprocess_exec", return_value=mock_proc):
            success, stdout, stderr = await runner.run(
                Path("/scripts/analysis.R"),
                {"input": "data.csv"},
                timeout=1,
            )
            assert success is False
            assert "timed out" in stderr
            mock_proc.kill.assert_called_once()

    @pytest.mark.asyncio
    async def test_run_exception(self):
        runner = RScriptRunner()

        with patch("asyncio.create_subprocess_exec", side_effect=FileNotFoundError("Rscript not found")):
            success, stdout, stderr = await runner.run(
                Path("/scripts/analysis.R"),
                {"input": "data.csv"},
            )
            assert success is False
            assert "not found" in stderr


class TestPythonScriptRunner:
    def test_init(self):
        runner = PythonScriptRunner()
        assert runner.python_executable is not None

    def test_init_custom(self):
        runner = PythonScriptRunner("/usr/bin/python3.11")
        assert runner.python_executable == "/usr/bin/python3.11"

    @pytest.mark.asyncio
    async def test_check_installation(self):
        runner = PythonScriptRunner()
        assert await runner.check_installation() is True

    @pytest.mark.asyncio
    async def test_check_packages_success(self):
        runner = PythonScriptRunner()

        mock_proc = AsyncMock()
        mock_proc.communicate = AsyncMock(return_value=(b"", b""))
        mock_proc.returncode = 0

        with patch("asyncio.create_subprocess_exec", return_value=mock_proc):
            results = await runner.check_packages(["json"])
            assert results["json"] is True

    @pytest.mark.asyncio
    async def test_check_packages_not_installed(self):
        runner = PythonScriptRunner()

        mock_proc = AsyncMock()
        mock_proc.communicate = AsyncMock(return_value=(b"", b"ModuleNotFoundError"))
        mock_proc.returncode = 1

        with patch("asyncio.create_subprocess_exec", return_value=mock_proc):
            results = await runner.check_packages(["nonexistent_pkg"])
            assert results["nonexistent_pkg"] is False

    @pytest.mark.asyncio
    async def test_check_packages_exception(self):
        runner = PythonScriptRunner()

        with patch("asyncio.create_subprocess_exec", side_effect=Exception("fail")):
            results = await runner.check_packages(["pkg"])
            assert results["pkg"] is False

    @pytest.mark.asyncio
    async def test_run_success(self):
        runner = PythonScriptRunner()

        mock_proc = AsyncMock()
        mock_proc.communicate = AsyncMock(return_value=(b"result output\n", b""))
        mock_proc.returncode = 0

        with patch("asyncio.create_subprocess_exec", return_value=mock_proc):
            success, stdout, stderr = await runner.run(
                Path("/scripts/analysis.py"),
                {"input": "data.csv", "output": "results.csv"},
            )
            assert success is True
            assert "result output" in stdout

    @pytest.mark.asyncio
    async def test_run_failure(self):
        runner = PythonScriptRunner()

        mock_proc = AsyncMock()
        mock_proc.communicate = AsyncMock(return_value=(b"", b"Traceback: ImportError"))
        mock_proc.returncode = 1

        with patch("asyncio.create_subprocess_exec", return_value=mock_proc):
            success, stdout, stderr = await runner.run(
                Path("/scripts/analysis.py"),
                {"input": "data.csv"},
            )
            assert success is False
            assert "Traceback" in stderr

    @pytest.mark.asyncio
    async def test_run_timeout(self):
        runner = PythonScriptRunner()

        mock_proc = AsyncMock()
        mock_proc.communicate = AsyncMock(side_effect=asyncio.TimeoutError())
        mock_proc.kill = MagicMock()

        with patch("asyncio.create_subprocess_exec", return_value=mock_proc):
            success, stdout, stderr = await runner.run(
                Path("/scripts/analysis.py"),
                {"input": "data.csv"},
                timeout=1,
            )
            assert success is False
            assert "timed out" in stderr
            mock_proc.kill.assert_called_once()

    @pytest.mark.asyncio
    async def test_run_exception(self):
        runner = PythonScriptRunner()

        with patch("asyncio.create_subprocess_exec", side_effect=OSError("no such file")):
            success, stdout, stderr = await runner.run(
                Path("/scripts/analysis.py"),
                {"input": "data.csv"},
            )
            assert success is False
            assert "no such file" in stderr

    @pytest.mark.asyncio
    async def test_run_args_passed_correctly(self):
        runner = PythonScriptRunner()

        mock_proc = AsyncMock()
        mock_proc.communicate = AsyncMock(return_value=(b"ok", b""))
        mock_proc.returncode = 0

        with patch("asyncio.create_subprocess_exec", return_value=mock_proc) as mock_exec:
            await runner.run(
                Path("/scripts/test.py"),
                {"input": "/data/in.csv", "output": "/data/out.csv"},
            )
            call_args = mock_exec.call_args[0]
            # Should contain python exec, script, --input, value, --output, value
            assert str(Path("/scripts/test.py")) in call_args
            assert "--input" in call_args
            assert "/data/in.csv" in call_args
            assert "--output" in call_args
            assert "/data/out.csv" in call_args
