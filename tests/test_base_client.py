"""
Tests for clients/base.py — BaseClient, ClientConfig, ClientResponse
"""

import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from clients.base import BaseClient, ClientConfig, ClientResponse


# Concrete subclass for testing the abstract BaseClient
class _StubClient(BaseClient):
    @property
    def name(self) -> str:
        return "stub"

    async def search(self, query, limit=20, **kw):
        return self._make_response(success=True, data=[], query=query, latency_ms=0)

    async def fetch_by_id(self, identifier, **kw):
        return self._make_response(success=True, data={}, query=identifier, latency_ms=0)


def _make_config(**overrides):
    defaults = {"base_url": "https://stub.example.com"}
    defaults.update(overrides)
    return ClientConfig(**defaults)


# ── ClientConfig ──────────────────────────────────────────────────

class TestClientConfig:
    def test_defaults(self):
        cfg = ClientConfig(base_url="https://x.com")
        assert cfg.timeout == 30
        assert cfg.max_retries == 3
        assert cfg.rate_limit_delay == 0.5
        assert cfg.cache_enabled is True
        assert cfg.api_key is None
        assert cfg.extra_headers == {}

    def test_custom(self):
        cfg = ClientConfig(
            base_url="https://x.com",
            timeout=10,
            max_retries=1,
            rate_limit_delay=2.0,
            cache_enabled=False,
            api_key="k",
            extra_headers={"X-Foo": "bar"},
        )
        assert cfg.timeout == 10
        assert cfg.api_key == "k"
        assert cfg.extra_headers == {"X-Foo": "bar"}


# ── ClientResponse ────────────────────────────────────────────────

class TestClientResponse:
    def test_to_dict_keys(self):
        r = ClientResponse(success=True, data="d", source="s", query="q", latency_ms=1.5)
        d = r.to_dict()
        assert set(d.keys()) == {
            "success", "data", "source", "query",
            "error_message", "latency_ms", "timestamp",
        }
        assert d["success"] is True
        assert d["latency_ms"] == 1.5

    def test_to_dict_timestamp_iso(self):
        r = ClientResponse(success=True, data=None, source="s", query="q")
        d = r.to_dict()
        # Should be a valid ISO timestamp string
        assert "T" in d["timestamp"]


# ── BaseClient concrete helpers ───────────────────────────────────

class TestBaseClientCacheAndMetrics:
    def test_cache_key(self):
        c = _StubClient(_make_config())
        assert c._cache_key("a", "b", "c") == "a|b|c"

    def test_get_set_cached(self):
        c = _StubClient(_make_config())
        resp = ClientResponse(success=True, data=1, source="s", query="q")
        c._set_cached("k1", resp)
        assert c._get_cached("k1") is resp

    def test_cache_disabled(self):
        c = _StubClient(_make_config(cache_enabled=False))
        resp = ClientResponse(success=True, data=1, source="s", query="q")
        c._set_cached("k1", resp)
        assert c._get_cached("k1") is None

    def test_cache_only_success(self):
        c = _StubClient(_make_config())
        resp = ClientResponse(success=False, data=None, source="s", query="q")
        c._set_cached("k1", resp)
        assert c._get_cached("k1") is None

    def test_make_response_updates_metrics(self):
        c = _StubClient(_make_config())
        c._make_response(success=True, data=None, query="q", latency_ms=50)
        c._make_response(success=True, data=None, query="q", latency_ms=100)
        assert c._request_count == 2
        assert c._total_latency_ms == 150

    def test_get_metrics(self):
        c = _StubClient(_make_config())
        c._make_response(success=True, data=None, query="q", latency_ms=100)
        m = c.get_metrics()
        assert m["name"] == "stub"
        assert m["request_count"] == 1
        assert m["avg_latency_ms"] == 100.0
        assert m["cache_size"] == 0
        assert m["cache_enabled"] is True

    def test_get_metrics_zero_requests(self):
        c = _StubClient(_make_config())
        m = c.get_metrics()
        assert m["avg_latency_ms"] == 0.0


