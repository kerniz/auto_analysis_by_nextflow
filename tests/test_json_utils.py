"""Tests for core.json_utils — shared JSON parsing utilities."""

from core.json_utils import (
    _find_balanced_json,
    extract_json_from_llm,
    repair_json,
    strip_think_tags,
)


class TestStripThinkTags:
    def test_removes_think_block(self):
        text = "<think>reasoning here</think>actual content"
        assert strip_think_tags(text) == "actual content"

    def test_removes_multiline_think(self):
        text = "<think>\nlong\nreasoning\n</think>\nresult"
        assert strip_think_tags(text) == "result"

    def test_no_think_tags(self):
        text = "plain text"
        assert strip_think_tags(text) == "plain text"

    def test_empty_string(self):
        assert strip_think_tags("") == ""


class TestRepairJson:
    def test_trailing_comma_object(self):
        result = repair_json('{"a": 1, "b": 2,}')
        assert '"b": 2}' in result

    def test_trailing_comma_array(self):
        result = repair_json('[1, 2, 3,]')
        assert result.endswith(']')

    def test_unclosed_brace(self):
        result = repair_json('{"a": 1')
        assert result.endswith('}')

    def test_unclosed_bracket(self):
        result = repair_json('{"a": [1, 2')
        assert result.endswith(']}')

    def test_unclosed_string(self):
        result = repair_json('{"key": "unclosed value')
        assert result.count('"') % 2 == 0

    def test_valid_json_unchanged(self):
        text = '{"a": 1, "b": [2, 3]}'
        assert repair_json(text) == text


class TestExtractJsonFromLlm:
    def test_code_block_json(self):
        content = 'Here is the result:\n```json\n{"score": 0.8}\n```'
        result = extract_json_from_llm(content)
        assert result == {"score": 0.8}

    def test_code_block_no_lang(self):
        content = '```\n{"score": 0.5}\n```'
        result = extract_json_from_llm(content)
        assert result == {"score": 0.5}

    def test_raw_json_braces(self):
        content = 'The analysis shows {"score": 0.9, "rating": "PASS"} as output.'
        result = extract_json_from_llm(content)
        assert result["score"] == 0.9

    def test_with_think_tags(self):
        content = '<think>Let me think...</think>{"result": "good"}'
        result = extract_json_from_llm(content)
        assert result == {"result": "good"}

    def test_broken_json_repair(self):
        content = '{"score": 0.7, "items": [1, 2,'
        result = extract_json_from_llm(content)
        assert result is not None
        assert result["score"] == 0.7

    def test_no_json_returns_none(self):
        content = "This is just plain text with no JSON."
        result = extract_json_from_llm(content)
        assert result is None

    def test_trailing_comma_repair(self):
        content = '{"a": 1, "b": 2,}'
        result = extract_json_from_llm(content)
        assert result == {"a": 1, "b": 2}

    def test_unclosed_think_tag(self):
        content = '<think>Still thinking...{"score": 0.5}'
        result = extract_json_from_llm(content)
        assert result is None or result.get("score") == 0.5

    def test_nested_json_in_string(self):
        content = '{"assessment": "The data shows {key: val} patterns", "score": 0.8}'
        result = extract_json_from_llm(content)
        assert result is not None
        assert result["score"] == 0.8

    def test_long_multiline_json(self):
        content = """```json
{
  "assessment": "Comprehensive evaluation of the research paper",
  "score": 0.75,
  "confidence": 0.85,
  "key_points": [
    "Point 1 about methodology",
    "Point 2 about results"
  ],
  "concerns": [
    "Concern about sample size",
    "Concern about reproducibility"
  ],
  "questions": ["Question 1"],
  "rebuttal_to": null
}
```"""
        result = extract_json_from_llm(content)
        assert result is not None
        assert result["score"] == 0.75
        assert len(result["key_points"]) == 2

    def test_json_with_korean_text(self):
        content = '{"assessment": "멜리틴의 항염증 효과가 유의미함", "score": 0.8}'
        result = extract_json_from_llm(content)
        assert result is not None
        assert result["score"] == 0.8
        assert "멜리틴" in result["assessment"]

    def test_json_after_text_explanation(self):
        content = """Based on my analysis, here is my assessment:

{"assessment": "Good study", "score": 0.7, "confidence": 0.8, "key_points": [], "concerns": [], "questions": [], "rebuttal_to": null}"""
        result = extract_json_from_llm(content)
        assert result is not None
        assert result["score"] == 0.7

    def test_rebuttal_to_string_null(self):
        content = '{"score": 0.6, "rebuttal_to": "null"}'
        result = extract_json_from_llm(content)
        assert result is not None
        assert result["rebuttal_to"] == "null"


class TestFindBalancedJson:
    def test_simple_object(self):
        text = '{"key": "value"}'
        assert _find_balanced_json(text) == '{"key": "value"}'

    def test_nested_objects(self):
        text = '{"outer": {"inner": 1}}'
        assert _find_balanced_json(text) == '{"outer": {"inner": 1}}'

    def test_braces_in_strings(self):
        text = '{"key": "value with {braces}"}'
        result = _find_balanced_json(text)
        assert result == '{"key": "value with {braces}"}'

    def test_prefix_text(self):
        text = 'Here is JSON: {"score": 0.5}'
        result = _find_balanced_json(text)
        assert result == '{"score": 0.5}'

    def test_no_json(self):
        assert _find_balanced_json("no json here") is None

    def test_unclosed_returns_rest(self):
        text = '{"score": 0.5, "items": [1, 2'
        result = _find_balanced_json(text)
        assert result is not None
        assert result.startswith('{"score"')
