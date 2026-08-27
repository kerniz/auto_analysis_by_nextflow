"""Tests for Web UI (FastAPI + SSE) components."""

import asyncio
import json
from pathlib import Path

from fastapi.testclient import TestClient

from core.events import (
    STAGE_LABELS,
    EventType,
    PipelineEvent,
)
from web.app import DashboardState, create_app

# ── DashboardState Tests ──

class TestDashboardState:
    """DashboardState in-memory 상태 관리 테스트"""

    def test_initial_state(self):
        state = DashboardState()
        assert state.running is False
        assert state.pmids == []
        assert state.pmid_status == {}
        assert state.completed_count == 0
        assert state.failed_count == 0
        assert state.log_messages == []

    def test_reset(self):
        state = DashboardState()
        state.reset(["111", "222"])
        assert state.running is True
        assert state.pmids == ["111", "222"]
        assert len(state.pmid_status) == 2
        assert state.start_time is not None
        assert state.completed_count == 0
        assert state.failed_count == 0

    def test_reset_pmid_status_structure(self):
        state = DashboardState()
        state.reset(["333"])
        info = state.pmid_status["333"]
        assert info["current_stage"] == "pending"
        assert info["completed"] == 0
        assert info["total"] == 8
        assert info["status"] == "pending"

    def test_to_dict(self):
        state = DashboardState()
        state.reset(["111"])
        d = state.to_dict()
        assert "running" in d
        assert "pmids" in d
        assert "pmid_status" in d
        assert "elapsed" in d
        assert "completed" in d
        assert "failed" in d
        assert "total" in d
        assert "logs" in d
        assert d["total"] == 1

    def test_to_dict_elapsed_format(self):
        state = DashboardState()
        state.reset(["111"])
        d = state.to_dict()
        # 시작 직후이므로 00:00:0x 형태
        assert d["elapsed"].startswith("00:00:")

    def test_handle_pipeline_start(self):
        state = DashboardState()
        state.reset(["111"])
        event = PipelineEvent(
            event_type=EventType.PIPELINE_START,
        )
        state.handle_event(event)
        assert len(state.log_messages) == 1
        assert "Pipeline started" in state.log_messages[0]["message"]

    def test_handle_pmid_start(self):
        state = DashboardState()
        state.reset(["111"])
        event = PipelineEvent(
            event_type=EventType.PMID_START, pmid="111",
        )
        state.handle_event(event)
        assert state.pmid_status["111"]["status"] == "running"
        assert state.pmid_status["111"]["start_time"] is not None

    def test_handle_pmid_stage_start(self):
        state = DashboardState()
        state.reset(["111"])
        event = PipelineEvent(
            event_type=EventType.PMID_STAGE_START,
            pmid="111",
            stage="pubmed",
        )
        state.handle_event(event)
        assert state.pmid_status["111"]["current_stage"] == STAGE_LABELS["pubmed"]

    def test_handle_pmid_stage_complete(self):
        state = DashboardState()
        state.reset(["111"])
        event = PipelineEvent(
            event_type=EventType.PMID_STAGE_COMPLETE,
            pmid="111",
            stage="pubmed",
            message="metadata fetched",
        )
        state.handle_event(event)
        assert state.pmid_status["111"]["completed"] == 1
        assert any("✅" in log["message"] for log in state.log_messages)

    def test_handle_pmid_stage_error(self):
        state = DashboardState()
        state.reset(["111"])
        event = PipelineEvent(
            event_type=EventType.PMID_STAGE_ERROR,
            pmid="111",
            stage="sra",
            message="timeout",
        )
        state.handle_event(event)
        assert any("❌" in log["message"] for log in state.log_messages)

    def test_handle_pmid_complete_success(self):
        state = DashboardState()
        state.reset(["111"])
        event = PipelineEvent(
            event_type=EventType.PMID_COMPLETE,
            pmid="111",
            data={"status": "completed"},
        )
        state.handle_event(event)
        assert state.pmid_status["111"]["status"] == "completed"
        assert state.completed_count == 1

    def test_handle_pmid_complete_failure(self):
        state = DashboardState()
        state.reset(["111"])
        event = PipelineEvent(
            event_type=EventType.PMID_COMPLETE,
            pmid="111",
            data={"status": "failed"},
        )
        state.handle_event(event)
        assert state.pmid_status["111"]["status"] == "failed"
        assert state.failed_count == 1

    def test_handle_pipeline_complete(self):
        state = DashboardState()
        state.reset(["111"])
        state.running = True
        event = PipelineEvent(event_type=EventType.PIPELINE_COMPLETE)
        state.handle_event(event)
        assert state.running is False
        assert any("Pipeline Complete" in log["message"] for log in state.log_messages)

    def test_handle_log_message(self):
        state = DashboardState()
        event = PipelineEvent(
            event_type=EventType.LOG_MESSAGE,
            message="custom log entry",
        )
        state.handle_event(event)
        assert len(state.log_messages) == 1
        assert state.log_messages[0]["message"] == "custom log entry"

    def test_log_limit_200(self):
        state = DashboardState()
        for i in range(250):
            state._add_log("00:00:00", "info", f"msg {i}")
        assert len(state.log_messages) == 200
        assert state.log_messages[0]["message"] == "msg 50"

    def test_stage_complete_accumulates(self):
        state = DashboardState()
        state.reset(["111"])
        stages = ["pubmed", "sra", "sequencing", "data_aggregation"]
        for stage in stages:
            event = PipelineEvent(
                event_type=EventType.PMID_STAGE_COMPLETE,
                pmid="111",
                stage=stage,
            )
            state.handle_event(event)
        assert state.pmid_status["111"]["completed"] == 4

    def test_unknown_pmid_event_ignored(self):
        state = DashboardState()
        state.reset(["111"])
        event = PipelineEvent(
            event_type=EventType.PMID_START, pmid="999",
        )
        # Should not raise
        state.handle_event(event)
        assert "999" not in state.pmid_status


