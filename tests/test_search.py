"""
Tests for Search Package
검색 패키지 테스트
"""

from unittest.mock import AsyncMock

import pytest

from clients.base import ClientResponse
from search import ResultRanker, SearchResult, TopicSearcher


@pytest.fixture
def sample_search_results():
    return [
        SearchResult(
            pmid="12345", title="Paper A", abstract="Abstract A",
            year=2024, citation_count=100, sources=["pubmed"],
        ),
        SearchResult(
            pmid="12345", title="Paper A", abstract="Abstract A",
            year=2024, citation_count=150, sources=["semantic_scholar"],
        ),
        SearchResult(
            pmid="67890", title="Paper B", abstract="Abstract B",
            year=2020, citation_count=50, sources=["europe_pmc"],
        ),
        SearchResult(
            pmid=None, title="Web Result", abstract="Some description",
            sources=["brave_search"],
        ),
    ]


class TestSearchResult:
    def test_create(self):
        r = SearchResult(pmid="123", title="Test", abstract="Abs")
        assert r.pmid == "123"
        assert r.relevance_score == 0.0
        assert r.sources == []

    def test_defaults(self):
        r = SearchResult(pmid=None, title="", abstract="")
        assert r.authors == []
        assert r.year is None
        assert r.citation_count == 0


class TestResultRanker:
    def test_empty(self):
        ranker = ResultRanker()
        assert ranker.rank([]) == []

    def test_deduplication(self, sample_search_results):
        ranker = ResultRanker()
        results = ranker.rank(sample_search_results)
        pmids = [r.pmid for r in results if r.pmid]
        # PMID 12345는 하나로 합쳐져야 함
        assert pmids.count("12345") == 1

    def test_source_merge(self, sample_search_results):
        ranker = ResultRanker()
        results = ranker.rank(sample_search_results)
        merged = [r for r in results if r.pmid == "12345"][0]
        assert "pubmed" in merged.sources
        assert "semantic_scholar" in merged.sources

    def test_citation_count_best(self, sample_search_results):
        ranker = ResultRanker()
        results = ranker.rank(sample_search_results)
        merged = [r for r in results if r.pmid == "12345"][0]
        assert merged.citation_count == 150  # 더 높은 값

    def test_scoring(self):
        ranker = ResultRanker()
        results = [
            SearchResult(
                pmid="1", title="High cite", abstract="",
                year=2025, citation_count=1000,
                sources=["pubmed", "semantic_scholar"],
            ),
            SearchResult(
                pmid="2", title="Low cite", abstract="",
                year=2015, citation_count=1,
                sources=["pubmed"],
            ),
        ]
        ranked = ranker.rank(results, current_year=2026)
        assert ranked[0].pmid == "1"
        assert ranked[0].relevance_score > ranked[1].relevance_score

    def test_recency_boost(self):
        ranker = ResultRanker()
        # 같은 인용수, 같은 소스 수 → 최신성만으로 차별화
        # rank_score는 순서에 따라 달라지므로 동일 citation으로 테스트
        results = [
            SearchResult(pmid="new", title="New", abstract="", year=2026, citation_count=100, sources=["pubmed"]),
            SearchResult(pmid="old", title="Old", abstract="", year=2010, citation_count=100, sources=["pubmed"]),
        ]
        ranked = ranker.rank(results, current_year=2026)
        new_r = [r for r in ranked if r.pmid == "new"][0]
        old_r = [r for r in ranked if r.pmid == "old"][0]
        assert new_r.relevance_score > old_r.relevance_score


class TestTopicSearcher:
    @pytest.mark.asyncio
    async def test_no_sources(self):
        searcher = TopicSearcher()
        results = await searcher.search("test query")
        assert results == []

    @pytest.mark.asyncio
    async def test_semantic_scholar_source(self):
        mock_ss = AsyncMock()
        mock_ss.search = AsyncMock(return_value=ClientResponse(
            success=True,
            data=[
                {"title": "Paper 1", "abstract": "Abs 1", "year": 2024,
                 "citationCount": 10, "authors": [{"name": "Auth"}],
                 "externalIds": {"PubMed": "111"}},
            ],
            source="semantic_scholar",
            query="test",
        ))
        searcher = TopicSearcher(ss_client=mock_ss)
        results = await searcher.search("test")
        assert len(results) == 1
        assert results[0].pmid == "111"
        assert results[0].sources == ["semantic_scholar"]

    @pytest.mark.asyncio
    async def test_europe_pmc_source(self):
        mock_epmc = AsyncMock()
        mock_epmc.search = AsyncMock(return_value=ClientResponse(
            success=True,
            data=[
                {"pmid": "222", "title": "PMC Paper", "abstractText": "Abs",
                 "pubYear": "2023", "citedByCount": 5, "authorList": {"author": []}},
            ],
            source="europe_pmc",
            query="test",
        ))
        searcher = TopicSearcher(epmc_client=mock_epmc)
        results = await searcher.search("test")
        assert len(results) == 1
        assert results[0].pmid == "222"

    @pytest.mark.asyncio
    async def test_brave_source(self):
        mock_brave = AsyncMock()
        mock_brave.search = AsyncMock(return_value=[
            {"title": "Web Result", "description": "Desc", "url": "https://example.com"},
        ])
        searcher = TopicSearcher(brave_client=mock_brave)
        results = await searcher.search("test")
        assert len(results) == 1
        assert results[0].pmid is None
        assert results[0].sources == ["brave_search"]

    @pytest.mark.asyncio
    async def test_failed_source_graceful(self):
        mock_ss = AsyncMock()
        mock_ss.search = AsyncMock(side_effect=Exception("API error"))
        mock_epmc = AsyncMock()
        mock_epmc.search = AsyncMock(return_value=ClientResponse(
            success=True,
            data=[{"pmid": "333", "title": "OK", "abstractText": "", "authorList": {"author": []}}],
            source="europe_pmc",
            query="test",
        ))
        searcher = TopicSearcher(ss_client=mock_ss, epmc_client=mock_epmc)
        results = await searcher.search("test")
        # SS 실패해도 EPMC 결과는 반환
        assert len(results) == 1
