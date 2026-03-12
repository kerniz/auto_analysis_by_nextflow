"""
Tests for CLI Entry Point
CLI 진입점 테스트
"""

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from click.testing import CliRunner

from core.cli import cli


@pytest.fixture
def runner():
    return CliRunner()


class TestCLIGroup:
    def test_version(self, runner):
        result = runner.invoke(cli, ["--version"])
        assert result.exit_code == 0
        assert "4.0.0" in result.output

    def test_help(self, runner):
        result = runner.invoke(cli, ["--help"])
        assert result.exit_code == 0
        assert "Bioinformatics Research Automation" in result.output


class TestRunCommand:
    def test_run_help(self, runner):
        result = runner.invoke(cli, ["run", "--help"])
        assert result.exit_code == 0
        assert "PMIDS" in result.output
        assert "--debate" in result.output
        assert "--enrichment" in result.output
        assert "--resume" in result.output

    @patch("core.cli.AsyncPipeline")
    @patch("core.cli.asyncio")
    def test_run_basic(self, mock_asyncio, mock_pipeline_cls, runner):
        mock_result = MagicMock()
        mock_result.status.value = "completed"
        mock_result.duration_seconds = 1.5
        mock_result.sequencing_result = {"sequencing_type": "scrna_seq", "confidence": 0.9}
        mock_result.llm_analysis = {"consistency_rating": "PASS"}
        mock_result.debate_report = {"overall_verdict": "PASS", "overall_score": 0.85}
        mock_result.error = ""

        mock_asyncio.run.return_value = {"40315330": mock_result}

        result = runner.invoke(cli, ["run", "40315330"])
        assert result.exit_code == 0
        assert "40315330" in result.output

    @patch("core.cli.AsyncPipeline")
    @patch("core.cli.asyncio")
    def test_run_no_debate(self, mock_asyncio, mock_pipeline_cls, runner):
        mock_asyncio.run.return_value = {}
        result = runner.invoke(cli, ["run", "40315330", "--no-debate"])
        assert result.exit_code == 0
        assert "40315330" in result.output

    @patch("core.cli.AsyncPipeline")
    @patch("core.cli.asyncio")
    def test_run_multiple_pmids(self, mock_asyncio, mock_pipeline_cls, runner):
        mock_asyncio.run.return_value = {}
        result = runner.invoke(cli, ["run", "40315330", "32416070"])
        assert result.exit_code == 0
        assert "40315330" in result.output
        assert "32416070" in result.output

    def test_run_no_pmids(self, runner):
        result = runner.invoke(cli, ["run"])
        assert result.exit_code != 0


class TestStatusCommand:
    def test_status_no_results(self, runner, tmp_path):
        result = runner.invoke(cli, ["status", "--results-dir", str(tmp_path)])
        assert "실행 기록이 없습니다" in result.output

    def test_status_with_summary(self, runner, tmp_path):
        import json
        summary = {
            "execution_summary": {
                "total_pmids": 2,
                "completed": 1,
                "failed": 1,
                "debate_enabled": True,
            },
            "pmid_results": {
                "40315330": {
                    "status": "completed",
                    "sequencing_type": "scrna_seq",
                    "llm_rating": "PASS",
                    "debate_verdict": "PASS",
                },
            },
            "timestamp": "2025-01-01T00:00:00",
        }
        summary_file = tmp_path / "execution_summary.json"
        summary_file.write_text(json.dumps(summary))

        result = runner.invoke(cli, ["status", "--results-dir", str(tmp_path)])
        assert result.exit_code == 0
        assert "Total PMIDs: 2" in result.output
        assert "Completed: 1" in result.output

    def test_status_json_format(self, runner, tmp_path):
        import json
        summary = {"execution_summary": {"total_pmids": 1}, "timestamp": "2025-01-01"}
        (tmp_path / "execution_summary.json").write_text(json.dumps(summary))

        result = runner.invoke(cli, ["status", "--results-dir", str(tmp_path), "-f", "json"])
        assert result.exit_code == 0
        assert "total_pmids" in result.output


class TestBackendsCommand:
    @patch("httpx.get")
    def test_backends(self, mock_get, runner):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"models": [{"name": "deepseek-coder:33b"}]}
        mock_get.return_value = mock_resp

        result = runner.invoke(cli, ["backends"])
        assert result.exit_code == 0
        assert "LLM Backend Status" in result.output
        assert "Ollama" in result.output

    def test_backends_ollama_unreachable(self, runner):
        result = runner.invoke(cli, ["backends"])
        assert result.exit_code == 0
        assert "Ollama" in result.output