# ── SSE Queue Tests ──

class TestSSEQueues:
    """SSE 큐 관리 테스트"""

    def test_add_sse_queue(self):
        state = DashboardState()
        q = state.add_sse_queue()
        assert q in state._sse_queues

    def test_remove_sse_queue(self):
        state = DashboardState()
        q = state.add_sse_queue()
        state.remove_sse_queue(q)
        assert q not in state._sse_queues

    def test_remove_nonexistent_queue(self):
        state = DashboardState()
        q = asyncio.Queue()
        state.remove_sse_queue(q)  # should not raise

    def test_broadcast_sse(self):
        state = DashboardState()
        state.reset(["111"])
        q = state.add_sse_queue()
        event = PipelineEvent(event_type=EventType.LOG_MESSAGE, message="test")
        state._broadcast_sse(event)
        assert not q.empty()
        data = q.get_nowait()
        parsed = json.loads(data)
        assert "logs" in parsed


# ── FastAPI App Tests ──

class TestFastAPIApp:
    """FastAPI 앱 엔드포인트 테스트"""

    def _make_client(self, state=None, results_dir="/tmp/test_results"):
        app = create_app(results_dir=results_dir, state=state)
        return TestClient(app)

    def test_dashboard_get(self):
        client = self._make_client()
        resp = client.get("/")
        assert resp.status_code == 200
        assert "BioAuto" in resp.text
        assert "Dashboard" in resp.text

    def test_api_status(self):
        state = DashboardState()
        state.reset(["111", "222"])
        client = self._make_client(state=state)

        resp = client.get("/api/status")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 2
        assert data["running"] is True
        assert "111" in data["pmids"]
        assert "222" in data["pmids"]

    def test_api_status_empty(self):
        client = self._make_client()
        resp = client.get("/api/status")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 0
        assert data["running"] is False

    def test_api_run_no_pmids(self):
        client = self._make_client()
        resp = client.post("/api/run", json={"pmids": []})
        assert resp.status_code == 400
        assert "PMIDs required" in resp.json()["error"]

    def test_api_run_already_running(self):
        state = DashboardState()
        state.running = True
        client = self._make_client(state=state)

        resp = client.post("/api/run", json={"pmids": ["111"]})
        assert resp.status_code == 409
        assert "already running" in resp.json()["error"]

    def test_api_results_not_found(self):
        client = self._make_client(results_dir="/tmp/nonexistent_results_dir")
        resp = client.get("/api/results/99999")
        assert resp.status_code == 404

    def test_api_results_found(self, tmp_path):
        # 결과 파일 생성
        pmid_dir = tmp_path / "12345"
        pmid_dir.mkdir()
        report_data = {"pmid": "12345", "status": "completed"}
        (pmid_dir / "final_report_12345.json").write_text(
            json.dumps(report_data), encoding="utf-8"
        )

        client = self._make_client(results_dir=str(tmp_path))
        resp = client.get("/api/results/12345")
        assert resp.status_code == 200
        assert resp.json()["pmid"] == "12345"

    def test_reports_not_found(self):
        client = self._make_client(results_dir="/tmp/nonexistent_results_dir")
        resp = client.get("/reports/99999")
        assert resp.status_code == 404

    def test_reports_found(self, tmp_path):
        pmid_dir = tmp_path / "12345"
        pmid_dir.mkdir()
        html = "<html><body>Report for 12345</body></html>"
        (pmid_dir / "report_12345.html").write_text(html, encoding="utf-8")

        client = self._make_client(results_dir=str(tmp_path))
        resp = client.get("/reports/12345")
        assert resp.status_code == 200
        assert "Report for 12345" in resp.text


