"""Results Scanner — 디스크에서 결과를 스캔하고 Queue로 그룹핑"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any


@dataclass
class QueueInfo:
    """하나의 실행 큐 (연구 주제 단위)"""

    queue_id: str
    name: str
    pmids: list[str]
    timestamp: str
    status: str  # completed / partial / failed
    completed_count: int = 0
    failed_count: int = 0
    has_project_report: bool = False
    pmid_summaries: dict[str, dict[str, Any]] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "queue_id": self.queue_id,
            "name": self.name,
            "pmids": self.pmids,
            "timestamp": self.timestamp,
            "status": self.status,
            "completed_count": self.completed_count,
            "failed_count": self.failed_count,
            "has_project_report": self.has_project_report,
            "pmid_summaries": self.pmid_summaries,
        }


class ResultsScanner:
    """results/ 디렉토리를 스캔하여 Queue 목록을 구성"""

    def __init__(self, results_dir: Path):
        self.results_dir = results_dir
        self._queues: list[QueueInfo] = []
        self._last_scanned: str = ""

    def scan(self) -> list[QueueInfo]:
        """전체 스캔: .queues/ → execution_summary → orphan PMIDs"""
        self._queues = []
        seen_pmids: set[str] = set()

        if not self.results_dir.exists():
            self._last_scanned = datetime.now().isoformat()
            return []

        # 1. .queues/ 매니페스트 스캔
        queue_dir = self.results_dir / ".queues"
        if queue_dir.exists():
            for manifest in sorted(queue_dir.glob("*.json"), reverse=True):
                queue = self._load_queue_manifest(manifest)
                if queue:
                    self._queues.append(queue)
                    seen_pmids.update(queue.pmids)

        # 2. execution_summary.json 폴백
        summary_file = self.results_dir / "execution_summary.json"
        if summary_file.exists():
            queue = self._load_from_execution_summary(summary_file, seen_pmids)
            if queue:
                self._queues.append(queue)
                seen_pmids.update(queue.pmids)

        # 3. Orphan PMID 디렉토리
        for pmid_dir in sorted(self.results_dir.iterdir(), reverse=True):
            if not pmid_dir.is_dir():
                continue
            if pmid_dir.name.startswith(".") or pmid_dir.name in (
                "enrichment", "raw_data",
            ):
                continue
            if pmid_dir.name in seen_pmids:
                continue
            final_report = pmid_dir / f"final_report_{pmid_dir.name}.json"
            if final_report.exists():
                queue = self._create_singleton_queue(pmid_dir.name)
                if queue:
                    self._queues.append(queue)

        self._last_scanned = datetime.now().isoformat()
        return self._queues

    @property
    def queues(self) -> list[QueueInfo]:
        return list(self._queues)

    @property
    def last_scanned(self) -> str:
        return self._last_scanned

    @property
    def total_pmids(self) -> int:
        return sum(len(q.pmids) for q in self._queues)

    def get_queue(self, queue_id: str) -> QueueInfo | None:
        for q in self._queues:
            if q.queue_id == queue_id:
                return q
        return None

    def _load_queue_manifest(self, path: Path) -> QueueInfo | None:
        """queue 매니페스트 JSON 로드"""
        try:
            with open(path) as f:
                data = json.load(f)
            pmids = data.get("pmids", [])
            if not pmids:
                return None
            summaries = {}
            for pmid in pmids:
                summaries[pmid] = self._load_pmid_summary(pmid)
            completed = sum(
                1 for s in summaries.values() if s.get("status") == "completed"
            )
            failed = sum(
                1 for s in summaries.values() if s.get("status") == "failed"
            )
            has_proj = (self.results_dir / "project_report.html").exists()
            return QueueInfo(
                queue_id=data.get("queue_id", path.stem),
                name=data.get("name", path.stem),
                pmids=pmids,
                timestamp=data.get("timestamp", ""),
                status=self._calc_status(completed, failed, len(pmids)),
                completed_count=completed,
                failed_count=failed,
                has_project_report=has_proj,
                pmid_summaries=summaries,
            )
        except (json.JSONDecodeError, OSError):
            return None

    def _load_from_execution_summary(
        self, path: Path, exclude: set[str],
    ) -> QueueInfo | None:
        """execution_summary.json에서 Queue 생성"""
        try:
            with open(path) as f:
                data = json.load(f)
            pmid_results = data.get("pmid_results", {})
            pmids = [p for p in pmid_results if p not in exclude]
            if not pmids:
                return None
            timestamp = data.get("timestamp", "")
            ts_short = timestamp[:19].replace("T", " ") if timestamp else ""
            queue_id = (
                "summary_" + timestamp[:10].replace("-", "") if timestamp
                else "summary"
            )
            summaries = {}
            for pmid in pmids:
                summaries[pmid] = self._load_pmid_summary(pmid)
            exec_summary = data.get("execution_summary", {})
            completed = exec_summary.get("completed", 0)
            failed = exec_summary.get("failed", 0)
            has_proj = (self.results_dir / "project_report.html").exists()
            return QueueInfo(
                queue_id=queue_id,
                name=f"Analysis ({ts_short})" if ts_short else "Analysis",
                pmids=pmids,
                timestamp=timestamp,
                status=self._calc_status(completed, failed, len(pmids)),
                completed_count=completed,
                failed_count=failed,
                has_project_report=has_proj,
                pmid_summaries=summaries,
            )
        except (json.JSONDecodeError, OSError):
            return None

    def _create_singleton_queue(self, pmid: str) -> QueueInfo | None:
        """단일 PMID로 Queue 생성"""
        summary = self._load_pmid_summary(pmid)
        if not summary:
            return None
        status = summary.get("status", "unknown")
        completed = 1 if status == "completed" else 0
        failed = 1 if status == "failed" else 0
        title = summary.get("title", "")
        short_title = title[:40] + "..." if len(title) > 40 else title
        name = short_title or f"PMID {pmid}"
        return QueueInfo(
            queue_id=f"pmid_{pmid}",
            name=name,
            pmids=[pmid],
            timestamp=summary.get("retrieved_at", ""),
            status=status,
            completed_count=completed,
            failed_count=failed,
            has_project_report=False,
            pmid_summaries={pmid: summary},
        )

    def _load_pmid_summary(self, pmid: str) -> dict[str, Any]:
        """final_report에서 표시용 요약 추출"""
        report_path = self.results_dir / pmid / f"final_report_{pmid}.json"
        if not report_path.exists():
            return {"pmid": pmid, "status": "unknown"}
        try:
            with open(report_path) as f:
                data = json.load(f)
            pubmed = data.get("pubmed_metadata", {})
            return {
                "pmid": pmid,
                "title": pubmed.get("title", ""),
                "journal": pubmed.get("journal", ""),
                "authors": pubmed.get("authors", [])[:3],
                "pub_date": pubmed.get("pub_date", ""),
                "status": data.get("status", "unknown"),
                "duration_seconds": data.get("duration_seconds", 0),
                "sequencing_type": data.get("sequencing_type", "unknown"),
                "sequencing_confidence": data.get("sequencing_confidence", 0),
                "llm_rating": data.get("llm_rating", ""),
                "debate_verdict": data.get("debate_verdict", ""),
                "debate_score": data.get("debate_score", 0),
                "enrichment_novelty": data.get(
                    "enrichment_summary", {}
                ).get("novelty_score", 0),
                "retrieved_at": pubmed.get("retrieved_at", ""),
            }
        except (json.JSONDecodeError, OSError):
            return {"pmid": pmid, "status": "error"}

    @staticmethod
    def _calc_status(completed: int, failed: int, total: int) -> str:
        if failed == total:
            return "failed"
        if completed == total:
            return "completed"
        if completed > 0 or failed > 0:
            return "partial"
        return "pending"
