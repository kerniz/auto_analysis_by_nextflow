"""Tests for ResultsScanner — 디스크 결과 스캔 및 Queue 그룹핑"""

import json
from pathlib import Path

from web.results_scanner import QueueInfo, ResultsScanner


class TestQueueInfo:
    """QueueInfo 데이터 클래스 테스트"""

    def test_to_dict(self):
        q = QueueInfo(
            queue_id="test_001",
            name="Test Queue",
            pmids=["111", "222"],
            timestamp="2026-03-03T12:00:00",
            status="completed",
            completed_count=2,
            failed_count=0,
            has_project_report=True,
            pmid_summaries={"111": {"title": "A"}, "222": {"title": "B"}},
        )
        d = q.to_dict()
        assert d["queue_id"] == "test_001"
        assert d["name"] == "Test Queue"
        assert len(d["pmids"]) == 2
        assert d["has_project_report"] is True

    def test_defaults(self):
        q = QueueInfo(
            queue_id="x", name="x", pmids=[], timestamp="",
            status="pending",
        )
        assert q.completed_count == 0
        assert q.failed_count == 0
        assert q.has_project_report is False
        assert q.pmid_summaries == {}


class TestResultsScannerEmpty:
    """빈 디렉토리 스캔 테스트"""

    def test_scan_nonexistent_dir(self):
        scanner = ResultsScanner(Path("/tmp/nonexistent_results_dir_xyz"))
        result = scanner.scan()
        assert result == []
        assert scanner.total_pmids == 0

    def test_scan_empty_dir(self, tmp_path):
        scanner = ResultsScanner(tmp_path)
        result = scanner.scan()
        assert result == []
        assert scanner.total_pmids == 0
        assert scanner.last_scanned != ""


class TestResultsScannerManifest:
    """Queue 매니페스트(.queues/) 스캔 테스트"""

    def _setup_manifest(self, tmp_path, queue_id, pmids):
        queue_dir = tmp_path / ".queues"
        queue_dir.mkdir()
        manifest = {
            "queue_id": queue_id,
            "name": f"Test {queue_id}",
            "pmids": pmids,
            "timestamp": "2026-03-03T12:00:00",
            "status": "completed",
        }
        (queue_dir / f"{queue_id}.json").write_text(
            json.dumps(manifest), encoding="utf-8"
        )
        # Create PMID dirs with final reports
        for pmid in pmids:
            pmid_dir = tmp_path / pmid
            pmid_dir.mkdir()
            report = {
                "pmid": pmid,
                "status": "completed",
                "duration_seconds": 100,
                "pubmed_metadata": {"title": f"Paper {pmid}", "journal": "Test"},
                "sequencing_type": "RNA-seq",
                "llm_rating": "CONSENSUS",
                "debate_verdict": "PASS",
                "debate_score": 0.85,
            }
            (pmid_dir / f"final_report_{pmid}.json").write_text(
                json.dumps(report), encoding="utf-8"
            )

    def test_scan_manifest(self, tmp_path):
        self._setup_manifest(tmp_path, "q1", ["111", "222"])
        scanner = ResultsScanner(tmp_path)
        result = scanner.scan()
        assert len(result) == 1
        assert result[0].queue_id == "q1"
        assert result[0].pmids == ["111", "222"]
        assert scanner.total_pmids == 2

    def test_manifest_pmid_summaries(self, tmp_path):
        self._setup_manifest(tmp_path, "q1", ["111"])
        scanner = ResultsScanner(tmp_path)
        result = scanner.scan()
        summary = result[0].pmid_summaries["111"]
        assert summary["title"] == "Paper 111"
        assert summary["debate_verdict"] == "PASS"
        assert summary["debate_score"] == 0.85

    def test_multiple_manifests(self, tmp_path):
        self._setup_manifest(tmp_path, "q1", ["111"])
        # Add second manifest
        queue_dir = tmp_path / ".queues"
        manifest2 = {
            "queue_id": "q2",
            "name": "Second",
            "pmids": ["222"],
            "timestamp": "2026-03-04T12:00:00",
        }
        (queue_dir / "q2.json").write_text(
            json.dumps(manifest2), encoding="utf-8"
        )
        pmid_dir = tmp_path / "222"
        pmid_dir.mkdir()
        (pmid_dir / "final_report_222.json").write_text(
            json.dumps({"pmid": "222", "status": "completed", "pubmed_metadata": {}}),
            encoding="utf-8",
        )
        scanner = ResultsScanner(tmp_path)
        result = scanner.scan()
        assert len(result) == 2
        assert scanner.total_pmids == 2


