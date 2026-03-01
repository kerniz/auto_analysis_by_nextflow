"""
Tests for clients/semantic_scholar_client.py
"""

import math
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from clients.base import ClientConfig
from clients.semantic_scholar_client import SemanticScholarClient


def _make_client(**cfg_overrides):
    cfg = ClientConfig(
        base_url="https://api.semanticscholar.org",
        rate_limit_delay=0,
        max_retries=1,
        **cfg_overrides,
    )
    return SemanticScholarClient(config=cfg)


class TestSemanticScholarInit:
    def test_default_config(self):
        c = SemanticScholarClient()
        assert c.name == "semantic_scholar"
        assert c.config.rate_limit_delay == 1.0

    def test_custom_config(self):
        cfg = ClientConfig(base_url="https://x.com", api_key="K")
        c = SemanticScholarClient(config=cfg)
        assert c.config.api_key == "K"


class TestSearch:
    @pytest.mark.asyncio
    async def test_search_success(self):
        c = _make_client()
        raw = {"data": [{"paperId": "p1", "title": "Paper 1"}]}
        with patch.object(c, "_request_with_retry", new_callable=AsyncMock, return_value=raw):
            resp = await c.search("cancer")
            assert resp.success is True
            assert len(resp.data) == 1
            assert resp.data[0]["paperId"] == "p1"

    @pytest.mark.asyncio
    async def test_search_cached(self):
        c = _make_client()
        raw = {"data": [{"paperId": "p1"}]}
        mock_retry = AsyncMock(return_value=raw)
        with patch.object(c, "_request_with_retry", mock_retry):
            r1 = await c.search("cancer", limit=5)
            r2 = await c.search("cancer", limit=5)
            assert r1.data == r2.data
            assert mock_retry.await_count == 1

    @pytest.mark.asyncio
    async def test_search_failure(self):
        c = _make_client()
        with patch.object(c, "_request_with_retry", new_callable=AsyncMock, side_effect=Exception("timeout")):
            resp = await c.search("fail")
            assert resp.success is False
            assert "실패" in resp.error_message or "timeout" in resp.error_message


class TestFetchById:
    @pytest.mark.asyncio
    async def test_fetch_success(self):
        c = _make_client()
        raw = {"paperId": "abc", "title": "T", "citationCount": 10}
        with patch.object(c, "_request_with_retry", new_callable=AsyncMock, return_value=raw):
            resp = await c.fetch_by_id("abc")
            assert resp.success is True
            assert resp.data["paperId"] == "abc"

    @pytest.mark.asyncio
    async def test_fetch_failure(self):
        c = _make_client()
        with patch.object(c, "_request_with_retry", new_callable=AsyncMock, side_effect=Exception("not found")):
            resp = await c.fetch_by_id("xyz")
            assert resp.success is False


class TestFetchByPmid:
    @pytest.mark.asyncio
    async def test_pmid_prefix_added(self):
        c = _make_client()
        raw = {"paperId": "s2id", "title": "T"}
        mock_retry = AsyncMock(return_value=raw)
        with patch.object(c, "_request_with_retry", mock_retry):
            resp = await c.fetch_by_pmid("12345")
            assert resp.success is True
            # Verify the URL contains PMID: prefix
            call_args = mock_retry.call_args
            assert "PMID:12345" in str(call_args)

    @pytest.mark.asyncio
    async def test_pmid_already_prefixed(self):
        c = _make_client()
        raw = {"paperId": "s2id"}
        with patch.object(c, "_request_with_retry", new_callable=AsyncMock, return_value=raw):
            resp = await c.fetch_by_pmid("PMID:12345")
            assert resp.success is True


class TestGetCitations:
    @pytest.mark.asyncio
    async def test_citations_success(self):
        c = _make_client()
        raw = {"data": [{"citingPaper": {"paperId": "c1"}}]}
        with patch.object(c, "_request_with_retry", new_callable=AsyncMock, return_value=raw):
            resp = await c.get_citations("PMID:123")
            assert resp.success is True
            assert len(resp.data) == 1

    @pytest.mark.asyncio
    async def test_citations_failure(self):
        c = _make_client()
        with patch.object(c, "_request_with_retry", new_callable=AsyncMock, side_effect=Exception("err")):
            resp = await c.get_citations("PMID:123")
            assert resp.success is False


class TestGetReferences:
    @pytest.mark.asyncio
    async def test_references_success(self):
        c = _make_client()
        raw = {"data": [{"citedPaper": {"paperId": "r1"}}]}
        with patch.object(c, "_request_with_retry", new_callable=AsyncMock, return_value=raw):
            resp = await c.get_references("PMID:123")
            assert resp.success is True

    @pytest.mark.asyncio
    async def test_references_failure(self):
        c = _make_client()
        with patch.object(c, "_request_with_retry", new_callable=AsyncMock, side_effect=Exception("err")):
            resp = await c.get_references("PMID:123")
            assert resp.success is False


class TestGetRecommendations:
    @pytest.mark.asyncio
    async def test_recommendations_success(self):
        c = _make_client()
        raw = {"recommendedPapers": [{"paperId": "rec1"}]}
        with patch.object(c, "_request_with_retry", new_callable=AsyncMock, return_value=raw):
            resp = await c.get_recommendations("PMID:123")
            assert resp.success is True
            assert resp.data[0]["paperId"] == "rec1"

    @pytest.mark.asyncio
    async def test_recommendations_failure(self):
        c = _make_client()
        with patch.object(c, "_request_with_retry", new_callable=AsyncMock, side_effect=Exception("err")):
            resp = await c.get_recommendations("PMID:123")
            assert resp.success is False


class TestGetInfluenceScore:
    @pytest.mark.asyncio
    async def test_influence_success(self):
        c = _make_client()
        raw = {
            "paperId": "abc",
            "title": "T",
            "citationCount": 100,
            "influentialCitationCount": 20,
        }
        with patch.object(c, "_request_with_retry", new_callable=AsyncMock, return_value=raw):
            resp = await c.get_influence_score("abc")
            assert resp.success is True
            assert resp.data["citation_count"] == 100
            assert resp.data["influential_citation_count"] == 20
            assert resp.data["influential_ratio"] == 0.2
            expected_citation = min(math.log10(101) * 20, 60)
            expected_ratio = 0.2 * 40
            expected = round(expected_citation + expected_ratio, 2)
            assert resp.data["influence_score"] == expected

    @pytest.mark.asyncio
    async def test_influence_zero_citations(self):
        c = _make_client()
        raw = {"paperId": "abc", "title": "T", "citationCount": 0, "influentialCitationCount": 0}
        with patch.object(c, "_request_with_retry", new_callable=AsyncMock, return_value=raw):
            resp = await c.get_influence_score("abc")
            assert resp.success is True
            assert resp.data["influential_ratio"] == 0.0

    @pytest.mark.asyncio
    async def test_influence_paper_fetch_fails(self):
        c = _make_client()
        with patch.object(c, "_request_with_retry", new_callable=AsyncMock, side_effect=Exception("err")):
            resp = await c.get_influence_score("abc")
            assert resp.success is False

    @pytest.mark.asyncio
    async def test_influence_none_counts(self):
        c = _make_client()
        raw = {"paperId": "abc", "title": "T", "citationCount": None, "influentialCitationCount": None}
        with patch.object(c, "_request_with_retry", new_callable=AsyncMock, return_value=raw):
            resp = await c.get_influence_score("abc")
            assert resp.success is True
            assert resp.data["citation_count"] == 0


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