# ── _get_client ───────────────────────────────────────────────────

class TestGetClient:
    @pytest.mark.asyncio
    async def test_creates_httpx_client(self):
        import httpx as real_httpx
        c = _StubClient(_make_config(api_key="abc", extra_headers={"X-A": "1"}))
        mock_async = MagicMock()
        mock_async.is_closed = False
        with patch.object(real_httpx, "AsyncClient", return_value=mock_async) as mock_cls:
            client = await c._get_client()
            assert client is mock_async
            call_kw = mock_cls.call_args[1]
            assert call_kw["base_url"] == "https://stub.example.com"
            assert "x-api-key" in call_kw["headers"]
            assert call_kw["headers"]["X-A"] == "1"

    @pytest.mark.asyncio
    async def test_reuses_existing_client(self):
        c = _StubClient(_make_config())
        mock_async = MagicMock()
        mock_async.is_closed = False
        c._client = mock_async
        c1 = await c._get_client()
        c2 = await c._get_client()
        assert c1 is c2
        assert c1 is mock_async

    @pytest.mark.asyncio
    async def test_recreates_closed_client(self):
        import httpx as real_httpx
        c = _StubClient(_make_config())
        mock_async = MagicMock()
        mock_async.is_closed = True
        c._client = mock_async
        new_mock = MagicMock()
        new_mock.is_closed = False
        with patch.object(real_httpx, "AsyncClient", return_value=new_mock):
            client = await c._get_client()
            assert client is new_mock


# ── _request_with_retry ──────────────────────────────────────────

