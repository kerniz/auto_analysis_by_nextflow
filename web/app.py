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


# ── Cleanup Helpers ──

def _cleanup_pmid_references(pmid: str, results_dir: Path) -> None:
    """PMID 삭제 후 관련 JSON 파일에서 참조 정리."""
    # execution_summary.json에서 PMID 제거
    summary_file = results_dir / "execution_summary.json"
    if summary_file.exists():
        try:
            with open(summary_file) as f:
                data = json.load(f)
            pmid_results = data.get("pmid_results", {})
            if pmid in pmid_results:
                del pmid_results[pmid]
                # 카운터 업데이트
                exec_summary = data.get("execution_summary", {})
                total = exec_summary.get("total", 0)
                if total > 0:
                    exec_summary["total"] = total - 1
                data["pmid_results"] = pmid_results
                data["execution_summary"] = exec_summary
                with open(summary_file, "w") as f:
                    json.dump(data, f, indent=2, ensure_ascii=False)
        except (json.JSONDecodeError, OSError):
            pass

    # progress.json에서 PMID 제거
    progress_file = results_dir / "progress.json"
    if progress_file.exists():
        try:
            with open(progress_file) as f:
                data = json.load(f)
            if pmid in data:
                del data[pmid]
                with open(progress_file, "w") as f:
                    json.dump(data, f, indent=2, ensure_ascii=False)
        except (json.JSONDecodeError, OSError):
            pass

    # error_log.json에서 PMID 관련 항목 제거
    error_file = results_dir / "error_log.json"
    if error_file.exists():
        try:
            with open(error_file) as f:
                data = json.load(f)
            if isinstance(data, list):
                data = [e for e in data if e.get("pmid") != pmid]
            elif isinstance(data, dict) and pmid in data:
                del data[pmid]
            with open(error_file, "w") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
        except (json.JSONDecodeError, OSError):
            pass


# ── App Factory ──

