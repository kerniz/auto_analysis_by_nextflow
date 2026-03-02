"""
Shared JSON parsing utilities for LLM responses.
LLM 응답에서 JSON을 추출·복구하는 공유 유틸리티.
"""

import json
import re
from typing import Any


def strip_think_tags(text: str) -> str:
    """qwen3 모델의 <think>...</think> 태그 제거 (닫히지 않은 태그도 처리)."""
    # 정상 닫힌 태그
    text = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL)
    # 닫히지 않은 <think> 태그 (응답 끝까지)
    text = re.sub(r"<think>.*", "", text, flags=re.DOTALL)
    return text.strip()


def repair_json(text: str) -> str:
    """
    불완전한 JSON 복구 시도.

    - 트레일링 콤마 제거
    - 닫히지 않은 문자열 닫기
    - 닫히지 않은 배열/객체 닫기
    - 문자열 내 이스케이프되지 않은 제어 문자 처리
    """
    # 제어 문자 (탭/개행 제외) 제거
    text = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f]', '', text)

    # 트레일링 콤마 제거
    text = re.sub(r",\s*([}\]])", r"\1", text)

    # 문자열 내부가 아닌 실제 구조 괄호만 세기
    open_braces = 0
    open_brackets = 0
    in_string = False
    escape_next = False

    for ch in text:
        if escape_next:
            escape_next = False
            continue
        if ch == '\\' and in_string:
            escape_next = True
            continue
        if ch == '"':
            in_string = not in_string
            continue
        if not in_string:
            if ch == '{':
                open_braces += 1
            elif ch == '}':
                open_braces -= 1
            elif ch == '[':
                open_brackets += 1
            elif ch == ']':
                open_brackets -= 1

    # 닫히지 않은 문자열 닫기
    if in_string:
        text += '"'

    # 닫히지 않은 배열/객체 닫기
    text += "]" * max(0, open_brackets)
    text += "}" * max(0, open_braces)

    # 닫는 괄호 추가 후 새로 생긴 트레일링 콤마 재거
    text = re.sub(r",\s*([}\]])", r"\1", text)

    return text


def _find_balanced_json(text: str) -> str | None:
    """
    텍스트에서 균형 잡힌 JSON 객체를 찾아 추출.
    중첩된 `{}`를 문자열 컨텍스트를 고려하여 올바르게 매칭.
    """
    start = text.find('{')
    if start == -1:
        return None

    depth = 0
    in_string = False
    escape_next = False

    for i in range(start, len(text)):
        ch = text[i]
        if escape_next:
            escape_next = False
            continue
        if ch == '\\' and in_string:
            escape_next = True
            continue
        if ch == '"':
            in_string = not in_string
            continue
        if not in_string:
            if ch == '{':
                depth += 1
            elif ch == '}':
                depth -= 1
                if depth == 0:
                    return text[start:i + 1]

    # 균형이 맞지 않으면 시작부터 끝까지 반환 (repair_json이 처리)
    return text[start:]


def extract_json_from_llm(content: str) -> dict[str, Any] | None:
    """
    LLM 응답 텍스트에서 JSON을 추출.

    시도 순서:
    1. ```json ... ``` 코드 블록
    2. 균형 잡힌 {...} 매치 (문자열 컨텍스트 고려)
    3. 탐욕적 {...} 매치
    4. 직접 json.loads
    5. JSON 복구 후 재시도
    """
    cleaned = strip_think_tags(content)

    # 1차: 코드 블록 추출
    try:
        json_match = re.search(
            r"```(?:json)?\s*\n?(.*?)\n?\s*```", cleaned, re.DOTALL
        )
        if json_match:
            return json.loads(json_match.group(1))
    except (json.JSONDecodeError, AttributeError):
        pass

    # 2차: 균형 잡힌 JSON 객체 추출 (문자열 내 {} 무시)
    try:
        balanced = _find_balanced_json(cleaned)
        if balanced:
            return json.loads(balanced)
    except (json.JSONDecodeError, AttributeError):
        pass

    # 3차: 탐욕적 매치
    try:
        brace_match = re.search(r"\{.*\}", cleaned, re.DOTALL)
        if brace_match:
            return json.loads(brace_match.group(0))
        return json.loads(cleaned)
    except (json.JSONDecodeError, AttributeError):
        pass

    # 4차: JSON 복구 시도
    try:
        json_match = re.search(r"```(?:json)?\s*\n?(.*)", cleaned, re.DOTALL)
        raw = json_match.group(1) if json_match else cleaned
        balanced = _find_balanced_json(raw)
        if balanced:
            repaired = repair_json(balanced)
            result = json.loads(repaired)
            if isinstance(result, dict):
                return result
        # 균형 매치 실패 시 첫 { 이후 전부 복구
        brace_match = re.search(r"\{.*", raw, re.DOTALL)
        if brace_match:
            repaired = repair_json(brace_match.group(0))
            result = json.loads(repaired)
            if isinstance(result, dict):
                return result
    except (json.JSONDecodeError, AttributeError, ValueError):
        pass

    return None
