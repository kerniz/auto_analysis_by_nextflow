"""
Europe PMC REST API Client
Europe PMC REST API 클라이언트

Europe PMC 웹서비스를 통해 생의학 문헌 검색, 인용/참고문헌 조회,
텍스트 마이닝 어노테이션 등을 수행합니다.
Provides biomedical literature search, citation/reference retrieval,
and text-mined annotation access via the Europe PMC REST API.
"""

import time

from .base import BaseClient, ClientConfig, ClientResponse


class EuropePMCClient(BaseClient):
    """
    Europe PMC REST API 클라이언트

    Europe PMC 웹서비스(https://www.ebi.ac.uk/europepmc/webservices/rest)를 통해
    생의학 문헌을 검색하고 메타데이터, 인용 정보, 텍스트 마이닝 어노테이션을 조회합니다.
    Client for the Europe PMC REST API providing biomedical literature search,
    citation/reference retrieval, and text-mined annotation access.
    """

    def __init__(self, config: ClientConfig | None = None):
        """
        Europe PMC 클라이언트 초기화
        Initialize the Europe PMC client.

        Args:
            config: 클라이언트 설정 (선택사항, 기본 URL 자동 설정)
                    Optional client config. Defaults to the public REST endpoint.
        """
        if config is None:
            config = ClientConfig(
                base_url="https://www.ebi.ac.uk/europepmc/webservices/rest",
                rate_limit_delay=0.35,
            )
        super().__init__(config)

    @property
    def name(self) -> str:
        """클라이언트 이름 / Client name"""
        return "europe_pmc"

    # ------------------------------------------------------------------
    # Core abstract implementations
    # ------------------------------------------------------------------

    async def search(self, query: str, limit: int = 25, **kwargs) -> ClientResponse:
        """
        문헌 검색
        Search the Europe PMC literature database.

        Args:
            query: 검색 쿼리 (Europe PMC 구문 지원)
                   Search query (supports Europe PMC syntax)
            limit: 최대 결과 수 (기본 25) / Maximum results (default 25)

        Returns:
            ClientResponse: 검색 결과 목록 / List of matching articles
        """
        cache_key = self._cache_key("search", query, str(limit))
        cached = self._get_cached(cache_key)
        if cached is not None:
            return cached

        start = time.time()
        try:
            raw = await self._request_with_retry(
                "GET",
                "/search",
                params={
                    "query": query,
                    "format": "json",
                    "pageSize": limit,
                    "resultType": "core",
                },
            )
            latency = (time.time() - start) * 1000

            result_list = raw.get("resultList", {}).get("result", [])
            resp = self._make_response(
                success=True,
                data=result_list,
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
                error_message=f"Europe PMC 검색 실패: {e}",
            )

    async def fetch_by_id(self, pmid: str, **kwargs) -> ClientResponse:
        """
        PubMed ID로 논문 상세 조회
        Fetch detailed article metadata by PubMed ID.

        Args:
            pmid: PubMed ID (숫자 문자열) / PubMed identifier

        Returns:
            ClientResponse: 논문 상세 정보 / Detailed article metadata
        """
        cache_key = self._cache_key("article", pmid)
        cached = self._get_cached(cache_key)
        if cached is not None:
            return cached

        start = time.time()
        try:
            raw = await self._request_with_retry(
                "GET",
                "/search",
                params={
                    "query": f"EXT_ID:{pmid} AND SRC:MED",
                    "format": "json",
                    "resultType": "core",
                },
            )
            latency = (time.time() - start) * 1000

            results = raw.get("resultList", {}).get("result", [])
            article = results[0] if results else {}

            resp = self._make_response(
                success=bool(article),
                data=article,
                query=f"PMID:{pmid}",
                latency_ms=latency,
                raw_response=raw,
                error_message="" if article else f"PMID {pmid}에 해당하는 논문을 찾을 수 없습니다",
            )
            self._set_cached(cache_key, resp)
            return resp

        except Exception as e:
            latency = (time.time() - start) * 1000
            return self._make_response(
                success=False,
                data={},
                query=f"PMID:{pmid}",
                latency_ms=latency,
                error_message=f"논문 조회 실패 (PMID:{pmid}): {e}",
            )

    # ------------------------------------------------------------------
    # Citations & References
    # ------------------------------------------------------------------

    async def get_citations(self, pmid: str, page: int = 1, page_size: int = 100) -> ClientResponse:
        """
        논문의 인용 목록 조회
        Retrieve articles that cite the given paper.

        Args:
            pmid: PubMed ID
            page: 페이지 번호 (기본 1) / Page number (default 1)
            page_size: 페이지 크기 (기본 100) / Page size (default 100)

        Returns:
            ClientResponse: 인용 논문 목록 / List of citing articles
        """
        cache_key = self._cache_key("citations", pmid, str(page), str(page_size))
        cached = self._get_cached(cache_key)
        if cached is not None:
            return cached

        start = time.time()
        try:
            raw = await self._request_with_retry(
                "GET",
                f"/MED/{pmid}/citations",
                params={
                    "format": "json",
                    "page": page,
                    "pageSize": page_size,
                },
            )
            latency = (time.time() - start) * 1000

            citations = raw.get("citationList", {}).get("citation", [])
            resp = self._make_response(
                success=True,
                data=citations,
                query=f"citations:{pmid}",
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
                query=f"citations:{pmid}",
                latency_ms=latency,
                error_message=f"인용 조회 실패 (PMID:{pmid}): {e}",
            )

    async def get_references(self, pmid: str, page: int = 1, page_size: int = 100) -> ClientResponse:
        """
        논문의 참고문헌 목록 조회
        Retrieve references cited by the given paper.

        Args:
            pmid: PubMed ID
            page: 페이지 번호 (기본 1) / Page number (default 1)
            page_size: 페이지 크기 (기본 100) / Page size (default 100)

        Returns:
            ClientResponse: 참고문헌 목록 / List of referenced articles
        """
        cache_key = self._cache_key("references", pmid, str(page), str(page_size))
        cached = self._get_cached(cache_key)
        if cached is not None:
            return cached

        start = time.time()
        try:
            raw = await self._request_with_retry(
                "GET",
                f"/MED/{pmid}/references",
                params={
                    "format": "json",
                    "page": page,
                    "pageSize": page_size,
                },
            )
            latency = (time.time() - start) * 1000

            references = raw.get("referenceList", {}).get("reference", [])
            resp = self._make_response(
                success=True,
                data=references,
                query=f"references:{pmid}",
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
                query=f"references:{pmid}",
                latency_ms=latency,
                error_message=f"참고문헌 조회 실패 (PMID:{pmid}): {e}",
            )

    # ------------------------------------------------------------------
    # Text-mined annotations
    # ------------------------------------------------------------------

    async def get_text_mined_terms(self, pmcid: str) -> ClientResponse:
        """
        텍스트 마이닝 어노테이션 조회
        Retrieve text-mined annotations for an article identified by PMC ID.

        Europe PMC annotations API를 사용하여 유전자, 질병, 화합물 등
        자동 추출된 생의학 개체를 반환합니다.
        Returns automatically extracted biomedical entities (genes, diseases,
        chemicals, etc.) using the Europe PMC annotations API.

        Args:
            pmcid: PubMed Central ID (숫자만, 'PMC' 접두사 없이)
                   PMC identifier (digits only, without 'PMC' prefix)

        Returns:
            ClientResponse: 텍스트 마이닝 어노테이션 목록 / Text-mined annotation list
        """
        # PMC 접두사 정규화 / Normalize PMC prefix
        clean_pmcid = pmcid.replace("PMC", "").strip()

        cache_key = self._cache_key("annotations", clean_pmcid)
        cached = self._get_cached(cache_key)
        if cached is not None:
            return cached

        start = time.time()
        try:
            # annotations API는 별도 엔드포인트 / Annotations API has a separate endpoint
            client = await self._get_client()
            response = await client.get(
                "/annotations_api/annotationsByArticleIds",
                params={
                    "articleIds": f"PMC:{clean_pmcid}",
                    "format": "JSON",
                },
            )
            response.raise_for_status()
            latency = (time.time() - start) * 1000

            raw = response.json() if response.content else []

            # 응답이 리스트인 경우 처리 / Handle list response
            annotations = raw if isinstance(raw, list) else raw.get("annotations", [])

            resp = self._make_response(
                success=True,
                data=annotations,
                query=f"annotations:PMC{clean_pmcid}",
                latency_ms=latency,
                raw_response={"annotations": annotations},
            )
            self._set_cached(cache_key, resp)
            return resp

        except Exception as e:
            latency = (time.time() - start) * 1000
            return self._make_response(
                success=False,
                data=[],
                query=f"annotations:PMC{clean_pmcid}",
                latency_ms=latency,
                error_message=f"텍스트 마이닝 어노테이션 조회 실패 (PMC{clean_pmcid}): {e}",
            )

    # ------------------------------------------------------------------
    # Health check override
    # ------------------------------------------------------------------

    async def health_check(self) -> bool:
        """
        Europe PMC API 상태 확인
        Verify the Europe PMC API is reachable.

        Returns:
            bool: API 정상 여부 / True if API is responding
        """
        try:
            client = await self._get_client()
            response = await client.get(
                "/search",
                params={"query": "test", "format": "json", "pageSize": 1},
            )
            return response.status_code == 200
        except Exception:
            return False
