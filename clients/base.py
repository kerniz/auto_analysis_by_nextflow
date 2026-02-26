"""
Data Source Client Abstract Base Class
데이터 소스 클라이언트 추상 기본 클래스

외부 API(Semantic Scholar, Europe PMC, TCGA 등)에 접근하기 위한 공통 인터페이스를 정의합니다.
All external API clients must inherit from BaseClient and implement the abstract methods.
"""

import asyncio
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional


@dataclass
class ClientConfig:
    """
    클라이언트 설정 데이터 클래스
    Client configuration dataclass for external API connections.
    """
    base_url: str
    timeout: int = 30
    max_retries: int = 3
    rate_limit_delay: float = 0.5
    cache_enabled: bool = True
    api_key: Optional[str] = None
    extra_headers: Dict[str, str] = field(default_factory=dict)


@dataclass
class ClientResponse:
    """
    클라이언트 응답 표준화 구조
    Standardized response structure returned by all client methods.
    """
    success: bool
    data: Any
    source: str
    query: str
    error_message: str = ""
    latency_ms: float = 0.0
    timestamp: datetime = field(default_factory=datetime.now)
    raw_response: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """
        응답을 딕셔너리로 변환
        Convert response to a serializable dictionary.
        """
        return {
            "success": self.success,
            "data": self.data,
            "source": self.source,
            "query": self.query,
            "error_message": self.error_message,
            "latency_ms": self.latency_ms,
            "timestamp": self.timestamp.isoformat(),
        }