# ── CLI Web Command Tests ──

class TestWebCLI:
    """Web CLI 명령 테스트"""

    def test_web_command_exists(self):
        from core.cli import cli
        commands = cli.commands
        assert "web" in commands

    def test_web_command_help(self):
        from click.testing import CliRunner

        from core.cli import cli
        runner = CliRunner()
        result = runner.invoke(cli, ["web", "--help"])
        assert result.exit_code == 0
        assert "웹 대시보드" in result.output
        assert "--port" in result.output
        assert "--host" in result.output


# ── create_app Factory Tests ──

class TestCreateApp:
    """create_app 팩토리 함수 테스트"""

    def test_creates_fastapi_app(self):
        app = create_app()
        assert app.title == "BioAuto Dashboard"

    def test_custom_results_dir(self):
        app = create_app(results_dir="/tmp/custom")
        assert app.state.results_dir == Path("/tmp/custom")

    def test_custom_state(self):
        state = DashboardState()
        state.reset(["AAA"])
        app = create_app(state=state)
        assert app.state.dashboard is state
        assert app.state.dashboard.pmids == ["AAA"]

    def test_default_state(self):
        app = create_app()
        assert isinstance(app.state.dashboard, DashboardState)
        assert app.state.dashboard.running is False

    def test_has_scanner(self):
        from web.results_scanner import ResultsScanner
        app = create_app()
        assert isinstance(app.state.scanner, ResultsScanner)


# ── Queue API Tests ──

