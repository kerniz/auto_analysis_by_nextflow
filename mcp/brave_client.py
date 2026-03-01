"""
Brave Search MCP Client
Brave Search API 클라이언트

Brave Search Web Search API를 통해 학술 검색을 보완하는
범용 웹 검색을 제공합니다.
API 키가 없을 경우 빈 결과를 반환합니다.
"""

import logging
import os
from typing import Any

logger = logging.getLogger(__name__)

try:
    import httpx
    HAS_HTTPX = True
except ImportError:
    HAS_HTTPX = False


class BraveSearchClient:
    """
    Brave Search Web Search API 클라이언트

    BaseClient를 상속받지 않는 독립 클라이언트입니다.
    MCP 도구 호출 패턴에 맞춰 설계되었습니다.
    """

    API_BASE = "https://api.search.brave.com/res/v1/web/search"

    def __init__(
        self,
        api_key: str | None = None,
        timeout: int = 15,
    ):
        self._api_key = api_key or os.environ.get("BRAVE_API_KEY")
        self._timeout = timeout
        self._client: Any | None = None

    def _get_client(self):
        """Lazy httpx client 초기화"""
        if self._client is None and HAS_HTTPX:
            self._client = httpx.AsyncClient(timeout=self._timeout)
        return self._client

    async def search(
        self, query: str, count: int = 10
    ) -> list[dict[str, Any]]:
        """
        Brave 웹 검색 실행

        Args:
            query: 검색 쿼리
            count: 최대 결과 수

        Returns:
            검색 결과 목록 (title, url, description 포함)
        """
        if not self._api_key:
            logger.warning(
                "Brave Search API 키 없음. "
                "BRAVE_API_KEY 환경변수를 설정하세요."
            )
            return []

        if not HAS_HTTPX:
            logger.warning("httpx 미설치, Brave Search 사용 불가")
            return []

        client = self._get_client()
        if not client:
            return []

        try:
            response = await client.get(
                self.API_BASE,
                params={"q": query, "count": count},
                headers={
                    "Accept": "application/json",
                    "Accept-Encoding": "gzip",
                    "X-Subscription-Token": self._api_key,
                },
            )
            response.raise_for_status()
            data = response.json()
            return self._parse_results(data)

        except Exception as e:
            logger.warning(f"Brave Search 실패: {e}")
            return []

    def _parse_results(self, raw: dict[str, Any]) -> list[dict[str, Any]]:
        """API 응답에서 검색 결과 추출"""
        results = []
        web_results = raw.get("web", {}).get("results", [])

        for item in web_results:
            results.append({
                "title": item.get("title", ""),
                "url": item.get("url", ""),
                "description": item.get("description", ""),
                "age": item.get("age", ""),
                "source": "brave_search",
            })

        return results

    async def close(self):
        """리소스 정리"""
        if self._client:
            await self._client.aclose()
            self._client = None
