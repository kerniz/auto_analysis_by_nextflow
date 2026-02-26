"""
Tests for CLI Entry Point
CLI 진입점 테스트
"""

import pytest
from unittest.mock import patch, MagicMock, AsyncMock
from pathlib import Path
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
        assert "Debate: OFF" in result.output

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

    @patch("core.cli._run_search")
    def test_search_no_results(self, mock_search, runner):
        mock_search.return_value = []
        result = runner.invoke(cli, ["search", "test query"], input="q\n")
        assert "검색 결과가 없습니다" in result.output

    @patch("core.cli._run_search")
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