class TestQueueAPI:
    """Queue API 엔드포인트 테스트"""

    def _make_client(self, results_dir="/tmp/nonexistent_test_dir"):
        app = create_app(results_dir=results_dir)
        return TestClient(app)

    def test_api_queues_empty(self):
        client = self._make_client()
        resp = client.get("/api/queues")
        assert resp.status_code == 200
        data = resp.json()
        assert data["queues"] == []
        assert data["total_pmids"] == 0

    def test_api_queues_with_data(self, tmp_path):
        # Create PMID results
        pmid_dir = tmp_path / "111"
        pmid_dir.mkdir()
        (pmid_dir / "final_report_111.json").write_text(
            json.dumps({
                "pmid": "111", "status": "completed",
                "pubmed_metadata": {"title": "Test paper"},
                "debate_verdict": "PASS", "debate_score": 0.9,
            }),
            encoding="utf-8",
        )

        client = self._make_client(results_dir=str(tmp_path))
        resp = client.get("/api/queues")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["queues"]) == 1
        assert data["total_pmids"] == 1
        assert "111" in data["queues"][0]["pmids"]

    def test_api_queue_detail(self, tmp_path):
        pmid_dir = tmp_path / "222"
        pmid_dir.mkdir()
        (pmid_dir / "final_report_222.json").write_text(
            json.dumps({
                "pmid": "222", "status": "completed",
                "pubmed_metadata": {"title": "Detail paper"},
            }),
            encoding="utf-8",
        )

        client = self._make_client(results_dir=str(tmp_path))
        resp = client.get("/api/queues/pmid_222")
        assert resp.status_code == 200
        data = resp.json()
        assert data["pmids"] == ["222"]

    def test_api_queue_detail_not_found(self, tmp_path):
        client = self._make_client(results_dir=str(tmp_path))
        resp = client.get("/api/queues/nonexistent")
        assert resp.status_code == 404

    def test_api_queues_rescan(self, tmp_path):
        client = self._make_client(results_dir=str(tmp_path))
        # Initially empty
        resp = client.get("/api/queues")
        assert resp.json()["total_pmids"] == 0

        # Add result
        pmid_dir = tmp_path / "333"
        pmid_dir.mkdir()
        (pmid_dir / "final_report_333.json").write_text(
            json.dumps({
                "pmid": "333", "status": "completed",
                "pubmed_metadata": {},
            }),
            encoding="utf-8",
        )

        # Rescan
        resp = client.post("/api/queues/rescan")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total_pmids"] == 1

    def test_dashboard_shows_results_tab(self, tmp_path):
        pmid_dir = tmp_path / "444"
        pmid_dir.mkdir()
        (pmid_dir / "final_report_444.json").write_text(
            json.dumps({
                "pmid": "444", "status": "completed",
                "pubmed_metadata": {"title": "Dashboard test"},
                "debate_verdict": "WARN",
            }),
            encoding="utf-8",
        )

        client = self._make_client(results_dir=str(tmp_path))
        resp = client.get("/")
        assert resp.status_code == 200
        assert "Results" in resp.text
        assert "444" in resp.text
        assert "Dashboard test" in resp.text

    def test_dashboard_empty_shows_no_results(self, tmp_path):
        client = self._make_client(results_dir=str(tmp_path))
        resp = client.get("/")
        assert resp.status_code == 200
        assert "No analysis results found" in resp.text


# ── Multi-Directory Tests ──

def _make_pmid_result(results_dir: Path, pmid: str, title: str = "Test"):
    """헬퍼: PMID 결과 폴더 + final_report 생성"""
    pmid_dir = results_dir / pmid
    pmid_dir.mkdir(parents=True, exist_ok=True)
    (pmid_dir / f"final_report_{pmid}.json").write_text(
        json.dumps({
            "pmid": pmid, "status": "completed",
            "pubmed_metadata": {"title": title},
        }),
        encoding="utf-8",
    )


