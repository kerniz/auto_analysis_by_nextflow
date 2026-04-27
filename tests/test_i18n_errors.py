"""Tests for i18n and error tracker modules."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from core.error_tracker import ErrorRecord, ErrorTracker, get_tracker
from core.i18n import MESSAGES, get_locale, set_locale, t

# ── i18n Tests ──


class TestI18n:
    """i18n 모듈 테스트."""

    def setup_method(self):
        set_locale("ko")

    def teardown_method(self):
        set_locale("en")  # reset to default

    def test_default_locale_ko(self):
        assert get_locale() == "ko"

    def test_set_locale_en(self):
        set_locale("en")
        assert get_locale() == "en"

    def test_t_korean(self):
        set_locale("ko")
        assert t("search.no_results") == "검색 결과가 없습니다"

    def test_t_english(self):
        set_locale("en")
        assert t("search.no_results") == "No search results found"

    def test_t_with_format(self):
        set_locale("ko")
        result = t("search.total_count", count=42)
        assert "42" in result

    def test_t_with_format_en(self):
        set_locale("en")
        result = t("search.total_count", count=42)
        assert "42" in result

    def test_t_unknown_key(self):
        result = t("nonexistent.key")
        assert result == "nonexistent.key"

    def test_t_invalid_locale_ignored(self):
        set_locale("xx")  # 유효하지 않은 로케일
        assert get_locale() == "ko"  # 변경 안 됨

    def test_all_messages_have_both_locales(self):
        """모든 메시지에 ko와 en이 있는지 확인."""
        for key, msg_dict in MESSAGES.items():
            assert "ko" in msg_dict, f"{key}: Korean translation missing"
            assert "en" in msg_dict, f"{key}: English translation missing"

    def test_doctype_labels(self):
        set_locale("ko")
        assert t("doctype.paper_abstract") == "논문"
        set_locale("en")
        assert t("doctype.paper_abstract") == "Papers"

    def test_locale_from_env(self):
        with patch.dict("os.environ", {"BIOAUTO_LOCALE": "en"}):
            from core.i18n import _detect_locale
            assert _detect_locale() == "en"

    def test_locale_from_env_var(self):
        """환경변수 BIOAUTO_LOCALE이 최우선."""
        import os
        with patch.dict(os.environ, {"BIOAUTO_LOCALE": "en"}):
            from core.i18n import _detect_locale
            assert _detect_locale() == "en"
        with patch.dict(os.environ, {"BIOAUTO_LOCALE": "ko"}):
            assert _detect_locale() == "ko"


# ── Error Tracker Tests ──


class TestErrorRecord:
    """ErrorRecord 테스트."""

    def test_create(self):
        record = ErrorRecord(
            stage="llm_consensus",
            message="Backend failed",
            severity="ERROR",
            pmid="12345",
            error_type="RuntimeError",
        )
        assert record.stage == "llm_consensus"
        assert record.pmid == "12345"
        assert record.severity == "ERROR"

    def test_to_dict(self):
        record = ErrorRecord(
            stage="debate",
            message="Timeout",
            pmid="12345",
            context={"model": "qwen3:30b"},
        )
        d = record.to_dict()
        assert d["stage"] == "debate"
        assert d["pmid"] == "12345"
        assert d["context"]["model"] == "qwen3:30b"
        assert "timestamp" in d

    def test_to_dict_minimal(self):
        record = ErrorRecord(stage="test", message="err")
        d = record.to_dict()
        assert "pmid" not in d
        assert "traceback" not in d
        assert "context" not in d


class TestErrorTracker:
    """ErrorTracker 테스트."""

    @pytest.fixture
    def tracker(self, tmp_path):
        return ErrorTracker(tmp_path)

    def test_record_and_get(self, tracker):
        tracker.record(stage="pubmed", message="API error", pmid="111")
        errors = tracker.get_errors()
        assert len(errors) == 1
        assert errors[0]["stage"] == "pubmed"
        assert errors[0]["pmid"] == "111"

    def test_record_with_exception(self, tracker):
        try:
            raise ValueError("test error")
        except ValueError as e:
            tracker.record(stage="llm", error=e, pmid="222")
        errors = tracker.get_errors()
        assert len(errors) == 1
        assert errors[0]["error_type"] == "ValueError"
        assert "test error" in errors[0]["message"]
        assert errors[0]["traceback"] is not None

    def test_record_with_context(self, tracker):
        tracker.record(
            stage="debate",
            message="All backends failed",
            context={"model": "qwen3:30b", "retries": 3},
        )
        errors = tracker.get_errors()
        assert errors[0]["context"]["model"] == "qwen3:30b"

    def test_filter_by_severity(self, tracker):
        tracker.record(stage="a", message="warn", severity="WARNING")
        tracker.record(stage="b", message="err", severity="ERROR")
        tracker.record(stage="c", message="info", severity="INFO")
        assert len(tracker.get_errors(severity="ERROR")) == 1
        assert len(tracker.get_errors(severity="WARNING")) == 1

    def test_filter_by_stage(self, tracker):
        tracker.record(stage="pubmed", message="err1")
        tracker.record(stage="debate", message="err2")
        tracker.record(stage="pubmed", message="err3")
        assert len(tracker.get_errors(stage="pubmed")) == 2

    def test_filter_by_pmid(self, tracker):
        tracker.record(stage="a", message="e1", pmid="111")
        tracker.record(stage="b", message="e2", pmid="222")
        assert len(tracker.get_errors(pmid="111")) == 1

    def test_get_summary(self, tracker):
        tracker.record(stage="pubmed", message="e1", severity="ERROR")
        tracker.record(stage="debate", message="e2", severity="WARNING")
        tracker.record(stage="pubmed", message="e3", severity="ERROR")
        summary = tracker.get_summary()
        assert summary["total"] == 3
        assert summary["by_severity"]["ERROR"] == 2
        assert summary["by_severity"]["WARNING"] == 1
        assert summary["by_stage"]["pubmed"] == 2

    def test_clear(self, tracker):
        tracker.record(stage="a", message="err")
        tracker.record(stage="b", message="err")
        count = tracker.clear()
        assert count == 2
        assert len(tracker.get_errors()) == 0

    def test_clear_by_pmid(self, tracker):
        tracker.record(stage="a", message="e1", pmid="111")
        tracker.record(stage="b", message="e2", pmid="222")
        tracker.record(stage="c", message="e3", pmid="111")
        count = tracker.clear_by_pmid("111")
        assert count == 2
        assert len(tracker.get_errors()) == 1

    def test_persistence(self, tmp_path):
        # 기록 후 새 인스턴스에서 로드
        tracker1 = ErrorTracker(tmp_path)
        tracker1.record(stage="test", message="persistent error")

        tracker2 = ErrorTracker(tmp_path)
        errors = tracker2.get_errors()
        assert len(errors) == 1
        assert errors[0]["message"] == "persistent error"

    def test_max_records_limit(self, tracker):
        for i in range(600):
            tracker.record(stage="test", message=f"error {i}")
        errors = tracker.get_errors(limit=1000)
        assert len(errors) <= ErrorTracker.MAX_RECORDS

    def test_get_tracker_helper(self, tmp_path):
        tracker = get_tracker(tmp_path)
        assert isinstance(tracker, ErrorTracker)

    def test_empty_summary(self, tracker):
        summary = tracker.get_summary()
        assert summary["total"] == 0
        assert summary["recent"] == []


class TestErrorsCommand:
    """bioauto errors CLI 명령어 테스트."""

    @pytest.fixture
    def runner(self):
        from click.testing import CliRunner
        return CliRunner()

    def test_errors_empty(self, runner, tmp_path):
        from core.cli import cli
        result = runner.invoke(cli, ["errors", "-o", str(tmp_path)])
        assert "기록된 에러가 없습니다" in result.output

    def test_errors_with_data(self, runner, tmp_path):
        from core.cli import cli
        # 에러 기록 생성
        tracker = ErrorTracker(tmp_path)
        tracker.record(stage="debate", message="Backend failed", severity="ERROR")
        tracker.record(stage="pubmed", message="API timeout", severity="WARNING")

        result = runner.invoke(cli, ["errors", "-o", str(tmp_path)])
        assert "2건" in result.output
        assert "debate" in result.output

    def test_errors_clear(self, runner, tmp_path):
        from core.cli import cli
        tracker = ErrorTracker(tmp_path)
        tracker.record(stage="test", message="err")

        result = runner.invoke(cli, ["errors", "-o", str(tmp_path), "--clear"], input="y\n")
        assert "삭제 완료" in result.output

    def test_errors_filter_severity(self, runner, tmp_path):
        from core.cli import cli
        tracker = ErrorTracker(tmp_path)
        tracker.record(stage="a", message="err", severity="ERROR")
        tracker.record(stage="b", message="warn", severity="WARNING")

        result = runner.invoke(cli, ["errors", "-o", str(tmp_path), "-s", "ERROR"])
        assert "ERROR" in result.output
