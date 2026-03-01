"""
Multi-API Annotation Client
다중 API 어노테이션 클라이언트

Gene Ontology (QuickGO), KEGG, Ensembl REST API를 통합하여
유전자 기능 어노테이션, 경로 분석, 유전자 정보를 조회합니다.
Integrates Gene Ontology (QuickGO), KEGG, and Ensembl REST APIs
for functional annotation, pathway analysis, and gene information.
"""

import asyncio
import time
from typing import Any

import httpx

from .base import BaseClient, ClientConfig, ClientResponse


class AnnotationClient(BaseClient):
    """
    다중 API 어노테이션 클라이언트

    세 가지 외부 서비스를 통합하여 유전자 기능 어노테이션을 제공합니다:
    - Gene Ontology (QuickGO): GO term 어노테이션
    - KEGG: 대사 경로 및 신호전달 경로
    - Ensembl: 유전자 정보, 심볼 조회, 오르톨로그

    Unified annotation client combining three external services:
    - Gene Ontology (QuickGO): GO term annotations
    - KEGG: Metabolic and signaling pathways
    - Ensembl: Gene information, symbol lookup, orthologs
    """

    # 각 API 기본 URL / Base URLs for each API
    QUICKGO_BASE = "https://www.ebi.ac.uk/QuickGO/services"
    KEGG_BASE = "https://rest.kegg.jp"
    ENSEMBL_BASE = "https://rest.ensembl.org"

    def __init__(self, config: ClientConfig | None = None):
        """
        어노테이션 클라이언트 초기화
        Initialize the annotation client.

        내부적으로 세 개의 httpx.AsyncClient를 별도로 관리합니다.
        Internally manages three separate httpx.AsyncClient instances.

        Args:
            config: 공통 클라이언트 설정 (선택사항)
                    Shared client config. base_url is used for QuickGO by default.
        """
        if config is None:
            config = ClientConfig(
                base_url=self.QUICKGO_BASE,
                rate_limit_delay=0.35,
            )
        super().__init__(config)
        # 추가 클라이언트 / Additional clients for KEGG and Ensembl
        self._kegg_client: httpx.AsyncClient | None = None
        self._ensembl_client: httpx.AsyncClient | None = None

    @property
    def name(self) -> str:
        """클라이언트 이름 / Client name"""
        return "annotation"

    # ------------------------------------------------------------------
    # Internal client management
    # ------------------------------------------------------------------

    async def _get_kegg_client(self) -> httpx.AsyncClient:
        """
        KEGG 전용 HTTP 클라이언트 반환
        Return (or lazily create) the KEGG-specific HTTP client.
        """
        if self._kegg_client is None or self._kegg_client.is_closed:
            self._kegg_client = httpx.AsyncClient(
                base_url=self.KEGG_BASE,
                timeout=self.config.timeout,
                headers={"Accept": "text/plain"},
                follow_redirects=True,
            )
        return self._kegg_client

    async def _get_ensembl_client(self) -> httpx.AsyncClient:
        """
        Ensembl 전용 HTTP 클라이언트 반환
        Return (or lazily create) the Ensembl-specific HTTP client.
        """
        if self._ensembl_client is None or self._ensembl_client.is_closed:
            self._ensembl_client = httpx.AsyncClient(
                base_url=self.ENSEMBL_BASE,
                timeout=self.config.timeout,
                headers={
                    "Accept": "application/json",
                    "Content-Type": "application/json",
                },
                follow_redirects=True,
            )
        return self._ensembl_client

    async def close(self) -> None:
        """
        모든 HTTP 클라이언트 리소스 정리
        Release all HTTP client resources.
        """
        await super().close()
        if self._kegg_client and not self._kegg_client.is_closed:
            await self._kegg_client.aclose()
            self._kegg_client = None
        if self._ensembl_client and not self._ensembl_client.is_closed:
            await self._ensembl_client.aclose()
            self._ensembl_client = None

    # ------------------------------------------------------------------
    # Core abstract implementations
    # ------------------------------------------------------------------

    async def search(self, query: str, limit: int = 20, **kwargs) -> ClientResponse:
        """
        통합 검색 (Ensembl 심볼 검색으로 위임)
        Unified search delegating to Ensembl symbol lookup.

        Args:
            query: 유전자 심볼 또는 ID / Gene symbol or identifier
            limit: 사용되지 않음 (API 제약) / Not used (API constraint)
            **kwargs: species 등 추가 파라미터 / Additional params like species

        Returns:
            ClientResponse: 유전자 정보 / Gene information
        """
        species = kwargs.get("species", "homo_sapiens")
        return await self.get_gene_by_symbol(query, species=species)

    async def fetch_by_id(self, identifier: str, **kwargs) -> ClientResponse:
        """
        Ensembl ID로 유전자 정보 조회
        Fetch gene information by Ensembl stable ID.

        Args:
            identifier: Ensembl 안정 ID (예: ENSG00000141510)
                        Ensembl stable ID (e.g., ENSG00000141510)

        Returns:
            ClientResponse: 유전자 상세 정보 / Detailed gene info
        """
        return await self.get_gene_info(identifier)

    # ==================================================================
    # Gene Ontology (QuickGO) methods
    # ==================================================================

    async def get_go_terms(self, gene_id: str, limit: int = 50) -> ClientResponse:
        """
        유전자의 GO term 어노테이션 조회
        Retrieve Gene Ontology annotations for a gene product.

        QuickGO annotation search API를 사용합니다.
        Uses the QuickGO annotation search API.

        Args:
            gene_id: 유전자 산물 ID (예: UniProt ID 'P04637')
                     Gene product ID (e.g., UniProt accession 'P04637')
            limit: 최대 결과 수 (기본 50) / Max annotations (default 50)

        Returns:
            ClientResponse: GO 어노테이션 목록 / List of GO annotations
        """
        cache_key = self._cache_key("go_terms", gene_id, str(limit))
        cached = self._get_cached(cache_key)
        if cached is not None:
            return cached

        start = time.time()
        try:
            raw = await self._request_with_retry(
                "GET",
                "/annotation/search",
                params={
                    "geneProductId": gene_id,
                    "limit": limit,
                },
            )
            latency = (time.time() - start) * 1000

            annotations = raw.get("results", [])
            resp = self._make_response(
                success=True,
                data=annotations,
                query=f"go_terms:{gene_id}",
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
                query=f"go_terms:{gene_id}",
                latency_ms=latency,
                error_message=f"GO term 조회 실패 ({gene_id}): {e}",
            )

    async def get_go_enrichment(self, gene_list: list[str]) -> ClientResponse:
        """
        유전자 목록의 GO term 일괄 조회 (배치)
        Batch lookup of GO annotations for a list of gene product IDs.

        각 유전자에 대해 개별 요청을 병렬로 수행하고 결과를 통합합니다.
        Performs parallel requests for each gene and aggregates the results.

        Args:
            gene_list: 유전자 산물 ID 목록 / List of gene product IDs

        Returns:
            ClientResponse: 유전자별 GO 어노테이션 통합 결과 / Aggregated GO annotations
        """
        start = time.time()
        try:
            tasks = [self.get_go_terms(gene_id, limit=20) for gene_id in gene_list]
            results = await asyncio.gather(*tasks, return_exceptions=True)

            enrichment: dict[str, Any] = {}
            go_term_counts: dict[str, int] = {}

            for gene_id, result in zip(gene_list, results):
                if isinstance(result, Exception):
                    enrichment[gene_id] = {"error": str(result)}
                    continue

                if result.success:
                    enrichment[gene_id] = result.data
                    # GO term 빈도 집계 / Count GO term frequencies
                    for ann in result.data:
                        go_id = ann.get("goId", "")
                        if go_id:
                            go_term_counts[go_id] = go_term_counts.get(go_id, 0) + 1
                else:
                    enrichment[gene_id] = {"error": result.error_message}

            # 빈도순 정렬 / Sort by frequency
            sorted_terms = sorted(
                go_term_counts.items(), key=lambda x: x[1], reverse=True
            )

            latency = (time.time() - start) * 1000
            return self._make_response(
                success=True,
                data={
                    "gene_annotations": enrichment,
                    "enriched_terms": sorted_terms[:50],
                    "total_genes_queried": len(gene_list),
                },
                query=f"go_enrichment:{len(gene_list)}_genes",
                latency_ms=latency,
            )

        except Exception as e:
            latency = (time.time() - start) * 1000
            return self._make_response(
                success=False,
                data={},
                query=f"go_enrichment:{len(gene_list)}_genes",
                latency_ms=latency,
                error_message=f"GO enrichment 조회 실패: {e}",
            )

    # ==================================================================
    # KEGG methods
    # ==================================================================

    async def get_kegg_pathways(
        self, gene_id: str, organism: str = "hsa"
    ) -> ClientResponse:
        """
        유전자의 KEGG 경로 조회
        Retrieve KEGG pathways associated with a gene.

        Args:
            gene_id: 유전자 ID (예: '7157' for TP53) / Gene ID
            organism: 생물종 코드 (기본 'hsa' = 인간) / Organism code (default 'hsa')

        Returns:
            ClientResponse: KEGG 경로 목록 / List of KEGG pathways
        """
        cache_key = self._cache_key("kegg_pathways", organism, gene_id)
        cached = self._get_cached(cache_key)
        if cached is not None:
            return cached

        start = time.time()
        try:
            kegg = await self._get_kegg_client()

            # 속도 제한 / Rate limit
            if self._last_request_time is not None:
                elapsed = time.time() - self._last_request_time
                if elapsed < self.config.rate_limit_delay:
                    await asyncio.sleep(self.config.rate_limit_delay - elapsed)
            self._last_request_time = time.time()

            response = await kegg.get(f"/link/pathway/{organism}:{gene_id}")
            response.raise_for_status()
            latency = (time.time() - start) * 1000

            # KEGG 탭 구분 텍스트 파싱 / Parse KEGG tab-delimited text
            pathways = []
            text = response.text.strip()
            if text:
                for line in text.split("\n"):
                    parts = line.strip().split("\t")
                    if len(parts) >= 2:
                        pathways.append({
                            "gene": parts[0].strip(),
                            "pathway_id": parts[1].strip(),
                        })

            resp = self._make_response(
                success=True,
                data=pathways,
                query=f"kegg_pathways:{organism}:{gene_id}",
                latency_ms=latency,
                raw_response={"_text": text},
            )
            self._request_count += 1  # 별도 클라이언트이므로 수동 증가 필요 없음 (make_response에서 처리)
            self._set_cached(cache_key, resp)
            return resp

        except Exception as e:
            latency = (time.time() - start) * 1000
            return self._make_response(
                success=False,
                data=[],
                query=f"kegg_pathways:{organism}:{gene_id}",
                latency_ms=latency,
                error_message=f"KEGG 경로 조회 실패 ({organism}:{gene_id}): {e}",
            )

    async def get_kegg_pathway_info(self, pathway_id: str) -> ClientResponse:
        """
        KEGG 경로 상세 정보 조회
        Retrieve detailed information about a KEGG pathway.

        Args:
            pathway_id: KEGG 경로 ID (예: 'hsa04110') / KEGG pathway ID

        Returns:
            ClientResponse: 경로 상세 정보 / Pathway detail information
        """
        cache_key = self._cache_key("kegg_info", pathway_id)
        cached = self._get_cached(cache_key)
        if cached is not None:
            return cached

        start = time.time()
        try:
            kegg = await self._get_kegg_client()

            if self._last_request_time is not None:
                elapsed = time.time() - self._last_request_time
                if elapsed < self.config.rate_limit_delay:
                    await asyncio.sleep(self.config.rate_limit_delay - elapsed)
            self._last_request_time = time.time()

            response = await kegg.get(f"/get/{pathway_id}")
            response.raise_for_status()
            latency = (time.time() - start) * 1000

            # KEGG flat-file 형식 파싱 / Parse KEGG flat-file format
            text = response.text
            info = self._parse_kegg_flat(text)
            info["pathway_id"] = pathway_id

            resp = self._make_response(
                success=True,
                data=info,
                query=f"kegg_info:{pathway_id}",
                latency_ms=latency,
                raw_response={"_text": text},
            )
            self._set_cached(cache_key, resp)
            return resp

        except Exception as e:
            latency = (time.time() - start) * 1000
            return self._make_response(
                success=False,
                data={},
                query=f"kegg_info:{pathway_id}",
                latency_ms=latency,
                error_message=f"KEGG 경로 정보 조회 실패 ({pathway_id}): {e}",
            )

    @staticmethod
    def _parse_kegg_flat(text: str) -> dict[str, Any]:
        """
        KEGG flat-file 텍스트를 딕셔너리로 파싱
        Parse KEGG flat-file format into a structured dictionary.

        Args:
            text: KEGG flat-file 텍스트 / Raw KEGG flat-file text

        Returns:
            dict: 파싱된 경로 정보 / Parsed pathway information
        """
        result: dict[str, Any] = {}
        current_key = ""
        current_value_lines: list[str] = []

        for line in text.split("\n"):
            if line.startswith("///"):
                break
            if line and not line[0].isspace():
                # 이전 키 저장 / Save previous key
                if current_key:
                    val = "\n".join(current_value_lines).strip()
                    result[current_key.lower()] = val

                parts = line.split(None, 1)
                current_key = parts[0] if parts else ""
                current_value_lines = [parts[1]] if len(parts) > 1 else []
            else:
                current_value_lines.append(line.strip())

        if current_key:
            result[current_key.lower()] = "\n".join(current_value_lines).strip()

        return result

    # ==================================================================
    # Ensembl methods
    # ==================================================================

    async def get_gene_info(self, gene_id: str) -> ClientResponse:
        """
        Ensembl 유전자 ID로 유전자 정보 조회
        Look up gene information by Ensembl stable ID.

        Args:
            gene_id: Ensembl 안정 ID (예: 'ENSG00000141510')
                     Ensembl stable ID (e.g., 'ENSG00000141510')

        Returns:
            ClientResponse: 유전자 상세 정보 / Gene details
        """
        cache_key = self._cache_key("ensembl_gene", gene_id)
        cached = self._get_cached(cache_key)
        if cached is not None:
            return cached

        start = time.time()
        try:
            ensembl = await self._get_ensembl_client()

            if self._last_request_time is not None:
                elapsed = time.time() - self._last_request_time
                if elapsed < self.config.rate_limit_delay:
                    await asyncio.sleep(self.config.rate_limit_delay - elapsed)
            self._last_request_time = time.time()

            response = await ensembl.get(
                f"/lookup/id/{gene_id}",
                params={"content-type": "application/json"},
            )
            response.raise_for_status()
            latency = (time.time() - start) * 1000

            data = response.json()
            resp = self._make_response(
                success=True,
                data=data,
                query=f"ensembl_gene:{gene_id}",
                latency_ms=latency,
                raw_response=data,
            )
            self._set_cached(cache_key, resp)
            return resp

        except Exception as e:
            latency = (time.time() - start) * 1000
            return self._make_response(
                success=False,
                data={},
                query=f"ensembl_gene:{gene_id}",
                latency_ms=latency,
                error_message=f"Ensembl 유전자 조회 실패 ({gene_id}): {e}",
            )

    async def get_gene_by_symbol(
        self, symbol: str, species: str = "homo_sapiens"
    ) -> ClientResponse:
        """
        유전자 심볼로 유전자 정보 조회
        Look up gene information by gene symbol and species.

        Args:
            symbol: 유전자 심볼 (예: 'TP53') / Gene symbol (e.g., 'TP53')
            species: 생물종 (기본 'homo_sapiens') / Species (default 'homo_sapiens')

        Returns:
            ClientResponse: 유전자 상세 정보 / Gene details
        """
        cache_key = self._cache_key("ensembl_symbol", species, symbol)
        cached = self._get_cached(cache_key)
        if cached is not None:
            return cached

        start = time.time()
        try:
            ensembl = await self._get_ensembl_client()

            if self._last_request_time is not None:
                elapsed = time.time() - self._last_request_time
                if elapsed < self.config.rate_limit_delay:
                    await asyncio.sleep(self.config.rate_limit_delay - elapsed)
            self._last_request_time = time.time()

            response = await ensembl.get(
                f"/lookup/symbol/{species}/{symbol}",
                params={"content-type": "application/json"},
            )
            response.raise_for_status()
            latency = (time.time() - start) * 1000

            data = response.json()
            resp = self._make_response(
                success=True,
                data=data,
                query=f"ensembl_symbol:{species}:{symbol}",
                latency_ms=latency,
                raw_response=data,
            )
            self._set_cached(cache_key, resp)
            return resp

        except Exception as e:
            latency = (time.time() - start) * 1000
            return self._make_response(
                success=False,
                data={},
                query=f"ensembl_symbol:{species}:{symbol}",
                latency_ms=latency,
                error_message=f"Ensembl 심볼 조회 실패 ({species}/{symbol}): {e}",
            )

    async def get_orthologs(self, gene_id: str) -> ClientResponse:
        """
        유전자의 오르톨로그 조회
        Retrieve ortholog data for a gene using Ensembl homology endpoint.

        Args:
            gene_id: Ensembl 안정 ID (예: 'ENSG00000141510')
                     Ensembl stable ID (e.g., 'ENSG00000141510')

        Returns:
            ClientResponse: 오르톨로그 정보 / Ortholog data
        """
        cache_key = self._cache_key("ensembl_orthologs", gene_id)
        cached = self._get_cached(cache_key)
        if cached is not None:
            return cached

        start = time.time()
        try:
            ensembl = await self._get_ensembl_client()

            if self._last_request_time is not None:
                elapsed = time.time() - self._last_request_time
                if elapsed < self.config.rate_limit_delay:
                    await asyncio.sleep(self.config.rate_limit_delay - elapsed)
            self._last_request_time = time.time()

            response = await ensembl.get(
                f"/homology/id/{gene_id}",
                params={"content-type": "application/json"},
            )
            response.raise_for_status()
            latency = (time.time() - start) * 1000

            raw = response.json()
            homologies = raw.get("data", [{}])[0].get("homologies", []) if raw.get("data") else []

            resp = self._make_response(
                success=True,
                data=homologies,
                query=f"orthologs:{gene_id}",
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
                query=f"orthologs:{gene_id}",
                latency_ms=latency,
                error_message=f"오르톨로그 조회 실패 ({gene_id}): {e}",
            )

    # ------------------------------------------------------------------
    # Health check override
    # ------------------------------------------------------------------

    async def health_check(self) -> bool:
        """
        모든 API 서비스 상태 확인
        Check health of all three API services.

        Returns:
            bool: 하나 이상의 서비스가 정상이면 True
                  True if at least one service is healthy
        """
        results = []
        try:
            # QuickGO
            client = await self._get_client()
            r = await client.get("/annotation/search", params={"limit": 1})
            results.append(r.status_code < 500)
        except Exception:
            results.append(False)

        try:
            # Ensembl
            ensembl = await self._get_ensembl_client()
            r = await ensembl.get("/info/ping", params={"content-type": "application/json"})
            results.append(r.status_code == 200)
        except Exception:
            results.append(False)

        try:
            # KEGG
            kegg = await self._get_kegg_client()
            r = await kegg.get("/info/kegg")
            results.append(r.status_code == 200)
        except Exception:
            results.append(False)

        return any(results)
