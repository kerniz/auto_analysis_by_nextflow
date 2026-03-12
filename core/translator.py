"""
Debate report translator powered by autotranslater patterns.

git@github.com:kerniz/autotranslater.git 의 핵심 로직 활용:
- ollama Python 라이브러리 (sync chat API)
- 캐시 시스템 (~/.translate_cache)
- 멀티스레드 병렬 번역
- 자동 재시도 + exponential backoff

config.json의 language 설정 참조:
  primary / secondary / translate_debate / translation_model
"""

import hashlib
import logging
import os
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any

logger = logging.getLogger(__name__)

# ── 설정 ──────────────────────────────────────────────────────────

DEFAULT_MODEL = "translategemma:27b"
DEFAULT_TIMEOUT = 300
DEFAULT_THREADS = 3  # 토론 번역은 chunk가 크므로 3스레드
CACHE_DIR = os.path.expanduser("~/.translate_cache")

# 모델 탐색 우선순위
_TRANSLATION_MODELS = [
    "translategemma:27b",
    "qwen3:30b",
    "qwen3-next",
    "glm-4.7-flash",
]

# 언어 이름 맵
LANG_NAMES = {
    "ko": "Korean", "en": "English", "ja": "Japanese",
    "zh": "Chinese", "de": "German", "fr": "French",
    "es": "Spanish", "pt": "Portuguese", "it": "Italian",
}

# ── ollama 클라이언트 (lazy init) ─────────────────────────────────

try:
    import ollama as _ollama_mod

    HAS_OLLAMA = True
except ImportError:
    _ollama_mod = None
    HAS_OLLAMA = False

_client = None


def _init_client(host: str | None = None):
    """Ollama 클라이언트 초기화 (autotranslater 패턴)."""
    global _client
    if not HAS_OLLAMA:
        return
    if host:
        if not host.startswith("http"):
            host = f"http://{host}"
        if ":" not in host.replace("http://", "").replace("https://", ""):
            host = f"{host}:11434"
        _client = _ollama_mod.Client(host=host)
        logger.info("Ollama 번역 클라이언트 연결: %s", host)
    else:
        _client = _ollama_mod


# ── 캐시 시스템 (autotranslater 패턴) ────────────────────────────

def _ensure_cache_dir():
    os.makedirs(CACHE_DIR, exist_ok=True)


def _cache_key(text: str, model: str, target: str) -> str:
    content = f"{model}:{target}:{text}"
    return hashlib.md5(content.encode()).hexdigest()


def _get_cached(text: str, model: str, target: str) -> str | None:
    path = os.path.join(CACHE_DIR, f"{_cache_key(text, model, target)}.txt")
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            return f.read()
    return None


def _save_cache(text: str, translated: str, model: str, target: str):
    _ensure_cache_dir()
    path = os.path.join(CACHE_DIR, f"{_cache_key(text, model, target)}.txt")
    with open(path, "w", encoding="utf-8") as f:
        f.write(translated)


# ── 번역 핵심 (autotranslater translate_unit 패턴) ────────────────

def _translate_unit(
    text: str,
    model: str,
    source_lang: str = "en",
    target_lang: str = "ko",
    use_cache: bool = True,
    retries: int = 3,
) -> str:
    """단일 텍스트 번역 (sync, 캐시+재시도)."""
    if not text.strip() or _client is None:
        return text

    if use_cache:
        cached = _get_cached(text, model, target_lang)
        if cached:
            return cached

    src_name = LANG_NAMES.get(source_lang, source_lang)
    tgt_name = LANG_NAMES.get(target_lang, target_lang)

    prompt = (
        f"Translate the following {src_name} text to {tgt_name}. "
        "Keep technical terms, gene names, pathway names, "
        "and abbreviations in their original form. "
        "Output ONLY the translation, nothing else.\n\n"
        f"{text}"
    )

    for attempt in range(retries):
        try:
            response = _client.chat(
                model=model,
                messages=[{"role": "user", "content": prompt}],
                options={"timeout": DEFAULT_TIMEOUT, "temperature": 0.1},
            )
            result = response["message"]["content"].strip()

            # 따옴표 감싸기 제거 (autotranslater 패턴)
            if (result.startswith('"') and result.endswith('"')
                    and text.count('"') < 2):
                result = result[1:-1]

            if use_cache:
                _save_cache(text, result, model, target_lang)
            return result
        except Exception as e:
            if attempt == retries - 1:
                logger.error("번역 실패 (최종): %s", str(e)[:200])
                return text
            wait = 2 ** attempt
            logger.warning(
                "번역 오류, %d초 후 재시도 (%d/%d): %s",
                wait, attempt + 1, retries, str(e)[:100],
            )
            time.sleep(wait)
    return text


def _translate_list(
    items: list[str],
    model: str,
    source_lang: str,
    target_lang: str,
    use_cache: bool = True,
) -> list[str]:
    """리스트 항목을 하나로 합쳐 번역 후 분리."""
    if not items:
        return items

    joined = "\n".join(f"- {p}" for p in items)
    translated = _translate_unit(
        joined, model, source_lang, target_lang, use_cache,
    )
    return [
        line.lstrip("- ").strip()
        for line in translated.split("\n")
        if line.strip()
    ]


# ── 모델 탐색 ────────────────────────────────────────────────────

