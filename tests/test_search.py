"""
Tests for Search Package
검색 패키지 테스트
"""

from unittest.mock import AsyncMock, MagicMock, patch

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


class TestTopicSearcherEdgeCases:
    """Edge case tests for TopicSearcher to improve coverage."""

    @pytest.mark.asyncio
    async def test_search_pubmed_exception_returns_empty(self):
        """Mock asyncio.to_thread to raise Exception, verify empty result."""
        mock_pubmed = AsyncMock()
        mock_pubmed.search_by_topic = MagicMock(side_effect=Exception("PubMed down"))
        searcher = TopicSearcher(pubmed_client=mock_pubmed)

        with patch("asyncio.to_thread", side_effect=Exception("PubMed down")):
            results = await searcher.search("cancer")

        assert results == []

    @pytest.mark.asyncio
    async def test_search_semantic_scholar_failed_response(self):
        """Return ClientResponse(success=False), verify empty."""
        mock_ss = AsyncMock()
        mock_ss.search = AsyncMock(return_value=ClientResponse(
            success=False,
            data=None,
            source="semantic_scholar",
            query="test",
            error_message="Rate limited",
        ))
        searcher = TopicSearcher(ss_client=mock_ss)
        results = await searcher.search("test")
        assert results == []

    @pytest.mark.asyncio
    async def test_search_europe_pmc_failed_response(self):
        """Return ClientResponse(success=False), verify empty."""
        mock_epmc = AsyncMock()
        mock_epmc.search = AsyncMock(return_value=ClientResponse(
            success=False,
            data=None,
            source="europe_pmc",
            query="test",
            error_message="Service unavailable",
        ))
        searcher = TopicSearcher(epmc_client=mock_epmc)
        results = await searcher.search("test")
        assert results == []

    @pytest.mark.asyncio
    async def test_search_europe_pmc_non_list_data(self):
        """Return ClientResponse(success=True, data='not a list'), verify handling."""
        mock_epmc = AsyncMock()
        mock_epmc.search = AsyncMock(return_value=ClientResponse(
            success=True,
            data="not a list",
            source="europe_pmc",
            query="test",
        ))
        searcher = TopicSearcher(epmc_client=mock_epmc)
        results = await searcher.search("test")
        # Non-list data should be handled gracefully (empty papers list)
        assert results == []

    @pytest.mark.asyncio
    async def test_search_brave_exception(self):
        """Mock brave search to raise, verify empty."""
        mock_brave = AsyncMock()
        mock_brave.search = AsyncMock(side_effect=RuntimeError("Network error"))
        searcher = TopicSearcher(brave_client=mock_brave)
        results = await searcher.search("genomics")
        assert results == []

    def test_normalize_ss_no_external_ids(self):
        """Paper dict without 'externalIds' key."""
        searcher = TopicSearcher()
        paper = {
            "title": "No External IDs Paper",
            "abstract": "Some abstract",
            "year": 2023,
            "citationCount": 5,
            "authors": [{"name": "Smith J"}],
        }
        result = searcher._normalize_ss(paper)
        assert result.pmid is None
        assert result.doi is None
        assert result.title == "No External IDs Paper"
        assert result.year == 2023
        assert result.citation_count == 5
        assert result.authors == ["Smith J"]
        assert result.sources == ["semantic_scholar"]

    def test_normalize_epmc_no_year(self):
        """Paper dict without 'pubYear' field."""
        searcher = TopicSearcher()
        paper = {
            "pmid": "99999",
            "title": "No Year Paper",
            "abstractText": "Abstract here",
            "citedByCount": 12,
            "authorList": {"author": [{"fullName": "Doe J"}]},
        }
        result = searcher._normalize_epmc(paper)
        assert result.year is None
        assert result.pmid == "99999"
        assert result.title == "No Year Paper"
        assert result.authors == ["Doe J"]
        assert result.citation_count == 12

    @pytest.mark.asyncio
    async def test_search_mixed_success_and_exception(self):
        """asyncio.gather returns mix of results and Exception objects."""
        # SS succeeds
        mock_ss = AsyncMock()
        mock_ss.search = AsyncMock(return_value=ClientResponse(
            success=True,
            data=[{
                "title": "Good Paper",
                "abstract": "Abs",
                "year": 2024,
                "citationCount": 10,
                "authors": [],
                "externalIds": {"PubMed": "444"},
            }],
            source="semantic_scholar",
            query="test",
        ))
        # EPMC raises exception
        mock_epmc = AsyncMock()
        mock_epmc.search = AsyncMock(side_effect=ConnectionError("timeout"))
        # Brave raises exception
        mock_brave = AsyncMock()
        mock_brave.search = AsyncMock(side_effect=ValueError("bad response"))

        searcher = TopicSearcher(
            ss_client=mock_ss, epmc_client=mock_epmc, brave_client=mock_brave
        )
        results = await searcher.search("mixed test")

        # Only SS result should come through; EPMC and Brave failures handled
        assert len(results) == 1
        assert results[0].pmid == "444"
        assert results[0].title == "Good Paper"