class BaseClient(ABC):
    """
    데이터 소스 클라이언트 추상 기본 클래스

    모든 외부 API 클라이언트(Semantic Scholar, Europe PMC, TCGA 등)는
    이 클래스를 상속받아 구현해야 합니다.
    All external API clients (Semantic Scholar, Europe PMC, TCGA, etc.)
    must inherit from this class and implement the abstract methods.
    """

    def __init__(self, config: ClientConfig):
        """
        기본 클라이언트 초기화
        Initialize base client with configuration.

        Args:
            config: 클라이언트 설정 / Client configuration
        """
        self.config = config
        self._client = None
        self._request_count: int = 0
        self._error_count: int = 0
        self._total_latency_ms: float = 0.0
        self._last_request_time: Optional[float] = None
        self._cache: Dict[str, ClientResponse] = {}

    # ------------------------------------------------------------------
    # Abstract properties & methods
    # ------------------------------------------------------------------

    @property
    @abstractmethod
    def name(self) -> str:
        """
        클라이언트 이름 (예: 'semantic_scholar', 'europe_pmc', 'tcga')
        Unique name identifying this client.
        """
        pass

    @abstractmethod
    async def search(self, query: str, limit: int = 20, **kwargs) -> ClientResponse:
        """
        검색 수행
        Execute a search query against the data source.

        Args:
            query: 검색 쿼리 / Search query string
            limit: 최대 결과 수 / Maximum number of results
            **kwargs: 추가 매개변수 / Additional parameters

        Returns:
            ClientResponse: 표준화된 응답 / Standardized response
        """
        pass

    @abstractmethod
    async def fetch_by_id(self, identifier: str, **kwargs) -> ClientResponse:
        """
        고유 식별자로 데이터 조회
        Fetch a single record by its unique identifier.

        Args:
            identifier: 고유 식별자 (PMID, DOI 등) / Unique identifier
            **kwargs: 추가 매개변수 / Additional parameters

        Returns:
            ClientResponse: 표준화된 응답 / Standardized response
        """
        pass

    # ------------------------------------------------------------------
    # Concrete methods
    # ------------------------------------------------------------------

    async def _get_client(self):
        """
        비동기 HTTP 클라이언트를 지연 초기화하여 반환
        Lazily initialize and return the async HTTP client.

        Returns:
            httpx.AsyncClient: 비동기 HTTP 클라이언트 인스턴스
        """
        import httpx

        if self._client is None or self._client.is_closed:
            headers = {"Accept": "application/json"}
            if self.config.api_key:
                headers["x-api-key"] = self.config.api_key
            if self.config.extra_headers:
                headers.update(self.config.extra_headers)

            self._client = httpx.AsyncClient(
                base_url=self.config.base_url,
                timeout=self.config.timeout,
                headers=headers,
                follow_redirects=True,
            )
        return self._client

    async def _request_with_retry(
        self,
        method: str,
        url: str,
        *,
        params: Optional[Dict[str, Any]] = None,
        json_body: Optional[Dict[str, Any]] = None,
        extra_headers: Optional[Dict[str, str]] = None,
    ) -> Dict[str, Any]:
        """
        재시도 로직과 속도 제한이 포함된 HTTP 요청
        Execute an HTTP request with automatic retry and rate limiting.

        Args:
            method: HTTP 메서드 ('GET' 또는 'POST') / HTTP method
            url: 요청 경로 (base_url에 상대적) / Request path relative to base_url
            params: 쿼리 파라미터 / Query parameters
            json_body: JSON 요청 본문 / JSON request body
            extra_headers: 추가 헤더 / Additional headers for this request

        Returns:
            dict: 파싱된 JSON 응답 / Parsed JSON response body

        Raises:
            Exception: 모든 재시도 실패 시 / When all retries are exhausted
        """
        last_error: Optional[Exception] = None
        client = await self._get_client()

        for attempt in range(self.config.max_retries):
            try:
                # 속도 제한 준수 / Respect rate limit
                if self._last_request_time is not None:
                    elapsed = time.time() - self._last_request_time
                    if elapsed < self.config.rate_limit_delay:
                        await asyncio.sleep(self.config.rate_limit_delay - elapsed)

                self._last_request_time = time.time()

                kwargs: Dict[str, Any] = {}
                if params:
                    kwargs["params"] = params
                if json_body:
                    kwargs["json"] = json_body
                if extra_headers:
                    kwargs["headers"] = extra_headers

                if method.upper() == "GET":
                    response = await client.get(url, **kwargs)
                elif method.upper() == "POST":
                    response = await client.post(url, **kwargs)
                else:
                    raise ValueError(f"지원하지 않는 HTTP 메서드: {method}")

                response.raise_for_status()

                # 응답이 비어있는 경우 처리 / Handle empty responses
                if response.status_code == 204 or not response.content:
                    return {}

                # Content-Type에 따른 파싱 / Parse based on content type
                content_type = response.headers.get("content-type", "")
                if "application/json" in content_type:
                    return response.json()
                else:
                    # 텍스트 응답 / Text response (e.g. KEGG)
                    return {"_text": response.text}

            except Exception as e:
                last_error = e
                self._error_count += 1

                if attempt < self.config.max_retries - 1:
                    # 지수 백오프 / Exponential backoff
                    wait_time = (2 ** attempt) * self.config.rate_limit_delay
                    await asyncio.sleep(wait_time)

        raise last_error  # type: ignore[misc]

    async def health_check(self) -> bool:
        """
        서비스 건강 상태 확인
        Check whether the external service is reachable and healthy.

        Returns:
            bool: 서비스가 정상이면 True / True if service is healthy
        """
        try:
            client = await self._get_client()
            response = await client.get("/")
            return response.status_code < 500
        except Exception:
            return False

    async def close(self) -> None:
        """
        클라이언트 리소스 정리
        Release all resources held by the client (HTTP connections, caches).
        """
        if self._client and not self._client.is_closed:
            await self._client.aclose()
            self._client = None
        self._cache.clear()

    def get_metrics(self) -> Dict[str, Any]:
        """
        클라이언트 메트릭 반환
        Return operational metrics for monitoring and debugging.

        Returns:
            dict: 요청 수, 에러 수, 평균 응답 시간 등 / Request count, error count, avg latency, etc.
        """
        avg_latency = (
            self._total_latency_ms / self._request_count
            if self._request_count > 0
            else 0.0
        )
        return {
            "name": self.name,
            "request_count": self._request_count,
            "error_count": self._error_count,
            "avg_latency_ms": round(avg_latency, 2),
            "cache_size": len(self._cache),
            "cache_enabled": self.config.cache_enabled,
        }

    def _cache_key(self, *parts: str) -> str:
        """
        캐시 키 생성
        Build a deterministic cache key from parts.
        """
        return "|".join(parts)

    def _get_cached(self, key: str) -> Optional[ClientResponse]:
        """
        캐시에서 응답 조회
        Retrieve a cached response if caching is enabled.
        """
        if self.config.cache_enabled and key in self._cache:
            return self._cache[key]
        return None

    def _set_cached(self, key: str, response: ClientResponse) -> None:
        """
        응답을 캐시에 저장
        Store a response in the cache if caching is enabled.
        """
        if self.config.cache_enabled and response.success:
            self._cache[key] = response

    def _make_response(
        self,
        *,
        success: bool,
        data: Any,
        query: str,
        latency_ms: float,
        error_message: str = "",
        raw_response: Optional[Dict[str, Any]] = None,
    ) -> ClientResponse:
        """
        표준 ClientResponse 생성 헬퍼
        Helper to build a ClientResponse with common fields pre-filled.
        """
        self._request_count += 1
        self._total_latency_ms += latency_ms
        return ClientResponse(
            success=success,
            data=data,
            source=self.name,
            query=query,
            error_message=error_message,
            latency_ms=latency_ms,
            raw_response=raw_response or {},
        )
