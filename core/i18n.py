"""
Internationalization (i18n) — 다국어 지원 모듈.

사용법:
    from core.i18n import t
    print(t("search.no_results"))  # 현재 로케일에 맞는 메시지 출력

로케일 설정:
    config.json → "locale": "en" 또는 "ko" (기본값: "ko")
    환경변수: BIOAUTO_LOCALE=en
"""

from __future__ import annotations

import logging
import os
from typing import Any

logger = logging.getLogger(__name__)

# 현재 로케일 (모듈 레벨에서 한번 결정)
_current_locale: str = "ko"

# ── 메시지 카탈로그 ──

MESSAGES: dict[str, dict[str, str]] = {
    # ── CLI 공통 ──
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

    # ── 검색 ──
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

    # ── 선택 ──
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

    # ── 파이프라인 ──
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

    # ── 상담 ──
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

    # ── 지식 DB ──
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

    # ── 에러 ──
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

    # ── 설치/제거 ──
    "uninstall.confirm1": {
        "ko": "bioauto를 완전히 제거합니다.",
        "en": "Completely uninstall bioauto.",
    },
    "uninstall.confirm2": {
        "ko": "정말 제거하시겠습니까? (results/ 데이터는 보존됩니다)",
        "en": "Really uninstall? (results/ data will be preserved)",
    },

    # ── doc_type 라벨 ──
    "doctype.paper_abstract": {"ko": "논문", "en": "Papers"},
    "doctype.analysis_result": {"ko": "LLM 분석", "en": "LLM Analysis"},
    "doctype.debate_report": {"ko": "토론 보고서", "en": "Debate Reports"},
    "doctype.search_record": {"ko": "검색 기록", "en": "Search Records"},
    "doctype.consult_exchange": {"ko": "상담 대화", "en": "Consult Chats"},
    "doctype.enrichment_result": {"ko": "경로 분석", "en": "Enrichment"},
    "doctype.pipeline_run": {"ko": "파이프라인", "en": "Pipeline Runs"},
}


def _detect_locale() -> str:
    """로케일 자동 감지. 우선순위: 환경변수 → config.json → 기본값(ko)."""
    # 환경변수
    env_locale = os.environ.get("BIOAUTO_LOCALE", "").strip().lower()
    if env_locale in ("en", "ko"):
        return env_locale

    # config.json
    try:
        import json
        from pathlib import Path
        for p in [Path(__file__).parent.parent / "config.json", Path.cwd() / "config.json"]:
            if p.exists():
                with open(p) as f:
                    cfg = json.load(f)
                locale = cfg.get("locale", "").strip().lower()
                if locale in ("en", "ko"):
                    return locale
                break
    except Exception:
        pass

    return "ko"


def set_locale(locale: str) -> None:
    """런타임에 로케일을 변경합니다."""
    global _current_locale
    if locale in ("en", "ko"):
        _current_locale = locale
        logger.debug("Locale set to %s", locale)


def get_locale() -> str:
    """현재 로케일을 반환합니다."""
    return _current_locale


def t(key: str, **kwargs: Any) -> str:
    """메시지 키를 현재 로케일로 번역합니다.

    Args:
        key: 메시지 키 (예: "search.no_results")
        **kwargs: 포맷 변수 (예: count=5)

    Returns:
        번역된 문자열. 키가 없으면 키 자체를 반환.
    """
    msg_dict = MESSAGES.get(key)
    if not msg_dict:
        return key

    msg = msg_dict.get(_current_locale, msg_dict.get("ko", key))

    if kwargs:
        try:
            msg = msg.format(**kwargs)
        except (KeyError, IndexError):
            pass

    return msg


# 모듈 로드 시 자동 감지
_current_locale = _detect_locale()