class TestResultsScannerExecutionSummary:
    """execution_summary.json 폴백 테스트"""

    def test_scan_execution_summary(self, tmp_path):
        # Create execution_summary.json
        summary = {
            "execution_summary": {"total_pmids": 1, "completed": 1, "failed": 0},
            "pmid_results": {"333": {"status": "completed"}},
            "timestamp": "2026-03-03T13:00:00",
        }
        (tmp_path / "execution_summary.json").write_text(
            json.dumps(summary), encoding="utf-8"
        )
        # Create PMID dir
        pmid_dir = tmp_path / "333"
        pmid_dir.mkdir()
        (pmid_dir / "final_report_333.json").write_text(
            json.dumps({
                "pmid": "333", "status": "completed",
                "pubmed_metadata": {"title": "COVID paper"},
                "debate_verdict": "WARN", "debate_score": 0.53,
            }),
            encoding="utf-8",
        )
        scanner = ResultsScanner(tmp_path)
        result = scanner.scan()
        assert len(result) == 1
        assert "333" in result[0].pmids
        assert result[0].pmid_summaries["333"]["title"] == "COVID paper"

    def test_execution_summary_skips_manifest_pmids(self, tmp_path):
        """manifest에 이미 있는 PMID는 execution_summary에서 제외"""
        # Create manifest with PMID 111
        queue_dir = tmp_path / ".queues"
        queue_dir.mkdir()
        (queue_dir / "q1.json").write_text(json.dumps({
            "queue_id": "q1", "name": "Q1",
            "pmids": ["111"], "timestamp": "2026-03-03",
        }), encoding="utf-8")

        # Create execution_summary with same PMID
        (tmp_path / "execution_summary.json").write_text(json.dumps({
            "pmid_results": {"111": {}},
            "timestamp": "2026-03-03T13:00:00",
        }), encoding="utf-8")

        pmid_dir = tmp_path / "111"
        pmid_dir.mkdir()
        (pmid_dir / "final_report_111.json").write_text(
            json.dumps({"pmid": "111", "status": "completed", "pubmed_metadata": {}}),
            encoding="utf-8",
        )

        scanner = ResultsScanner(tmp_path)
        result = scanner.scan()
        # Only 1 queue from manifest, execution_summary produces nothing new
        assert len(result) == 1
        assert result[0].queue_id == "q1"


class TestResultsScannerOrphan:
    """Orphan PMID 디렉토리 테스트"""

    def test_orphan_pmid_creates_singleton_queue(self, tmp_path):
        pmid_dir = tmp_path / "444"
        pmid_dir.mkdir()
        (pmid_dir / "final_report_444.json").write_text(
            json.dumps({
                "pmid": "444", "status": "completed",
                "pubmed_metadata": {"title": "Orphan paper"},
                "sequencing_type": "scRNA-seq",
            }),
            encoding="utf-8",
        )
        scanner = ResultsScanner(tmp_path)
        result = scanner.scan()
        assert len(result) == 1
        assert result[0].queue_id == "pmid_444"
        assert result[0].pmids == ["444"]

    def test_enrichment_dir_ignored(self, tmp_path):
        (tmp_path / "enrichment").mkdir()
        (tmp_path / "raw_data").mkdir()
        scanner = ResultsScanner(tmp_path)
        result = scanner.scan()
        assert len(result) == 0

    def test_mixed_manifest_and_orphan(self, tmp_path):
        """manifest + orphan이 공존하는 경우"""
        queue_dir = tmp_path / ".queues"
        queue_dir.mkdir()
        (queue_dir / "q1.json").write_text(json.dumps({
            "queue_id": "q1", "name": "Q1",
            "pmids": ["111"], "timestamp": "2026-03-03",
        }), encoding="utf-8")

        for pmid in ["111", "999"]:
            d = tmp_path / pmid
            d.mkdir()
            (d / f"final_report_{pmid}.json").write_text(
                json.dumps({
                    "pmid": pmid, "status": "completed",
                    "pubmed_metadata": {"title": f"Paper {pmid}"},
                }),
                encoding="utf-8",
            )

        scanner = ResultsScanner(tmp_path)
        result = scanner.scan()
        assert len(result) == 2
        queue_ids = {q.queue_id for q in result}
        assert "q1" in queue_ids
        assert "pmid_999" in queue_ids