class TestMultiDirScanner:
    """멀티 디렉토리 ResultsScanner 테스트"""

    def test_scan_multiple_dirs(self, tmp_path):
        from web.results_scanner import ResultsScanner
        dir_a = tmp_path / "proj_a" / "results"
        dir_b = tmp_path / "proj_b" / "results"
        _make_pmid_result(dir_a, "111", "Paper A")
        _make_pmid_result(dir_b, "222", "Paper B")

        scanner = ResultsScanner([dir_a, dir_b])
        scanner.scan()
        assert scanner.total_pmids == 2
        all_pmids = [p for q in scanner.queues for p in q.pmids]
        assert "111" in all_pmids
        assert "222" in all_pmids

    def test_queue_source_dir(self, tmp_path):
        from web.results_scanner import ResultsScanner
        dir_a = tmp_path / "proj_a" / "results"
        _make_pmid_result(dir_a, "111")

        scanner = ResultsScanner([dir_a])
        scanner.scan()
        assert len(scanner.queues) == 1
        assert scanner.queues[0].source_dir == str(dir_a.resolve())

    def test_resolve_pmid_path_multi_dir(self, tmp_path):
        from web.results_scanner import ResultsScanner
        dir_a = tmp_path / "a"
        dir_b = tmp_path / "b"
        _make_pmid_result(dir_a, "111")
        _make_pmid_result(dir_b, "222")

        scanner = ResultsScanner([dir_a, dir_b])
        assert scanner.resolve_pmid_path("111") == dir_a / "111"
        assert scanner.resolve_pmid_path("222") == dir_b / "222"
        assert scanner.resolve_pmid_path("999") is None

    def test_single_path_backward_compat(self, tmp_path):
        from web.results_scanner import ResultsScanner
        _make_pmid_result(tmp_path, "111")
        scanner = ResultsScanner(tmp_path)  # Path (not list)
        scanner.scan()
        assert scanner.total_pmids == 1

    def test_queue_id_no_collision(self, tmp_path):
        from web.results_scanner import ResultsScanner
        dir_a = tmp_path / "alpha"
        dir_b = tmp_path / "beta"
        _make_pmid_result(dir_a, "111")
        _make_pmid_result(dir_b, "222")

        scanner = ResultsScanner([dir_a, dir_b])
        scanner.scan()
        ids = [q.queue_id for q in scanner.queues]
        assert len(ids) == len(set(ids)), "Queue IDs should be unique"

    def test_is_safe_path(self, tmp_path):
        from web.results_scanner import ResultsScanner
        dir_a = tmp_path / "a"
        dir_a.mkdir()
        scanner = ResultsScanner([dir_a])
        assert scanner.is_safe_path(dir_a / "some_pmid")
        assert not scanner.is_safe_path(tmp_path / "outside")


# ── Delete API Tests ──

class TestDeleteAPI:
    """DELETE 엔드포인트 테스트"""

    def _make_client(self, results_dirs: list[str]):
        app = create_app(results_dirs=results_dirs)
        return TestClient(app)

    def test_delete_pmid_success(self, tmp_path):
        _make_pmid_result(tmp_path, "111")
        client = self._make_client([str(tmp_path)])
        resp = client.delete("/api/results/111")
        assert resp.status_code == 200
        assert resp.json()["status"] == "deleted"
        assert not (tmp_path / "111").exists()

    def test_delete_pmid_not_found(self, tmp_path):
        client = self._make_client([str(tmp_path)])
        resp = client.delete("/api/results/999")
        assert resp.status_code == 404

    def test_delete_pmid_rescan(self, tmp_path):
        _make_pmid_result(tmp_path, "111")
        _make_pmid_result(tmp_path, "222")
        client = self._make_client([str(tmp_path)])
        # 삭제 전
        resp = client.get("/api/queues")
        assert resp.json()["total_pmids"] == 2
        # 삭제
        client.delete("/api/results/111")
        # 삭제 후 자동 rescan
        resp = client.get("/api/queues")
        assert resp.json()["total_pmids"] == 1

    def test_delete_queue_success(self, tmp_path):
        _make_pmid_result(tmp_path, "111")
        client = self._make_client([str(tmp_path)])
        # queue_id 확인
        resp = client.get("/api/queues")
        queue_id = resp.json()["queues"][0]["queue_id"]
        # 삭제
        resp = client.delete(f"/api/queues/{queue_id}")
        assert resp.status_code == 200
        assert resp.json()["status"] == "deleted"
        assert not (tmp_path / "111").exists()

    def test_delete_queue_not_found(self, tmp_path):
        client = self._make_client([str(tmp_path)])
        resp = client.delete("/api/queues/nonexistent")
        assert resp.status_code == 404

    def test_delete_multi_dir(self, tmp_path):
        """멀티 디렉토리에서 PMID 삭제"""
        dir_a = tmp_path / "a"
        dir_b = tmp_path / "b"
        _make_pmid_result(dir_a, "111")
        _make_pmid_result(dir_b, "222")
        client = self._make_client([str(dir_a), str(dir_b)])
        # dir_b의 PMID 삭제
        resp = client.delete("/api/results/222")
        assert resp.status_code == 200
        assert not (dir_b / "222").exists()
        assert (dir_a / "111").exists()  # dir_a는 무사


