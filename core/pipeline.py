"""
Async Pipeline Module - Main Orchestrator
비동기 파이프라인 실행 관리 (통합 메인 파이프라인)
"""

import asyncio
import json
import os
import sys
from datetime import datetime
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path

try:
    import httpx
    HAS_HTTPX = True
except ImportError:
    HAS_HTTPX = False

from backends import LLMRouter, OllamaBackend, OpenAIBackend, LLMConfig
from backends.base import BackendStatus
from backends.router import RouterConfig
from plugins import PluginRegistry, register_default_plugins
from core.progress_manager import ProgressManager


class PipelineStatus(Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    PARTIAL = "partial"


@dataclass
class PMIDResult:
    pmid: str
    status: PipelineStatus
    pubmed_metadata: Dict[str, Any] = field(default_factory=dict)
    sra_results: Dict[str, Any] = field(default_factory=dict)
    sequencing_result: Dict[str, Any] = field(default_factory=dict)
    # Pipeline execution results (v4.0)
    fetchngs_result: Dict[str, Any] = field(default_factory=dict)
    pipeline_execution: Dict[str, Any] = field(default_factory=dict)
    downstream_analysis: Dict[str, Any] = field(default_factory=dict)
    # Existing
    llm_analysis: Dict[str, Any] = field(default_factory=dict)
    aggregated_data: Dict[str, Any] = field(default_factory=dict)
    enrichment_results: Dict[str, Any] = field(default_factory=dict)
    debate_report: Dict[str, Any] = field(default_factory=dict)
    error: str = ""
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None

    @property
    def duration_seconds(self) -> float:
        if self.start_time and self.end_time:
            return (self.end_time - self.start_time).total_seconds()
        return 0.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "pmid": self.pmid,
            "status": self.status.value,
            "duration_seconds": self.duration_seconds,
            "error": self.error,
            "pubmed_metadata": self.pubmed_metadata,
            "sra_results": self.sra_results,
            "sequencing_type": self.sequencing_result.get("sequencing_type", "unknown"),
            "sequencing_confidence": self.sequencing_result.get("confidence", 0.0),
            "llm_rating": self.llm_analysis.get("consistency_rating", "UNKNOWN"),
            "llm_consensus": self.llm_analysis.get("consensus", {}),
            "aggregated_sources": list(self.aggregated_data.get("sources_succeeded", [])),
            "enrichment_summary": {
                k: v for k, v in self.enrichment_results.items()
                if k in ("top_pathways_count", "top_genes_count", "novelty_score")
            },
            "debate_verdict": self.debate_report.get("overall_verdict", "UNDETERMINED"),
            "debate_score": self.debate_report.get("overall_score", 0.0),
            # Pipeline execution (v4.0)
            "fetchngs": self.fetchngs_result if self.fetchngs_result else None,
            "pipeline_execution": self.pipeline_execution if self.pipeline_execution else None,
            "downstream_analysis": self.downstream_analysis if self.downstream_analysis else None,
        }


@dataclass
class PipelineConfig:
    pmids: List[str]
    results_dir: Path = Path("./results")
    max_concurrent: int = 5
    llm_router_config: Optional[RouterConfig] = None
    enable_resume: bool = True
    enable_data_aggregation: bool = True
    enable_enrichment: bool = True
    enable_debate: bool = True
    debate_rounds: int = 3
    progress_file: Optional[str] = None
    rag_dir: Optional[Path] = None
    # Pipeline execution (v4.0)
    enable_pipeline_execution: bool = False
    nextflow_config: Optional[Any] = None  # NextflowExecutionConfig
    # Project isolation (v4.1)
    project_slug: Optional[str] = None

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "PipelineConfig":
        return cls(
            pmids=data.get("pmids", []),
            results_dir=Path(data.get("results_dir", "./results")),
            max_concurrent=data.get("max_concurrent", 5),
            enable_resume=data.get("enable_resume", True),
            enable_data_aggregation=data.get("enable_data_aggregation", True),
            enable_enrichment=data.get("enable_enrichment", True),
            enable_debate=data.get("enable_debate", True),
            debate_rounds=data.get("debate_rounds", 3),
            project_slug=data.get("project_slug"),
        )

    @classmethod
    def from_json(cls, config_path: str) -> "PipelineConfig":
        with open(config_path, "r") as f:
            data = json.load(f)
        return cls.from_dict(data)