class TestRequestWithRetry:
    @pytest.mark.asyncio
    async def test_get_success(self):
        c = _StubClient(_make_config(rate_limit_delay=0))
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.content = b'{"ok":true}'
        mock_resp.headers = {"content-type": "application/json"}
        mock_resp.json.return_value = {"ok": True}
        mock_resp.raise_for_status = MagicMock()

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_resp)
        mock_client.is_closed = False
        c._client = mock_client

        result = await c._request_with_retry("GET", "/test", params={"a": "1"})
        assert result == {"ok": True}

    @pytest.mark.asyncio
    async def test_post_success(self):
        c = _StubClient(_make_config(rate_limit_delay=0))
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.content = b'{"ok":true}'
        mock_resp.headers = {"content-type": "application/json"}
        mock_resp.json.return_value = {"ok": True}
        mock_resp.raise_for_status = MagicMock()

        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=mock_resp)
        mock_client.is_closed = False
        c._client = mock_client

        result = await c._request_with_retry("POST", "/test", json_body={"x": 1})
        assert result == {"ok": True}

    @pytest.mark.asyncio
    async def test_unsupported_method(self):
        c = _StubClient(_make_config(rate_limit_delay=0, max_retries=1))
        mock_client = AsyncMock()
        mock_client.is_closed = False
        c._client = mock_client
        with pytest.raises(ValueError, match="HTTP"):
            await c._request_with_retry("DELETE", "/test")

    @pytest.mark.asyncio
    async def test_204_empty_response(self):
        c = _StubClient(_make_config(rate_limit_delay=0))
        mock_resp = MagicMock()
        mock_resp.status_code = 204
        mock_resp.content = b""
        mock_resp.raise_for_status = MagicMock()

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_resp)
        mock_client.is_closed = False
        c._client = mock_client

        result = await c._request_with_retry("GET", "/empty")
        assert result == {}

    @pytest.mark.asyncio
    async def test_text_response(self):
        c = _StubClient(_make_config(rate_limit_delay=0))
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.content = b"some text"
        mock_resp.headers = {"content-type": "text/plain"}
        mock_resp.text = "some text"
        mock_resp.raise_for_status = MagicMock()

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_resp)
        mock_client.is_closed = False
        c._client = mock_client

        result = await c._request_with_retry("GET", "/text")
        assert result == {"_text": "some text"}

    @pytest.mark.asyncio
    async def test_retry_on_failure(self):
        c = _StubClient(_make_config(rate_limit_delay=0, max_retries=3))

        ok_resp = MagicMock()
        ok_resp.status_code = 200
        ok_resp.content = b'{"ok":true}'
        ok_resp.headers = {"content-type": "application/json"}
        ok_resp.json.return_value = {"ok": True}
        ok_resp.raise_for_status = MagicMock()

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(
            side_effect=[Exception("fail1"), Exception("fail2"), ok_resp]
        )
        mock_client.is_closed = False
        c._client = mock_client

        result = await c._request_with_retry("GET", "/retry")
        assert result == {"ok": True}
        assert c._error_count == 2

    @pytest.mark.asyncio
    async def test_all_retries_exhausted(self):
        c = _StubClient(_make_config(rate_limit_delay=0, max_retries=2))
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(side_effect=Exception("always fail"))
        mock_client.is_closed = False
        c._client = mock_client

        with pytest.raises(Exception, match="always fail"):
            await c._request_with_retry("GET", "/fail")

    @pytest.mark.asyncio
    async def test_extra_headers(self):
        c = _StubClient(_make_config(rate_limit_delay=0))
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.content = b'{"ok":true}'
        mock_resp.headers = {"content-type": "application/json"}
        mock_resp.json.return_value = {"ok": True}
        mock_resp.raise_for_status = MagicMock()

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_resp)
        mock_client.is_closed = False
        c._client = mock_client

        await c._request_with_retry("GET", "/h", extra_headers={"X-Custom": "val"})
        _, kwargs = mock_client.get.call_args
        assert kwargs["headers"]["X-Custom"] == "val"

    @pytest.mark.asyncio
    async def test_rate_limiting(self):
        c = _StubClient(_make_config(rate_limit_delay=0))
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.content = b'{}'
        mock_resp.headers = {"content-type": "application/json"}
        mock_resp.json.return_value = {}
        mock_resp.raise_for_status = MagicMock()

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_resp)
        mock_client.is_closed = False
        c._client = mock_client

        # Set _last_request_time to now to trigger rate-limit path
        c._last_request_time = time.time()
        await c._request_with_retry("GET", "/rate")
        assert c._last_request_time is not None


# ── health_check ──────────────────────────────────────────────────

class TestHealthCheck:
    @pytest.mark.asyncio
    async def test_healthy(self):
        c = _StubClient(_make_config())
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_resp)
        mock_client.is_closed = False
        c._client = mock_client
        assert await c.health_check() is True

    @pytest.mark.asyncio
    async def test_unhealthy_500(self):
        c = _StubClient(_make_config())
        mock_resp = MagicMock()
        mock_resp.status_code = 500
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_resp)
        mock_client.is_closed = False
        c._client = mock_client
        assert await c.health_check() is False

    @pytest.mark.asyncio
    async def test_exception(self):
        c = _StubClient(_make_config())
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(side_effect=Exception("down"))
        mock_client.is_closed = False
        c._client = mock_client
        assert await c.health_check() is False


# ── close ─────────────────────────────────────────────────────────

class TestClose:
    @pytest.mark.asyncio
    async def test_close_clears_client_and_cache(self):
        c = _StubClient(_make_config())
        mock_client = AsyncMock()
        mock_client.is_closed = False
        c._client = mock_client
        c._cache["k"] = "v"

        await c.close()
        assert c._client is None
        assert c._cache == {}
        mock_client.aclose.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_close_already_closed(self):
        c = _StubClient(_make_config())
        mock_client = MagicMock()
        mock_client.is_closed = True
        c._client = mock_client
        await c.close()
        # Should not crash

    @pytest.mark.asyncio
    async def test_close_no_client(self):
        c = _StubClient(_make_config())
        await c.close()
        # Should not crash
