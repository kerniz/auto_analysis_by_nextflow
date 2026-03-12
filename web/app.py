"""BioAuto Web Dashboard — FastAPI + HTMX + SSE"""

from __future__ import annotations

import asyncio
import json
from datetime import datetime
from pathlib import Path
from typing import Any

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sse_starlette.sse import EventSourceResponse

from core.events import (
    STAGE_LABELS,
    EventType,
    PipelineEvent,
    PipelineEventBus,
)
from web.results_scanner import ResultsScanner

# ── In-memory State ──

_WEB_DIR = Path(__file__).parent
_TEMPLATES_DIR = _WEB_DIR / "templates"
_STATIC_DIR = _WEB_DIR / "static"


class DashboardState:
    """파이프라인 실행 상태 (in-memory)"""

    def __init__(self):
        self.running = False
        self.pmids: list[str] = []
        self.pmid_status: dict[str, dict[str, Any]] = {}
        self.start_time: datetime | None = None
        self.completed_count = 0
        self.failed_count = 0
        self.log_messages: list[dict[str, str]] = []
        self.event_bus = PipelineEventBus()
        self._sse_queues: list[asyncio.Queue] = []

    def reset(self, pmids: list[str]) -> None:
        self.running = True
        self.pmids = pmids
        self.pmid_status = {
            pmid: {
                "current_stage": "pending",
                "completed": 0,
                "total": 8,
                "status": "pending",
                "start_time": None,
                "duration": None,
            }
            for pmid in pmids
        }
        self.start_time = datetime.now()
        self.completed_count = 0
        self.failed_count = 0
        self.log_messages = []

    def handle_event(self, event: PipelineEvent) -> None:
        """이벤트 처리 및 상태 업데이트"""
        ts = event.timestamp.strftime("%H:%M:%S")

        if event.event_type == EventType.PIPELINE_START:
            self._add_log(ts, "info", f"파이프라인 시작 ({len(self.pmids)}개 PMID)")

        elif event.event_type == EventType.PMID_START:
            if event.pmid in self.pmid_status:
                self.pmid_status[event.pmid]["status"] = "running"
                self.pmid_status[event.pmid]["start_time"] = event.timestamp.isoformat()
            self._add_log(ts, "info", f"[{event.pmid}] 처리 시작")

        elif event.event_type == EventType.PMID_STAGE_START:
            stage_label = STAGE_LABELS.get(event.stage, event.stage)
            if event.pmid in self.pmid_status:
                self.pmid_status[event.pmid]["current_stage"] = stage_label
            self._add_log(ts, "info", f"[{event.pmid}] {stage_label} ...")

        elif event.event_type == EventType.PMID_STAGE_COMPLETE:
            stage_label = STAGE_LABELS.get(event.stage, event.stage)
            if event.pmid in self.pmid_status:
                info = self.pmid_status[event.pmid]
                info["completed"] = info.get("completed", 0) + 1
                info["current_stage"] = stage_label
            extra = f" — {event.message}" if event.message else ""
            self._add_log(ts, "success", f"[{event.pmid}] ✅ {stage_label}{extra}")

        elif event.event_type == EventType.PMID_STAGE_ERROR:
            stage_label = STAGE_LABELS.get(event.stage, event.stage)
            self._add_log(ts, "error", f"[{event.pmid}] ❌ {stage_label}: {event.message}")

        elif event.event_type == EventType.PMID_COMPLETE:
            status_val = event.data.get("status", "completed")
            if event.pmid in self.pmid_status:
                if status_val == "completed":
                    self.pmid_status[event.pmid]["status"] = "completed"
                    self.completed_count += 1
                    self._add_log(ts, "success", f"[{event.pmid}] 완료!")
                else:
                    self.pmid_status[event.pmid]["status"] = "failed"
                    self.failed_count += 1
                    self._add_log(ts, "error", f"[{event.pmid}] 실패")

        elif event.event_type == EventType.PIPELINE_COMPLETE:
            self.running = False
            self._add_log(ts, "success", "═══ 파이프라인 완료 ═══")

        elif event.event_type == EventType.LOG_MESSAGE:
            self._add_log(ts, "info", event.message)

        # SSE로 이벤트 전파
        self._broadcast_sse(event)

    def _add_log(self, ts: str, level: str, message: str) -> None:
        self.log_messages.append({
            "timestamp": ts,
            "level": level,
            "message": message,
        })
        # 최근 200개만 유지
        if len(self.log_messages) > 200:
            self.log_messages = self.log_messages[-200:]

    def _broadcast_sse(self, event: PipelineEvent) -> None:
        """모든 SSE 클라이언트에 이벤트 전파"""
        data = json.dumps(self.to_dict(), ensure_ascii=False)
        dead_queues = []
        for q in self._sse_queues:
            try:
                q.put_nowait(data)
            except asyncio.QueueFull:
                dead_queues.append(q)
        for q in dead_queues:
            self._sse_queues.remove(q)

    def add_sse_queue(self) -> asyncio.Queue:
        q: asyncio.Queue = asyncio.Queue(maxsize=50)
        self._sse_queues.append(q)
        return q

    def remove_sse_queue(self, q: asyncio.Queue) -> None:
        if q in self._sse_queues:
            self._sse_queues.remove(q)

    def to_dict(self) -> dict[str, Any]:
        elapsed = ""
        if self.start_time:
            delta = (datetime.now() - self.start_time).total_seconds()
            mins, secs = divmod(int(delta), 60)
            hours, mins = divmod(mins, 60)
            elapsed = f"{hours:02d}:{mins:02d}:{secs:02d}"

        return {
            "running": self.running,
            "pmids": self.pmids,
            "pmid_status": self.pmid_status,
            "elapsed": elapsed,
            "completed": self.completed_count,
            "failed": self.failed_count,
            "total": len(self.pmids),
            "logs": self.log_messages[-50:],
        }


