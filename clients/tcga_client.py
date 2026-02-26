"""
NCI GDC (TCGA) API Client
NCI GDC (TCGA) API 클라이언트

NCI Genomic Data Commons API를 통해 TCGA 및 기타 암 유전체 데이터셋의
프로젝트, 케이스, 파일, 유전자 발현, 임상 데이터를 조회합니다.
Provides access to TCGA and other cancer genomics datasets through the
NCI Genomic Data Commons (GDC) API for projects, cases, files, gene
expression, and clinical data.
"""

import time
from typing import Any, Dict, List, Optional, Union

from .base import BaseClient, ClientConfig, ClientResponse


def _gdc_filter(
    field: str, value: Union[str, List[str]], op: str = "="
) -> Dict[str, Any]:
    """
    GDC 필터 형식 생성 헬퍼
    Build a single GDC filter expression.

    Args:
        field: 필터 대상 필드 / Field to filter on
        value: 필터 값 (문자열 또는 리스트) / Filter value(s)
        op: 연산자 (기본 '=') / Operator (default '=')

    Returns:
        dict: GDC 필터 객체 / GDC filter object
    """
    if isinstance(value, str):
        value = [value]
    return {"op": op, "content": {"field": field, "value": value}}


def _gdc_and(*filters: Dict[str, Any]) -> Dict[str, Any]:
    """
    여러 GDC 필터를 AND로 결합
    Combine multiple GDC filter expressions with AND.

    Args:
        *filters: GDC 필터 객체들 / GDC filter objects

    Returns:
        dict: AND로 결합된 필터 / AND-combined filter
    """
    active = [f for f in filters if f]
    if len(active) == 1:
        return active[0]
    return {"op": "and", "content": list(active)}


