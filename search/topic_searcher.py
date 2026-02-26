"""
Topic Search Orchestrator
주제 기반 논문 검색 오케스트레이터

PubMed, Semantic Scholar, Europe PMC, Brave Search를 병렬 쿼리하여
통합된 논문 검색 결과를 반환합니다.
"""

import asyncio
import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class SearchResult:
    """
    통합 검색 결과
    Normalized search result from any source.
    """
    pmid: Optional[str]
    title: str
    abstract: str
    authors: List[str] = field(default_factory=list)
    year: Optional[int] = None
    citation_count: int = 0
    sources: List[str] = field(default_factory=list)
    relevance_score: float = 0.0
    doi: Optional[str] = None
    url: Optional[str] = None


class TopicSearcher:
    """
    주제 기반 논문 검색 오케스트레이터

    4개 소스(PubMed, Semantic Scholar, Europe PMC, Brave Search)를
    asyncio.gather로 병렬 쿼리한 후 통합 결과를 반환합니다.
    """

    def __init__(
        self,
        pubmed_client=None,
        ss_client=None,
        epmc_client=None,
        brave_client=None,
        limit_per_source: int = 20,
    ):
        self.pubmed_client = pubmed_client
        self.ss_client = ss_client
        self.epmc_client = epmc_client
        self.brave_client = brave_client
        self.limit_per_source = limit_per_source

    async def search(self, query: str) -> List[SearchResult]:
        """
        모든 소스에서 병렬 검색 후 통합 결과 반환

        Args:
            query: 검색 키워드

        Returns:
            통합된 SearchResult 목록 (미정렬)
        """
        tasks = []

        if self.pubmed_client:
            tasks.append(self._search_pubmed(query))
        if self.ss_client:
            tasks.append(self._search_semantic_scholar(query))
        if self.epmc_client:
            tasks.append(self._search_europe_pmc(query))
        if self.brave_client:
            tasks.append(self._search_brave(query))

        if not tasks:
            logger.warning("검색 소스가 설정되지 않았습니다.")
            return []

        results_per_source = await asyncio.gather(
            *tasks, return_exceptions=True
        )

        all_results: List[SearchResult] = []
        for result in results_per_source:
            if isinstance(result, Exception):
                logger.warning(f"검색 소스 실패: {result}")
                continue
            all_results.extend(result)

        return all_results

    async def _search_pubmed(self, query: str) -> List[SearchResult]:
        """PubMed 검색 (동기 → asyncio.to_thread)"""
        try:
            papers = await asyncio.to_thread(
                self.pubmed_client.search_by_topic,
                query,
                self.limit_per_source,
            )
            return [self._normalize_pubmed(p) for p in papers]
        except Exception as e:
            logger.warning(f"PubMed 검색 실패: {e}")
            return []

    async def _search_semantic_scholar(self, query: str) -> List[SearchResult]:
        """Semantic Scholar 검색"""
        try:
            response = await self.ss_client.search(
                query, limit=self.limit_per_source
            )
            if not response.success:
                return []
            papers = response.data if isinstance(response.data, list) else []
            return [self._normalize_ss(p) for p in papers]
        except Exception as e:
            logger.warning(f"Semantic Scholar 검색 실패: {e}")
            return []

    async def _search_europe_pmc(self, query: str) -> List[SearchResult]:
        """Europe PMC 검색"""
        try:
            response = await self.epmc_client.search(
                query, limit=self.limit_per_source
            )
            if not response.success:
                return []
            papers = response.data if isinstance(response.data, list) else []
            return [self._normalize_epmc(p) for p in papers]
        except Exception as e:
            logger.warning(f"Europe PMC 검색 실패: {e}")
            return []

    async def _search_brave(self, query: str) -> List[SearchResult]:
        """Brave Search 검색 (학술 보완)"""
        try:
            # 학술 검색어 보강
            academic_query = f"{query} research paper pubmed"
            results = await self.brave_client.search(
                academic_query, count=self.limit_per_source
            )
            return [self._normalize_brave(r) for r in results]
        except Exception as e:
            logger.warning(f"Brave Search 실패: {e}")
            return []

    def _normalize_pubmed(self, paper: Dict[str, Any]) -> SearchResult:
        """PubMed 결과 정규화"""
        # pub_date에서 연도 추출
        year = None
        pub_date = paper.get("pub_date", "")
        if pub_date:
            try:
                year = int(pub_date[:4])
            except (ValueError, IndexError):
                pass

        return SearchResult(
            pmid=paper.get("pmid"),
            title=paper.get("title", ""),
            abstract=paper.get("abstract", ""),
            authors=paper.get("authors", []),
            year=year,
            citation_count=0,
            sources=["pubmed"],
            doi=paper.get("doi", ""),
        )

    def _normalize_ss(self, paper: Dict[str, Any]) -> SearchResult:
        """Semantic Scholar 결과 정규화"""
        # externalIds에서 PMID 추출
        pmid = None
        ext_ids = paper.get("externalIds", {})
        if ext_ids:
            pmid = ext_ids.get("PubMed")

        authors = []
        for author in paper.get("authors", []):
            name = author.get("name", "")
            if name:
                authors.append(name)

        return SearchResult(
            pmid=pmid,
            title=paper.get("title", ""),
            abstract=paper.get("abstract", "") or "",
            authors=authors,
            year=paper.get("year"),
            citation_count=paper.get("citationCount", 0) or 0,
            sources=["semantic_scholar"],
            doi=ext_ids.get("DOI") if ext_ids else None,
        )

    def _normalize_epmc(self, paper: Dict[str, Any]) -> SearchResult:
        """Europe PMC 결과 정규화"""
        authors = []
        author_list = paper.get("authorList", {}).get("author", [])
        for author in author_list:
            name = author.get("fullName", "")
            if name:
                authors.append(name)

        year = None
        pub_year = paper.get("pubYear")
        if pub_year:
            try:
                year = int(pub_year)
            except ValueError:
                pass

        return SearchResult(
            pmid=paper.get("pmid"),
            title=paper.get("title", ""),
            abstract=paper.get("abstractText", "") or "",
            authors=authors,
            year=year,
            citation_count=paper.get("citedByCount", 0) or 0,
            sources=["europe_pmc"],
            doi=paper.get("doi"),
        )

    def _normalize_brave(self, result: Dict[str, Any]) -> SearchResult:
        """Brave Search 결과 정규화 (웹 결과 → 학술 형식)"""
        return SearchResult(
            pmid=None,
            title=result.get("title", ""),
            abstract=result.get("description", ""),
            authors=[],
            year=None,
            citation_count=0,
            sources=["brave_search"],
            url=result.get("url"),
        )