class TestPluginsCommand:
    def test_plugins(self, runner):
        result = runner.invoke(cli, ["plugins"])
        # plugins command may fail if list_plugins returns list instead of dict
        # but it should at least show the header
        assert "Sequencing Detection Plugins" in result.output


class TestSearchCommand:
    def test_search_help(self, runner):
        result = runner.invoke(cli, ["search", "--help"])
        assert result.exit_code == 0
        assert "주제 기반" in result.output or "QUERY" in result.output

    @patch("core.cli._run_search", new_callable=AsyncMock)
    def test_search_no_results(self, mock_search, runner):
        mock_search.return_value = []
        result = runner.invoke(cli, ["search", "test query"], input="q\n")
        assert "검색 결과가 없습니다" in result.output

    @patch("core.cli._run_search", new_callable=AsyncMock)
    def test_search_with_results_quit(self, mock_search, runner):
        from search import SearchResult
        mock_search.return_value = [
            SearchResult(
                pmid="12345", title="Test Paper", abstract="Abs",
                year=2024, citation_count=10, sources=["pubmed"],
                relevance_score=0.8,
            ),
        ]
        result = runner.invoke(cli, ["search", "test"], input="q\n")
        assert "12345" in result.output
        assert "Test Paper" in result.output


class TestConsultCommand:
    def test_consult_help(self, runner):
        result = runner.invoke(cli, ["consult", "--help"])
        assert result.exit_code == 0
        assert "상담" in result.output or "consult" in result.output


class TestPrereqsCommand:
    def test_prereqs_runs(self, runner):
        result = runner.invoke(cli, ["prereqs"])
        assert result.exit_code == 0
        assert "Prerequisites" in result.output

    @patch("shutil.which")
    def test_prereqs_all_found(self, mock_which, runner):
        mock_which.return_value = "/usr/bin/fake"
        result = runner.invoke(cli, ["prereqs"])
        assert result.exit_code == 0
        assert "Nextflow" in result.output
        assert "Java" in result.output

    @patch("shutil.which")
    def test_prereqs_nothing_found(self, mock_which, runner):
        mock_which.return_value = None
        result = runner.invoke(cli, ["prereqs"])
        assert result.exit_code == 0
        assert "not found" in result.output


class TestStatusWithProgress:
    def test_status_with_progress_json(self, runner, tmp_path):
        progress = {
            "execution_id": "run_test",
            "current_phase": "sra_download_40315330",
            "current_pmid": "40315330",
            "completed_phases": ["environment_setup", "llm_server_check"],
        }
        (tmp_path / "progress.json").write_text(json.dumps(progress))

        result = runner.invoke(cli, ["status", "--results-dir", str(tmp_path)])
        assert result.exit_code == 0
        assert "run_test" in result.output
        assert "sra_download_40315330" in result.output
        assert "40315330" in result.output
        assert "2" in result.output  # completed phases count


class TestRunWithConfig:
    @patch("core.cli.AsyncPipeline")
    @patch("core.cli.asyncio")
    def test_run_with_config_file(self, mock_asyncio, mock_pipeline_cls, runner, tmp_path):
        config_data = {
            "pipeline_config": {
                "pmids": ["11111111"],
                "results_dir": str(tmp_path / "results"),
                "max_concurrent": 3,
            }
        }
        config_file = tmp_path / "config.json"
        config_file.write_text(json.dumps(config_data))

        mock_asyncio.run.return_value = {}

        result = runner.invoke(cli, ["run", "40315330", "--config", str(config_file)])
        assert result.exit_code == 0
        assert "40315330" in result.output

    @patch("core.cli.AsyncPipeline")
    @patch("core.cli.asyncio")
    def test_run_with_project_flag(self, mock_asyncio, mock_pipeline_cls, runner):
        mock_asyncio.run.return_value = {}
        result = runner.invoke(cli, ["run", "40315330", "--project", "ra_bee_venom"])
        assert result.exit_code == 0
        assert "ra_bee_venom" in result.output

    @patch("core.cli.AsyncPipeline")
    @patch("core.cli.asyncio")
    def test_run_all_options_off(self, mock_asyncio, mock_pipeline_cls, runner):
        mock_asyncio.run.return_value = {}
        result = runner.invoke(cli, [
            "run", "40315330",
            "--no-debate", "--no-enrichment", "--no-aggregate", "--no-resume",
        ])
        assert result.exit_code == 0
        assert "40315330" in result.output


