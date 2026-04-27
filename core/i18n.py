"""
Internationalization (i18n) — multilingual support module.

Usage:
    from core.i18n import t
    print(t("search.no_results"))  # prints message in current locale

Locale configuration:
    config.json → "locale": "en" or "ko" (default: "en")
    env var: BIOAUTO_LOCALE=en
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# Current locale (determined once at module level)
_current_locale: str = "en"

# Cached locale data from YAML files: {locale: {key: value}}
_locale_cache: dict[str, dict[str, str]] = {}

_LOCALES_DIR = Path(__file__).parent.parent / "locales"

# ── Legacy MESSAGES dict (fallback for keys not in YAML) ──

MESSAGES: dict[str, dict[str, str]] = {
    # ── CLI common ──
    "cli.loading_config": {
        "ko": "설정 로드 중...",
        "en": "Loading configuration...",
    },
    "cli.quit": {
        "ko": "종료합니다.",
        "en": "Exiting.",
    },
    "cli.cancelled": {
        "ko": "취소됨.",
        "en": "Cancelled.",
    },
    "cli.confirm_yes_no": {
        "ko": "계속하시겠습니까?",
        "en": "Do you want to continue?",
    },

    # ── Search ──
    "search.no_results": {
        "ko": "검색 결과가 없습니다",
        "en": "No search results found",
    },
    "search.searching": {
        "ko": "논문 검색 중",
        "en": "Searching papers",
    },
    "search.results_header": {
        "ko": "검색 결과",
        "en": "Search Results",
    },
    "search.total_count": {
        "ko": "총 {count}건",
        "en": "{count} results total",
    },
    "search.page_info": {
        "ko": "({shown}/{total}건 표시) Enter=다음 {next}건 / a=전체 / q=그만",
        "en": "({shown}/{total} shown) Enter=next {next} / a=all / q=stop",
    },

    # ── Select ──
    "select.prompt": {
        "ko": "선택",
        "en": "Select",
    },
    "select.help": {
        "ko": "번호: 1,3,5  |  범위: 1-10  |  전체: a  |  "
              "조건: >2023  cited>50  \"키워드\"  |  종료: q",
        "en": "Numbers: 1,3,5  |  Range: 1-10  |  All: a  |  "
              "Filter: >2023  cited>50  \"keyword\"  |  Quit: q",
    },
    "select.methods": {
        "ko": "선택 방법:",
        "en": "Selection methods:",
    },
    "select.empty_input": {
        "ko": "입력이 없습니다.",
        "en": "No input provided.",
    },
    "select.invalid_retry": {
        "ko": "숫자만 입력하세요 (예: 1,3,5 또는 1-10). 재시도 {remaining}회 남음",
        "en": "Numbers only (e.g., 1,3,5 or 1-10). {remaining} retries left",
    },
    "select.invalid_final": {
        "ko": "잘못된 입력입니다.",
        "en": "Invalid input.",
    },
    "select.out_of_range": {
        "ko": "범위 밖 번호 무시됨: {invalid} (1~{total} 사이만 가능)",
        "en": "Out of range ignored: {invalid} (must be 1~{total})",
    },
    "select.no_valid": {
        "ko": "유효한 번호가 없습니다. 재시도 {remaining}회 남음",
        "en": "No valid numbers. {remaining} retries left",
    },
    "select.no_pmid": {
        "ko": "선택한 논문에 PMID가 없습니다. 다른 번호를 선택하세요.",
        "en": "Selected papers have no PMID. Please choose different ones.",
    },
    "select.all_selected": {
        "ko": "전체 {count}건 선택됨",
        "en": "All {count} papers selected",
    },
    "select.condition_matched": {
        "ko": "조건 매칭 {count}건",
        "en": "{count} papers matched",
    },
    "select.no_condition_match": {
        "ko": "조건에 맞는 PMID 논문이 없습니다.",
        "en": "No papers with PMID match the condition.",
    },
    "select.no_pmid_all": {
        "ko": "PMID가 있는 논문이 없습니다.",
        "en": "No papers have a PMID.",
    },

    # ── Pipeline ──
    "pipeline.start": {
        "ko": "파이프라인 실행 시작",
        "en": "Starting pipeline execution",
    },
    "pipeline.complete": {
        "ko": "파이프라인 실행 완료!",
        "en": "Pipeline execution complete!",
    },
    "pipeline.confirm": {
        "ko": "파이프라인을 실행할까요?",
        "en": "Run the pipeline?",
    },
    "pipeline.running": {
        "ko": "파이프라인 실행 중",
        "en": "Running pipeline",
    },

    # ── Consult ──
    "consult.banner_title": {
        "ko": "연구 상담 모드",
        "en": "Research Consultation Mode",
    },
    "consult.llm_test": {
        "ko": "LLM 백엔드 연결 테스트 중",
        "en": "Testing LLM backend connection",
    },
    "consult.ollama_ok": {
        "ko": "Ollama 연결 OK",
        "en": "Ollama connected",
    },
    "consult.ollama_fail": {
        "ko": "Ollama 연결 실패 — 10초 타임아웃",
        "en": "Ollama connection failed — 10s timeout",
    },
    "consult.ready": {
        "ko": "상담 준비 완료",
        "en": "Consultation ready",
    },
    "consult.quit_hint": {
        "ko": "종료: q 입력 후 Enter",
        "en": "Quit: type q then Enter",
    },
    "consult.previous_interests": {
        "ko": "이전 연구 관심사 감지",
        "en": "Previous research interests detected",
    },
    "consult.recent_interests": {
        "ko": "최근 관심사: ",
        "en": "Recent interests: ",
    },

    # ── Knowledge DB ──
    "knowledge.empty": {
        "ko": "지식 DB가 비어 있습니다",
        "en": "Knowledge DB is empty",
    },
    "knowledge.title": {
        "ko": "연구 지식 DB",
        "en": "Research Knowledge DB",
    },
    "knowledge.recent_interests": {
        "ko": "최근 연구 관심사:",
        "en": "Recent research interests:",
    },
    "knowledge.searching": {
        "ko": "\"{query}\" 관련 지식 검색 중...",
        "en": "Searching for \"{query}\"...",
    },
    "knowledge.no_match": {
        "ko": "관련 지식을 찾지 못했습니다.",
        "en": "No related knowledge found.",
    },
    "knowledge.deleted": {
        "ko": "{count}건 삭제 완료",
        "en": "{count} items deleted",
    },
    "knowledge.reset_warn": {
        "ko": "지식 DB 전체 초기화 ({count}건 삭제)",
        "en": "Reset entire knowledge DB ({count} items)",
    },
    "knowledge.reset_confirm1": {
        "ko": "정말 삭제하시겠습니까?",
        "en": "Are you sure you want to delete?",
    },
    "knowledge.reset_confirm2": {
        "ko": "복구 불가합니다. 확실합니까?",
        "en": "This cannot be undone. Are you certain?",
    },
    "knowledge.reset_done": {
        "ko": "지식 DB 초기화 완료 ({count}건 삭제됨)",
        "en": "Knowledge DB reset ({count} items deleted)",
    },

    # ── Errors ──
    "error.no_errors": {
        "ko": "기록된 에러가 없습니다.",
        "en": "No errors recorded.",
    },
    "error.title": {
        "ko": "에러 기록",
        "en": "Error Log",
    },
    "error.cleared": {
        "ko": "에러 기록 삭제 완료 ({count}건)",
        "en": "Error log cleared ({count} items)",
    },

    # ── RAG ──
    "rag.not_installed": {
        "ko": "RAG 모듈이 설치되지 않았습니다.\n"
              "  설치: pip install chromadb sentence-transformers",
        "en": "RAG module not installed.\n"
              "  Install: pip install chromadb sentence-transformers",
    },

    # ── Uninstall ──
    "uninstall.confirm1": {
        "ko": "bioauto를 완전히 제거합니다.",
        "en": "Completely uninstall bioauto.",
    },
    "uninstall.confirm2": {
        "ko": "정말 제거하시겠습니까? (results/ 데이터는 보존됩니다)",
        "en": "Really uninstall? (results/ data will be preserved)",
    },

    # ── doc_type labels ──
    "doctype.paper_abstract": {"ko": "논문", "en": "Papers"},
    "doctype.analysis_result": {"ko": "LLM 분석", "en": "LLM Analysis"},
    "doctype.debate_report": {"ko": "토론 보고서", "en": "Debate Reports"},
    "doctype.search_record": {"ko": "검색 기록", "en": "Search Records"},
    "doctype.consult_exchange": {"ko": "상담 대화", "en": "Consult Chats"},
    "doctype.enrichment_result": {"ko": "경로 분석", "en": "Enrichment"},
    "doctype.pipeline_run": {"ko": "파이프라인", "en": "Pipeline Runs"},
}


def _load_locale_file(locale: str) -> dict[str, str]:
    """Load locales/{locale}.yaml. Returns empty dict if not found."""
    if locale in _locale_cache:
        return _locale_cache[locale]

    path = _LOCALES_DIR / f"{locale}.yaml"
    if not path.exists():
        _locale_cache[locale] = {}
        return {}

    try:
        import yaml  # type: ignore[import-untyped]
        with open(path, encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
        result = {k: str(v) for k, v in data.items() if v is not None}
        _locale_cache[locale] = result
        return result
    except Exception as exc:
        logger.warning("Failed to load locale file %s: %s", path, exc)
        _locale_cache[locale] = {}
        return {}


def _detect_locale() -> str:
    """Auto-detect locale. Priority: env var → config.json → default (en)."""
    # Environment variable
    env_locale = os.environ.get("BIOAUTO_LOCALE", "").strip().lower()
    if env_locale in ("en", "ko", "de", "ja"):
        return env_locale

    # config.json
    try:
        import json
        for p in [Path(__file__).parent.parent / "config.json", Path.cwd() / "config.json"]:
            if p.exists():
                with open(p) as f:
                    cfg = json.load(f)
                locale = cfg.get("locale", "").strip().lower()
                if locale in ("en", "ko", "de", "ja"):
                    return locale
                break
    except Exception:
        pass

    return "en"


def set_locale(locale: str) -> None:
    """Change locale at runtime."""
    global _current_locale
    if locale in ("en", "ko", "de", "ja"):
        _current_locale = locale
        logger.debug("Locale set to %s", locale)


def get_locale() -> str:
    """Return current locale."""
    return _current_locale


def t(key: str, **kwargs: Any) -> str:
    """Translate a message key to the current locale.

    Lookup order:
    1. locales/{locale}.yaml
    2. MESSAGES dict (legacy fallback)
    3. English fallback (locales/en.yaml or MESSAGES["en"])
    4. Key itself

    Args:
        key: Message key (e.g. "search.no_results")
        **kwargs: Format variables (e.g. count=5)

    Returns:
        Translated string. Returns the key itself if not found.
    """
    # 1. Current locale YAML
    locale_data = _load_locale_file(_current_locale)
    msg = locale_data.get(key)

    # 2. Legacy MESSAGES dict
    if msg is None:
        msg_dict = MESSAGES.get(key)
        if msg_dict:
            msg = msg_dict.get(_current_locale)

    # 3. English fallback
    if msg is None and _current_locale != "en":
        en_data = _load_locale_file("en")
        msg = en_data.get(key)
        if msg is None:
            msg_dict = MESSAGES.get(key)
            if msg_dict:
                msg = msg_dict.get("en")

    # 4. Key itself
    if msg is None:
        return key

    if kwargs:
        try:
            msg = msg.format(**kwargs)
        except (KeyError, IndexError):
            pass

    return msg


# Auto-detect on module load
_current_locale = _detect_locale()
