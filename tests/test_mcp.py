"""
Tests for MCP Package (Brave Search Client)
MCP 패키지 테스트
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from mcp.brave_client import BraveSearchClient


class TestBraveSearchClient:
    def test_init_no_key(self, monkeypatch):
        monkeypatch.delenv("BRAVE_API_KEY", raising=False)
        client = BraveSearchClient()
        assert client._api_key is None

    def test_init_with_key(self):
        client = BraveSearchClient(api_key="test-key")
        assert client._api_key == "test-key"

    def test_init_from_env(self, monkeypatch):
        monkeypatch.setenv("BRAVE_API_KEY", "env-key")
        client = BraveSearchClient()
        assert client._api_key == "env-key"

    def test_init_custom_timeout(self):
        client = BraveSearchClient(api_key="k", timeout=30)
        assert client._timeout == 30

    def test_init_default_timeout(self):
        client = BraveSearchClient(api_key="k")
        assert client._timeout == 15

    def test_api_base_constant(self):
        assert BraveSearchClient.API_BASE == "https://api.search.brave.com/res/v1/web/search"

    @pytest.mark.asyncio
    async def test_search_no_key_returns_empty(self, monkeypatch):
        monkeypatch.delenv("BRAVE_API_KEY", raising=False)
        client = BraveSearchClient(api_key=None)
        results = await client.search("test query")
        assert results == []

    @pytest.mark.asyncio
    async def test_search_no_httpx_returns_empty(self):
        client = BraveSearchClient(api_key="test-key")
        with patch("mcp.brave_client.HAS_HTTPX", False):
            results = await client.search("test query")
            assert results == []

    @pytest.mark.asyncio
    async def test_search_no_client_returns_empty(self):
        client = BraveSearchClient(api_key="test-key")
        with patch.object(client, "_get_client", return_value=None):
            results = await client.search("test query")
            assert results == []

    @pytest.mark.asyncio
    async def test_search_success(self):
        client = BraveSearchClient(api_key="test-key")

        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()
        mock_response.json.return_value = {
            "web": {
                "results": [
                    {
                        "title": "Result 1",
                        "url": "https://example.com",
                        "description": "Desc 1",
                        "age": "1 day ago",
                    }
                ]
            }
        }

        mock_http_client = AsyncMock()
        mock_http_client.get = AsyncMock(return_value=mock_response)
        client._client = mock_http_client

        results = await client.search("test query", count=5)
        assert len(results) == 1
        assert results[0]["title"] == "Result 1"
        assert results[0]["source"] == "brave_search"

        # Verify API call params
        call_kwargs = mock_http_client.get.call_args
        assert call_kwargs.kwargs["params"]["q"] == "test query"
        assert call_kwargs.kwargs["params"]["count"] == 5
        assert "X-Subscription-Token" in call_kwargs.kwargs["headers"]

    @pytest.mark.asyncio
    async def test_search_exception_returns_empty(self):
        client = BraveSearchClient(api_key="test-key")

        mock_http_client = AsyncMock()
        mock_http_client.get = AsyncMock(side_effect=Exception("network error"))
        client._client = mock_http_client

        results = await client.search("test query")
        assert results == []

    @pytest.mark.asyncio
    async def test_search_http_error_returns_empty(self):
        client = BraveSearchClient(api_key="test-key")

        mock_response = MagicMock()
        mock_response.raise_for_status.side_effect = Exception("403 Forbidden")

        mock_http_client = AsyncMock()
        mock_http_client.get = AsyncMock(return_value=mock_response)
        client._client = mock_http_client

        results = await client.search("test query")
        assert results == []

    @pytest.mark.asyncio
    async def test_search_default_count(self):
        client = BraveSearchClient(api_key="test-key")

        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()
        mock_response.json.return_value = {"web": {"results": []}}

        mock_http_client = AsyncMock()
        mock_http_client.get = AsyncMock(return_value=mock_response)
        client._client = mock_http_client

        await client.search("test")
        call_kwargs = mock_http_client.get.call_args
        assert call_kwargs.kwargs["params"]["count"] == 10

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
        assert results[0]["age"] == "2 days ago"
        assert results[1]["url"] == "https://example2.com"
        assert results[1]["age"] == ""  # Missing age defaults to ""

    def test_parse_results_empty(self):
        client = BraveSearchClient(api_key="test")
        assert client._parse_results({}) == []
        assert client._parse_results({"web": {}}) == []
        assert client._parse_results({"web": {"results": []}}) == []

    def test_parse_results_missing_fields(self):
        client = BraveSearchClient(api_key="test")
        raw = {"web": {"results": [{}]}}
        results = client._parse_results(raw)
        assert len(results) == 1
        assert results[0]["title"] == ""
        assert results[0]["url"] == ""
        assert results[0]["description"] == ""
        assert results[0]["age"] == ""
        assert results[0]["source"] == "brave_search"

    def test_get_client_lazy_init(self):
        client = BraveSearchClient(api_key="test")
        assert client._client is None
        with patch("mcp.brave_client.HAS_HTTPX", True):
            with patch("mcp.brave_client.httpx") as mock_httpx:
                mock_instance = MagicMock()
                mock_httpx.AsyncClient.return_value = mock_instance
                result = client._get_client()
                assert result is mock_instance

    def test_get_client_no_httpx(self):
        client = BraveSearchClient(api_key="test")
        with patch("mcp.brave_client.HAS_HTTPX", False):
            result = client._get_client()
            assert result is None

    def test_get_client_reuses_existing(self):
        client = BraveSearchClient(api_key="test")
        mock_client = MagicMock()
        client._client = mock_client
        result = client._get_client()
        assert result is mock_client

    @pytest.mark.asyncio
    async def test_close(self):
        client = BraveSearchClient(api_key="test")
        await client.close()
        assert client._client is None

    @pytest.mark.asyncio
    async def test_close_with_client(self):
        client = BraveSearchClient(api_key="test")
        mock_http_client = AsyncMock()
        client._client = mock_http_client

        await client.close()
        mock_http_client.aclose.assert_called_once()
        assert client._client is None

    @pytest.mark.asyncio
    async def test_search_multiple_results(self):
        client = BraveSearchClient(api_key="test-key")

        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()
        mock_response.json.return_value = {
            "web": {
                "results": [
                    {"title": f"Result {i}", "url": f"https://example{i}.com", "description": f"Desc {i}"}
                    for i in range(5)
                ]
            }
        }

        mock_http_client = AsyncMock()
        mock_http_client.get = AsyncMock(return_value=mock_response)
        client._client = mock_http_client

        results = await client.search("bio query")
        assert len(results) == 5
        for i, r in enumerate(results):
            assert r["title"] == f"Result {i}"