def create_app(
    results_dir: str = "./results",
    state: DashboardState | None = None,
    results_dirs: list[str] | None = None,
) -> FastAPI:
    """FastAPI 앱 생성 (멀티 디렉토리 지원)"""
    app = FastAPI(title="BioAuto Dashboard", version="1.0.0")
    app.state.dashboard = state or DashboardState()

    if results_dirs:
        dirs = [Path(d) for d in results_dirs]
    else:
        dirs = [Path(results_dir)]
    app.state.results_dirs = dirs
    app.state.results_dir = dirs[0]  # 하위 호환 (파이프라인 실행 대상)
    app.state.scanner = ResultsScanner(dirs)
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
        scanner: ResultsScanner = app.state.scanner
        pmid_path = scanner.resolve_pmid_path(pmid)
        if not pmid_path:
            return JSONResponse(
                {"error": f"No results for {pmid}"}, status_code=404,
            )
        result_file = pmid_path / f"final_report_{pmid}.json"
        if not result_file.exists():
            return JSONResponse(
                {"error": f"No results for {pmid}"}, status_code=404,
            )
        with open(result_file) as f:
            return json.load(f)

    @app.delete("/api/results/{pmid}", response_class=JSONResponse)
    async def api_delete_pmid(pmid: str):
        """PMID 결과 폴더 + 관련 참조 깨끗이 삭제"""
        import shutil

        scanner: ResultsScanner = app.state.scanner
        pmid_path = scanner.resolve_pmid_path(pmid)
        if not pmid_path or not pmid_path.exists():
            return JSONResponse(
                {"error": f"PMID '{pmid}' not found"}, status_code=404,
            )
        if not scanner.is_safe_path(pmid_path):
            return JSONResponse(
                {"error": "Invalid path"}, status_code=400,
            )
        results_dir = pmid_path.parent
        shutil.rmtree(pmid_path)
        _cleanup_pmid_references(pmid, results_dir)
        scanner.scan()
        return {"status": "deleted", "pmid": pmid}

    @app.delete("/api/queues/{queue_id}", response_class=JSONResponse)
    async def api_delete_queue(queue_id: str):
        """Queue(연구 주제) 전체 삭제"""
        import shutil

        scanner: ResultsScanner = app.state.scanner
        queue = scanner.get_queue(queue_id)
        if not queue:
            return JSONResponse(
                {"error": f"Queue '{queue_id}' not found"}, status_code=404,
            )
        source_dir = Path(queue.source_dir) if queue.source_dir else None

        # 다른 Queue에서도 참조하는 PMID는 폴더 삭제 안 함
        other_pmids: set[str] = set()
        for other_q in scanner.queues:
            if other_q.queue_id != queue_id:
                other_pmids.update(other_q.pmids)

        deleted_pmids = []
        skipped_pmids = []
        for pmid in queue.pmids:
            if pmid in other_pmids:
                skipped_pmids.append(pmid)
                continue  # 다른 Queue에서 참조 → 폴더 보존
            pmid_path = (source_dir / pmid) if source_dir else None
            if pmid_path and pmid_path.exists() and scanner.is_safe_path(pmid_path):
                shutil.rmtree(pmid_path)
                if source_dir:
                    _cleanup_pmid_references(pmid, source_dir)
                deleted_pmids.append(pmid)
        # queue manifest 삭제
        if source_dir:
            manifest_dir = source_dir / ".queues"
            if manifest_dir.exists():
                # queue_id에서 dir_slug prefix 제거하여 원본 파일명 탐색
                raw_id = queue_id.split(":", 1)[-1] if ":" in queue_id else queue_id
                for candidate in [f"{raw_id}.json", f"{queue_id}.json"]:
                    manifest = manifest_dir / candidate
                    if manifest.exists():
                        manifest.unlink()
        scanner.scan()
        return {
            "status": "deleted",
            "queue_id": queue_id,
            "deleted_pmids": deleted_pmids,
            "skipped_pmids": skipped_pmids,
        }

    @app.get("/pipeline-files/{file_path:path}")
    async def serve_pipeline_file(file_path: str):
        """nf-core 산출물 파일 서빙 (results/ 하위)"""
        from fastapi.responses import FileResponse
        for results_dir in app.state.results_dirs:
            candidate = results_dir / file_path
            if candidate.exists() and candidate.is_file():
                # 보안: results_dir 안에 있는지 확인
                scanner: ResultsScanner = app.state.scanner
                if scanner.is_safe_path(candidate):
                    return FileResponse(str(candidate))
        return HTMLResponse("<h1>File not found</h1>", status_code=404)

    @app.get("/reports/{pmid}", response_class=HTMLResponse)
    async def serve_report(pmid: str):
        """HTML 리포트 서빙"""
        scanner: ResultsScanner = app.state.scanner
        pmid_path = scanner.resolve_pmid_path(pmid)
        if not pmid_path:
            return HTMLResponse(
                f"<h1>Report not found for {pmid}</h1>", status_code=404,
            )
        report_file = pmid_path / f"report_{pmid}.html"
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

    # ── Slurm API ──

    @app.get("/api/slurm/jobs", response_class=JSONResponse)
    async def api_slurm_jobs():
        """Slurm 작업 목록 (REST API 경유)."""
        try:
            from core.slurm_client import SlurmClient
            c = SlurmClient()
            jobs = c.jobs()
            summary = []
            for j in jobs:
                st = j.get("job_state", ["?"])
                if isinstance(st, list):
                    st = st[0] if st else "?"
                summary.append({
                    "job_id": j.get("job_id"),
                    "name": j.get("name", ""),
                    "state": st,
                    "partition": j.get("partition", ""),
                    "node": j.get("batch_host", ""),
                    "reason": j.get("state_reason", ""),
                })
            return {"jobs": summary, "total": len(summary)}
        except Exception as e:
            return JSONResponse(
                {"error": str(e), "jobs": []}, status_code=200,
            )

    @app.get("/api/slurm/nodes", response_class=JSONResponse)
    async def api_slurm_nodes():
        """Slurm 노드 정보."""
        try:
            from core.slurm_client import SlurmClient
            c = SlurmClient()
            nodes = c.nodes()
            return {"nodes": [
                {
                    "name": n.get("name"),
                    "cpus": n.get("cpus"),
                    "memory_mb": n.get("real_memory"),
                    "state": n.get("state"),
                    "gres": n.get("gres", ""),
                }
                for n in nodes
            ]}
        except Exception as e:
            return JSONResponse(
                {"error": str(e), "nodes": []},
                status_code=200,
            )

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
