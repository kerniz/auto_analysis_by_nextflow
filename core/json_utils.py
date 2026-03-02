"""
Shared JSON parsing utilities for LLM responses.
LLM 응답에서 JSON을 추출·복구하는 공유 유틸리티.
"""

import json
import re
from typing import Any


def strip_think_tags(text: str) -> str:
    """qwen3 모델의 <think>...</think> 태그 제거."""
    return re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL).strip()


def repair_json(text: str) -> str:
    """
    불완전한 JSON 복구 시도.

    - 트레일링 콤마 제거
    - 닫히지 않은 문자열 닫기
    - 닫히지 않은 배열/객체 닫기
    """
    text = re.sub(r",\s*([}\]])", r"\1", text)

    open_braces = text.count("{") - text.count("}")
    open_brackets = text.count("[") - text.count("]")

    in_string = False
    last_char = ""
    for ch in text:
        if ch == '"' and last_char != "\\":
            in_string = not in_string
        last_char = ch

    if in_string:
        text += '"'

    text += "]" * max(0, open_brackets)
    text += "}" * max(0, open_braces)

    # 닫는 괄호 추가 후 새로 생긴 트레일링 콤마 재거
    text = re.sub(r",\s*([}\]])", r"\1", text)

    return text


def extract_json_from_llm(content: str) -> dict[str, Any] | None:
    """
    LLM 응답 텍스트에서 JSON을 추출.

    시도 순서:
    1. ```json ... ``` 코드 블록
    2. 첫 번째 {...} 매치
    3. 직접 json.loads
    4. JSON 복구 후 재시도
    """
    cleaned = strip_think_tags(content)

    # 1차: 코드 블록 또는 중괄호 추출
    try:
        json_match = re.search(
            r"```(?:json)?\s*\n?(.*?)\n?\s*```", cleaned, re.DOTALL
        )
        if json_match:
            return json.loads(json_match.group(1))

        brace_match = re.search(r"\{.*\}", cleaned, re.DOTALL)
        if brace_match:
            return json.loads(brace_match.group(0))

        return json.loads(cleaned)
    except (json.JSONDecodeError, AttributeError):
        pass

    # 2차: JSON 복구 시도
    try:
        json_match = re.search(r"```(?:json)?\s*\n?(.*)", cleaned, re.DOTALL)
        raw = json_match.group(1) if json_match else cleaned
        brace_match = re.search(r"\{.*", raw, re.DOTALL)
        if brace_match:
            repaired = repair_json(brace_match.group(0))
            result = json.loads(repaired)
            if isinstance(result, dict):
                return result
    except (json.JSONDecodeError, AttributeError, ValueError):
        pass

    return None
