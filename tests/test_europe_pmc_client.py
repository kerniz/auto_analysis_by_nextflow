"""
Tests for clients/europe_pmc_client.py
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from clients.base import ClientConfig
from clients.europe_pmc_client import EuropePMCClient


def _make_client(**cfg_overrides):
    cfg = ClientConfig(
        base_url="https://www.ebi.ac.uk/europepmc/webservices/rest",
        rate_limit_delay=0,
        max_retries=1,
        **cfg_overrides,
    )
    c = EuropePMCClient(config=cfg)
    return c


class TestEuropePMCInit:
    def test_default_config(self):
        c = EuropePMCClient()
        assert c.name == "europe_pmc"
        assert c.config.rate_limit_delay == 0.35

    def test_custom_config(self):
        cfg = ClientConfig(base_url="https://custom.ebi.ac.uk")
        c = EuropePMCClient(config=cfg)
        assert c.config.base_url == "https://custom.ebi.ac.uk"


class TestSearch:
    @pytest.mark.asyncio
    async def test_search_success(self):
        c = _make_client()
        raw = {"resultList": {"result": [
            {"id": "1", "title": "Article 1"},
            {"id": "2", "title": "Article 2"},
        ]}}
        with patch.object(c, "_request_with_retry", new_callable=AsyncMock, return_value=raw):
            resp = await c.search("cancer rna-seq")
            assert resp.success is True
            assert len(resp.data) == 2

    @pytest.mark.asyncio
    async def test_search_cached(self):
        c = _make_client()
        raw = {"resultList": {"result": [{"id": "1"}]}}
        mock_retry = AsyncMock(return_value=raw)
        with patch.object(c, "_request_with_retry", mock_retry):
            r1 = await c.search("test", limit=5)
            r2 = await c.search("test", limit=5)
            assert r1.data == r2.data
            assert mock_retry.await_count == 1

    @pytest.mark.asyncio
    async def test_search_empty(self):
        c = _make_client()
        raw = {"resultList": {"result": []}}
        with patch.object(c, "_request_with_retry", new_callable=AsyncMock, return_value=raw):
            resp = await c.search("nonexistent query xyz")
            assert resp.success is True
            assert resp.data == []

    @pytest.mark.asyncio
    async def test_search_failure(self):
        c = _make_client()
        with patch.object(c, "_request_with_retry", new_callable=AsyncMock, side_effect=Exception("timeout")):
            resp = await c.search("fail")
            assert resp.success is False


class TestFetchById:
    @pytest.mark.asyncio
    async def test_fetch_found(self):
        c = _make_client()
        raw = {"resultList": {"result": [
            {"pmid": "12345", "title": "My Paper", "pmcid": "PMC999"}
        ]}}
        with patch.object(c, "_request_with_retry", new_callable=AsyncMock, return_value=raw):
            resp = await c.fetch_by_id("12345")
            assert resp.success is True
            assert resp.data["pmid"] == "12345"

    @pytest.mark.asyncio
    async def test_fetch_not_found(self):
        c = _make_client()
        raw = {"resultList": {"result": []}}
        with patch.object(c, "_request_with_retry", new_callable=AsyncMock, return_value=raw):
            resp = await c.fetch_by_id("99999999")
            assert resp.success is False
            assert "찾을 수 없습니다" in resp.error_message

    @pytest.mark.asyncio
    async def test_fetch_failure(self):
        c = _make_client()
        with patch.object(c, "_request_with_retry", new_callable=AsyncMock, side_effect=Exception("err")):
            resp = await c.fetch_by_id("12345")
            assert resp.success is False


class TestGetCitations:
    @pytest.mark.asyncio
    async def test_citations_success(self):
        c = _make_client()
        raw = {"citationList": {"citation": [
            {"id": "c1", "title": "Citing paper"},
        ]}}
        with patch.object(c, "_request_with_retry", new_callable=AsyncMock, return_value=raw):
            resp = await c.get_citations("12345")
            assert resp.success is True
            assert len(resp.data) == 1

    @pytest.mark.asyncio
    async def test_citations_cached(self):
        c = _make_client()
        raw = {"citationList": {"citation": [{"id": "c1"}]}}
        mock_retry = AsyncMock(return_value=raw)
        with patch.object(c, "_request_with_retry", mock_retry):
            await c.get_citations("12345")
            await c.get_citations("12345")
            assert mock_retry.await_count == 1

    @pytest.mark.asyncio
    async def test_citations_failure(self):
        c = _make_client()
        with patch.object(c, "_request_with_retry", new_callable=AsyncMock, side_effect=Exception("err")):
            resp = await c.get_citations("12345")
            assert resp.success is False


class TestGetReferences:
    @pytest.mark.asyncio
    async def test_references_success(self):
        c = _make_client()
        raw = {"referenceList": {"reference": [
            {"id": "r1", "title": "Referenced paper"},
        ]}}
        with patch.object(c, "_request_with_retry", new_callable=AsyncMock, return_value=raw):
            resp = await c.get_references("12345")
            assert resp.success is True
            assert len(resp.data) == 1

    @pytest.mark.asyncio
    async def test_references_failure(self):
        c = _make_client()
        with patch.object(c, "_request_with_retry", new_callable=AsyncMock, side_effect=Exception("err")):
            resp = await c.get_references("12345")
            assert resp.success is False


class TestGetTextMinedTerms:
    @pytest.mark.asyncio
    async def test_annotations_success(self):
        c = _make_client()
        ann_data = [{"type": "Gene", "exact": "TP53"}]
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.content = b'[{"type":"Gene","exact":"TP53"}]'
        mock_resp.json.return_value = ann_data
        mock_resp.raise_for_status = MagicMock()
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_resp)
        mock_client.is_closed = False
        with patch.object(c, "_get_client", new_callable=AsyncMock, return_value=mock_client):
            resp = await c.get_text_mined_terms("PMC12345")
            assert resp.success is True
            assert len(resp.data) == 1
            assert resp.data[0]["type"] == "Gene"

    @pytest.mark.asyncio
    async def test_annotations_strip_pmc_prefix(self):
        c = _make_client()
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.content = b'[]'
        mock_resp.json.return_value = []
        mock_resp.raise_for_status = MagicMock()
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_resp)
        mock_client.is_closed = False
        with patch.object(c, "_get_client", new_callable=AsyncMock, return_value=mock_client):
            resp = await c.get_text_mined_terms("PMC12345")
            assert resp.success is True
            assert "PMC12345" in resp.query

    @pytest.mark.asyncio
    async def test_annotations_dict_response(self):
        c = _make_client()
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.content = b'{"annotations": [{"type": "Chemical"}]}'
        mock_resp.json.return_value = {"annotations": [{"type": "Chemical"}]}
        mock_resp.raise_for_status = MagicMock()
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_resp)
        mock_client.is_closed = False
        with patch.object(c, "_get_client", new_callable=AsyncMock, return_value=mock_client):
            resp = await c.get_text_mined_terms("12345")
            assert resp.success is True
            assert resp.data[0]["type"] == "Chemical"

    @pytest.mark.asyncio
    async def test_annotations_empty(self):
        c = _make_client()
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.content = b''
        mock_resp.json.return_value = []
        mock_resp.raise_for_status = MagicMock()
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_resp)
        mock_client.is_closed = False
        with patch.object(c, "_get_client", new_callable=AsyncMock, return_value=mock_client):
            resp = await c.get_text_mined_terms("99999")
            assert resp.success is True

    @pytest.mark.asyncio
    async def test_annotations_failure(self):
        c = _make_client()
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(side_effect=Exception("err"))
        mock_client.is_closed = False
        with patch.object(c, "_get_client", new_callable=AsyncMock, return_value=mock_client):
            resp = await c.get_text_mined_terms("12345")
            assert resp.success is False


class TestHealthCheck:
    @pytest.mark.asyncio
    async def test_healthy(self):
        c = _make_client()
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_resp)
        mock_client.is_closed = False
        with patch.object(c, "_get_client", new_callable=AsyncMock, return_value=mock_client):
            assert await c.health_check() is True

    @pytest.mark.asyncio
    async def test_unhealthy(self):
        c = _make_client()
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(side_effect=Exception("down"))
        mock_client.is_closed = False
        with patch.object(c, "_get_client", new_callable=AsyncMock, return_value=mock_client):
            assert await c.health_check() is False