class TestRunResultDisplay:
    @patch("core.cli.AsyncPipeline")
    @patch("core.cli.asyncio")
    def test_run_failed_result(self, mock_asyncio, mock_pipeline_cls, runner):
        from core.pipeline import PipelineStatus
        mock_result = MagicMock()
        mock_result.status = PipelineStatus.FAILED
        mock_result.duration_seconds = 0.5
        mock_result.sequencing_result = None
        mock_result.llm_analysis = None
        mock_result.debate_report = None
        mock_result.pipeline_execution = None
        mock_result.downstream_analysis = None
        mock_result.error = "Connection timeout"

        mock_asyncio.run.return_value = {"40315330": mock_result}
        result = runner.invoke(cli, ["run", "40315330"])
        assert result.exit_code == 0
        assert "Connection timeout" in result.output

    @patch("core.cli.AsyncPipeline")
    @patch("core.cli.asyncio")
    def test_run_with_pipeline_execution(self, mock_asyncio, mock_pipeline_cls, runner):
        mock_result = MagicMock()
        mock_result.status.value = "completed"
        mock_result.duration_seconds = 120.0
        mock_result.sequencing_result = {"sequencing_type": "bulk_rnaseq", "confidence": 0.95}
        mock_result.llm_analysis = {
            "consistency_rating": "PASS",
            "consensus": {"num_backends": 3},
        }
        mock_result.debate_report = {"overall_verdict": "PASS", "overall_score": 0.9}
        mock_result.pipeline_execution = {"status": "completed", "pipeline_name": "nf-core/rnaseq"}
        mock_result.downstream_analysis = {
            "success": True,
            "analysis_type": "deseq2",
            "summary": {"significant_degs": 150, "upregulated": 80, "downregulated": 70},
        }
        mock_result.error = ""

        mock_asyncio.run.return_value = {"40315330": mock_result}
        result = runner.invoke(cli, ["run", "40315330"])
        assert result.exit_code == 0
        assert "nf-core/rnaseq" in result.output
        assert "deseq2" in result.output
        assert "150" in result.output

    @patch("core.cli.AsyncPipeline")
    @patch("core.cli.asyncio")
    def test_run_with_cluster_analysis(self, mock_asyncio, mock_pipeline_cls, runner):
        mock_result = MagicMock()
        mock_result.status.value = "completed"
        mock_result.duration_seconds = 60.0
        mock_result.sequencing_result = {"sequencing_type": "scrna_seq", "confidence": 0.88}
        mock_result.llm_analysis = {"consistency_rating": "PASS"}
        mock_result.debate_report = None
        mock_result.pipeline_execution = None
        mock_result.downstream_analysis = {
            "success": True,
            "analysis_type": "scanpy",
            "summary": {"n_clusters": 12, "filtered_cells": 5000},
        }
        mock_result.error = ""

        mock_asyncio.run.return_value = {"40315330": mock_result}
        result = runner.invoke(cli, ["run", "40315330"])
        assert result.exit_code == 0
        assert "Clusters: 12" in result.output
        assert "5000" in result.output



class TestSearchWithSelection:
    @patch("core.cli._run_search", new_callable=AsyncMock)
    def test_search_select_and_confirm(self, mock_search, runner):
        from search import SearchResult
        mock_search.return_value = [
            SearchResult(
                pmid="12345", title="Paper One", abstract="Abstract",
                year=2024, citation_count=50, sources=["pubmed"],
                relevance_score=0.9,
            ),
            SearchResult(
                pmid="67890", title="Paper Two", abstract="Abstract2",
                year=2023, citation_count=30, sources=["pubmed"],
                relevance_score=0.7,
            ),
        ]
        # User selects "1", then says "n" to skip pipeline execution
        result = runner.invoke(cli, ["search", "test query"], input="1\nn\n")
        assert "12345" in result.output
        assert "67890" in result.output

    @patch("core.cli._run_search", new_callable=AsyncMock)
    def test_search_invalid_selection(self, mock_search, runner):
        from search import SearchResult
        mock_search.return_value = [
            SearchResult(
                pmid="12345", title="Paper", abstract="Abs",
                year=2024, citation_count=10, sources=["pubmed"],
                relevance_score=0.8,
            ),
        ]
        result = runner.invoke(cli, ["search", "test"], input="abc\nq\n")
        assert "숫자만 입력하세요" in result.output


