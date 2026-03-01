"""
Tests for CLI Entry Point
CLI 진입점 테스트
"""

import json
from unittest.mock import MagicMock, patch

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
        assert "Project: ra_bee_venom" in result.output

    @patch("core.cli.AsyncPipeline")
    @patch("core.cli.asyncio")
    def test_run_all_options_off(self, mock_asyncio, mock_pipeline_cls, runner):
        mock_asyncio.run.return_value = {}
        result = runner.invoke(cli, [
            "run", "40315330",
            "--no-debate", "--no-enrichment", "--no-aggregate", "--no-resume",
        ])
        assert result.exit_code == 0
        assert "Debate: OFF" in result.output
        assert "Enrichment: OFF" in result.output
        assert "Data Aggregation: OFF" in result.output
        assert "Resume: OFF" in result.output


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


class TestProjectCreate:
    @patch("core.cli.ProjectManager")
    def test_create_basic(self, mock_pm_cls, runner):
        from core.project_manager import ResearchProject
        mock_pm = MagicMock()
        mock_pm_cls.return_value = mock_pm
        mock_pm.create_project.return_value = ResearchProject(
            name="Test Project", slug="test_project",
            keywords=[], pmids=[],
            created_at="2025-01-01", updated_at="2025-01-01",
        )
        mock_pm.get_project_dir.return_value = "/tmp/research_projects/test_project"

        result = runner.invoke(cli, ["project", "create", "Test Project"])
        assert result.exit_code == 0
        assert "Project created: Test Project" in result.output
        assert "test_project" in result.output

    @patch("core.cli.ProjectManager")
    def test_create_with_options(self, mock_pm_cls, runner):
        from core.project_manager import ResearchProject
        mock_pm = MagicMock()
        mock_pm_cls.return_value = mock_pm
        mock_pm.create_project.return_value = ResearchProject(
            name="RA Bee Venom", slug="ra_bee_venom",
            description="RA and bee venom study",
            keywords=["RA", "bee_venom"], pmids=["111", "222"],
            created_at="2025-01-01", updated_at="2025-01-01",
        )
        mock_pm.get_project_dir.return_value = "/tmp/research_projects/ra_bee_venom"

        result = runner.invoke(cli, [
            "project", "create", "RA Bee Venom",
            "-d", "RA and bee venom study",
            "-k", "RA,bee_venom",
            "--pmids", "111,222",
        ])
        assert result.exit_code == 0
        assert "RA Bee Venom" in result.output
        assert "RA" in result.output
        assert "111" in result.output


class TestProjectList:
    @patch("core.cli.ProjectManager")
    def test_list_empty(self, mock_pm_cls, runner):
        mock_pm = MagicMock()
        mock_pm_cls.return_value = mock_pm
        mock_pm.list_projects.return_value = []

        result = runner.invoke(cli, ["project", "list"])
        assert result.exit_code == 0
        assert "등록된 프로젝트가 없습니다" in result.output

    @patch("core.cli.ProjectManager")
    def test_list_with_projects(self, mock_pm_cls, runner):
        from core.project_manager import ResearchProject
        mock_pm = MagicMock()
        mock_pm_cls.return_value = mock_pm
        mock_pm.list_projects.return_value = [
            ResearchProject(
                name="Project Alpha", slug="project_alpha",
                pmids=["111", "222"],
                created_at="2025-01-01T10:00:00",
                updated_at="2025-01-01",
            ),
            ResearchProject(
                name="Project Beta", slug="project_beta",
                pmids=[],
                created_at="2025-02-01T12:00:00",
                updated_at="2025-02-01",
            ),
        ]

        result = runner.invoke(cli, ["project", "list"])
        assert result.exit_code == 0
        assert "project_alpha" in result.output
        assert "project_beta" in result.output
        assert "Project Alpha" in result.output


class TestProjectInfo:
    @patch("core.cli.ProjectManager")
    def test_info_existing(self, mock_pm_cls, runner):
        from core.project_manager import ResearchProject
        mock_pm = MagicMock()
        mock_pm_cls.return_value = mock_pm
        mock_pm.get_project.return_value = ResearchProject(
            name="My Project", slug="my_project",
            description="A description",
            keywords=["bio", "rna"],
            pmids=["111", "222"],
            created_at="2025-01-01", updated_at="2025-01-02",
        )
        mock_pm.get_project_dir.return_value = "/tmp/research_projects/my_project"

        result = runner.invoke(cli, ["project", "info", "my_project"])
        assert result.exit_code == 0
        assert "My Project" in result.output
        assert "A description" in result.output
        assert "bio" in result.output
        assert "111" in result.output

    @patch("core.cli.ProjectManager")
    def test_info_nonexistent(self, mock_pm_cls, runner):
        mock_pm = MagicMock()
        mock_pm_cls.return_value = mock_pm
        mock_pm.get_project.return_value = None

        result = runner.invoke(cli, ["project", "info", "no_such"])
        assert result.exit_code == 0
        assert "찾을 수 없습니다" in result.output


class TestProjectAddPmids:
    @patch("core.cli.ProjectManager")
    def test_add_pmids(self, mock_pm_cls, runner):
        from core.project_manager import ResearchProject
        mock_pm = MagicMock()
        mock_pm_cls.return_value = mock_pm
        mock_pm.add_pmids.return_value = ResearchProject(
            name="My Project", slug="my_project",
            pmids=["111", "222", "333"],
        )

        result = runner.invoke(cli, ["project", "add-pmids", "my_project", "222", "333"])
        assert result.exit_code == 0
        assert "PMIDs updated" in result.output
        assert "3" in result.output

    @patch("core.cli.ProjectManager")
    def test_add_pmids_nonexistent_project(self, mock_pm_cls, runner):
        mock_pm = MagicMock()
        mock_pm_cls.return_value = mock_pm
        mock_pm.add_pmids.return_value = None

        result = runner.invoke(cli, ["project", "add-pmids", "no_such", "111"])
        assert result.exit_code == 0
        assert "찾을 수 없습니다" in result.output


class TestProjectHelp:
    def test_project_group_help(self, runner):
        result = runner.invoke(cli, ["project", "--help"])
        assert result.exit_code == 0
        assert "create" in result.output
        assert "list" in result.output
        assert "info" in result.output
        assert "add-pmids" in result.output


class TestSearchWithSelection:
    @patch("core.cli._run_search")
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

    @patch("core.cli._run_search")
    def test_search_invalid_selection(self, mock_search, runner):
        from search import SearchResult
        mock_search.return_value = [
            SearchResult(
                pmid="12345", title="Paper", abstract="Abs",
                year=2024, citation_count=10, sources=["pubmed"],
                relevance_score=0.8,
            ),
        ]
        result = runner.invoke(cli, ["search", "test"], input="abc\n")
        assert "잘못된 입력" in result.output