class AsyncPipeline:
    """
    통합 비동기 파이프라인 오케스트레이터

    파이프라인 스테이지:
    1. PubMed 메타데이터 수집
    2. SRA 데이터 탐색
    3. 시퀀싱 타입 탐지 (Plugin System)
    4. 데이터 통합 (DataAggregator - 모든 소스 동시 쿼리)
    5. 농축 분석 (GSEA, DEG, Pathway)
    6. LLM 멀티 합의 분석
    7. 멀티 에이전트 토론 (3인 패널 × N라운드)
    8. 최종 리포트 생성
    """

    def __init__(self, config: PipelineConfig):
        self.config = config
        self.results: Dict[str, PMIDResult] = {}
        self.llm_router: Optional[LLMRouter] = None
        self.plugin_registry: Optional[PluginRegistry] = None
        self.progress: Optional[ProgressManager] = None
        self.data_aggregator = None
        self.debate_manager = None
        self.doc_store = None
        self._semaphore = asyncio.Semaphore(config.max_concurrent)
        self._http_client: Optional[Any] = None

        # Project isolation: redirect results_dir if project_slug is set
        if config.project_slug:
            from core.project_manager import ProjectManager
            pm = ProjectManager()
            self.config.results_dir = pm.get_results_dir(config.project_slug)

        self.config.results_dir.mkdir(parents=True, exist_ok=True)

    async def initialize(self):
        """파이프라인 초기화: 플러그인, 백엔드, 프로그레스 매니저"""
        # Plugin registry
        self.plugin_registry = register_default_plugins()

        # Progress manager
        if self.config.enable_resume:
            progress_file = self.config.progress_file or str(
                self.config.results_dir / "progress.json"
            )
            self.progress = ProgressManager(progress_file)

        # LLM backends
        backends = []

        ollama_config = LLMConfig(model="deepseek-coder:33b", timeout=60)
        backends.append(OllamaBackend(
            base_url="http://localhost:11434",
            config=ollama_config
        ))

        if os.environ.get("OPENAI_API_KEY"):
            openai_config = LLMConfig(model="gpt-4", timeout=30)
            backends.append(OpenAIBackend(config=openai_config))

        try:
            from backends import AnthropicBackend
            if os.environ.get("ANTHROPIC_API_KEY"):
                anthropic_config = LLMConfig(model="claude-sonnet-4-20250514", timeout=30)
                backends.append(AnthropicBackend(config=anthropic_config))
        except ImportError:
            pass

        router_config = self.config.llm_router_config or RouterConfig(
            strategy="priority",
            enable_auto_failover=True
        )

        self.llm_router = LLMRouter(backends=backends, config=router_config)
        await self.llm_router.start()

        # Data aggregator (lazy import)
        if self.config.enable_data_aggregation:
            try:
                from clients.data_aggregator import DataAggregator
                self.data_aggregator = DataAggregator()
                await self.data_aggregator.initialize()
            except ImportError:
                print("[WARN] clients 패키지 없음, 데이터 집계 비활성화")

        # Debate manager (lazy import)
        if self.config.enable_debate and self.llm_router:
            try:
                from agents.debate_manager import DebateManager, DebateConfig
                debate_config = DebateConfig(num_rounds=self.config.debate_rounds)
                self.debate_manager = DebateManager.create_default_panel(
                    self.llm_router, config=debate_config
                )
            except ImportError:
                print("[WARN] agents 패키지 없음, 토론 비활성화")

        # RAG document store (lazy import)
        if self.config.rag_dir:
            try:
                from rag.document_store import DocumentStore
                self.doc_store = DocumentStore(self.config.rag_dir)
            except ImportError:
                print("[WARN] rag 패키지 없음, RAG 비활성화")

        # Nextflow execution layer (v4.0, lazy, conditional)
        self.nf_executor = None
        self.fetchngs_runner = None
        self.samplesheet_gen = None
        self.analysis_orchestrator = None

        if self.config.enable_pipeline_execution:
            try:
                from nextflow import (
                    NextflowExecutor, FetchNGSRunner, SamplesheetGenerator,
                )
                from nextflow.config import NextflowExecutionConfig
                from analysis import AnalysisOrchestrator

                nf_config = self.config.nextflow_config or NextflowExecutionConfig()
                self.nf_executor = NextflowExecutor(nf_config)
                self.fetchngs_runner = FetchNGSRunner(nf_config)
                self.samplesheet_gen = SamplesheetGenerator()
                self.analysis_orchestrator = AnalysisOrchestrator(
                    r_executable=nf_config.r_executable,
                    scanpy_enabled=nf_config.scanpy_enabled,
                    analysis_params=nf_config.analysis_params,
                )

                prereqs = await self.nf_executor.check_prerequisites()
                if not prereqs.get("nextflow"):
                    print("[WARN] Nextflow not installed, pipeline execution disabled")
                    self.nf_executor = None
            except ImportError as e:
                print(f"[WARN] nextflow/analysis packages not available: {e}")

        # HTTP client
        if HAS_HTTPX:
            self._http_client = httpx.AsyncClient(timeout=30.0)

    async def shutdown(self):
        """리소스 정리"""
        if self.llm_router:
            await self.llm_router.stop()
        if self._http_client:
            await self._http_client.aclose()
        if self.data_aggregator:
            await self.data_aggregator.close()

    async def run(self) -> Dict[str, PMIDResult]:
        """전체 파이프라인 실행"""
        await self.initialize()

        try:
            tasks = [
                self._process_pmid(pmid)
                for pmid in self.config.pmids
            ]

            results = await asyncio.gather(*tasks, return_exceptions=True)

            for pmid, result in zip(self.config.pmids, results):
                if isinstance(result, Exception):
                    self.results[pmid] = PMIDResult(
                        pmid=pmid,
                        status=PipelineStatus.FAILED,
                        error=str(result)
                    )
                else:
                    self.results[pmid] = result

            await self._save_summary()

            return self.results

        finally:
            await self.shutdown()

    async def _process_pmid(self, pmid: str) -> PMIDResult:
        """개별 PMID 처리 - 전체 8단계 파이프라인"""
        async with self._semaphore:
            result = PMIDResult(
                pmid=pmid,
                status=PipelineStatus.RUNNING,
                start_time=datetime.now()
            )

            if self.progress:
                self.progress.set_current_pmid(pmid)

            try:
                # Stage 1: PubMed 메타데이터
                if not self._is_step_done(pmid, "pubmed_done"):
                    pubmed_metadata = await self._fetch_pubmed(pmid)
                    result.pubmed_metadata = pubmed_metadata
                    self._mark_step_done(pmid, "pubmed_done")
                else:
                    result.pubmed_metadata = await self._load_cached(
                        f"pubmed_{pmid}.json"
                    )

                # Stage 2: SRA 탐색
                if not self._is_step_done(pmid, "sra_discovery_done"):
                    sra_results = await self._explore_sra(pmid, result.pubmed_metadata)
                    result.sra_results = sra_results
                    self._mark_step_done(pmid, "sra_discovery_done")
                else:
                    result.sra_results = await self._load_cached(
                        f"sra_exploration_{pmid}.json"
                    )

                # Stage 3: 시퀀싱 타입 탐지
                if self.plugin_registry:
                    detection, _ = self.plugin_registry.detect(
                        result.pubmed_metadata, result.sra_results
                    )
                    result.sequencing_result = {
                        "sequencing_type": detection.sequencing_type,
                        "confidence": detection.confidence,
                        "evidence": detection.evidence,
                        "recommended_pipeline": (
                            detection.recommended_pipeline.nf_core_name
                            if detection.recommended_pipeline else None
                        ),
                    }

                # Stage 3.5: SRA 데이터 다운로드 (nf-core/fetchngs)
                if (self.fetchngs_runner
                        and not self._is_step_done(pmid, "sra_download_done")):
                    try:
                        srr_ids = result.sra_results.get("public_sra_ids", [])
                        if not srr_ids:
                            srr_ids = result.sra_results.get("sra_ids", [])
                        if srr_ids:
                            fetchngs_result = await self.fetchngs_runner.run(
                                srr_accessions=srr_ids,
                                output_dir=self.config.results_dir / f"fetchngs_{pmid}",
                                pmid=pmid,
                            )
                            result.fetchngs_result = fetchngs_result.to_dict()
                            if fetchngs_result.success:
                                self._mark_step_done(pmid, "sra_download_done")
                    except Exception as e:
                        result.fetchngs_result = {"error": str(e)}

                # Stage 3.6: nf-core 파이프라인 실행
                if (self.nf_executor
                        and result.fetchngs_result.get("success")
                        and not self._is_step_done(pmid, "pipeline_done")):
                    try:
                        pipeline_def = (
                            detection.recommended_pipeline
                            if self.plugin_registry and detection.recommended_pipeline
                            else None
                        )
                        if pipeline_def:
                            fastq_dir = Path(result.fetchngs_result["fastq_dir"])
                            srr_ids = result.fetchngs_result.get(
                                "accessions_processed",
                                result.sra_results.get("public_sra_ids", []),
                            )
                            samplesheet_path = (
                                self.config.results_dir / f"samplesheet_{pmid}.csv"
                            )
                            self.samplesheet_gen.generate(
                                pipeline_name=pipeline_def.nf_core_name,
                                srr_accessions=srr_ids,
                                fastq_dir=fastq_dir,
                                output_path=samplesheet_path,
                            )
                            exec_result = await self.nf_executor.execute_pipeline(
                                pipeline_def=pipeline_def,
                                samplesheet_path=samplesheet_path,
                                output_dir=self.config.results_dir / f"nfcore_{pmid}",
                            )
                            result.pipeline_execution = exec_result.to_dict()
                            if exec_result.status == "completed":
                                self._mark_step_done(pmid, "pipeline_done")
                    except Exception as e:
                        result.pipeline_execution = {"error": str(e)}

                # Stage 3.7: 다운스트림 R/Python 분석
                if (self.analysis_orchestrator
                        and result.pipeline_execution.get("status") == "completed"
                        and not self._is_step_done(pmid, "analysis_done")):
                    try:
                        analysis_type = ""
                        if self.plugin_registry and detection.recommended_pipeline:
                            analysis_type = detection.recommended_pipeline.analysis_type
                        if analysis_type:
                            analysis_result = await self.analysis_orchestrator.run_analysis(
                                analysis_type=analysis_type,
                                pipeline_outputs=result.pipeline_execution.get(
                                    "output_files", {}
                                ),
                                output_dir=self.config.results_dir / f"analysis_{pmid}",
                            )
                            result.downstream_analysis = analysis_result.to_dict()
                            if analysis_result.success:
                                self._mark_step_done(pmid, "analysis_done")
                    except Exception as e:
                        result.downstream_analysis = {"error": str(e)}

                # Stage 4: 데이터 통합
                if self.data_aggregator:
                    try:
                        aggregated = await self.data_aggregator.aggregate(
                            pmid=pmid,
                            doi=result.pubmed_metadata.get("doi"),
                        )
                        result.aggregated_data = aggregated.to_dict()
                    except Exception as e:
                        result.aggregated_data = {"error": str(e)}

                # Stage 5: 농축 분석
                if self.config.enable_enrichment:
                    try:
                        enrichment = await self._run_enrichment(result)
                        result.enrichment_results = enrichment
                    except Exception as e:
                        result.enrichment_results = {"error": str(e)}

                # Stage 6: LLM 멀티 합의 분석
                if not self._is_step_done(pmid, "llm_analysis_done"):
                    llm_analysis = await self._analyze_with_llm_consensus(
                        pmid, result.pubmed_metadata, result.sequencing_result,
                        downstream_analysis=result.downstream_analysis,
                    )
                    result.llm_analysis = llm_analysis
                    self._mark_step_done(pmid, "llm_analysis_done")
                else:
                    result.llm_analysis = await self._load_cached(
                        f"deepseek_analysis_{pmid}.json"
                    )

                # Stage 7: 멀티 에이전트 토론
                if self.debate_manager:
                    try:
                        research_data = {
                            "paper": result.pubmed_metadata,
                            "sequencing": result.sequencing_result,
                            "aggregated": result.aggregated_data,
                            "enrichment": result.enrichment_results,
                            "llm_analysis": result.llm_analysis,
                        }
                        debate_result = await self.debate_manager.run_debate(research_data)
                        result.debate_report = debate_result.to_dict()
                    except Exception as e:
                        result.debate_report = {"error": str(e)}

                # Stage 8: RAG 인덱싱 (옵션)
                if self.doc_store:
                    try:
                        self._index_result_in_rag(result)
                    except Exception as e:
                        print(f"[WARN] RAG 인덱싱 실패: {e}")

                # Stage 9: 완료
                result.status = PipelineStatus.COMPLETED
                self._mark_step_done(pmid, "final_report_done")

            except Exception as e:
                result.status = PipelineStatus.FAILED
                result.error = str(e)
                if self.progress:
                    self.progress.add_failed_step(
                        f"pmid_{pmid}", str(e)
                    )

            result.end_time = datetime.now()
            await self._save_pmid_result(result)
            return result

    async def _fetch_pubmed(self, pmid: str) -> Dict[str, Any]:
        """PubMed 메타데이터 수집 (캐시 지원)"""
        cached_file = self.config.results_dir / f"pubmed_{pmid}.json"

        if cached_file.exists():
            with open(cached_file, "r") as f:
                return json.load(f)

        try:
            from core.pubmed_client import PubMedClient
            client = PubMedClient()
            metadata = client.fetch_paper_metadata(pmid)
            if metadata:
                with open(cached_file, "w") as f:
                    json.dump(metadata, f, indent=2, default=str)
                return metadata
        except ImportError:
            pass

        return {"pmid": pmid, "title": "", "abstract": "", "source": "unavailable"}

    async def _explore_sra(
        self, pmid: str, pubmed_metadata: Dict[str, Any]
    ) -> Dict[str, Any]:
        """SRA 데이터 탐색 (캐시 지원)"""
        cached_file = self.config.results_dir / f"sra_exploration_{pmid}.json"

        if cached_file.exists():
            with open(cached_file, "r") as f:
                return json.load(f)

        try:
            from core.sra_explorer import SRAExplorer
            explorer = SRAExplorer()
            sra_links = pubmed_metadata.get("sra_links", [])
            result = explorer.explore_sra_datasets(pmid, sra_links)
            if result:
                with open(cached_file, "w") as f:
                    json.dump(result, f, indent=2, default=str)
                return result
        except ImportError:
            pass

        return {"pmid": pmid, "sra_ids": [], "source": "unavailable"}

    async def _analyze_with_llm_consensus(
        self,
        pmid: str,
        pubmed_metadata: Dict[str, Any],
        sequencing_result: Dict[str, Any],
        downstream_analysis: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """LLM 멀티 합의: 모든 건강한 백엔드에 동시 쿼리 후 가중 합의"""
        cached_file = self.config.results_dir / f"deepseek_analysis_{pmid}.json"

        if cached_file.exists():
            with open(cached_file, "r") as f:
                return json.load(f)

        if not self.llm_router:
            return {"pmid": pmid, "consistency_rating": "WARN", "error": "No LLM router"}

        prompt = self._build_analysis_prompt(pubmed_metadata, sequencing_result)

        # RAG 컨텍스트 주입 (기존 분석 결과 참조)
        if self.doc_store:
            try:
                from rag.rag_context import RAGContext
                rag_ctx = RAGContext(self.doc_store)
                context_block = rag_ctx.build_context(
                    pubmed_metadata.get("title", "bioinformatics"),
                    n_results=3,
                )
                if context_block:
                    prompt = f"[Related prior analyses]\n{context_block}\n\n{prompt}"
            except Exception:
                pass

        # 모든 건강한 백엔드에 동시 쿼리
        healthy_backends = [
            (name, backend)
            for name, backend in self.llm_router.backends.items()
            if backend.status in (BackendStatus.HEALTHY, BackendStatus.UNKNOWN)
        ]

        if not healthy_backends:
            # 폴백: 라우터의 표준 generate 사용
            response = await self.llm_router.generate(prompt)
            if response.success:
                result = self._parse_llm_response(response.content)
                result["backend"] = response.backend_name
                return result
            return {"pmid": pmid, "consistency_rating": "WARN", "error": "All backends unavailable"}

        # 동시 쿼리
        tasks = []
        backend_names = []
        for name, backend in healthy_backends:
            tasks.append(backend.generate_with_retry(prompt))
            backend_names.append(name)

        responses = await asyncio.gather(*tasks, return_exceptions=True)

        # 결과 합의
        valid_results = []
        for name, resp in zip(backend_names, responses):
            if isinstance(resp, Exception):
                continue
            if resp.success:
                parsed = self._parse_llm_response(resp.content)
                parsed["backend"] = name
                parsed["health_score"] = self.llm_router.backends[name].health_score
                valid_results.append(parsed)

        if not valid_results:
            return {"pmid": pmid, "consistency_rating": "WARN", "error": "All backends failed"}

        if len(valid_results) == 1:
            return valid_results[0]

        # 가중 합의
        return self._merge_consensus(valid_results)

    def _merge_consensus(self, results: List[Dict[str, Any]]) -> Dict[str, Any]:
        """여러 LLM 결과를 가중 합의로 병합"""
        total_weight = sum(r.get("health_score", 1.0) for r in results)

        # 점수 가중 평균
        weighted_score = sum(
            r.get("consistency_score", 0.5) * r.get("health_score", 1.0)
            for r in results
        ) / max(total_weight, 0.001)

        # 등급 투표 (가중)
        rating_votes: Dict[str, float] = {}
        for r in results:
            rating = r.get("consistency_rating", "WARN")
            weight = r.get("health_score", 1.0)
            rating_votes[rating] = rating_votes.get(rating, 0) + weight

        consensus_rating = max(rating_votes, key=rating_votes.get)

        # 기술 평가 합산
        assessments = [r.get("technical_assessment", "") for r in results if r.get("technical_assessment")]
        recommendations = []
        for r in results:
            recommendations.extend(r.get("recommendations", []))

        return {
            "consistency_score": round(weighted_score, 3),
            "consistency_rating": consensus_rating,
            "technical_assessment": " | ".join(assessments[:3]),
            "recommendations": list(set(recommendations)),
            "consensus": {
                "num_backends": len(results),
                "backends": [r.get("backend", "unknown") for r in results],
                "rating_votes": rating_votes,
                "individual_scores": [
                    {"backend": r.get("backend"), "score": r.get("consistency_score", 0.5)}
                    for r in results
                ],
            },
        }

    async def _run_enrichment(self, result: PMIDResult) -> Dict[str, Any]:
        """농축 분석 실행 (GSEA, DEG, Pathway)"""
        try:
            from enrichment import GSEAAnalyzer, PathwayAnalyzer, NoveltyScorer
            enrichment_data: Dict[str, Any] = {}

            # 논문에서 유전자 목록 추출 시도
            gene_list = self._extract_genes_from_metadata(result)

            if gene_list:
                gsea = GSEAAnalyzer()
                gsea_results = await gsea.run_enrichr(gene_list)
                enrichment_data["gsea"] = gsea_results
                enrichment_data["top_pathways_count"] = len(
                    gsea_results.get("significant_terms", [])
                )

                pathway = PathwayAnalyzer()
                pathway_results = await pathway.analyze_pathways(gene_list)
                enrichment_data["pathways"] = pathway_results

            # Novelty 스코어링
            if self.data_aggregator:
                novelty = NoveltyScorer()
                novelty_result = await novelty.score_novelty(
                    result.pubmed_metadata,
                    enrichment_data,
                    result.aggregated_data,
                )
                enrichment_data["novelty_score"] = novelty_result.get("score", 0.0)
                enrichment_data["novelty_factors"] = novelty_result.get("factors", {})

            enrichment_data["top_genes_count"] = len(gene_list)
            return enrichment_data

        except ImportError:
            return {"error": "enrichment 패키지 없음"}

    def _extract_genes_from_metadata(self, result: PMIDResult) -> List[str]:
        """메타데이터/집계 데이터에서 유전자 목록 추출"""
        genes = []
        # text-mined terms에서 추출
        text_mined = result.aggregated_data.get("europe_pmc_data", {}).get("text_mined_terms", [])
        for term in text_mined:
            if term.get("type") == "Gene":
                genes.append(term.get("name", ""))
        # 키워드에서 추출
        keywords = result.pubmed_metadata.get("keywords", [])
        for kw in keywords:
            if kw.isupper() and len(kw) <= 10:
                genes.append(kw)
        return list(set(g for g in genes if g))

    def _index_result_in_rag(self, result: PMIDResult):
        """파이프라인 결과를 RAG 벡터 DB에 인덱싱"""
        pmid = result.pmid
        meta = result.pubmed_metadata

        if meta.get("title") and meta.get("abstract"):
            year = None
            pub_date = meta.get("pub_date", "")
            if pub_date:
                try:
                    year = int(pub_date[:4])
                except (ValueError, IndexError):
                    pass
            self.doc_store.add_paper(
                pmid=pmid,
                title=meta["title"],
                abstract=meta["abstract"],
                year=year,
            )

        if result.llm_analysis and not result.llm_analysis.get("error"):
            self.doc_store.add_analysis(
                pmid=pmid,
                analysis_text=json.dumps(
                    result.llm_analysis, ensure_ascii=False
                ),
                rating=result.llm_analysis.get(
                    "consistency_rating", "UNKNOWN"
                ),
            )

        if result.debate_report and result.debate_report.get("overall_verdict"):
            self.doc_store.add_debate_report(
                pmid=pmid,
                report_text=json.dumps(
                    result.debate_report, ensure_ascii=False
                ),
                verdict=result.debate_report["overall_verdict"],
                score=result.debate_report.get("overall_score", 0.0),
            )

    def _build_analysis_prompt(
        self,
        pubmed_metadata: Dict[str, Any],
        sequencing_result: Dict[str, Any],
        downstream_analysis: Optional[Dict[str, Any]] = None,
    ) -> str:
        title = pubmed_metadata.get("title", "")
        abstract = pubmed_metadata.get("abstract", "")[:1000]
        seq_type = sequencing_result.get("sequencing_type", "unknown")

        prompt = f"""Analyze this bioinformatics paper and sequencing data:

Title: {title}
Abstract: {abstract[:500]}
Detected Sequencing Type: {seq_type}
"""

        # Inject actual downstream analysis results if available
        if downstream_analysis and downstream_analysis.get("success"):
            summary = downstream_analysis.get("summary", {})
            if summary:
                prompt += "\nActual Analysis Results:\n"
                for key, val in summary.items():
                    if key in ("success", "qc_params"):
                        continue
                    if isinstance(val, (list, dict)):
                        prompt += f"- {key}: {json.dumps(val, default=str)[:200]}\n"
                    else:
                        prompt += f"- {key}: {val}\n"

        prompt += f"""
Provide a JSON response with:
{{"consistency_score": 0.0-1.0, "consistency_rating": "PASS|WARN|FAIL", "technical_assessment": "...", "recommendations": []}}
"""
        return prompt

    def _parse_llm_response(self, content: str) -> Dict[str, Any]:
        try:
            start = content.find("{")
            end = content.rfind("}") + 1
            if start != -1 and end > start:
                return json.loads(content[start:end])
        except json.JSONDecodeError:
            pass
        return {
            "consistency_rating": "WARN",
            "technical_assessment": content[:500]
        }

    async def _load_cached(self, filename: str) -> Dict[str, Any]:
        cached_file = self.config.results_dir / filename
        if cached_file.exists():
            with open(cached_file, "r") as f:
                return json.load(f)
        return {}

    def _is_step_done(self, pmid: str, step: str) -> bool:
        if self.progress and self.config.enable_resume:
            return self.progress.is_pmid_step_completed(pmid, step)
        return False

    def _mark_step_done(self, pmid: str, step: str):
        if self.progress:
            self.progress.mark_pmid_step_completed(pmid, step)

    async def _save_pmid_result(self, result: PMIDResult):
        output_file = self.config.results_dir / f"final_report_{result.pmid}.json"
        with open(output_file, "w") as f:
            json.dump(result.to_dict(), f, indent=2, default=str, ensure_ascii=False)

    async def _save_summary(self):
        summary = {
            "execution_summary": {
                "total_pmids": len(self.results),
                "completed": sum(
                    1 for r in self.results.values()
                    if r.status == PipelineStatus.COMPLETED
                ),
                "failed": sum(
                    1 for r in self.results.values()
                    if r.status == PipelineStatus.FAILED
                ),
                "debate_enabled": self.config.enable_debate,
                "enrichment_enabled": self.config.enable_enrichment,
                "data_aggregation_enabled": self.config.enable_data_aggregation,
            },
            "pmid_results": {
                pmid: result.to_dict()
                for pmid, result in self.results.items()
            },
            "timestamp": datetime.now().isoformat(),
        }

        output_file = self.config.results_dir / "execution_summary.json"
        with open(output_file, "w") as f:
            json.dump(summary, f, indent=2, default=str, ensure_ascii=False)


async def main():
    config = PipelineConfig(
        pmids=["40315330", "32416070"],
        results_dir=Path("./results"),
        max_concurrent=3
    )

    pipeline = AsyncPipeline(config)
    results = await pipeline.run()

    print(f"\n=== Pipeline Complete ===")
    for pmid, result in results.items():
        print(f"PMID {pmid}: {result.status.value} ({result.duration_seconds:.1f}s)")
        if result.debate_report.get("overall_verdict"):
            print(f"  Debate: {result.debate_report['overall_verdict']} "
                  f"(score: {result.debate_report.get('overall_score', 0):.2f})")


if __name__ == "__main__":
    asyncio.run(main())
