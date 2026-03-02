"""Tests for core.json_utils — shared JSON parsing utilities."""

from core.json_utils import extract_json_from_llm, repair_json, strip_think_tags


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