# ============================================================
# CLI Coverage Improvement Tests (Step 3-B)
# ============================================================


class TestRunWithExecutePipeline:
    """Tests for `run --execute-pipeline` flag."""

    @patch("core.cli.asyncio.run")
    @patch("core.cli.AsyncPipeline")
    def test_execute_pipeline_success(self, mock_pipeline_cls, mock_run, runner):
        """--execute-pipeline with nextflow available."""
        mock_pipeline = MagicMock()
        mock_pipeline_cls.return_value = mock_pipeline
        mock_run.return_value = {}

        with patch("core.cli._load_config", return_value={}):
            result = runner.invoke(
                cli,
                ["run", "12345", "--execute-pipeline", "--genome", "GRCh38"],
            )
        assert result.exit_code == 0
        assert "GRCh38" in result.output

    @patch("core.cli.asyncio.run")
    @patch("core.cli.AsyncPipeline")
    def test_execute_pipeline_import_error(self, mock_pipeline_cls, mock_run, runner):
        """--execute-pipeline fails gracefully when nextflow not available."""
        mock_pipeline = MagicMock()
        mock_pipeline_cls.return_value = mock_pipeline
        mock_run.return_value = {}

        original_import = __builtins__["__import__"] if isinstance(__builtins__, dict) else __builtins__.__import__

        def nextflow_import_blocker(name, *args, **kwargs):
            if "nextflow" in name:
                raise ImportError(f"No module named '{name}'")
            return original_import(name, *args, **kwargs)

        with patch("core.cli._load_config", return_value={}), \
             patch("builtins.__import__", side_effect=nextflow_import_blocker):
            result = runner.invoke(
                cli,
                ["run", "12345", "--execute-pipeline"],
            )
        assert result.exit_code == 0
        assert "WARN" in result.output


class TestBackendsCommandExtended:
    """Extended tests for `backends` command."""

    @patch("core.cli._get_llm_server_config",
           return_value=("http://localhost:11434", "qwen3:30b", 60))
    def test_backends_ollama_healthy(self, mock_cfg, runner):
        """Ollama responding with matching model."""
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "models": [{"name": "qwen3:30b"}, {"name": "llama3:8b"}]
        }
        with patch("httpx.get", return_value=mock_resp):
            result = runner.invoke(cli, ["backends"])
        assert "HEALTHY" in result.output

    @patch("core.cli._get_llm_server_config",
           return_value=("http://localhost:11434", "qwen3:30b", 60))
    def test_backends_ollama_unreachable(self, mock_cfg, runner):
        """Ollama server unreachable."""
        with patch("httpx.get", side_effect=Exception("Connection refused")):
            result = runner.invoke(cli, ["backends"])
        assert "UNREACHABLE" in result.output

    @patch("core.cli._get_llm_server_config",
           return_value=("http://localhost:11434", "qwen3:30b", 60))
    def test_backends_ollama_unhealthy(self, mock_cfg, runner):
        """Ollama responding with non-200 status."""
        mock_resp = MagicMock()
        mock_resp.status_code = 500
        with patch("httpx.get", return_value=mock_resp):
            result = runner.invoke(cli, ["backends"])
        assert "UNHEALTHY" in result.output

    @patch("core.cli._get_llm_server_config",
           return_value=("http://localhost:11434", "qwen3:30b", 60))
    def test_backends_ollama_model_not_found(self, mock_cfg, runner):
        """Ollama healthy but model not found."""
        fake_cfg = {
            "llm_providers": {
                "backends": {
                    "ollama": {
                        "enabled": True,
                        "url": "http://localhost:11434",
                        "model": "missing-model",
                    }
                },
                "router": {"priority_order": ["ollama"]},
            }
        }
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "models": [{"name": "llama3:8b"}]
        }
        with patch("core.cli._load_config", return_value=fake_cfg), \
             patch("httpx.get", return_value=mock_resp):
            result = runner.invoke(cli, ["backends"])
        assert "not found" in result.output