class TestResultsScannerSummary:
    """PMID 요약 추출 테스트"""

    def test_load_pmid_summary_full(self, tmp_path):
        pmid_dir = tmp_path / "555"
        pmid_dir.mkdir()
        report = {
            "pmid": "555",
            "status": "completed",
            "duration_seconds": 500.5,
            "pubmed_metadata": {
                "title": "A great paper",
                "journal": "Nature",
                "authors": ["Kim A", "Lee B", "Park C", "Choi D"],
                "pub_date": "2025 Jan",
                "retrieved_at": "2026-03-03T12:00:00",
            },
            "sequencing_type": "RNA-seq",
            "sequencing_confidence": 0.95,
            "llm_rating": "CONSENSUS",
            "debate_verdict": "PASS",
            "debate_score": 0.88,
            "enrichment_summary": {"novelty_score": 0.75},
        }
        (pmid_dir / "final_report_555.json").write_text(
            json.dumps(report), encoding="utf-8"
        )
        scanner = ResultsScanner(tmp_path)
        summary = scanner._load_pmid_summary("555", tmp_path)
        assert summary["title"] == "A great paper"
        assert summary["journal"] == "Nature"
        assert len(summary["authors"]) == 3  # capped at 3
        assert summary["sequencing_type"] == "RNA-seq"
        assert summary["debate_verdict"] == "PASS"
        assert summary["enrichment_novelty"] == 0.75

    def test_load_pmid_summary_missing(self, tmp_path):
        scanner = ResultsScanner(tmp_path)
        summary = scanner._load_pmid_summary("nonexistent", tmp_path)
        assert summary["pmid"] == "nonexistent"
        assert summary["status"] == "unknown"


class TestResultsScannerMisc:
    """기타 테스트"""

    def test_get_queue_found(self, tmp_path):
        pmid_dir = tmp_path / "111"
        pmid_dir.mkdir()
        (pmid_dir / "final_report_111.json").write_text(
            json.dumps({"pmid": "111", "status": "completed", "pubmed_metadata": {}}),
            encoding="utf-8",
        )
        scanner = ResultsScanner(tmp_path)
        scanner.scan()
        q = scanner.get_queue("pmid_111")
        assert q is not None
        assert q.pmids == ["111"]

    def test_get_queue_not_found(self, tmp_path):
        scanner = ResultsScanner(tmp_path)
        scanner.scan()
        assert scanner.get_queue("nonexistent") is None

    def test_calc_status(self):
        assert ResultsScanner._calc_status(5, 0, 5) == "completed"
        assert ResultsScanner._calc_status(0, 5, 5) == "failed"
        assert ResultsScanner._calc_status(3, 1, 5) == "partial"
        assert ResultsScanner._calc_status(0, 0, 5) == "pending"

    def test_rescan_updates(self, tmp_path):
        scanner = ResultsScanner(tmp_path)
        scanner.scan()
        assert len(scanner.queues) == 0

        # Add a PMID and rescan
        pmid_dir = tmp_path / "777"
        pmid_dir.mkdir()
        (pmid_dir / "final_report_777.json").write_text(
            json.dumps({"pmid": "777", "status": "completed", "pubmed_metadata": {}}),
            encoding="utf-8",
        )
        scanner.scan()
        assert len(scanner.queues) == 1

    def test_has_project_report(self, tmp_path):
        (tmp_path / "project_report.html").write_text("<html></html>")
        queue_dir = tmp_path / ".queues"
        queue_dir.mkdir()
        (queue_dir / "q1.json").write_text(json.dumps({
            "queue_id": "q1", "name": "Q1",
            "pmids": ["111"], "timestamp": "",
        }), encoding="utf-8")
        pmid_dir = tmp_path / "111"
        pmid_dir.mkdir()
        (pmid_dir / "final_report_111.json").write_text(
            json.dumps({"pmid": "111", "status": "completed", "pubmed_metadata": {}}),
            encoding="utf-8",
        )
        scanner = ResultsScanner(tmp_path)
        result = scanner.scan()
        assert result[0].has_project_report is True