class TCGAClient(BaseClient):
    """
    NCI GDC (Genomic Data Commons) API 클라이언트

    TCGA, TARGET 등 NCI 암 유전체 프로젝트 데이터를 GDC REST API v0을 통해
    조회합니다. 프로젝트 검색, 케이스 조회, 파일 검색, 유전자 발현 데이터,
    임상 데이터 등을 지원합니다.

    Client for the NCI Genomic Data Commons REST API providing access to
    TCGA, TARGET, and other NCI cancer genomics project data including
    project search, case lookup, file search, gene expression data,
    and clinical information.
    """

    # GDC 프로젝트 엔드포인트 기본 필드 / Default fields for projects endpoint
    _PROJECT_FIELDS = [
        "project_id",
        "name",
        "disease_type",
        "primary_site",
        "program.name",
        "summary.case_count",
        "summary.file_count",
    ]

    # GDC 케이스 엔드포인트 기본 필드 / Default fields for cases endpoint
    _CASE_FIELDS = [
        "case_id",
        "submitter_id",
        "project.project_id",
        "project.disease_type",
        "primary_site",
        "demographic.gender",
        "demographic.race",
        "diagnoses.primary_diagnosis",
        "diagnoses.tumor_stage",
    ]

    # GDC 파일 엔드포인트 기본 필드 / Default fields for files endpoint
    _FILE_FIELDS = [
        "file_id",
        "file_name",
        "file_size",
        "data_category",
        "data_type",
        "data_format",
        "experimental_strategy",
        "access",
        "cases.case_id",
        "cases.project.project_id",
    ]

    def __init__(self, config: Optional[ClientConfig] = None):
        """
        TCGA/GDC 클라이언트 초기화
        Initialize the GDC API client.

        Args:
            config: 클라이언트 설정 (선택사항, 기본 URL 자동 설정)
                    Optional client config. Defaults to the public GDC endpoint.
        """
        if config is None:
            config = ClientConfig(
                base_url="https://api.gdc.cancer.gov",
                rate_limit_delay=0.3,
                timeout=60,
            )
        super().__init__(config)

    @property
    def name(self) -> str:
        """클라이언트 이름 / Client name"""
        return "tcga_gdc"

    # ------------------------------------------------------------------
    # Core abstract implementations
    # ------------------------------------------------------------------

    async def search(self, query: str, limit: int = 20, **kwargs) -> ClientResponse:
        """
        프로젝트 텍스트 검색 (disease_type 기준)
        Search GDC projects by disease type keyword.

        Args:
            query: 질환 유형 키워드 (예: 'Breast Invasive Carcinoma')
                   Disease type keyword
            limit: 최대 결과 수 / Max results
            **kwargs: primary_site 등 추가 필터 / Additional filters

        Returns:
            ClientResponse: 프로젝트 목록 / List of matching projects
        """
        primary_site = kwargs.get("primary_site")
        return await self.search_projects(
            disease_type=query, primary_site=primary_site, size=limit
        )

    async def fetch_by_id(self, identifier: str, **kwargs) -> ClientResponse:
        """
        케이스 ID로 임상 데이터 조회
        Fetch clinical data for a case by its GDC case UUID.

        Args:
            identifier: GDC 케이스 UUID / GDC case UUID

        Returns:
            ClientResponse: 임상 데이터 / Clinical data
        """
        return await self.get_clinical_data(identifier)

    # ------------------------------------------------------------------
    # Project search
    # ------------------------------------------------------------------

    async def search_projects(
        self,
        disease_type: Optional[str] = None,
        primary_site: Optional[str] = None,
        size: int = 20,
    ) -> ClientResponse:
        """
        GDC 프로젝트 검색
        Search GDC projects by disease type and/or primary site.

        Args:
            disease_type: 질환 유형 (예: 'Breast Invasive Carcinoma')
                          Disease type string
            primary_site: 원발 부위 (예: 'Breast') / Primary site
            size: 최대 결과 수 / Max results

        Returns:
            ClientResponse: 프로젝트 목록 / List of matching projects
        """
        query_desc = f"projects:{disease_type or ''}:{primary_site or ''}"
        cache_key = self._cache_key("projects", disease_type or "", primary_site or "", str(size))
        cached = self._get_cached(cache_key)
        if cached is not None:
            return cached

        start = time.time()
        try:
            # 필터 구성 / Build filters
            filters_list = []
            if disease_type:
                filters_list.append(
                    _gdc_filter("projects.disease_type", disease_type)
                )
            if primary_site:
                filters_list.append(
                    _gdc_filter("projects.primary_site", primary_site)
                )

            body: Dict[str, Any] = {
                "fields": ",".join(self._PROJECT_FIELDS),
                "size": size,
            }
            if filters_list:
                body["filters"] = _gdc_and(*filters_list)

            raw = await self._request_with_retry(
                "POST",
                "/projects",
                json_body=body,
            )
            latency = (time.time() - start) * 1000

            hits = raw.get("data", {}).get("hits", [])
            resp = self._make_response(
                success=True,
                data=hits,
                query=query_desc,
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
                query=query_desc,
                latency_ms=latency,
                error_message=f"GDC 프로젝트 검색 실패: {e}",
            )

    # ------------------------------------------------------------------
    # Case search
    # ------------------------------------------------------------------

    async def search_cases(
        self, project_id: str, size: int = 50
    ) -> ClientResponse:
        """
        프로젝트 내 케이스 검색
        Search cases within a GDC project.

        Args:
            project_id: GDC 프로젝트 ID (예: 'TCGA-BRCA')
                        GDC project ID (e.g., 'TCGA-BRCA')
            size: 최대 결과 수 / Max results

        Returns:
            ClientResponse: 케이스 목록 / List of cases
        """
        cache_key = self._cache_key("cases", project_id, str(size))
        cached = self._get_cached(cache_key)
        if cached is not None:
            return cached

        start = time.time()
        try:
            body: Dict[str, Any] = {
                "filters": _gdc_filter(
                    "cases.project.project_id", project_id
                ),
                "fields": ",".join(self._CASE_FIELDS),
                "size": size,
            }

            raw = await self._request_with_retry(
                "POST",
                "/cases",
                json_body=body,
            )
            latency = (time.time() - start) * 1000

            hits = raw.get("data", {}).get("hits", [])
            resp = self._make_response(
                success=True,
                data=hits,
                query=f"cases:{project_id}",
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
                query=f"cases:{project_id}",
                latency_ms=latency,
                error_message=f"GDC 케이스 검색 실패 ({project_id}): {e}",
            )

    # ------------------------------------------------------------------
    # File search
    # ------------------------------------------------------------------

    async def search_files(
        self,
        case_id: str,
        data_category: str = "Transcriptome Profiling",
        size: int = 50,
    ) -> ClientResponse:
        """
        케이스에 연결된 파일 검색
        Search files associated with a case, filtered by data category.

        Args:
            case_id: GDC 케이스 UUID / GDC case UUID
            data_category: 데이터 카테고리 (기본 'Transcriptome Profiling')
                           Data category filter
            size: 최대 결과 수 / Max results

        Returns:
            ClientResponse: 파일 목록 / List of files
        """
        cache_key = self._cache_key("files", case_id, data_category, str(size))
        cached = self._get_cached(cache_key)
        if cached is not None:
            return cached

        start = time.time()
        try:
            filters = _gdc_and(
                _gdc_filter("cases.case_id", case_id),
                _gdc_filter("files.data_category", data_category),
            )

            body: Dict[str, Any] = {
                "filters": filters,
                "fields": ",".join(self._FILE_FIELDS),
                "size": size,
            }

            raw = await self._request_with_retry(
                "POST",
                "/files",
                json_body=body,
            )
            latency = (time.time() - start) * 1000

            hits = raw.get("data", {}).get("hits", [])
            resp = self._make_response(
                success=True,
                data=hits,
                query=f"files:{case_id}:{data_category}",
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
                query=f"files:{case_id}:{data_category}",
                latency_ms=latency,
                error_message=f"GDC 파일 검색 실패 ({case_id}): {e}",
            )

    # ------------------------------------------------------------------
    # Gene expression data
    # ------------------------------------------------------------------

    async def get_gene_expression(
        self, file_ids: List[str]
    ) -> ClientResponse:
        """
        파일 ID 목록으로 유전자 발현 데이터 다운로드 요청
        Request gene expression data download for given file IDs.

        GDC data endpoint에 POST 요청을 보내 데이터를 요청합니다.
        실제 대용량 데이터 다운로드는 별도 처리가 필요합니다.
        Sends a POST request to the GDC data endpoint. Actual large-scale
        downloads require separate handling (streaming, etc.).

        Args:
            file_ids: GDC 파일 UUID 목록 / List of GDC file UUIDs

        Returns:
            ClientResponse: 다운로드 응답 메타데이터 / Download response metadata
        """
        if not file_ids:
            return self._make_response(
                success=False,
                data={},
                query="gene_expression:[]",
                latency_ms=0.0,
                error_message="파일 ID 목록이 비어 있습니다 / Empty file ID list",
            )

        start = time.time()
        try:
            client = await self._get_client()

            # 속도 제한 / Rate limit
            import asyncio
            if self._last_request_time is not None:
                elapsed = time.time() - self._last_request_time
                if elapsed < self.config.rate_limit_delay:
                    await asyncio.sleep(self.config.rate_limit_delay - elapsed)
            self._last_request_time = time.time()

            # GDC data endpoint는 tar.gz를 반환하므로 메타데이터만 수집
            # The /data endpoint returns tar.gz; we collect metadata only
            response = await client.post(
                "/data",
                json={"ids": file_ids},
                headers={"Accept": "application/json"},
            )
            latency = (time.time() - start) * 1000

            # 성공 여부 확인 / Check success
            if response.status_code == 200:
                # JSON 응답 또는 바이너리 데이터
                content_type = response.headers.get("content-type", "")
                if "application/json" in content_type:
                    data = response.json()
                else:
                    data = {
                        "content_type": content_type,
                        "content_length": len(response.content),
                        "file_ids": file_ids,
                        "message": "바이너리 데이터 수신됨. 별도 저장 필요 / Binary data received. Requires separate storage.",
                    }

                return self._make_response(
                    success=True,
                    data=data,
                    query=f"gene_expression:{len(file_ids)}_files",
                    latency_ms=latency,
                )
            else:
                error_text = response.text[:500] if response.text else ""
                return self._make_response(
                    success=False,
                    data={},
                    query=f"gene_expression:{len(file_ids)}_files",
                    latency_ms=latency,
                    error_message=f"HTTP {response.status_code}: {error_text}",
                )

        except Exception as e:
            latency = (time.time() - start) * 1000
            return self._make_response(
                success=False,
                data={},
                query=f"gene_expression:{len(file_ids)}_files",
                latency_ms=latency,
                error_message=f"유전자 발현 데이터 요청 실패: {e}",
            )

    # ------------------------------------------------------------------
    # Clinical data
    # ------------------------------------------------------------------

    async def get_clinical_data(self, case_id: str) -> ClientResponse:
        """
        케이스의 임상 데이터 조회
        Retrieve clinical data (diagnoses, exposures) for a given case.

        Args:
            case_id: GDC 케이스 UUID / GDC case UUID

        Returns:
            ClientResponse: 임상 데이터 (진단, 노출 정보 포함) / Clinical data
        """
        cache_key = self._cache_key("clinical", case_id)
        cached = self._get_cached(cache_key)
        if cached is not None:
            return cached

        start = time.time()
        try:
            raw = await self._request_with_retry(
                "GET",
                f"/cases/{case_id}",
                params={"expand": "diagnoses,exposures"},
            )
            latency = (time.time() - start) * 1000

            # GDC는 data 래퍼 사용 / GDC uses data wrapper
            case_data = raw.get("data", raw)

            resp = self._make_response(
                success=True,
                data=case_data,
                query=f"clinical:{case_id}",
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
                query=f"clinical:{case_id}",
                latency_ms=latency,
                error_message=f"임상 데이터 조회 실패 ({case_id}): {e}",
            )

    # ------------------------------------------------------------------
    # Health check override
    # ------------------------------------------------------------------

    async def health_check(self) -> bool:
        """
        GDC API 상태 확인
        Verify the GDC API is reachable.

        Returns:
            bool: API 정상 여부 / True if API is responding
        """
        try:
            client = await self._get_client()
            response = await client.get("/status")
            if response.status_code == 200:
                data = response.json()
                return data.get("status", "") == "OK"
            return False
        except Exception:
            return False
