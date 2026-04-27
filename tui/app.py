"""BioAuto TUI — Textual 기반 파이프라인 모니터링 대시보드"""

from __future__ import annotations

import asyncio
from datetime import datetime
from pathlib import Path
from typing import Any

from textual import work
from textual.app import App, ComposeResult
from textual.containers import Vertical
from textual.message import Message
from textual.widgets import (
    DataTable,
    Footer,
    Header,
    ProgressBar,
    RichLog,
    Static,
)

from core.events import (
    EventType,
    PipelineEvent,
    PipelineEventBus,
    get_stage_label,
)
from core.i18n import t

# ── Custom Messages ──

class PipelineEventMessage(Message):
    """Textual 메시지 래퍼 (이벤트 버스 → UI 스레드)"""
    def __init__(self, event: PipelineEvent):
        super().__init__()
        self.event = event


# ── Widgets ──

class PipelineStatus(Static):
    """파이프라인 전체 상태 표시"""

    def __init__(self, pmid_count: int = 0):
        super().__init__()
        self.pmid_count = pmid_count
        self.start_time = datetime.now()
        self.completed = 0
        self.failed = 0

    def compose(self) -> ComposeResult:
        yield Static(id="status-text")

    def on_mount(self) -> None:
        self._update_display()
        self.set_interval(1, self._update_display)

    def _update_display(self) -> None:
        elapsed = datetime.now() - self.start_time
        mins, secs = divmod(int(elapsed.total_seconds()), 60)
        hours, mins = divmod(mins, 60)
        time_str = f"{hours:02d}:{mins:02d}:{secs:02d}"

        text = (
            f"[bold]PMIDs:[/] {self.pmid_count}  "
            f"[bold]Completed:[/] [green]{self.completed}[/]  "
            f"[bold]Failed:[/] [red]{self.failed}[/]  "
            f"[bold]Elapsed:[/] {time_str}"
        )
        try:
            self.query_one("#status-text", Static).update(text)
        except Exception:
            pass


class BackendIndicator(Static):
    """LLM 백엔드 상태 인디케이터"""

    def __init__(self, backends: list[str] | None = None):
        super().__init__()
        self.backend_names = backends or []

    def update_backends(self, backends: list[str]) -> None:
        self.backend_names = backends
        parts = []
        for name in self.backend_names:
            parts.append(f"[green]●[/] {name}")
        self.update("Backends: " + "  ".join(parts) if parts else "No backends")


# ── Main App ──

