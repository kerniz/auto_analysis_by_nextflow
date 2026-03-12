"""Tests for TUI (Textual Terminal UI) components."""

from datetime import datetime
from unittest.mock import MagicMock, patch

from core.events import (
    EventType,
    PipelineEvent,
    PipelineEventBus,
)

# ── Import Guard ──

class TestTUIImport:
    """TUI 모듈 임포트 테스트"""

    def test_import_tui_package(self):
        import tui
        assert tui is not None

    def test_import_app_module(self):
        from tui.app import BackendIndicator, BioAutoTUI, PipelineStatus, run_tui
        assert BioAutoTUI is not None
        assert PipelineStatus is not None
        assert BackendIndicator is not None
        assert run_tui is not None

    def test_import_pipeline_event_message(self):
        from tui.app import PipelineEventMessage
        assert PipelineEventMessage is not None


# ── Widget Unit Tests ──

class TestPipelineEventMessage:
    """PipelineEventMessage 래퍼 테스트"""

    def test_wraps_event(self):
        from tui.app import PipelineEventMessage
        event = PipelineEvent(
            event_type=EventType.PMID_START,
            pmid="12345",
        )
        msg = PipelineEventMessage(event)
        assert msg.event is event
        assert msg.event.pmid == "12345"

    def test_wraps_event_with_data(self):
        from tui.app import PipelineEventMessage
        event = PipelineEvent(
            event_type=EventType.PMID_STAGE_COMPLETE,
            pmid="99999",
            stage="pubmed",
            message="done",
            data={"count": 5},
        )
        msg = PipelineEventMessage(event)
        assert msg.event.stage == "pubmed"
        assert msg.event.data["count"] == 5


# ── BioAutoTUI Initialization Tests ──

class TestBioAutoTUIInit:
    """BioAutoTUI 앱 초기화 테스트"""

    def test_init_with_pmids(self):
        from tui.app import BioAutoTUI
        app = BioAutoTUI(pmids=["111", "222", "333"])
        assert app.pmids == ["111", "222", "333"]
        assert len(app._pmid_stages) == 3
        assert app._total_stages == 8

    def test_init_default_results_dir(self):
        from pathlib import Path

        from tui.app import BioAutoTUI
        app = BioAutoTUI(pmids=["111"])
        assert app.results_dir == Path("./results")

    def test_init_custom_results_dir(self):
        from pathlib import Path

        from tui.app import BioAutoTUI
        app = BioAutoTUI(pmids=["111"], results_dir="/tmp/test_results")
        assert app.results_dir == Path("/tmp/test_results")

    def test_init_with_config_data(self):
        from tui.app import BioAutoTUI
        cfg = {"pipeline_config": {"llm_server": {"url": "http://test:11434"}}}
        app = BioAutoTUI(pmids=["111"], config_data=cfg)
        assert app.config_data == cfg

    def test_init_empty_config(self):
        from tui.app import BioAutoTUI
        app = BioAutoTUI(pmids=["111"])
        assert app.config_data == {}

    def test_init_pmid_stages_structure(self):
        from tui.app import BioAutoTUI
        app = BioAutoTUI(pmids=["AAA", "BBB"])
        for pmid in ["AAA", "BBB"]:
            stage_info = app._pmid_stages[pmid]
            assert stage_info["current_stage"] == "pending"
            assert stage_info["completed"] == 0
            assert stage_info["status"] == "⏳"

    def test_init_event_bus(self):
        from tui.app import BioAutoTUI
        app = BioAutoTUI(pmids=["111"])
        assert isinstance(app.event_bus, PipelineEventBus)


# ── Event Handler Logic Tests (no actual rendering) ──

class TestEventHandlerLogic:
    """이벤트 핸들러 로직 테스트 (위젯 렌더링 없이)"""

    def _make_app(self, pmids=None):
        from tui.app import BioAutoTUI
        return BioAutoTUI(pmids=pmids or ["111", "222"])

    def test_pmid_stages_update_on_start(self):
        app = self._make_app()
        # Simulate PMID_START event data update
        app._pmid_stages["111"]["status"] = "🔄"
        app._pmid_stages["111"]["start_time"] = datetime.now()
        assert app._pmid_stages["111"]["status"] == "🔄"
        assert "start_time" in app._pmid_stages["111"]

    def test_pmid_stages_update_on_stage_complete(self):
        app = self._make_app()
        info = app._pmid_stages["111"]
        info["completed"] = info.get("completed", 0) + 1
        info["current_stage"] = "PubMed 메타데이터"
        assert info["completed"] == 1
        assert info["current_stage"] == "PubMed 메타데이터"

    def test_pmid_stages_progress_accumulates(self):
        app = self._make_app()
        info = app._pmid_stages["222"]
        for i in range(5):
            info["completed"] = info.get("completed", 0) + 1
        assert info["completed"] == 5

    def test_pmid_complete_success(self):
        app = self._make_app()
        app._pmid_stages["111"]["status"] = "✅"
        assert app._pmid_stages["111"]["status"] == "✅"

    def test_pmid_complete_failure(self):
        app = self._make_app()
        app._pmid_stages["111"]["status"] = "❌"
        assert app._pmid_stages["111"]["status"] == "❌"

    def test_progress_bar_string_format(self):
        """테이블 행 진행률 문자열 포맷 검증"""
        completed = 3
        total = 8
        filled = "█" * completed + "░" * (total - completed)
        progress_str = f"{filled} {completed}/{total}"
        assert progress_str == "███░░░░░ 3/8"

    def test_progress_bar_full(self):
        completed = 8
        total = 8
        filled = "█" * completed + "░" * (total - completed)
        progress_str = f"{filled} {completed}/{total}"
        assert progress_str == "████████ 8/8"

    def test_progress_bar_empty(self):
        completed = 0
        total = 8
        filled = "█" * completed + "░" * (total - completed)
        progress_str = f"{filled} {completed}/{total}"
        assert progress_str == "░░░░░░░░ 0/8"

    def test_duration_format(self):
        """경과 시간 포맷 검증"""
        elapsed_seconds = 185  # 3분 5초
        mins, secs = divmod(int(elapsed_seconds), 60)
        duration = f"{mins}m {secs:02d}s"
        assert duration == "3m 05s"


