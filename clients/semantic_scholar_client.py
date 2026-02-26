"""
Semantic Scholar API Client
Semantic Scholar API 클라이언트

Semantic Scholar Graph API v1을 사용하여 논문 검색, 인용 분석,
추천 등의 학술 데이터를 조회합니다.
Uses the Semantic Scholar Graph API v1 for paper search, citation analysis,
recommendations, and influence scoring.
"""

import time
from typing import Any, Dict, List, Optional

from .base import BaseClient, ClientConfig, ClientResponse


# Semantic Scholar Graph API 기본 필드 / Default fields for API requests
_SEARCH_FIELDS = (
    "paperId,title,abstract,citationCount,"
    "influentialCitationCount,year,authors"
)
_DETAIL_FIELDS = (
    "paperId,title,abstract,citationCount,references,citations,"
    "year,authors,venue,externalIds"
)
_CITATION_FIELDS = "paperId,title,year,citationCount"


class SemanticScholarClient(BaseClient):
    """
    Semantic Scholar API 클라이언트

    Semantic Scholar Graph API v1을 통해 학술 논문 메타데이터,
    인용 네트워크, 추천 논문 등을 조회합니다.
    Client for the Semantic Scholar Graph API v1 providing paper search,
    citation networks, recommendations, and influence scoring.
    """

    def __init__(self, config: Optional[ClientConfig] = None):
        """
        Semantic Scholar 클라이언트 초기화
        Initialize the Semantic Scholar client.

        Args:
            config: 클라이언트 설정 (선택사항, 기본 URL 자동 설정)
                    Optional client config. Defaults to the public API endpoint.
        """
        if config is None:
            config = ClientConfig(
                base_url="https://api.semanticscholar.org",
                rate_limit_delay=1.0,  # 공개 API 속도 제한 / Public API rate limit
            )
        super().__init__(config)

    @property
    def name(self) -> str:
        """클라이언트 이름 / Client name"""
        return "semantic_scholar"

    # ------------------------------------------------------------------
    # Core abstract implementations
    # ------------------------------------------------------------------

    async def search(self, query: str, limit: int = 20, **kwargs) -> ClientResponse:
        """
        논문 검색
        Search for papers by keyword query.

        Args:
            query: 검색어 / Search query string
            limit: 최대 결과 수 (기본 20) / Maximum results (default 20)

        Returns:
            ClientResponse: 검색 결과 목록 / List of matching papers
        """
        cache_key = self._cache_key("search", query, str(limit))
        cached = self._get_cached(cache_key)
        if cached is not None:
            return cached

        start = time.time()
        try:
            raw = await self._request_with_retry(
                "GET",
                "/graph/v1/paper/search",
                params={
                    "query": query,
                    "limit": limit,
                    "fields": _SEARCH_FIELDS,
                },
            )
            latency = (time.time() - start) * 1000
            papers = raw.get("data", [])
            resp = self._make_response(
                success=True,
                data=papers,
                query=query,
                latency_ms=latency,
                raw_response=raw,
            )
            self._set_cached(cache_key, resp)
            return resp

        except Exception as e:
            latency = (time.time() - start) * 1000
            return self._make_response(
                success=False,
                data=[],
                query=query,
                latency_ms=latency,
                error_message=f"Semantic Scholar 검색 실패: {e}",
            )

    async def fetch_by_id(self, paper_id: str, **kwargs) -> ClientResponse:
        """
        논문 ID로 상세 정보 조회
        Fetch detailed metadata for a single paper.

        PMID로 조회하려면 'PMID:12345678' 형식을 사용하세요.
        Use the 'PMID:12345678' prefix to look up by PubMed ID.

        Args:
            paper_id: Semantic Scholar paper ID, DOI, 또는 PMID:접두사 형식
                      Semantic Scholar paper ID, DOI, or PMID: prefixed ID

        Returns:
            ClientResponse: 논문 상세 정보 / Detailed paper metadata
        """
        cache_key = self._cache_key("paper", paper_id)
        cached = self._get_cached(cache_key)
        if cached is not None:
            return cached

        start = time.time()
        try:
            raw = await self._request_with_retry(
                "GET",
                f"/graph/v1/paper/{paper_id}",
                params={"fields": _DETAIL_FIELDS},
            )
            latency = (time.time() - start) * 1000
            resp = self._make_response(
                success=True,
                data=raw,
                query=paper_id,
                latency_ms=latency,
                raw_response=raw,
            )
            self._set_cached(cache_key, resp)
            return resp

        except Exception as e:
            latency = (time.time() - start) * 1000
            return self._make_response(
                success=False,
                data={},
                query=paper_id,
                latency_ms=latency,
                error_message=f"논문 조회 실패 ({paper_id}): {e}",
            )

    # ------------------------------------------------------------------
    # Citation & Reference helpers
    # ------------------------------------------------------------------

    async def get_citations(
        self, paper_id: str, limit: int = 100
    ) -> ClientResponse:
        """
        논문의 인용 목록 조회
        Retrieve papers that cite the given paper.

        Args:
            paper_id: 논문 ID / Paper identifier
            limit: 최대 인용 수 (기본 100) / Max citations to return

        Returns:
            ClientResponse: 인용 논문 목록 / List of citing papers
        """
        cache_key = self._cache_key("citations", paper_id, str(limit))
        cached = self._get_cached(cache_key)
        if cached is not None:
            return cached

        start = time.time()
        try:
            raw = await self._request_with_retry(
                "GET",
                f"/graph/v1/paper/{paper_id}/citations",
                params={
                    "fields": _CITATION_FIELDS,
                    "limit": limit,
                },
            )
            latency = (time.time() - start) * 1000
            citations = raw.get("data", [])
            resp = self._make_response(
                success=True,
                data=citations,
                query=f"citations:{paper_id}",
                latency_ms=latency,
                raw_response=raw,
            )
            self._set_cached(cache_key, resp)
            return resp

        except Exception as e:
            latency = (time.time() - start) * 1000
            return self._make_response(
                success=False,
                data=[],
                query=f"citations:{paper_id}",
                latency_ms=latency,
                error_message=f"인용 조회 실패 ({paper_id}): {e}",
            )

    async def get_references(
        self, paper_id: str, limit: int = 100
    ) -> ClientResponse:
        """
        논문의 참고문헌 목록 조회
        Retrieve papers referenced by the given paper.

        Args:
            paper_id: 논문 ID / Paper identifier
            limit: 최대 참고문헌 수 (기본 100) / Max references to return

        Returns:
            ClientResponse: 참고문헌 목록 / List of referenced papers
        """
        cache_key = self._cache_key("references", paper_id, str(limit))
        cached = self._get_cached(cache_key)
        if cached is not None:
            return cached

        start = time.time()
        try:
            raw = await self._request_with_retry(
                "GET",
                f"/graph/v1/paper/{paper_id}/references",
                params={
                    "fields": _CITATION_FIELDS,
                    "limit": limit,
                },
            )
            latency = (time.time() - start) * 1000
            references = raw.get("data", [])
            resp = self._make_response(
                success=True,
                data=references,
                query=f"references:{paper_id}",
                latency_ms=latency,
                raw_response=raw,
            )
            self._set_cached(cache_key, resp)
            return resp

        except Exception as e:
            latency = (time.time() - start) * 1000
            return self._make_response(
                success=False,
                data=[],
                query=f"references:{paper_id}",
                latency_ms=latency,
                error_message=f"참고문헌 조회 실패 ({paper_id}): {e}",
            )

    # ------------------------------------------------------------------
    # Recommendations
    # ------------------------------------------------------------------

    async def get_recommendations(
        self, paper_id: str, limit: int = 10
    ) -> ClientResponse:
        """
        논문 기반 추천
        Get paper recommendations based on a seed paper.

        Args:
            paper_id: 기준 논문 ID / Seed paper identifier
            limit: 최대 추천 수 (기본 10) / Max recommendations

        Returns:
            ClientResponse: 추천 논문 목록 / List of recommended papers
        """
        cache_key = self._cache_key("recommendations", paper_id, str(limit))
        cached = self._get_cached(cache_key)
        if cached is not None:
            return cached

        start = time.time()
        try:
            raw = await self._request_with_retry(
                "POST",
                "/recommendations/v1/papers/",
                json_body={"positivePaperIds": [paper_id]},
                params={
                    "fields": _SEARCH_FIELDS,
                    "limit": limit,
                },
            )
            latency = (time.time() - start) * 1000
            papers = raw.get("recommendedPapers", [])
            resp = self._make_response(
                success=True,
                data=papers,
                query=f"recommendations:{paper_id}",
                latency_ms=latency,
                raw_response=raw,
            )
            self._set_cached(cache_key, resp)
            return resp

        except Exception as e:
            latency = (time.time() - start) * 1000
            return self._make_response(
                success=False,
                data=[],
                query=f"recommendations:{paper_id}",
                latency_ms=latency,
                error_message=f"추천 조회 실패 ({paper_id}): {e}",
            )

    # ------------------------------------------------------------------
    # Influence score
    # ------------------------------------------------------------------

    async def get_influence_score(self, paper_id: str) -> ClientResponse:
        """
        논문 영향력 점수 계산
        Calculate an influence score from citation data.

        영향력 점수는 influentialCitationCount와 총 citationCount의 비율 및
        절대 수치를 기반으로 계산됩니다.
        The influence score is derived from the ratio of influential citations
        to total citations, combined with absolute citation volume.

        Args:
            paper_id: 논문 ID / Paper identifier

        Returns:
            ClientResponse: 영향력 점수 데이터 / Influence score data
        """
        start = time.time()
        try:
            paper_resp = await self.fetch_by_id(paper_id)
            if not paper_resp.success:
                return self._make_response(
                    success=False,
                    data={},
                    query=f"influence:{paper_id}",
                    latency_ms=(time.time() - start) * 1000,
                    error_message=paper_resp.error_message,
                )

            paper = paper_resp.data
            citation_count = paper.get("citationCount", 0) or 0
            influential_count = paper.get("influentialCitationCount", 0) or 0

            # 영향력 비율 / Influential ratio
            influential_ratio = (
                influential_count / citation_count if citation_count > 0 else 0.0
            )

            # 복합 점수 (0-100 스케일) / Composite score on 0-100 scale
            # 인용 수 로그 스케일 + 영향력 비율 가중치
            import math

            citation_score = min(math.log10(citation_count + 1) * 20, 60)
            ratio_score = influential_ratio * 40
            influence_score = round(citation_score + ratio_score, 2)

            result = {
                "paper_id": paper_id,
                "citation_count": citation_count,
                "influential_citation_count": influential_count,
                "influential_ratio": round(influential_ratio, 4),
                "influence_score": influence_score,
                "title": paper.get("title", ""),
            }

            latency = (time.time() - start) * 1000
            return self._make_response(
                success=True,
                data=result,
                query=f"influence:{paper_id}",
                latency_ms=latency,
            )

        except Exception as e:
            latency = (time.time() - start) * 1000
            return self._make_response(
                success=False,
                data={},
                query=f"influence:{paper_id}",
                latency_ms=latency,
                error_message=f"영향력 점수 계산 실패 ({paper_id}): {e}",
            )

    # ------------------------------------------------------------------
    # PMID convenience helper
    # ------------------------------------------------------------------

    async def fetch_by_pmid(self, pmid: str) -> ClientResponse:
        """
        PubMed ID로 논문 조회 (편의 메서드)
        Convenience method to fetch a paper by its PubMed ID.

        Args:
            pmid: PubMed ID (숫자만 또는 'PMID:' 접두사 포함)
                  PubMed ID (digits only, or with 'PMID:' prefix)

        Returns:
            ClientResponse: 논문 상세 정보 / Detailed paper metadata
        """
        if not pmid.startswith("PMID:"):
            pmid = f"PMID:{pmid}"
        return await self.fetch_by_id(pmid)

    # ------------------------------------------------------------------
    # Health check override
    # ------------------------------------------------------------------

    async def health_check(self) -> bool:
        """
        Semantic Scholar API 상태 확인
        Verify the Semantic Scholar API is reachable.

        Returns:
            bool: API 정상 여부 / True if API is responding
        """
        try:
            client = await self._get_client()
            response = await client.get(
                "/graph/v1/paper/search",
                params={"query": "test", "limit": 1, "fields": "paperId"},
            )
            return response.status_code == 200
        except Exception:
            return False