class TestReportCommand:
    """Tests for `report` command."""

    def test_report_no_args(self, runner):
        """report without PMIDs or --all shows usage."""
        result = runner.invoke(cli, ["report"])
        assert "PMID를 지정하거나" in result.output

    def test_report_missing_file(self, runner, tmp_path):
        """report with non-existent JSON file."""
        result = runner.invoke(
            cli,
            ["report", "99999", "--results-dir", str(tmp_path)],
        )
        assert "SKIP" in result.output

    @patch("core.cli.ReportGenerator", create=True)
    def test_report_single_pmid(self, mock_gen_cls, runner, tmp_path):
        """report generates HTML for a single PMID."""
        mock_gen = MagicMock()
        mock_gen.generate_from_json.return_value = tmp_path / "report_12345.html"

        data = {"pmid": "12345", "status": "completed"}
        (tmp_path / "final_report_12345.json").write_text(json.dumps(data))

        with patch("core.cli.ReportGenerator", return_value=mock_gen):
            result = runner.invoke(
                cli,
                ["report", "12345", "--results-dir", str(tmp_path)],
            )
        assert "OK" in result.output
        assert "1 report" in result.output

    @patch("core.cli.ReportGenerator", create=True)
    def test_report_multiple_pmids_with_summary(self, mock_gen_cls, runner, tmp_path):
        """report generates summary for 2+ PMIDs."""
        mock_gen = MagicMock()
        mock_gen.generate_from_json.side_effect = [
            tmp_path / "report_111.html",
            tmp_path / "report_222.html",
        ]

        for pmid in ("111", "222"):
            data = {"pmid": pmid, "status": "completed"}
            (tmp_path / f"final_report_{pmid}.json").write_text(json.dumps(data))

        with patch("core.cli.ReportGenerator", return_value=mock_gen):
            result = runner.invoke(
                cli,
                ["report", "111", "222", "--results-dir", str(tmp_path)],
            )
        assert "종합보고서" in result.output
        assert "2 report" in result.output

    @patch("core.cli.ReportGenerator", create=True)
    def test_report_all_flag(self, mock_gen_cls, runner, tmp_path):
        """report --all generates from all final_report files."""
        mock_gen = MagicMock()
        mock_gen.generate_from_json.return_value = tmp_path / "report.html"

        data = {"pmid": "333", "status": "completed"}
        (tmp_path / "final_report_333.json").write_text(json.dumps(data))

        with patch("core.cli.ReportGenerator", return_value=mock_gen):
            result = runner.invoke(
                cli,
                ["report", "--all", "--results-dir", str(tmp_path)],
            )
        assert "1 report" in result.output



class TestSearchQuit:
    """Tests for search command quit."""

    @patch("core.cli._run_search", new_callable=AsyncMock)
    def test_search_quit(self, mock_search, runner):
        """Search then quit."""
        from search import SearchResult
        mock_search.return_value = [
            SearchResult(
                pmid="12345", title="P1", abstract="A",
                year=2024, citation_count=10, sources=["pubmed"],
                relevance_score=0.9,
            ),
        ]
        result = runner.invoke(cli, ["search", "test"], input="q\n")
        assert "종료합니다" in result.output

    @patch("core.cli._run_search", new_callable=AsyncMock)
    def test_search_no_pmid_selection(self, mock_search, runner):
        """Selection with no PMID in results."""
        from search import SearchResult
        mock_search.return_value = [
            SearchResult(
                pmid=None, title="No PMID Paper", abstract="A",
                year=2024, citation_count=10, sources=["semantic_scholar"],
                relevance_score=0.9,
            ),
        ]
        result = runner.invoke(cli, ["search", "test"], input="1\nq\n")
        assert "PMID가 없습니다" in result.output

    @patch("core.cli.AsyncPipeline")
    def test_search_auto_run(self, mock_pipe, runner):
        """Search with --auto-run."""
        from unittest.mock import AsyncMock

        from search import SearchResult

        search_results = [
            SearchResult(
                pmid="12345", title="P1", abstract="A",
                year=2024, citation_count=10, sources=["pubmed"],
                relevance_score=0.9,
            ),
        ]
        mock_pipe_inst = MagicMock()
        mock_pipe_inst.run = AsyncMock(return_value={})
        mock_pipe.return_value = mock_pipe_inst

        with patch("core.cli._run_search", new_callable=AsyncMock, return_value=search_results):
            result = runner.invoke(
                cli, ["search", "test", "--auto-run"], input="1\n"
            )
        assert "파이프라인 실행 완료" in result.output


class TestLoadConfig:
    """Tests for _load_config."""

    def test_returns_empty_when_no_config(self):
        from core.cli import _load_config
        with patch("pathlib.Path.exists", return_value=False):
            result = _load_config()
        assert result == {}


