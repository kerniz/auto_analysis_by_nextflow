"""
Tests for MCP Package (Brave Search Client)
MCP 패키지 테스트
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from mcp.brave_client import BraveSearchClient


class TestBraveSearchClient:
    def test_init_no_key(self, monkeypatch):
        monkeypatch.delenv("BRAVE_API_KEY", raising=False)
        client = BraveSearchClient()
        assert client._api_key is None

    def test_init_with_key(self):
        client = BraveSearchClient(api_key="test-key")
        assert client._api_key == "test-key"

    @pytest.mark.asyncio
    async def test_search_no_key_returns_empty(self, monkeypatch):
        monkeypatch.delenv("BRAVE_API_KEY", raising=False)
        client = BraveSearchClient(api_key=None)
        results = await client.search("test query")
        assert results == []

    def test_parse_results(self):
        client = BraveSearchClient(api_key="test")
        raw = {
            "web": {
                "results": [
                    {
                        "title": "Result 1",
                        "url": "https://example.com",
                        "description": "Description 1",
                        "age": "2 days ago",
                    },
                    {
                        "title": "Result 2",
                        "url": "https://example2.com",
                        "description": "Description 2",
                    },
                ]
            }
        }
        results = client._parse_results(raw)
        assert len(results) == 2
        assert results[0]["title"] == "Result 1"
        assert results[0]["source"] == "brave_search"
        assert results[1]["url"] == "https://example2.com"

    def test_parse_results_empty(self):
        client = BraveSearchClient(api_key="test")
        assert client._parse_results({}) == []
        assert client._parse_results({"web": {}}) == []
        assert client._parse_results({"web": {"results": []}}) == []

    @pytest.mark.asyncio
    async def test_close(self):
        client = BraveSearchClient(api_key="test")
        await client.close()
        assert client._client is None