class BioAutoTUI(App):
    """BioAuto 파이프라인 모니터링 TUI"""

    TITLE = "BioAuto Pipeline Monitor"
    CSS = """
    #status-bar {
        height: 3;
        dock: top;
        padding: 0 1;
        background: $primary-background;
    }
    #pmid-table {
        height: 1fr;
        min-height: 5;
    }
    #log-panel {
        height: 2fr;
        border-top: solid $primary;
    }
    #backend-bar {
        height: 1;
        dock: bottom;
        padding: 0 1;
        background: $primary-background;
    }
    #progress-bar {
        height: 1;
        padding: 0 1;
    }
    """
    BINDINGS = [
        ("q", "quit", "Quit"),
        ("c", "clear_log", "Clear Log"),
    ]

    def __init__(
        self,
        pmids: list[str],
        results_dir: str = "./results",
        config_data: dict[str, Any] | None = None,
        **kwargs,
    ):
        super().__init__(**kwargs)
        self.pmids = pmids
        self.results_dir = Path(results_dir)
        self.config_data = config_data or {}
        self.event_bus = PipelineEventBus()
        self._pmid_stages: dict[str, dict] = {
            pmid: {"current_stage": "pending", "completed": 0, "status": "⏳"}
            for pmid in pmids
        }
        self._total_stages = 8

    def compose(self) -> ComposeResult:
        yield Header()
        with Vertical():
            yield PipelineStatus(pmid_count=len(self.pmids), id="status-bar")
            yield ProgressBar(
                total=len(self.pmids) * self._total_stages,
                show_eta=False,
                id="progress-bar",
            )
            yield DataTable(id="pmid-table")
            yield RichLog(highlight=True, markup=True, id="log-panel")
        yield BackendIndicator(id="backend-bar")
        yield Footer()

    def on_mount(self) -> None:
        # Setup PMID table
        table = self.query_one("#pmid-table", DataTable)
        table.add_columns("PMID", "Stage", "Progress", "Status", "Duration")
        for pmid in self.pmids:
            table.add_row(
                pmid,
                "Pending",
                "░░░░░░░░ 0/8",
                "⏳",
                "—",
                key=pmid,
            )

        # Subscribe to events
        self.event_bus.subscribe(self._on_pipeline_event)

        # Start pipeline
        self._run_pipeline()

    @work(thread=True)
    def _run_pipeline(self) -> None:
        """백그라운드 스레드에서 파이프라인 실행"""
        loop = asyncio.new_event_loop()
        try:
            loop.run_until_complete(self._execute_pipeline())
        finally:
            loop.close()

    async def _execute_pipeline(self) -> None:
        """실제 파이프라인 실행"""
        from core.pipeline import AsyncPipeline, PipelineConfig

        if self.config_data:
            config = PipelineConfig.from_dict(self.config_data)
            config.pmids = self.pmids
            config.results_dir = self.results_dir
        else:
            config = PipelineConfig(
                pmids=self.pmids,
                results_dir=self.results_dir,
            )

        pipeline = AsyncPipeline(config)
        pipeline.event_bus = self.event_bus
        await pipeline.run()

    def _on_pipeline_event(self, event: PipelineEvent) -> None:
        """이벤트 버스 콜백 → UI 스레드로 전달"""
        self.post_message(PipelineEventMessage(event))

    def on_pipeline_event_message(self, message: PipelineEventMessage) -> None:
        """UI 스레드에서 이벤트 처리"""
        event = message.event
        log = self.query_one("#log-panel", RichLog)
        table = self.query_one("#pmid-table", DataTable)
        progress = self.query_one("#progress-bar", ProgressBar)
        status_bar = self.query_one("#status-bar", PipelineStatus)
        ts = event.timestamp.strftime("%H:%M:%S")

        if event.event_type == EventType.PIPELINE_START:
            log.write(
                f"[bold green]{ts}[/] {t('tui.pipeline_start', count=len(self.pmids))}"
            )

        elif event.event_type == EventType.PMID_START:
            log.write(f"[cyan]{ts}[/] {t('tui.pmid_start', pmid=event.pmid)}")
            self._pmid_stages[event.pmid]["status"] = "🔄"
            self._pmid_stages[event.pmid]["start_time"] = event.timestamp

        elif event.event_type == EventType.PMID_STAGE_START:
            stage_label = get_stage_label(event.stage)
            log.write(
                f"[dim]{ts}[/] {t('tui.pmid_stage', pmid=event.pmid, stage=stage_label)}"
            )
            self._pmid_stages[event.pmid]["current_stage"] = stage_label
            self._update_table_row(table, event.pmid)

        elif event.event_type == EventType.PMID_STAGE_COMPLETE:
            stage_label = get_stage_label(event.stage)
            extra = f" — {event.message}" if event.message else ""
            log.write(
                f"[green]{ts}[/] {t('tui.pmid_done', pmid=event.pmid, stage=stage_label, extra=extra)}"
            )
            info = self._pmid_stages[event.pmid]
            info["completed"] = info.get("completed", 0) + 1
            info["current_stage"] = stage_label
            progress.advance(1)
            self._update_table_row(table, event.pmid)

        elif event.event_type == EventType.PMID_STAGE_ERROR:
            stage_label = get_stage_label(event.stage)
            log.write(
                f"[red]{ts}[/] {t('tui.pmid_error', pmid=event.pmid, stage=stage_label, message=event.message)}"
            )

        elif event.event_type == EventType.PMID_COMPLETE:
            status_val = event.data.get("status", "completed")
            if status_val == "completed":
                self._pmid_stages[event.pmid]["status"] = "✅"
                status_bar.completed += 1
                log.write(
                    f"[bold green]{ts}[/] {t('tui.pmid_complete', pmid=event.pmid)}"
                )
            else:
                self._pmid_stages[event.pmid]["status"] = "❌"
                status_bar.failed += 1
                log.write(
                    f"[bold red]{ts}[/] {t('tui.pmid_failed', pmid=event.pmid)}"
                )
            self._update_table_row(table, event.pmid)

        elif event.event_type == EventType.PIPELINE_COMPLETE:
            log.write(
                f"\n[bold green]{ts}[/] {t('tui.pipeline_complete')}"
            )

        elif event.event_type == EventType.LOG_MESSAGE:
            log.write(f"[dim]{ts}[/] {event.message}")

    def _update_table_row(self, table: DataTable, pmid: str) -> None:
        """PMID 테이블 행 업데이트"""
        info = self._pmid_stages.get(pmid, {})
        completed = info.get("completed", 0)
        total = self._total_stages
        filled = "█" * completed + "░" * (total - completed)
        progress_str = f"{filled} {completed}/{total}"

        duration = "—"
        start_time = info.get("start_time")
        if start_time:
            elapsed = (datetime.now() - start_time).total_seconds()
            mins, secs = divmod(int(elapsed), 60)
            duration = f"{mins}m {secs:02d}s"

        try:
            table.update_cell(pmid, "Stage", info.get("current_stage", "—"))
            table.update_cell(pmid, "Progress", progress_str)
            table.update_cell(pmid, "Status", info.get("status", "⏳"))
            table.update_cell(pmid, "Duration", duration)
        except Exception:
            pass

    def action_clear_log(self) -> None:
        """로그 패널 클리어"""
        self.query_one("#log-panel", RichLog).clear()


def run_tui(pmids: list[str], results_dir: str = "./results",
            config_data: dict | None = None) -> None:
    """TUI 앱 실행 헬퍼"""
    app = BioAutoTUI(
        pmids=pmids,
        results_dir=results_dir,
        config_data=config_data,
    )
    app.run()