def _find_model(host: str) -> str | None:
    """사용 가능한 번역 모델 자동 탐색."""
    if not HAS_OLLAMA:
        return None
    try:
        _init_client(host)
        if _client is None:
            return None
        resp = _client.list()
        models = [m.model for m in resp.models] if hasattr(resp, "models") else []
        if not models:
            # fallback: dict 형태
            models = [m.get("name", "") for m in (resp.get("models", []) if isinstance(resp, dict) else [])]
    except Exception as e:
        logger.warning("모델 목록 조회 실패: %s", e)
        return None

    for candidate in _TRANSLATION_MODELS:
        for m in models:
            if candidate in m or m.startswith(candidate.split(":")[0]):
                return m
    return None


# ── 메인 API (async wrapper for pipeline integration) ────────────

async def translate_debate_report(
    debate_report: dict[str, Any],
    ollama_url: str,
    model: str | None = None,
    source_lang: str = "en",
    target_lang: str = "ko",
    threads: int = DEFAULT_THREADS,
    use_cache: bool = True,
) -> dict[str, Any]:
    """토론 보고서를 target_lang으로 번역 (멀티스레드 병렬).

    autotranslater의 ThreadPoolExecutor 패턴 사용.
    """
    if not HAS_OLLAMA:
        logger.warning("ollama 패키지 미설치 — pip install ollama")
        return {}
    if not debate_report or debate_report.get("error"):
        return {}
    if source_lang == target_lang:
        return {}

    # 클라이언트 초기화
    _init_client(ollama_url)
    if _client is None:
        return {}

    # 모델 결정
    if not model or model == "auto":
        model = _find_model(ollama_url)
    if not model:
        logger.warning("번역 모델을 찾을 수 없음 — 번역 건너뜀")
        return {}

    tgt_name = LANG_NAMES.get(target_lang, target_lang)
    logger.info("토론 보고서 %s 번역 시작 (model=%s, threads=%d)", tgt_name, model, threads)
    start = time.time()

    ko: dict[str, Any] = {}

    # ── 1. 합의 요약 번역 ──
    consensus = debate_report.get("final_consensus", {})
    if consensus and consensus.get("summary"):
        try:
            ko["final_consensus"] = {
                **consensus,
                "summary": _translate_unit(
                    consensus["summary"], model, source_lang, target_lang, use_cache,
                ),
            }
        except Exception as e:
            logger.warning("합의 요약 번역 실패: %s", e)
            ko["final_consensus"] = consensus

    # ── 2. 라운드별 에이전트 응답 병렬 번역 ──
    rounds = debate_report.get("rounds", [])
    ko_rounds = []

    # 모든 라운드의 모든 응답을 flat하게 수집
    tasks: list[tuple[int, int, str, str]] = []  # (round_idx, resp_idx, field, text)
    for ri, rnd in enumerate(rounds):
        for rsi, resp in enumerate(rnd.get("responses", [])):
            if resp.get("assessment"):
                tasks.append((ri, rsi, "assessment", resp["assessment"]))
            for field in ("key_points", "concerns", "questions"):
                items = resp.get(field, [])
                if items:
                    joined = "\n".join(f"- {p}" for p in items)
                    tasks.append((ri, rsi, field, joined))

    # 멀티스레드 병렬 번역 (autotranslater ThreadPoolExecutor 패턴)
    translated_map: dict[tuple[int, int, str], str] = {}
    total = len(tasks)

    if total > 0:
        with ThreadPoolExecutor(max_workers=threads) as executor:
            future_map = {
                executor.submit(
                    _translate_unit, text, model, source_lang, target_lang, use_cache,
                ): (ri, rsi, field)
                for ri, rsi, field, text in tasks
            }
            completed = 0
            for future in as_completed(future_map):
                key = future_map[future]
                try:
                    translated_map[key] = future.result()
                except Exception:
                    # 실패 시 원문 유지
                    ri, rsi, field = key
                    for t in tasks:
                        if t[:3] == (ri, rsi, field):
                            translated_map[key] = t[3]
                            break
                completed += 1
                if completed % 10 == 0 or completed == total:
                    logger.info("번역 진행: %d/%d", completed, total)

    # 번역 결과를 rounds 구조에 매핑
    for ri, rnd in enumerate(rounds):
        ko_responses = []
        for rsi, resp in enumerate(rnd.get("responses", [])):
            ko_resp = {**resp}

            # assessment
            key = (ri, rsi, "assessment")
            if key in translated_map:
                ko_resp["assessment"] = translated_map[key]

            # list fields
            for field in ("key_points", "concerns", "questions"):
                key = (ri, rsi, field)
                if key in translated_map:
                    ko_resp[field] = [
                        line.lstrip("- ").strip()
                        for line in translated_map[key].split("\n")
                        if line.strip()
                    ]

            ko_responses.append(ko_resp)
        ko_rounds.append({**rnd, "responses": ko_responses})

    ko["rounds"] = ko_rounds

    # ── 3. 소수 의견 번역 ──
    dissenting = debate_report.get("dissenting_opinions", [])
    if dissenting:
        try:
            ko["dissenting_opinions"] = _translate_list(
                dissenting, model, source_lang, target_lang, use_cache,
            )
        except Exception:
            ko["dissenting_opinions"] = dissenting

    # ── 4. 수치 데이터 복사 ──
    ko["overall_verdict"] = debate_report.get("overall_verdict")
    ko["overall_score"] = debate_report.get("overall_score")
    ko["per_agent_scores"] = debate_report.get("per_agent_scores", {})
    ko["_translated_to"] = target_lang

    elapsed = time.time() - start
    logger.info(
        "토론 보고서 %s 번역 완료 (%.1f초, %d chunks)", tgt_name, elapsed, total,
    )
    return ko