# ── BackendIndicator Tests ──

class TestBackendIndicator:
    """BackendIndicator 위젯 테스트"""

    def test_init_empty(self):
        from tui.app import BackendIndicator
        indicator = BackendIndicator()
        assert indicator.backend_names == []

    def test_init_with_backends(self):
        from tui.app import BackendIndicator
        indicator = BackendIndicator(backends=["ollama", "openai"])
        assert indicator.backend_names == ["ollama", "openai"]


# ── CLI TUI Command Tests ──

class TestTUICLI:
    """TUI CLI 명령 테스트"""

    def test_tui_command_exists(self):
        from core.cli import cli
        commands = cli.commands
        assert "tui" in commands

    def test_tui_command_help(self):
        from click.testing import CliRunner

        from core.cli import cli
        runner = CliRunner()
        result = runner.invoke(cli, ["tui", "--help"])
        assert result.exit_code == 0
        assert "TUI 대시보드" in result.output

    @patch("tui.app.run_tui")
    def test_tui_command_invokes_run_tui(self, mock_run_tui):
        from click.testing import CliRunner

        from core.cli import cli
        runner = CliRunner()
        result = runner.invoke(cli, ["tui", "12345", "67890"])
        assert result.exit_code == 0
        mock_run_tui.assert_called_once()
        call_kwargs = mock_run_tui.call_args
        assert call_kwargs.kwargs["pmids"] == ["12345", "67890"]

    @patch("tui.app.run_tui")
    def test_tui_command_custom_results_dir(self, mock_run_tui):
        from click.testing import CliRunner

        from core.cli import cli
        runner = CliRunner()
        result = runner.invoke(cli, ["tui", "12345", "-o", "/tmp/out"])
        assert result.exit_code == 0
        call_kwargs = mock_run_tui.call_args
        assert call_kwargs.kwargs["results_dir"] == "/tmp/out"

    @patch("tui.app.run_tui")
    def test_tui_command_passes_config_data(self, mock_run_tui):
        from click.testing import CliRunner

        from core.cli import cli
        runner = CliRunner()
        result = runner.invoke(cli, ["tui", "12345"])
        assert result.exit_code == 0
        call_kwargs = mock_run_tui.call_args
        config_data = call_kwargs.kwargs["config_data"]
        assert "_cli_overrides" in config_data
        overrides = config_data["_cli_overrides"]
        assert overrides["pmids"] == ["12345"]
        assert overrides["enable_debate"] is True

    def test_tui_command_no_pmids_fails(self):
        from click.testing import CliRunner

        from core.cli import cli
        runner = CliRunner()
        result = runner.invoke(cli, ["tui"])
        assert result.exit_code != 0


# ── Event Integration Tests ──

class TestEventIntegration:
    """이벤트 버스와 TUI 연동 테스트"""

    def test_event_bus_callback_creates_message(self):
        from tui.app import BioAutoTUI, PipelineEventMessage

        app = BioAutoTUI(pmids=["111"])
        received = []

        # Mock post_message to capture messages
        app.post_message = MagicMock(side_effect=lambda msg: received.append(msg))

        # Simulate event bus callback
        event = PipelineEvent(
            event_type=EventType.PMID_START, pmid="111",
        )
        app._on_pipeline_event(event)

        assert len(received) == 1
        assert isinstance(received[0], PipelineEventMessage)
        assert received[0].event.pmid == "111"

    def test_event_bus_multiple_events(self):
        from tui.app import BioAutoTUI

        app = BioAutoTUI(pmids=["111"])
        received = []
        app.post_message = MagicMock(side_effect=lambda msg: received.append(msg))

        events = [
            PipelineEvent(event_type=EventType.PIPELINE_START),
            PipelineEvent(event_type=EventType.PMID_START, pmid="111"),
            PipelineEvent(event_type=EventType.PMID_STAGE_START, pmid="111", stage="pubmed"),
            PipelineEvent(event_type=EventType.PMID_STAGE_COMPLETE, pmid="111", stage="pubmed"),
        ]

        for event in events:
            app._on_pipeline_event(event)

        assert len(received) == 4

    def test_run_tui_function_signature(self):
        """run_tui 함수 시그니처 검증"""
        import inspect

        from tui.app import run_tui

        sig = inspect.signature(run_tui)
        params = list(sig.parameters.keys())
        assert "pmids" in params
        assert "results_dir" in params
        assert "config_data" in params
