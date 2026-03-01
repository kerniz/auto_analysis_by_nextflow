"""
Data Aggregator - Unified Data Collection Layer
데이터 어그리게이터 - 통합 데이터 수집 계층

여러 외부 API 클라이언트를 통합하여 단일 인터페이스로 논문 메타데이터,
인용 네트워크, 유전자 어노테이션, 임상 데이터를 수집합니다.
모든 소스에 대해 우아한 실패 처리(graceful degradation)를 적용합니다.

Aggregates multiple external API clients into a single interface for
collecting paper metadata, citation networks, gene annotations, and
clinical data with graceful degradation across all sources.
"""

import asyncio
import time
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from .annotation_client import AnnotationClient
from .base import ClientConfig, ClientResponse
from .europe_pmc_client import EuropePMCClient
from .semantic_scholar_client import SemanticScholarClient
from .tcga_client import TCGAClient


@dataclass
class AggregatedResult:
    """
    통합 수집 결과 데이터 클래스
    Aggregated result containing data from all sources.

    각 소스의 데이터, 성공 여부, 에러 정보를 통합합니다.
    Combines data, success status, and error information from each source.
    """
    # 쿼리 메타데이터 / Query metadata
    pmid: str
    doi: str | None = None
    query_timestamp: datetime = field(default_factory=datetime.now)
    total_latency_ms: float = 0.0

    # Semantic Scholar 데이터 / Semantic Scholar data
    semantic_scholar_paper: dict[str, Any] = field(default_factory=dict)
    semantic_scholar_citations: list[dict[str, Any]] = field(default_factory=list)
    semantic_scholar_references: list[dict[str, Any]] = field(default_factory=list)
    semantic_scholar_recommendations: list[dict[str, Any]] = field(default_factory=list)
    semantic_scholar_influence: dict[str, Any] = field(default_factory=dict)

    # Europe PMC 데이터 / Europe PMC data
    europe_pmc_article: dict[str, Any] = field(default_factory=dict)
    europe_pmc_citations: list[dict[str, Any]] = field(default_factory=list)
    europe_pmc_references: list[dict[str, Any]] = field(default_factory=list)
    europe_pmc_annotations: list[dict[str, Any]] = field(default_factory=list)

    # 유전자 어노테이션 데이터 / Gene annotation data
    gene_annotations: dict[str, Any] = field(default_factory=dict)
    kegg_pathways: dict[str, Any] = field(default_factory=dict)
    ensembl_genes: dict[str, Any] = field(default_factory=dict)

    # TCGA/GDC 데이터 / TCGA/GDC data
    tcga_projects: list[dict[str, Any]] = field(default_factory=list)

    # 에러 추적 / Error tracking
    errors: dict[str, str] = field(default_factory=dict)
    sources_succeeded: list[str] = field(default_factory=list)
    sources_failed: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """
        결과를 직렬화 가능한 딕셔너리로 변환
        Convert the aggregated result to a serializable dictionary.
        """
        return {
            "pmid": self.pmid,
            "doi": self.doi,
            "query_timestamp": self.query_timestamp.isoformat(),
            "total_latency_ms": round(self.total_latency_ms, 2),
            "semantic_scholar": {
                "paper": self.semantic_scholar_paper,
                "citations_count": len(self.semantic_scholar_citations),
                "references_count": len(self.semantic_scholar_references),
                "recommendations_count": len(self.semantic_scholar_recommendations),
                "influence": self.semantic_scholar_influence,
            },
            "europe_pmc": {
                "article": self.europe_pmc_article,
                "citations_count": len(self.europe_pmc_citations),
                "references_count": len(self.europe_pmc_references),
                "annotations_count": len(self.europe_pmc_annotations),
            },
            "gene_annotations": self.gene_annotations,
            "kegg_pathways": self.kegg_pathways,
            "ensembl_genes": self.ensembl_genes,
            "tcga_projects": self.tcga_projects,
            "errors": self.errors,
            "sources_succeeded": self.sources_succeeded,
            "sources_failed": self.sources_failed,
        }