# ── Multi-Dir App Tests ──

class TestMultiDirApp:
    """멀티 디렉토리 앱 통합 테스트"""

    def test_create_app_with_results_dirs(self, tmp_path):
        dir_a = tmp_path / "a"
        dir_b = tmp_path / "b"
        _make_pmid_result(dir_a, "111")
        _make_pmid_result(dir_b, "222")
        app = create_app(results_dirs=[str(dir_a), str(dir_b)])
        assert len(app.state.results_dirs) == 2
        client = TestClient(app)
        resp = client.get("/api/queues")
        assert resp.json()["total_pmids"] == 2

    def test_api_results_multi_dir(self, tmp_path):
        dir_a = tmp_path / "a"
        dir_b = tmp_path / "b"
        _make_pmid_result(dir_a, "111", "Paper A")
        _make_pmid_result(dir_b, "222", "Paper B")
        app = create_app(results_dirs=[str(dir_a), str(dir_b)])
        client = TestClient(app)
        # dir_b의 PMID 접근
        resp = client.get("/api/results/222")
        assert resp.status_code == 200
        assert resp.json()["pmid"] == "222"

    def test_dashboard_shows_delete_buttons(self, tmp_path):
        _make_pmid_result(tmp_path, "111")
        app = create_app(results_dirs=[str(tmp_path)])
        client = TestClient(app)
        resp = client.get("/")
        assert resp.status_code == 200
        assert "deletePmid" in resp.text
        assert "deleteQueue" in resp.text


class TestServerTokenAuth:
    """SEC-001 원격 토큰 인증 테스트"""

    def test_token_auth_blocks_unauthorized_post(self, tmp_path):
        app = create_app(results_dirs=[str(tmp_path)], server_token="secret-token-123")
        client = TestClient(app)
        # 토큰 없는 POST 거부 (401)
        resp = client.post("/api/run", json={"pmids": ["111"]})
        assert resp.status_code == 401
        assert "Unauthorized" in resp.json()["error"]

        # 잘못된 토큰 거부 (401)
        resp = client.post("/api/run", json={"pmids": ["111"]}, headers={"X-Server-Token": "wrong-token"})
        assert resp.status_code == 401

        # 올바른 토큰 허용
        resp = client.post("/api/run", json={"pmids": ["111"]}, headers={"X-Server-Token": "secret-token-123"})
        assert resp.status_code == 200

    def test_token_auth_allows_status_get(self, tmp_path):
        app = create_app(results_dirs=[str(tmp_path)], server_token="secret-token-123")
        client = TestClient(app)
        resp = client.get("/api/status")
        assert resp.status_code == 200

    def test_token_auth_blocks_protected_reads(self, tmp_path):
        """원격 모드에서 결과/파이프라인 파일 GET도 토큰이 필요하다."""
        app = create_app(results_dirs=[str(tmp_path)], server_token="secret-token-123")
        client = TestClient(app)

        denied = client.get("/api/results/111")
        assert denied.status_code == 401

        denied_file = client.get("/pipeline-files/dummy.html")
        assert denied_file.status_code == 401

        allowed = client.get(
            "/api/results/111",
            headers={"X-Server-Token": "secret-token-123"},
        )
        assert allowed.status_code != 401

