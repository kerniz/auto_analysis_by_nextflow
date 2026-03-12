"""
Structured Error Tracker — 구조화된 에러 추적 시스템.

파이프라인 실행 중 발생하는 모든 에러를 JSON 형식으로 기록하고
분석/조회할 수 있습니다.

사용법:
    tracker = ErrorTracker("./results")
    tracker.record(stage="llm_consensus", pmid="12345",
                   error=exc, context={"model": "qwen3:30b"})
"""

from __future__ import annotations

import json
import logging
import traceback
from datetime import datetime
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# 에러 심각도 레벨
SEVERITY_LEVELS = {
    "CRITICAL": 0,  # 파이프라인 전체 중단
    "ERROR": 1,     # 개별 스테이지 실패
    "WARNING": 2,   # 스킵 가능한 오류
    "INFO": 3,      # 참고용 기록
}


class ErrorRecord:
    """단일 에러 기록."""

    def __init__(
        self,
        stage: str,
        message: str,
        severity: str = "ERROR",
        pmid: str | None = None,
        error_type: str = "Unknown",
        traceback_str: str | None = None,
        context: dict[str, Any] | None = None,
    ) -> None:
        self.timestamp = datetime.now().isoformat()
        self.stage = stage
        self.message = message
        self.severity = severity
        self.pmid = pmid
        self.error_type = error_type
        self.traceback_str = traceback_str
        self.context = context or {}

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {
            "timestamp": self.timestamp,
            "severity": self.severity,
            "stage": self.stage,
            "message": self.message,
            "error_type": self.error_type,
        }
        if self.pmid:
            d["pmid"] = self.pmid
        if self.traceback_str:
            d["traceback"] = self.traceback_str
        if self.context:
            d["context"] = self.context
        return d


class ErrorTracker:
    """구조화된 에러 추적기."""

    ERROR_LOG_FILE = "error_log.json"
    MAX_RECORDS = 500  # 최대 보관 에러 수

    def __init__(self, results_dir: str | Path = "./results") -> None:
        self.results_dir = Path(results_dir)
        self._log_path = self.results_dir / self.ERROR_LOG_FILE
        self._records: list[dict[str, Any]] = []
        self._loaded = False

    def _ensure_loaded(self) -> None:
        """기존 에러 로그 파일을 로드합니다."""
        if self._loaded:
            return
        self._loaded = True
        if self._log_path.exists():
            try:
                with open(self._log_path) as f:
                    data = json.load(f)
                self._records = data.get("errors", [])
            except (json.JSONDecodeError, OSError) as e:
                logger.debug("Error log load failed: %s", e)
                self._records = []

    def _save(self) -> None:
        """에러 로그를 파일에 저장합니다."""
        try:
            self.results_dir.mkdir(parents=True, exist_ok=True)
            # 최대 레코드 수 유지
            if len(self._records) > self.MAX_RECORDS:
                self._records = self._records[-self.MAX_RECORDS:]

            data = {
                "version": "1.0",
                "updated_at": datetime.now().isoformat(),
                "total_errors": len(self._records),
                "errors": self._records,
            }
            with open(self._log_path, "w") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except OSError as e:
            logger.debug("Error log save failed: %s", e)

    def record(
        self,
        stage: str,
        message: str | None = None,
        severity: str = "ERROR",
        pmid: str | None = None,
        error: BaseException | None = None,
        context: dict[str, Any] | None = None,
    ) -> None:
        """에러를 기록합니다.

        Args:
            stage: 발생 단계 (예: "pubmed", "llm_consensus", "debate")
            message: 에러 메시지 (없으면 exception에서 추출)
            severity: 심각도 ("CRITICAL", "ERROR", "WARNING", "INFO")
            pmid: 관련 PMID
            error: 예외 객체
            context: 추가 컨텍스트 (모델명, URL 등)
        """
        self._ensure_loaded()

        error_type = type(error).__name__ if error else "Unknown"
        if not message and error:
            message = str(error)
        if not message:
            message = "Unknown error"

        tb_str = None
        if error:
            tb_str = "".join(traceback.format_exception(type(error), error, error.__traceback__))

        record = ErrorRecord(
            stage=stage,
            message=message,
            severity=severity,
            pmid=pmid,
            error_type=error_type,
            traceback_str=tb_str,
            context=context,
        )

        self._records.append(record.to_dict())
        self._save()

        # 콘솔 로깅도 연동
        log_msg = f"[{severity}] {stage}"
        if pmid:
            log_msg += f" (PMID:{pmid})"
        log_msg += f": {message}"

        if severity == "CRITICAL":
            logger.critical(log_msg)
        elif severity == "ERROR":
            logger.error(log_msg)
        elif severity == "WARNING":
            logger.warning(log_msg)
        else:
            logger.info(log_msg)

    def get_errors(
        self,
        severity: str | None = None,
        stage: str | None = None,
        pmid: str | None = None,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        """에러 기록을 조회합니다."""
        self._ensure_loaded()
        filtered = self._records

        if severity:
            filtered = [r for r in filtered if r.get("severity") == severity]
        if stage:
            filtered = [r for r in filtered if r.get("stage") == stage]
        if pmid:
            filtered = [r for r in filtered if r.get("pmid") == pmid]

        return filtered[-limit:]

    def get_summary(self) -> dict[str, Any]:
        """에러 통계 요약을 반환합니다."""
        self._ensure_loaded()
        if not self._records:
            return {"total": 0, "by_severity": {}, "by_stage": {}, "recent": []}

        by_severity: dict[str, int] = {}
        by_stage: dict[str, int] = {}

        for r in self._records:
            sev = r.get("severity", "UNKNOWN")
            stg = r.get("stage", "unknown")
            by_severity[sev] = by_severity.get(sev, 0) + 1
            by_stage[stg] = by_stage.get(stg, 0) + 1

        return {
            "total": len(self._records),
            "by_severity": by_severity,
            "by_stage": by_stage,
            "recent": self._records[-5:],
        }

    def clear(self) -> int:
        """모든 에러 기록을 삭제합니다."""
        self._ensure_loaded()
        count = len(self._records)
        self._records = []
        self._save()
        return count

    def clear_by_pmid(self, pmid: str) -> int:
        """특정 PMID의 에러 기록을 삭제합니다."""
        self._ensure_loaded()
        before = len(self._records)
        self._records = [r for r in self._records if r.get("pmid") != pmid]
        after = len(self._records)
        self._save()
        return before - after


def get_tracker(results_dir: str | Path = "./results") -> ErrorTracker:
    """ErrorTracker 인스턴스를 반환합니다."""
    return ErrorTracker(results_dir)