class DataAggregator:
    """
    통합 데이터 어그리게이터

    Semantic Scholar, Europe PMC, 어노테이션(QuickGO/KEGG/Ensembl),
    TCGA/GDC 클라이언트를 통합하여 하나의 PMID로부터 모든 관련 데이터를
    병렬로 수집합니다.

    Unified data aggregator that combines Semantic Scholar, Europe PMC,
    annotation (QuickGO/KEGG/Ensembl), and TCGA/GDC clients to collect
    all relevant data in parallel from a single PMID.
    """

    def __init__(self):
        """
        어그리게이터 초기화 (클라이언트 미생성)
        Initialize aggregator without creating clients.
        Call initialize() to create default clients.
        """
        self.ss_client: SemanticScholarClient | None = None
        self.epmc_client: EuropePMCClient | None = None
        self.annotation_client: AnnotationClient | None = None
        self.tcga_client: TCGAClient | None = None
        self._initialized = False

    async def initialize(
        self,
        ss_config: ClientConfig | None = None,
        epmc_config: ClientConfig | None = None,
        annotation_config: ClientConfig | None = None,
        tcga_config: ClientConfig | None = None,
    ) -> None:
        """
        모든 클라이언트를 기본 또는 사용자 지정 설정으로 초기화
        Initialize all clients with default or custom configurations.

        Args:
            ss_config: Semantic Scholar 설정 / Semantic Scholar config
            epmc_config: Europe PMC 설정 / Europe PMC config
            annotation_config: 어노테이션 설정 / Annotation config
            tcga_config: TCGA/GDC 설정 / TCGA/GDC config
        """
        self.ss_client = SemanticScholarClient(config=ss_config)
        self.epmc_client = EuropePMCClient(config=epmc_config)
        self.annotation_client = AnnotationClient(config=annotation_config)
        self.tcga_client = TCGAClient(config=tcga_config)
        self._initialized = True

    async def close(self) -> None:
        """
        모든 클라이언트 리소스 정리
        Release resources held by all clients.
        """
        clients = [
            self.ss_client,
            self.epmc_client,
            self.annotation_client,
            self.tcga_client,
        ]
        for client in clients:
            if client is not None:
                try:
                    await client.close()
                except Exception:
                    pass
        self._initialized = False

    # ------------------------------------------------------------------
    # Main aggregation entry point
    # ------------------------------------------------------------------

    async def aggregate(
        self,
        pmid: str,
        doi: str | None = None,
        gene_list: list[str] | None = None,
    ) -> AggregatedResult:
        """
        PMID 기반 통합 데이터 수집
        Collect all available data for a publication identified by PMID.

        모든 소스에 대해 병렬 요청을 수행하며, 개별 소스 실패는 전체
        결과에 영향을 주지 않습니다 (graceful degradation).

        Performs parallel requests to all sources. Individual source failures
        do not affect the overall result (graceful degradation).

        Args:
            pmid: PubMed ID / PubMed identifier
            doi: DOI (선택사항, Semantic Scholar 조회에 사용)
                 Optional DOI for Semantic Scholar lookup
            gene_list: 유전자 심볼/ID 목록 (선택사항, 어노테이션 조회용)
                       Optional gene symbols/IDs for annotation lookup

        Returns:
            AggregatedResult: 모든 소스의 통합 결과 / Aggregated data from all sources
        """
        if not self._initialized:
            await self.initialize()

        start = time.time()
        result = AggregatedResult(pmid=pmid, doi=doi)

        # 병렬 수집 태스크 구성 / Build parallel collection tasks
        tasks = {
            "ss_paper": self._query_ss_paper(pmid, doi),
            "ss_citations": self._query_ss_citations(pmid),
            "ss_references": self._query_ss_references(pmid),
            "ss_recommendations": self._query_ss_recommendations(pmid),
            "ss_influence": self._query_ss_influence(pmid),
            "epmc_article": self._query_epmc_article(pmid),
            "epmc_citations": self._query_epmc_citations(pmid),
            "epmc_references": self._query_epmc_references(pmid),
        }

        # 유전자 목록이 있는 경우 어노테이션 태스크 추가
        # Add annotation tasks if gene list is provided
        if gene_list:
            tasks["gene_annotations"] = self._query_gene_annotations(gene_list)
            tasks["kegg_pathways"] = self._query_kegg_pathways(gene_list)
            tasks["ensembl_genes"] = self._query_ensembl_genes(gene_list)

        # 병렬 실행 / Execute all tasks in parallel
        task_keys = list(tasks.keys())
        task_coros = list(tasks.values())
        responses = await asyncio.gather(*task_coros, return_exceptions=True)

        # 결과 매핑 / Map results
        for key, resp in zip(task_keys, responses):
            if isinstance(resp, Exception):
                result.errors[key] = str(resp)
                result.sources_failed.append(key)
                continue

            if isinstance(resp, ClientResponse):
                if resp.success:
                    result.sources_succeeded.append(key)
                else:
                    result.errors[key] = resp.error_message
                    result.sources_failed.append(key)

        # 결과를 AggregatedResult에 매핑 / Map to AggregatedResult fields
        result = self._merge_results(result, task_keys, responses)
        result.total_latency_ms = (time.time() - start) * 1000

        return result

    # ------------------------------------------------------------------
    # Individual source query methods
    # ------------------------------------------------------------------

    async def _query_ss_paper(
        self, pmid: str, doi: str | None = None
    ) -> ClientResponse:
        """
        Semantic Scholar 논문 메타데이터 조회
        Query Semantic Scholar for paper metadata.

        DOI가 있으면 DOI로, 없으면 PMID로 조회합니다.
        Uses DOI if available, otherwise falls back to PMID.
        """
        try:
            if doi:
                return await self.ss_client.fetch_by_id(doi)
            return await self.ss_client.fetch_by_pmid(pmid)
        except Exception as e:
            return ClientResponse(
                success=False, data={}, source="semantic_scholar",
                query=f"paper:{pmid}", error_message=str(e),
            )

    async def _query_ss_citations(self, pmid: str) -> ClientResponse:
        """
        Semantic Scholar 인용 데이터 조회
        Query Semantic Scholar for citation data.
        """
        try:
            return await self.ss_client.get_citations(f"PMID:{pmid}")
        except Exception as e:
            return ClientResponse(
                success=False, data=[], source="semantic_scholar",
                query=f"citations:{pmid}", error_message=str(e),
            )

    async def _query_ss_references(self, pmid: str) -> ClientResponse:
        """
        Semantic Scholar 참고문헌 데이터 조회
        Query Semantic Scholar for reference data.
        """
        try:
            return await self.ss_client.get_references(f"PMID:{pmid}")
        except Exception as e:
            return ClientResponse(
                success=False, data=[], source="semantic_scholar",
                query=f"references:{pmid}", error_message=str(e),
            )

    async def _query_ss_recommendations(self, pmid: str) -> ClientResponse:
        """
        Semantic Scholar 추천 논문 조회
        Query Semantic Scholar for paper recommendations.
        """
        try:
            return await self.ss_client.get_recommendations(f"PMID:{pmid}")
        except Exception as e:
            return ClientResponse(
                success=False, data=[], source="semantic_scholar",
                query=f"recommendations:{pmid}", error_message=str(e),
            )

    async def _query_ss_influence(self, pmid: str) -> ClientResponse:
        """
        Semantic Scholar 영향력 점수 조회
        Query Semantic Scholar for influence score.
        """
        try:
            return await self.ss_client.get_influence_score(f"PMID:{pmid}")
        except Exception as e:
            return ClientResponse(
                success=False, data={}, source="semantic_scholar",
                query=f"influence:{pmid}", error_message=str(e),
            )

    async def _query_epmc_article(self, pmid: str) -> ClientResponse:
        """
        Europe PMC 논문 메타데이터 조회
        Query Europe PMC for article metadata.
        """
        try:
            return await self.epmc_client.fetch_by_id(pmid)
        except Exception as e:
            return ClientResponse(
                success=False, data={}, source="europe_pmc",
                query=f"article:{pmid}", error_message=str(e),
            )

    async def _query_epmc_citations(self, pmid: str) -> ClientResponse:
        """
        Europe PMC 인용 데이터 조회
        Query Europe PMC for citation data.
        """
        try:
            return await self.epmc_client.get_citations(pmid)
        except Exception as e:
            return ClientResponse(
                success=False, data=[], source="europe_pmc",
                query=f"citations:{pmid}", error_message=str(e),
            )

    async def _query_epmc_references(self, pmid: str) -> ClientResponse:
        """
        Europe PMC 참고문헌 데이터 조회
        Query Europe PMC for reference data.
        """
        try:
            return await self.epmc_client.get_references(pmid)
        except Exception as e:
            return ClientResponse(
                success=False, data=[], source="europe_pmc",
                query=f"references:{pmid}", error_message=str(e),
            )

    async def _query_gene_annotations(
        self, gene_list: list[str]
    ) -> ClientResponse:
        """
        유전자 목록의 GO 어노테이션 일괄 조회
        Batch query GO annotations for a gene list.
        """
        try:
            return await self.annotation_client.get_go_enrichment(gene_list)
        except Exception as e:
            return ClientResponse(
                success=False, data={}, source="annotation",
                query=f"go_enrichment:{len(gene_list)}", error_message=str(e),
            )

    async def _query_kegg_pathways(
        self, gene_list: list[str]
    ) -> ClientResponse:
        """
        유전자 목록의 KEGG 경로 일괄 조회
        Batch query KEGG pathways for a gene list.
        """
        start = time.time()
        try:
            all_pathways: dict[str, Any] = {}
            for gene_id in gene_list:
                resp = await self.annotation_client.get_kegg_pathways(gene_id)
                if resp.success:
                    all_pathways[gene_id] = resp.data
                else:
                    all_pathways[gene_id] = {"error": resp.error_message}

            latency = (time.time() - start) * 1000
            return ClientResponse(
                success=True,
                data=all_pathways,
                source="annotation",
                query=f"kegg_pathways:{len(gene_list)}",
                latency_ms=latency,
            )
        except Exception as e:
            latency = (time.time() - start) * 1000
            return ClientResponse(
                success=False, data={}, source="annotation",
                query=f"kegg_pathways:{len(gene_list)}", error_message=str(e),
                latency_ms=latency,
            )

    async def _query_ensembl_genes(
        self, gene_list: list[str]
    ) -> ClientResponse:
        """
        유전자 심볼 목록의 Ensembl 정보 일괄 조회
        Batch query Ensembl gene information for a symbol list.
        """
        start = time.time()
        try:
            all_genes: dict[str, Any] = {}
            tasks = []
            for symbol in gene_list:
                tasks.append(self.annotation_client.get_gene_by_symbol(symbol))

            results = await asyncio.gather(*tasks, return_exceptions=True)
            for symbol, resp in zip(gene_list, results):
                if isinstance(resp, Exception):
                    all_genes[symbol] = {"error": str(resp)}
                elif resp.success:
                    all_genes[symbol] = resp.data
                else:
                    all_genes[symbol] = {"error": resp.error_message}

            latency = (time.time() - start) * 1000
            return ClientResponse(
                success=True,
                data=all_genes,
                source="annotation",
                query=f"ensembl_genes:{len(gene_list)}",
                latency_ms=latency,
            )
        except Exception as e:
            latency = (time.time() - start) * 1000
            return ClientResponse(
                success=False, data={}, source="annotation",
                query=f"ensembl_genes:{len(gene_list)}", error_message=str(e),
                latency_ms=latency,
            )

    # ------------------------------------------------------------------
    # Result merging
    # ------------------------------------------------------------------

    def _merge_results(
        self,
        result: AggregatedResult,
        keys: list[str],
        responses: list[Any],
    ) -> AggregatedResult:
        """
        개별 소스 응답을 AggregatedResult에 병합
        Merge individual source responses into the AggregatedResult.

        중복 데이터는 소스별로 분리하여 저장합니다.
        Duplicate data is stored separately per source.

        Args:
            result: 대상 통합 결과 객체 / Target aggregated result
            keys: 태스크 키 목록 / Task key list
            responses: 태스크 응답 목록 / Task response list

        Returns:
            AggregatedResult: 병합된 결과 / Merged result
        """
        resp_map: dict[str, Any] = {}
        for key, resp in zip(keys, responses):
            if isinstance(resp, Exception):
                resp_map[key] = None
            elif isinstance(resp, ClientResponse):
                resp_map[key] = resp.data if resp.success else None
            else:
                resp_map[key] = None

        # Semantic Scholar
        if resp_map.get("ss_paper") is not None:
            result.semantic_scholar_paper = resp_map["ss_paper"]
        if resp_map.get("ss_citations") is not None:
            result.semantic_scholar_citations = resp_map["ss_citations"]
        if resp_map.get("ss_references") is not None:
            result.semantic_scholar_references = resp_map["ss_references"]
        if resp_map.get("ss_recommendations") is not None:
            result.semantic_scholar_recommendations = resp_map["ss_recommendations"]
        if resp_map.get("ss_influence") is not None:
            result.semantic_scholar_influence = resp_map["ss_influence"]

        # Europe PMC
        if resp_map.get("epmc_article") is not None:
            result.europe_pmc_article = resp_map["epmc_article"]
        if resp_map.get("epmc_citations") is not None:
            result.europe_pmc_citations = resp_map["epmc_citations"]
        if resp_map.get("epmc_references") is not None:
            result.europe_pmc_references = resp_map["epmc_references"]

        # Annotations
        if resp_map.get("gene_annotations") is not None:
            result.gene_annotations = resp_map["gene_annotations"]
        if resp_map.get("kegg_pathways") is not None:
            result.kegg_pathways = resp_map["kegg_pathways"]
        if resp_map.get("ensembl_genes") is not None:
            result.ensembl_genes = resp_map["ensembl_genes"]

        # Text-mined annotations from EPMC article (if PMC ID available)
        # PMC ID가 있으면 텍스트 마이닝 어노테이션 조회 (별도 비동기 수행 필요)
        epmc = result.europe_pmc_article
        if isinstance(epmc, dict) and epmc.get("pmcid"):
            # 어노테이션은 별도 호출이 필요하므로 여기선 pmcid만 기록
            result.europe_pmc_annotations = []  # 채워지지 않은 상태

        return result

    # ------------------------------------------------------------------
    # Convenience: full aggregate with text mining
    # ------------------------------------------------------------------

    async def aggregate_with_annotations(
        self,
        pmid: str,
        doi: str | None = None,
        gene_list: list[str] | None = None,
    ) -> AggregatedResult:
        """
        텍스트 마이닝 어노테이션을 포함한 완전한 통합 수집
        Full aggregation including text-mined annotations from Europe PMC.

        aggregate()를 호출한 후, PMC ID가 있으면 텍스트 마이닝 어노테이션도
        추가로 수집합니다.
        Calls aggregate() and additionally fetches text-mined annotations
        if a PMC ID is available in the Europe PMC article data.

        Args:
            pmid: PubMed ID
            doi: DOI (선택사항) / Optional DOI
            gene_list: 유전자 목록 (선택사항) / Optional gene list

        Returns:
            AggregatedResult: 어노테이션 포함 통합 결과 / Full aggregated result
        """
        result = await self.aggregate(pmid, doi=doi, gene_list=gene_list)

        # PMC ID가 있으면 텍스트 마이닝 어노테이션 추가 수집
        epmc = result.europe_pmc_article
        if isinstance(epmc, dict) and epmc.get("pmcid"):
            pmcid = epmc["pmcid"]
            try:
                ann_resp = await self.epmc_client.get_text_mined_terms(pmcid)
                if ann_resp.success:
                    result.europe_pmc_annotations = ann_resp.data
                    result.sources_succeeded.append("epmc_annotations")
                else:
                    result.errors["epmc_annotations"] = ann_resp.error_message
                    result.sources_failed.append("epmc_annotations")
            except Exception as e:
                result.errors["epmc_annotations"] = str(e)
                result.sources_failed.append("epmc_annotations")

        return result

    # ------------------------------------------------------------------
    # Metrics
    # ------------------------------------------------------------------

    def get_all_metrics(self) -> dict[str, Any]:
        """
        모든 클라이언트의 메트릭 반환
        Return metrics from all initialized clients.

        Returns:
            dict: 클라이언트별 메트릭 / Per-client metrics
        """
        metrics: dict[str, Any] = {"initialized": self._initialized}
        clients = {
            "semantic_scholar": self.ss_client,
            "europe_pmc": self.epmc_client,
            "annotation": self.annotation_client,
            "tcga_gdc": self.tcga_client,
        }
        for name, client in clients.items():
            if client is not None:
                metrics[name] = client.get_metrics()
            else:
                metrics[name] = {"status": "not_initialized"}
        return metrics