# ── App Factory ──

def create_app(
    results_dir: str = "./results",
    state: DashboardState | None = None,
) -> FastAPI:
    """FastAPI 앱 생성"""
    app = FastAPI(title="BioAuto Dashboard", version="1.0.0")
    app.state.dashboard = state or DashboardState()
    app.state.results_dir = Path(results_dir)
    app.state.scanner = ResultsScanner(Path(results_dir))
    app.state.scanner.scan()  # 초기 스캔 (동기)

    templates = Jinja2Templates(directory=str(_TEMPLATES_DIR))

    if _STATIC_DIR.exists():
        app.mount("/static", StaticFiles(directory=str(_STATIC_DIR)), name="static")

    @app.get("/", response_class=HTMLResponse)
    async def dashboard(request: Request):
        """메인 대시보드"""
        scanner: ResultsScanner = app.state.scanner
        queues_data = [q.to_dict() for q in scanner.queues]
        return templates.TemplateResponse(
            request, "dashboard.html",
            {
                "state": app.state.dashboard.to_dict(),
                "queues": queues_data,
                "total_pmids": scanner.total_pmids,
            },
        )

    @app.get("/api/status", response_class=JSONResponse)
    async def api_status():
        """전체 상태 JSON"""
        return app.state.dashboard.to_dict()

    @app.get("/api/stream")
    async def api_stream(request: Request):
        """SSE 실시간 이벤트 스트림"""
        dashboard_state: DashboardState = app.state.dashboard
        queue = dashboard_state.add_sse_queue()

        async def event_generator():
            try:
                # 초기 상태 전송
                yield {
                    "event": "status",
                    "data": json.dumps(
                        dashboard_state.to_dict(), ensure_ascii=False
                    ),
                }
                while True:
                    if await request.is_disconnected():
                        break
                    try:
                        data = await asyncio.wait_for(queue.get(), timeout=15.0)
                        yield {"event": "status", "data": data}
                    except asyncio.TimeoutError:
                        yield {"event": "ping", "data": ""}
            finally:
                dashboard_state.remove_sse_queue(queue)

        return EventSourceResponse(event_generator())

    @app.post("/api/run", response_class=JSONResponse)
    async def api_run(request: Request):
        """새 파이프라인 실행"""
        body = await request.json()
        pmids = body.get("pmids", [])
        config_data = body.get("config", {})

        if not pmids:
            return JSONResponse(
                {"error": "PMIDs required"}, status_code=400,
            )

        dashboard_state: DashboardState = app.state.dashboard
        if dashboard_state.running:
            return JSONResponse(
                {"error": "Pipeline already running"}, status_code=409,
            )

        dashboard_state.reset(pmids)

        # 백그라운드에서 파이프라인 실행
        asyncio.create_task(
            _run_pipeline_bg(dashboard_state, pmids, app.state.results_dir, config_data)
        )

        return {"status": "started", "pmids": pmids}

    @app.get("/api/results/{pmid}", response_class=JSONResponse)
    async def api_results(pmid: str):
        """PMID별 결과 JSON"""
        result_file = app.state.results_dir / pmid / f"final_report_{pmid}.json"
        if not result_file.exists():
            return JSONResponse(
                {"error": f"No results for {pmid}"}, status_code=404,
            )
        with open(result_file) as f:
            return json.load(f)

    @app.get("/reports/{pmid}", response_class=HTMLResponse)
    async def serve_report(pmid: str):
        """HTML 리포트 서빙"""
        report_file = app.state.results_dir / pmid / f"report_{pmid}.html"
        if not report_file.exists():
            return HTMLResponse(
                f"<h1>Report not found for {pmid}</h1>", status_code=404,
            )
        return HTMLResponse(report_file.read_text(encoding="utf-8"))

    # ── Queue API ──

    @app.get("/api/queues", response_class=JSONResponse)
    async def api_queues():
        """Queue 목록 반환"""
        scanner: ResultsScanner = app.state.scanner
        return {
            "queues": [q.to_dict() for q in scanner.queues],
            "total_pmids": scanner.total_pmids,
            "last_scanned": scanner.last_scanned,
        }

    @app.get("/api/queues/{queue_id}", response_class=JSONResponse)
    async def api_queue_detail(queue_id: str):
        """Queue 상세"""
        scanner: ResultsScanner = app.state.scanner
        queue = scanner.get_queue(queue_id)
        if not queue:
            return JSONResponse(
                {"error": f"Queue '{queue_id}' not found"}, status_code=404,
            )
        return queue.to_dict()

    @app.post("/api/queues/rescan", response_class=JSONResponse)
    async def api_queues_rescan():
        """디스크 재스캔"""
        scanner: ResultsScanner = app.state.scanner
        scanner.scan()
        return {
            "queues": [q.to_dict() for q in scanner.queues],
            "total_pmids": scanner.total_pmids,
            "last_scanned": scanner.last_scanned,
        }

    return app


async def _run_pipeline_bg(
    state: DashboardState,
    pmids: list[str],
    results_dir: Path,
    config_data: dict,
) -> None:
    """백그라운드 파이프라인 실행"""
    try:
        from core.pipeline import AsyncPipeline, PipelineConfig

        if config_data:
            config = PipelineConfig.from_dict(config_data)
            config.pmids = pmids
            config.results_dir = results_dir
        else:
            config = PipelineConfig(pmids=pmids, results_dir=results_dir)

        pipeline = AsyncPipeline(config)
        pipeline.event_bus = state.event_bus
        state.event_bus.subscribe(state.handle_event)

        await pipeline.run()
    except Exception as e:
        state.running = False
        state._add_log(
            datetime.now().strftime("%H:%M:%S"),
            "error",
            f"파이프라인 오류: {e}",
        )
