"""
Async Pipeline Module - Main Orchestrator
비동기 파이프라인 실행 관리 (통합 메인 파이프라인)
"""

import asyncio
import json
import logging
import os
import shutil
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any

from backends import LLMConfig, LLMRouter, OllamaBackend, OpenAIBackend
from backends.base import BackendStatus
from backends.router import RouterConfig
from core.progress_manager import ProgressManager
from plugins import PluginRegistry, register_default_plugins

logger = logging.getLogger(__name__)

try:
    import httpx
    HAS_HTTPX = True
except ImportError:
    HAS_HTTPX = False


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
    pubmed_metadata: dict[str, Any] = field(default_factory=dict)
    sra_results: dict[str, Any] = field(default_factory=dict)
    sequencing_result: dict[str, Any] = field(default_factory=dict)
    # Pipeline execution results (v4.0)
    fetchngs_result: dict[str, Any] = field(default_factory=dict)
    pipeline_execution: dict[str, Any] = field(default_factory=dict)
    downstream_analysis: dict[str, Any] = field(default_factory=dict)
    # Existing
    llm_analysis: dict[str, Any] = field(default_factory=dict)
    aggregated_data: dict[str, Any] = field(default_factory=dict)
    enrichment_results: dict[str, Any] = field(default_factory=dict)
    debate_report: dict[str, Any] = field(default_factory=dict)
    error: str = ""
    start_time: datetime | None = None
    end_time: datetime | None = None

    @property
    def duration_seconds(self) -> float:
        if self.start_time and self.end_time:
            return (self.end_time - self.start_time).total_seconds()
        return 0.0

    def to_dict(self) -> dict[str, Any]:
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
class LLMServerConfig:
    """LLM server settings from config.json pipeline_config.llm_server"""
    url: str = "http://localhost:11434"
    model: str = "auto"
    timeout: int = 120
    max_retries: int = 3


@dataclass
class LLMBackendConfig:
    """프로바이더별 LLM 백엔드 설정 (llm_providers.backends.{name})"""
    enabled: bool = False
    model: str = ""
    timeout: int = 120
    max_retries: int = 3
    max_tokens: int = 4096
    temperature: float = 0.1
    top_p: float = 0.9
    url: str = ""                   # Ollama 전용
    api_key_env: str = ""           # OpenAI/Anthropic
    base_url: str | None = None     # OpenAI (Azure 호환)


@dataclass
class LLMRouterSettings:
    """Router 설정 (llm_providers.router)"""
    strategy: str = "priority"
    priority_order: list[str] = field(
        default_factory=lambda: ["ollama", "openai", "anthropic"]
    )
    enable_auto_failover: bool = True
    health_check_interval: int = 60
    max_concurrent_requests: int = 10


@dataclass
class LLMProvidersConfig:
    """llm_providers 섹션 전체"""
    backends: dict[str, LLMBackendConfig] = field(default_factory=dict)
    router: LLMRouterSettings = field(default_factory=LLMRouterSettings)


@dataclass
class ContainerRuntimeConfig:
    """Container runtime settings from config.json pipeline_config.container_runtime"""
    preferred: str = "docker"
    fallback: str = "singularity"


@dataclass
class SRADownloadConfig:
    """SRA download settings from config.json pipeline_config.sra_download"""
    max_parallel: int = 4
    timeout_minutes: int = 30
    max_samples: int = 50


@dataclass
class DebateSettings:
    """Debate settings from config.json debate section"""
    num_rounds: int = 3
    consensus_threshold: float = 0.7
    enable_cross_examination: bool = True
    timeout_per_agent: int = 120
    parallel_assessment: bool = True
    specialist_max_rounds: int = 1
    agent_weights: dict[str, float] = field(default_factory=lambda: {
        "phd_expert": 0.20, "undergraduate": 0.12, "layperson": 0.08,
        "statistical_skeptic": 0.18, "biological_realist": 0.15,
        "experimental_critic": 0.13, "translation_evaluator": 0.14,
    })


@dataclass
class ResearchEvaluationConfig:
    """Research evaluation settings from config.json research_evaluation section"""
    enabled: bool = True
    meta_agent_enabled: bool = True
    dimensions: dict[str, dict] = field(default_factory=lambda: {
        "literature_redundancy": {"weight": 20},
        "data_support": {"weight": 25},
        "cross_dataset_reproducibility": {"weight": 20},
        "biological_plausibility": {"weight": 15},
        "technical_feasibility": {"weight": 10},
        "clinical_industrial_impact": {"weight": 10},
    })
    verdict_thresholds: dict[str, int] = field(default_factory=lambda: {
        "go": 75, "revise": 45, "drop": 0,
    })


@dataclass
class EnrichmentSettings:
    """Enrichment settings from config.json enrichment section"""
    gsea_gene_set_db: str = "KEGG_2021_Human"
    organism: str = "human"
    deg_fc_threshold: float = 1.5
    deg_padj_threshold: float = 0.05
    top_pathways_count: int = 10
    top_genes_count: int = 50


@dataclass
class DirectoriesConfig:
    """Directory paths from config.json directories section"""
    raw_data: str = "/workspace/raw_data"
    processed_data: str = "/workspace/processed_data"
    nextflow_work: str = "/workspace/nextflow_work"
    containers: str = "/workspace/containers"
    results: str = "/workspace/results"
    logs: str = "/workspace/logs"
    research_projects: str = "./research_projects"


@dataclass
class BraveSearchConfig:
    """Brave search settings from config.json brave_search section"""
    api_key_env: str = "BRAVE_API_KEY"
    timeout: int = 15
    results_per_query: int = 10
    enabled: bool = False


@dataclass
class RAGConfig:
    """RAG settings from config.json rag section"""
    enabled: bool = True
    persist_dir: str = "./results/rag_db"
    embedding_model: str = "all-MiniLM-L6-v2"
    max_context_tokens: int = 1500


@dataclass
class SearchConfig:
    """Search settings from config.json search section"""
    limit_per_source: int = 20
    pubmed_enabled: bool = True
    semantic_scholar_enabled: bool = True
    europe_pmc_enabled: bool = True
    brave_enabled: bool = False


@dataclass
class ExecutionConfig:
    """Execution settings from config.json execution section"""
    resume_enabled: bool = True
    progress_file: str = "/workspace/progress.json"
    log_level: str = "ERROR"
    dry_run_first: bool = True
    max_concurrent: int = 5
    enable_debate: bool = True
    enable_enrichment: bool = True
    enable_data_aggregation: bool = True


@dataclass
class PipelineConfig:
    pmids: list[str]
    results_dir: Path = Path("./results")
    max_concurrent: int = 5
    llm_router_config: RouterConfig | None = None
    enable_resume: bool = True
    enable_data_aggregation: bool = True
    enable_enrichment: bool = True
    enable_debate: bool = True
    debate_rounds: int = 3
    progress_file: str | None = None
    rag_dir: Path | None = None
    # Pipeline execution (v4.0)
    enable_pipeline_execution: bool = False
    nextflow_config: Any | None = None  # NextflowExecutionConfig
    # Project isolation (v4.1)
    project_slug: str | None = None

    # Config sections from config.json
    llm_server: LLMServerConfig = field(default_factory=LLMServerConfig)
    container_runtime: ContainerRuntimeConfig = field(default_factory=ContainerRuntimeConfig)
    sra_download: SRADownloadConfig = field(default_factory=SRADownloadConfig)
    debate_settings: DebateSettings = field(default_factory=DebateSettings)
    enrichment_settings: EnrichmentSettings = field(default_factory=EnrichmentSettings)
    directories: DirectoriesConfig = field(default_factory=DirectoriesConfig)
    brave_search: BraveSearchConfig = field(default_factory=BraveSearchConfig)
    rag_config: RAGConfig = field(default_factory=RAGConfig)
    search_config: SearchConfig = field(default_factory=SearchConfig)
    execution: ExecutionConfig = field(default_factory=ExecutionConfig)
    research_evaluation: ResearchEvaluationConfig = field(
        default_factory=ResearchEvaluationConfig
    )
    # Multi-provider LLM config (v4.2)
    llm_providers: LLMProvidersConfig | None = None

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "PipelineConfig":
        pipeline_cfg = data.get("pipeline_config", {})
        debate_data = data.get("debate", {})
        res_eval_data = data.get("research_evaluation", {})
        enrichment_data = data.get("enrichment", {})
        directories_data = data.get("directories", {})
        brave_data = data.get("brave_search", {})
        rag_data = data.get("rag", {})
        search_data = data.get("search", {})
        execution_data = data.get("execution", {})

        # LLM server config (legacy)
        llm_srv_data = pipeline_cfg.get("llm_server", {})
        llm_server = LLMServerConfig(
            url=llm_srv_data.get("url", "http://localhost:11434"),
            model=llm_srv_data.get("model", "auto"),
            timeout=llm_srv_data.get("timeout", 120),
            max_retries=llm_srv_data.get("max_retries", 3),
        )

        # Multi-provider LLM config (v4.2)
        llm_providers = None
        llm_providers_data = data.get("llm_providers")
        if llm_providers_data:
            backends_data = llm_providers_data.get("backends", {})
            parsed_backends = {}
            for name, bcfg in backends_data.items():
                parsed_backends[name] = LLMBackendConfig(
                    enabled=bcfg.get("enabled", False),
                    model=bcfg.get("model", ""),
                    timeout=bcfg.get("timeout", 120),
                    max_retries=bcfg.get("max_retries", 3),
                    max_tokens=bcfg.get("max_tokens", 4096),
                    temperature=bcfg.get("temperature", 0.1),
                    top_p=bcfg.get("top_p", 0.9),
                    url=bcfg.get("url", ""),
                    api_key_env=bcfg.get("api_key_env", ""),
                    base_url=bcfg.get("base_url"),
                )
            router_data = llm_providers_data.get("router", {})
            router_settings = LLMRouterSettings(
                strategy=router_data.get("strategy", "priority"),
                priority_order=router_data.get(
                    "priority_order", ["ollama", "openai", "anthropic"]
                ),
                enable_auto_failover=router_data.get(
                    "enable_auto_failover", True
                ),
                health_check_interval=router_data.get(
                    "health_check_interval", 60
                ),
                max_concurrent_requests=router_data.get(
                    "max_concurrent_requests", 10
                ),
            )
            llm_providers = LLMProvidersConfig(
                backends=parsed_backends,
                router=router_settings,
            )

        # Container runtime config
        cr_data = pipeline_cfg.get("container_runtime", {})
        container_runtime = ContainerRuntimeConfig(
            preferred=cr_data.get("preferred", "docker"),
            fallback=cr_data.get("fallback", "singularity"),
        )

        # SRA download config
        sra_data = pipeline_cfg.get("sra_download", {})
        sra_download = SRADownloadConfig(
            max_parallel=sra_data.get("max_parallel", 4),
            timeout_minutes=sra_data.get("timeout_minutes", 30),
            max_samples=sra_data.get("max_samples", 50),
        )

        # Debate settings
        debate_settings = DebateSettings(
            num_rounds=debate_data.get("num_rounds", 3),
            consensus_threshold=debate_data.get("consensus_threshold", 0.7),
            enable_cross_examination=debate_data.get("enable_cross_examination", True),
            timeout_per_agent=debate_data.get("timeout_per_agent", 120),
            parallel_assessment=debate_data.get("parallel_assessment", True),
            specialist_max_rounds=debate_data.get("specialist_max_rounds", 1),
            agent_weights=debate_data.get("agent_weights", {
                "phd_expert": 0.20, "undergraduate": 0.12, "layperson": 0.08,
                "statistical_skeptic": 0.18, "biological_realist": 0.15,
                "experimental_critic": 0.13, "translation_evaluator": 0.14,
            }),
        )

        # Research evaluation config
        res_eval_config = ResearchEvaluationConfig(
            enabled=res_eval_data.get("enabled", True),
            meta_agent_enabled=res_eval_data.get("meta_agent_enabled", True),
            dimensions=res_eval_data.get("dimensions", {
                "literature_redundancy": {"weight": 20},
                "data_support": {"weight": 25},
                "cross_dataset_reproducibility": {"weight": 20},
                "biological_plausibility": {"weight": 15},
                "technical_feasibility": {"weight": 10},
                "clinical_industrial_impact": {"weight": 10},
            }),
            verdict_thresholds=res_eval_data.get("verdict_thresholds", {
                "go": 75, "revise": 45, "drop": 0,
            }),
        )

        # Enrichment settings
        enrichment_settings = EnrichmentSettings(
            gsea_gene_set_db=enrichment_data.get("gsea_gene_set_db", "KEGG_2021_Human"),
            organism=enrichment_data.get("organism", "human"),
            deg_fc_threshold=enrichment_data.get("deg_fc_threshold", 1.5),
            deg_padj_threshold=enrichment_data.get("deg_padj_threshold", 0.05),
            top_pathways_count=enrichment_data.get("top_pathways_count", 10),
            top_genes_count=enrichment_data.get("top_genes_count", 50),
        )

        # Directories config
        directories = DirectoriesConfig(
            raw_data=directories_data.get("raw_data", "/workspace/raw_data"),
            processed_data=directories_data.get("processed_data", "/workspace/processed_data"),
            nextflow_work=directories_data.get("nextflow_work", "/workspace/nextflow_work"),
            containers=directories_data.get("containers", "/workspace/containers"),
            results=directories_data.get("results", "/workspace/results"),
            logs=directories_data.get("logs", "/workspace/logs"),
            research_projects=directories_data.get("research_projects", "./research_projects"),
        )

        # Brave search config
        brave_search = BraveSearchConfig(
            api_key_env=brave_data.get("api_key_env", "BRAVE_API_KEY"),
            timeout=brave_data.get("timeout", 15),
            results_per_query=brave_data.get("results_per_query", 10),
            enabled=brave_data.get("enabled", False),
        )

        # RAG config
        rag_config = RAGConfig(
            enabled=rag_data.get("enabled", True),
            persist_dir=rag_data.get("persist_dir", "./results/rag_db"),
            embedding_model=rag_data.get("embedding_model", "all-MiniLM-L6-v2"),
            max_context_tokens=rag_data.get("max_context_tokens", 1500),
        )

        # Search config
        search_config = SearchConfig(
            limit_per_source=search_data.get("limit_per_source", 20),
            pubmed_enabled=search_data.get("pubmed_enabled", True),
            semantic_scholar_enabled=search_data.get("semantic_scholar_enabled", True),
            europe_pmc_enabled=search_data.get("europe_pmc_enabled", True),
            brave_enabled=search_data.get("brave_enabled", False),
        )

        # Execution config (nested section values)
        exec_cfg = ExecutionConfig(
            resume_enabled=execution_data.get("resume_enabled", True),
            progress_file=execution_data.get("progress_file", "/workspace/progress.json"),
            log_level=execution_data.get("log_level", "ERROR"),
            dry_run_first=execution_data.get("dry_run_first", True),
            max_concurrent=execution_data.get("max_concurrent", 5),
            enable_debate=execution_data.get("enable_debate", True),
            enable_enrichment=execution_data.get("enable_enrichment", True),
            enable_data_aggregation=execution_data.get("enable_data_aggregation", True),
        )

        # Top-level flat keys override nested section values (backward compat)
        max_concurrent = data.get("max_concurrent", exec_cfg.max_concurrent)
        enable_resume = data.get("enable_resume", exec_cfg.resume_enabled)
        enable_data_aggregation = data.get(
            "enable_data_aggregation", exec_cfg.enable_data_aggregation,
        )
        enable_enrichment = data.get("enable_enrichment", exec_cfg.enable_enrichment)
        enable_debate = data.get("enable_debate", exec_cfg.enable_debate)
        debate_rounds = data.get("debate_rounds", debate_settings.num_rounds)

        # Determine results_dir: top-level first, then directories section
        if "results_dir" in data:
            results_dir_str = data["results_dir"]
        elif "results" in directories_data:
            results_dir_str = directories_data["results"]
        else:
            results_dir_str = "./results"

        # Determine rag_dir: top-level rag_dir, or from RAG config
        if "rag_dir" in data:
            rag_dir = Path(data["rag_dir"]) if data["rag_dir"] else None
        elif rag_config.enabled:
            rag_dir = Path(rag_config.persist_dir)
        else:
            rag_dir = None

        instance = cls(
            pmids=data.get("pmids", pipeline_cfg.get("test_pmids", [])),
            results_dir=Path(results_dir_str),
            max_concurrent=max_concurrent,
            enable_resume=enable_resume,
            enable_data_aggregation=enable_data_aggregation,
            enable_enrichment=enable_enrichment,
            enable_debate=enable_debate,
            debate_rounds=debate_rounds,
            progress_file=data.get(
                "progress_file", execution_data.get("progress_file"),
            ),
            rag_dir=rag_dir,
            project_slug=data.get("project_slug"),
            llm_server=llm_server,
            container_runtime=container_runtime,
            sra_download=sra_download,
            debate_settings=debate_settings,
            enrichment_settings=enrichment_settings,
            directories=directories,
            brave_search=brave_search,
            rag_config=rag_config,
            search_config=search_config,
            execution=exec_cfg,
            research_evaluation=res_eval_config,
            llm_providers=llm_providers,
        )
        # 원본 config dict 보존 (language 등 추가 설정 참조용)
        instance._raw_config = data
        return instance

    @classmethod
    def from_json(cls, config_path: str) -> "PipelineConfig":
        with open(config_path) as f:
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
        self.results: dict[str, PMIDResult] = {}
        self.llm_router: LLMRouter | None = None
        self.plugin_registry: PluginRegistry | None = None
        self.progress: ProgressManager | None = None
        self.data_aggregator = None
        self.debate_manager = None
        self.doc_store = None
        self.error_tracker = None
        self._semaphore = asyncio.Semaphore(config.max_concurrent)
        # LLM 동시 요청 방지 (qwen3:30b 단일 GPU 보호)
        self._llm_semaphore = asyncio.Semaphore(1)
        self._http_client: Any | None = None
        # Event bus for TUI / Web UI (optional)
        self.event_bus: Any | None = None
        # 터미널 상단 고정 상태바 (optional)
        self._sticky_header = None

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

        if self.config.llm_providers:
            # === Config-driven multi-provider (v4.2) ===
            providers_cfg = self.config.llm_providers
            for provider_name in providers_cfg.router.priority_order:
                bcfg = providers_cfg.backends.get(provider_name)
                if not bcfg or not bcfg.enabled:
                    continue
                llm_config = LLMConfig(
                    model=bcfg.model,
                    temperature=bcfg.temperature,
                    top_p=bcfg.top_p,
                    max_tokens=bcfg.max_tokens,
                    timeout=bcfg.timeout,
                    max_retries=bcfg.max_retries,
                )
                if provider_name == "ollama":
                    backends.append(OllamaBackend(
                        base_url=bcfg.url or "http://localhost:11434",
                        config=llm_config,
                    ))
                elif provider_name == "openai":
                    api_key = (
                        os.environ.get(bcfg.api_key_env)
                        if bcfg.api_key_env else None
                    )
                    if api_key:
                        backends.append(OpenAIBackend(
                            config=llm_config,
                            api_key=api_key,
                            base_url=bcfg.base_url,
                        ))
                    else:
                        logger.warning(
                            "OpenAI enabled but %s not set, skipping",
                            bcfg.api_key_env,
                        )
                elif provider_name == "anthropic":
                    try:
                        from backends import AnthropicBackend
                        api_key = (
                            os.environ.get(bcfg.api_key_env)
                            if bcfg.api_key_env else None
                        )
                        if api_key:
                            backends.append(AnthropicBackend(
                                config=llm_config,
                                api_key=api_key,
                            ))
                        else:
                            logger.warning(
                                "Anthropic enabled but %s not set, skipping",
                                bcfg.api_key_env,
                            )
                    except ImportError:
                        logger.warning(
                            "anthropic package not installed, skipping"
                        )
                else:
                    logger.warning(
                        "Unknown provider: %s, skipping", provider_name
                    )
            router_config = RouterConfig(
                strategy=providers_cfg.router.strategy,
                health_check_interval=(
                    providers_cfg.router.health_check_interval
                ),
                enable_auto_failover=(
                    providers_cfg.router.enable_auto_failover
                ),
                max_concurrent_requests=(
                    providers_cfg.router.max_concurrent_requests
                ),
            )
        else:
            # === Legacy path (backward compatible) ===
            llm_srv = self.config.llm_server
            ollama_config = LLMConfig(
                model=llm_srv.model,
                timeout=llm_srv.timeout,
                max_retries=llm_srv.max_retries,
                max_tokens=4096,
            )
            backends.append(OllamaBackend(
                base_url=llm_srv.url,
                config=ollama_config,
            ))
            if os.environ.get("OPENAI_API_KEY"):
                backends.append(OpenAIBackend(
                    config=LLMConfig(
                        model="gpt-4o",
                        timeout=llm_srv.timeout,
                        max_retries=llm_srv.max_retries,
                    ),
                ))
            try:
                from backends import AnthropicBackend
                if os.environ.get("ANTHROPIC_API_KEY"):
                    anthropic_config = LLMConfig(
                        model="claude-sonnet-4-20250514",
                        timeout=llm_srv.timeout,
                        max_retries=llm_srv.max_retries,
                    )
                    backends.append(AnthropicBackend(
                        config=anthropic_config,
                    ))
            except ImportError:
                pass
            router_config = self.config.llm_router_config or RouterConfig(
                strategy="priority",
                enable_auto_failover=True,
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
                logger.warning("clients 패키지 없음, 데이터 집계 비활성화")

        # Debate manager (lazy import)
        self.research_evaluator = None
        self.meta_agent = None
        if self.config.enable_debate and self.llm_router:
            try:
                from agents.base import AgentRole
                from agents.debate_manager import DebateConfig, DebateManager
                ds = self.config.debate_settings
                debate_config = DebateConfig(
                    num_rounds=self.config.debate_rounds,
                    consensus_threshold=ds.consensus_threshold,
                    enable_cross_examination=ds.enable_cross_examination,
                    timeout_per_agent=ds.timeout_per_agent,
                    parallel_assessment=ds.parallel_assessment,
                    specialist_max_rounds=ds.specialist_max_rounds,
                )
                # config의 agent_weights (str 키) → AgentRole enum 키 변환
                role_weights = None
                if ds.agent_weights:
                    role_map = {r.value: r for r in AgentRole if r != AgentRole.META_AGENT}
                    role_weights = {}
                    for k, v in ds.agent_weights.items():
                        if k in role_map:
                            role_weights[role_map[k]] = v
                self.debate_manager = DebateManager.create_default_panel(
                    self.llm_router, config=debate_config,
                    role_weights=role_weights,
                )
            except ImportError:
                logger.warning("agents 패키지 없음, 토론 비활성화")

            # Research Evaluation Scorer + Meta-Agent
            res_cfg = self.config.research_evaluation
            if res_cfg.enabled:
                try:
                    from agents.research_evaluation import ResearchEvaluationScorer
                    dim_weights = {
                        k: v.get("weight", 0)
                        for k, v in res_cfg.dimensions.items()
                    }
                    self.research_evaluator = ResearchEvaluationScorer(
                        dimension_weights=dim_weights,
                        verdict_thresholds=res_cfg.verdict_thresholds,
                    )
                except ImportError:
                    logger.warning("research_evaluation 모듈 없음, RES 비활성화")

            if res_cfg.meta_agent_enabled and self.llm_router:
                try:
                    from agents.meta_agent import MetaAgent
                    self.meta_agent = MetaAgent(self.llm_router)
                except ImportError:
                    logger.warning("meta_agent 모듈 없음, 메타 에이전트 비활성화")

        # Error tracker
        self.error_tracker = None
        try:
            from core.error_tracker import ErrorTracker
            self.error_tracker = ErrorTracker(self.config.results_dir)
        except Exception:
            pass

        # RAG document store (lazy import)
        if self.config.rag_dir:
            try:
                from rag.document_store import DocumentStore
                self.doc_store = DocumentStore(self.config.rag_dir)
            except ImportError:
                logger.warning("rag 패키지 없음, RAG 비활성화")

        # Nextflow execution layer (v4.0, lazy, conditional)
        self.nf_executor = None
        self.fetchngs_runner = None
        self.samplesheet_gen = None
        self.analysis_orchestrator = None

        if self.config.enable_pipeline_execution:
            try:
                from analysis import AnalysisOrchestrator
                from nextflow import (
                    FetchNGSRunner,
                    NextflowExecutor,
                    SamplesheetGenerator,
                )
                from nextflow.config import NextflowExecutionConfig

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
                    logger.warning("Nextflow not installed, pipeline execution disabled")
                    self.nf_executor = None
            except ImportError as e:
                logger.warning("nextflow/analysis packages not available: %s", e)

        # HTTP client
        if HAS_HTTPX:
            self._http_client = httpx.AsyncClient(
                timeout=float(self.config.llm_server.timeout),
            )

    def _emit(self, event_type: str, pmid: str = "", stage: str = "",
              message: str = "", **data):
        """이벤트 버스에 이벤트 발행 (TUI/Web UI용) + 상단 테이블 업데이트"""
        if self._sticky_header and pmid and stage:
            if "stage_start" in event_type:
                self._sticky_header.update(pmid=pmid, stage=stage)
            elif "stage_complete" in event_type:
                self._sticky_header.mark_done(pmid=pmid, stage=stage)
            elif "stage_fail" in event_type or "stage_error" in event_type:
                self._sticky_header.mark_fail(pmid=pmid, stage=stage)

        if not self.event_bus:
            return
        try:
            from core.events import EventType, PipelineEvent
            self.event_bus.emit(PipelineEvent(
                event_type=EventType(event_type),
                pmid=pmid, stage=stage, message=message,
                data=data,
            ))
        except Exception:
            pass

    async def shutdown(self):
        """리소스 정리"""
        if self._sticky_header:
            self._sticky_header.stop()
            self._sticky_header = None
        if self.llm_router:
            await self.llm_router.stop()
        if self._http_client:
            await self._http_client.aclose()
        if self.data_aggregator:
            await self.data_aggregator.close()

    async def run(self) -> dict[str, PMIDResult]:
        """전체 파이프라인 실행"""
        await self.initialize()

        # 터미널 상단 고정 상태바 시작
        try:
            from core.terminal_fx import StickyHeader
            model_name = ""
            if self.llm_router and self.llm_router.backends:
                for b in self.llm_router.backends:
                    if hasattr(b, "config") and b.config.model:
                        m = b.config.model
                        if m not in ("auto", ""):
                            model_name = m
                            break
            self._sticky_header = StickyHeader(
                model=model_name,
                total_pmids=len(self.config.pmids),
                pmids=list(self.config.pmids),
            )
            self._sticky_header.start()
        except Exception:
            self._sticky_header = None

        # LLM 백엔드 사전 검증 — 실패 시 즉시 중단
        if self.llm_router:
            llm_ok = False
            for backend in self.llm_router.backends.values():
                try:
                    if await backend.health_check():
                        llm_ok = True
                        break
                except Exception:
                    continue
            if not llm_ok:
                # 1회 추가 재시도 (간헐적 DNS 오류 대비)
                logger.warning("LLM 사전 검증 1차 실패, 3초 후 재시도")
                await asyncio.sleep(3)
                for backend in self.llm_router.backends.values():
                    try:
                        if await backend.health_check():
                            llm_ok = True
                            break
                    except Exception:
                        continue
            if not llm_ok:
                logger.error("LLM 백엔드 사전 검증 실패 — 파이프라인 중단")
                self._emit(
                    "pipeline_error",
                    message="LLM 백엔드에 연결할 수 없습니다. "
                            "Ollama 서버 상태를 확인하세요.",
                )
                await self.shutdown()
                return self.results

        self._emit(
            "pipeline_start",
            message=f"파이프라인 시작: {len(self.config.pmids)}개 PMID",
            pmid_count=len(self.config.pmids),
            pmids=self.config.pmids,
        )

        try:
            # 순차 처리: PMID를 하나씩 실행, 실패 시 전체 중단
            abort = False
            for pmid in self.config.pmids:
                if abort:
                    self.results[pmid] = PMIDResult(
                        pmid=pmid,
                        status=PipelineStatus.FAILED,
                        error="이전 PMID 실패로 중단됨",
                    )
                    if self._sticky_header:
                        self._sticky_header.mark_skip(pmid)
                    continue

                try:
                    result = await self._process_pmid(pmid)
                    self.results[pmid] = result

                    # LLM 단계(Stage 6+7) 완전 실패 감지 → 중단
                    if (result.status == PipelineStatus.FAILED
                            and "백엔드 실패" in (result.error or "")):
                        logger.error(
                            "PMID %s LLM 백엔드 실패 — 나머지 PMID 중단", pmid
                        )
                        abort = True

                except Exception as exc:
                    self.results[pmid] = PMIDResult(
                        pmid=pmid,
                        status=PipelineStatus.FAILED,
                        error=str(exc),
                    )
                    # 연결 오류는 전체 중단
                    err_str = str(exc).lower()
                    if any(k in err_str for k in (
                        "connection", "dns", "resolution", "refused",
                    )):
                        logger.error("연결 오류로 파이프라인 중단: %s", exc)
                        abort = True

            await self._save_summary()
            await self._save_queue_manifest()

            # 종합보고서 자동 생성 (2개 이상 성공)
            success_count = sum(
                1 for r in self.results.values()
                if r.status == PipelineStatus.COMPLETED
            )
            if success_count >= 2:
                await self._generate_project_report()

            self._emit(
                "pipeline_complete",
                message=f"파이프라인 완료: {len(self.results)}개 결과",
            )

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
            self._emit("pmid_start", pmid=pmid, message=f"PMID {pmid} 처리 시작")

            if self.progress:
                self.progress.set_current_pmid(pmid)

            try:
                # Stage 1: PubMed 메타데이터
                self._emit("pmid_stage_start", pmid=pmid, stage="pubmed")
                if not self._is_step_done(pmid, "pubmed_done"):
                    pubmed_metadata = await self._fetch_pubmed(pmid)
                    result.pubmed_metadata = pubmed_metadata
                    self._mark_step_done(pmid, "pubmed_done")
                else:
                    result.pubmed_metadata = await self._load_cached(
                        f"pubmed_{pmid}.json"
                    )
                self._emit(
                    "pmid_stage_complete", pmid=pmid, stage="pubmed",
                    message=result.pubmed_metadata.get("title", "")[:80],
                )

                # Stage 2: SRA 탐색
                self._emit("pmid_stage_start", pmid=pmid, stage="sra")
                if not self._is_step_done(pmid, "sra_discovery_done"):
                    sra_results = await self._explore_sra(pmid, result.pubmed_metadata)
                    result.sra_results = sra_results
                    self._mark_step_done(pmid, "sra_discovery_done")
                else:
                    result.sra_results = await self._load_cached(
                        f"sra_exploration_{pmid}.json"
                    )
                self._emit("pmid_stage_complete", pmid=pmid, stage="sra")

                # Stage 3: 시퀀싱 타입 탐지
                self._emit("pmid_stage_start", pmid=pmid, stage="sequencing")
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

                self._emit(
                    "pmid_stage_complete", pmid=pmid, stage="sequencing",
                    message=result.sequencing_result.get(
                        "sequencing_type", ""
                    ) if isinstance(result.sequencing_result, dict) else "",
                )

                # Organism detection → auto-set genome for Nextflow
                if self.config.enable_pipeline_execution:
                    try:
                        from core.organism_detector import OrganismDetector

                        detection_result = OrganismDetector.detect_organism(
                            result.pubmed_metadata
                        )
                        result.sequencing_result["organism_detection"] = (
                            detection_result
                        )
                        nf_cfg = self.config.nextflow_config
                        if (
                            nf_cfg
                            and detection_result["genome"]
                            and detection_result["confidence"] >= 0.6
                        ):
                            nf_cfg.genome = detection_result["genome"]
                            logger.info(
                                "PMID %s: auto-detected organism '%s' → "
                                "genome %s (confidence %.2f)",
                                pmid,
                                detection_result["organism"],
                                detection_result["genome"],
                                detection_result["confidence"],
                            )
                    except Exception as e:
                        logger.warning(
                            "Organism detection failed for PMID %s: %s",
                            pmid, e,
                        )

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
                self._emit("pmid_stage_start", pmid=pmid, stage="data_aggregation")
                if self.data_aggregator:
                    try:
                        aggregated = await self.data_aggregator.aggregate(
                            pmid=pmid,
                            doi=result.pubmed_metadata.get("doi"),
                        )
                        result.aggregated_data = aggregated.to_dict()
                    except Exception as e:
                        result.aggregated_data = {"error": str(e)}

                self._emit(
                    "pmid_stage_complete", pmid=pmid,
                    stage="data_aggregation",
                )

                # Stage 5: 농축 분석
                self._emit("pmid_stage_start", pmid=pmid, stage="enrichment")
                if self.config.enable_enrichment:
                    try:
                        enrichment = await self._run_enrichment(result)
                        result.enrichment_results = enrichment
                    except Exception as e:
                        result.enrichment_results = {"error": str(e)}

                self._emit("pmid_stage_complete", pmid=pmid, stage="enrichment")

                # Stage 6+7: LLM 분석 및 토론 (세마포어로 동시 요청 방지)
                async with self._llm_semaphore:
                    # Stage 6: LLM 멀티 합의 분석
                    self._emit(
                        "pmid_stage_start", pmid=pmid, stage="llm_consensus",
                    )
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

                    self._emit(
                        "pmid_stage_complete", pmid=pmid,
                        stage="llm_consensus",
                    )

                    # Stage 7: 멀티 에이전트 토론
                    self._emit("pmid_stage_start", pmid=pmid, stage="debate")
                    if self.debate_manager:
                        # HPC 파이프라인 작업과 리소스 경합 방지
                        await self._wait_for_hpc_idle()
                        try:
                            research_data = {
                                "paper_info": result.pubmed_metadata or {},
                                "sequencing_type": (
                                    result.sequencing_result.get(
                                        "sequencing_type", "Unknown"
                                    )
                                    if isinstance(result.sequencing_result, dict)
                                    else "Unknown"
                                ),
                                "pipeline_info": result.sequencing_result or {},
                                "analysis_results": {
                                    **(result.aggregated_data or {}),
                                    **(result.enrichment_results or {}),
                                    **(result.llm_analysis or {}),
                                },
                            }
                            debate_result = (
                                await self.debate_manager.run_debate(research_data)
                            )
                            result.debate_report = debate_result.to_dict()

                            # Stage 7.5: RES + Meta-Agent
                            await self._run_research_evaluation(
                                result, research_data, debate_result,
                            )
                        except Exception as e:
                            result.debate_report = {"error": str(e)}
                            self._emit(
                                "pmid_stage_error", pmid=pmid,
                                stage="debate", message=str(e),
                            )
                    self._emit(
                        "pmid_stage_complete", pmid=pmid, stage="debate",
                    )

                # Stage 7.8: 토론 보고서 번역 (language 설정 참조)
                lang_cfg = getattr(self.config, "_raw_config", {}).get(
                    "language", {},
                )
                translate_debate = lang_cfg.get("translate_debate", True)
                primary_lang = lang_cfg.get("primary", "en")
                secondary_lang = lang_cfg.get("secondary", "ko")
                trans_model = lang_cfg.get("translation_model", "auto")

                if (translate_debate
                        and primary_lang != secondary_lang
                        and result.debate_report
                        and not result.debate_report.get("error")):
                    try:
                        from core.translator import translate_debate_report
                        ollama_url = self.config.llm_server.url
                        ko_report = await translate_debate_report(
                            result.debate_report, ollama_url,
                            model=trans_model if trans_model != "auto" else None,
                            source_lang=primary_lang,
                            target_lang=secondary_lang,
                        )
                        if ko_report:
                            result.debate_report["debate_ko"] = ko_report
                    except Exception as e:
                        logger.warning("토론 번역 실패: %s", e)

                # Stage 8: RAG 인덱싱 (옵션)
                self._emit("pmid_stage_start", pmid=pmid, stage="rag_indexing")
                if self.doc_store:
                    try:
                        self._index_result_in_rag(result)
                    except Exception as e:
                        logger.warning("RAG 인덱싱 실패: %s", e)
                        if self.error_tracker:
                            self.error_tracker.record(
                                stage="rag_indexing", pmid=pmid,
                                error=e, severity="WARNING",
                            )
                self._emit(
                    "pmid_stage_complete", pmid=pmid, stage="rag_indexing",
                )

                # Stage 9: 완료
                self._emit("pmid_stage_start", pmid=pmid, stage="report")

                # LLM 분석 + 토론 모두 실패 → 전체 실패 처리
                llm_failed = (
                    isinstance(result.llm_analysis, dict)
                    and result.llm_analysis.get("error")
                    and not result.llm_analysis.get("consensus")
                )
                debate_failed = (
                    isinstance(result.debate_report, dict)
                    and result.debate_report.get("error")
                )
                if llm_failed and debate_failed:
                    result.status = PipelineStatus.FAILED
                    result.error = (
                        f"LLM 백엔드 실패: "
                        f"{result.llm_analysis.get('error', 'unknown')}"
                    )
                else:
                    result.status = PipelineStatus.COMPLETED

                self._mark_step_done(pmid, "final_report_done")
                self._emit(
                    "pmid_stage_complete", pmid=pmid, stage="report",
                )

            except Exception as e:
                result.status = PipelineStatus.FAILED
                result.error = str(e)
                self._emit(
                    "pmid_stage_error", pmid=pmid,
                    message=str(e),
                )
                if self.progress:
                    self.progress.add_failed_step(
                        f"pmid_{pmid}", str(e)
                    )
                if self.error_tracker:
                    self.error_tracker.record(
                        stage="pipeline",
                        pmid=pmid,
                        error=e,
                        severity="ERROR",
                    )

            result.end_time = datetime.now()
            self._emit(
                "pmid_complete", pmid=pmid,
                message=result.status.value,
                status=result.status.value,
            )
            await self._save_pmid_result(result)
            return result

    async def _fetch_pubmed(self, pmid: str) -> dict[str, Any]:
        """PubMed 메타데이터 수집 (캐시 지원)"""
        pmid_dir = self._pmid_dir(pmid)
        cached_file = pmid_dir / f"pubmed_{pmid}.json"

        if cached_file.exists():
            with open(cached_file) as f:
                return json.load(f)

        try:
            from core.pubmed_client import PubMedClient
            client = PubMedClient()
            metadata = await asyncio.to_thread(
                client.fetch_paper_metadata, pmid
            )
            if metadata:
                with open(cached_file, "w") as f:
                    json.dump(metadata, f, indent=2, default=str)
                return metadata
        except ImportError:
            pass

        return {"pmid": pmid, "title": "", "abstract": "", "source": "unavailable"}

    async def _explore_sra(
        self, pmid: str, pubmed_metadata: dict[str, Any]
    ) -> dict[str, Any]:
        """SRA 데이터 탐색 (캐시 지원)"""
        pmid_dir = self._pmid_dir(pmid)
        cached_file = pmid_dir / f"sra_exploration_{pmid}.json"

        if cached_file.exists():
            with open(cached_file) as f:
                return json.load(f)

        try:
            from core.sra_explorer import SRAExplorer
            explorer = SRAExplorer(
                results_dir=str(self.config.results_dir),
                download_timeout=self.config.sra_download.timeout_minutes * 60,
            )
            sra_links = pubmed_metadata.get("sra_links", [])
            result = await asyncio.to_thread(
                explorer.explore_sra_datasets, pmid, sra_links
            )
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
        pubmed_metadata: dict[str, Any],
        sequencing_result: dict[str, Any],
        downstream_analysis: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """LLM 멀티 합의: 모든 건강한 백엔드에 동시 쿼리 후 가중 합의"""
        pmid_dir = self._pmid_dir(pmid)
        cached_file = pmid_dir / f"deepseek_analysis_{pmid}.json"

        if cached_file.exists():
            with open(cached_file) as f:
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

    def _merge_consensus(self, results: list[dict[str, Any]]) -> dict[str, Any]:
        """여러 LLM 결과를 가중 합의로 병합"""
        total_weight = sum(r.get("health_score", 1.0) for r in results)

        # 점수 가중 평균
        weighted_score = sum(
            r.get("consistency_score", 0.5) * r.get("health_score", 1.0)
            for r in results
        ) / max(total_weight, 0.001)

        # 등급 투표 (가중)
        rating_votes: dict[str, float] = {}
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

    async def _run_research_evaluation(
        self,
        result: PMIDResult,
        research_data: dict[str, Any],
        debate_result: Any,
    ):
        """Stage 7.5: RES 평가 + 메타 에이전트 종합 판정"""
        debate_dict = debate_result.to_dict()

        # RES 평가
        if self.research_evaluator:
            try:
                agent_scores = debate_dict.get("per_agent_scores", {})
                multi_pmid = len(self.config.pmids) > 1
                res_result = self.research_evaluator.evaluate(
                    research_data=research_data,
                    agent_scores=agent_scores,
                    enrichment_data=result.enrichment_results or {},
                    novelty_data={
                        "score": (result.enrichment_results or {}).get(
                            "novelty_score", 0.5
                        ),
                    },
                    aggregated_data=result.aggregated_data or {},
                    multi_pmid=multi_pmid,
                )
                result.debate_report["research_evaluation"] = res_result.to_dict()
            except Exception as e:
                logger.warning("RES 평가 실패: %s", e)
                result.debate_report["research_evaluation"] = {"error": str(e)}

        # 메타 에이전트 판정
        if self.meta_agent:
            try:
                res_dict = result.debate_report.get("research_evaluation")
                meta_verdict = await self.meta_agent.synthesize(
                    research_data=research_data,
                    debate_result=debate_dict,
                    res_result=res_dict if isinstance(res_dict, dict) else None,
                )
                result.debate_report["meta_verdict"] = meta_verdict.to_dict()
            except Exception as e:
                logger.warning("메타 에이전트 판정 실패: %s", e)
                result.debate_report["meta_verdict"] = {"error": str(e)}

    async def _run_enrichment(self, result: PMIDResult) -> dict[str, Any]:
        """농축 분석 실행 (GSEA, DEG, Pathway)"""
        try:
            from enrichment import GSEAAnalyzer, NoveltyScorer, PathwayAnalyzer
            enrichment_data: dict[str, Any] = {}

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

    def _extract_genes_from_metadata(self, result: PMIDResult) -> list[str]:
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

        # Enrichment 결과 인덱싱
        if result.enrichment_results and not result.enrichment_results.get("error"):
            try:
                text = json.dumps(result.enrichment_results, ensure_ascii=False)
                top_pathways = []
                if "top_pathways" in result.enrichment_results:
                    top_pathways = [
                        p.get("name", str(p)) if isinstance(p, dict) else str(p)
                        for p in result.enrichment_results["top_pathways"][:10]
                    ]
                self.doc_store.add_enrichment(
                    pmid=pmid,
                    enrichment_text=text,
                    top_pathways=top_pathways,
                    novelty_score=result.enrichment_results.get("novelty_score", 0.0),
                )
            except Exception as e:
                logger.debug("Enrichment RAG 인덱싱 실패: %s", e)

        # 파이프라인 실행 메타데이터 인덱싱
        seq_type = "unknown"
        if isinstance(result.sequencing_result, dict):
            seq_type = result.sequencing_result.get("sequencing_type", "unknown")
        try:
            params = {
                "genome": getattr(self.config, "genome", ""),
                "sequencing_type": seq_type,
                "enable_debate": self.config.enable_debate,
                "enable_enrichment": self.config.enable_enrichment,
            }
            self.doc_store.add_pipeline_run(
                pmid=pmid,
                pipeline_type=seq_type,
                params_summary=json.dumps(params, ensure_ascii=False),
                success=result.status == PipelineStatus.COMPLETED,
            )
        except Exception as e:
            logger.debug("Pipeline run RAG 인덱싱 실패: %s", e)

    def _build_analysis_prompt(
        self,
        pubmed_metadata: dict[str, Any],
        sequencing_result: dict[str, Any],
        downstream_analysis: dict[str, Any] | None = None,
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

        prompt += """
Provide a JSON response with:
{"consistency_score": 0.0-1.0, "consistency_rating": "PASS|WARN|FAIL", "technical_assessment": "...", "recommendations": []}
"""
        return prompt

    def _parse_llm_response(self, content: str) -> dict[str, Any]:
        from core.json_utils import extract_json_from_llm
        result = extract_json_from_llm(content)
        if result:
            return result
        return {
            "consistency_rating": "WARN",
            "technical_assessment": content[:500]
        }

    async def _wait_for_hpc_idle(
        self,
        check_interval: int = 30,
        max_wait: int = 1800,
    ):
        """
        Slurm HPC 노드의 부하가 낮아질 때까지 대기.

        nf-core 파이프라인이 Slurm에서 실행 중이면
        토론(LLM 호출)을 지연시켜 리소스 경합을 방지합니다.

        확인 항목:
        1. squeue: 현재 사용자의 RUNNING 상태 Nextflow/nf-core 작업 수
        2. sinfo: 노드의 CPU 할당률 (AllocCPU/TotalCPU)

        Args:
            check_interval: 체크 간격 (초, 기본 30초)
            max_wait: 최대 대기 시간 (초, 기본 1800초 = 30분)
        """
        if not shutil.which("squeue"):
            return  # Slurm이 없으면 즉시 진행

        waited = 0
        while waited < max_wait:
            try:
                # squeue: 현재 사용자의 RUNNING 작업 수 확인
                proc = await asyncio.create_subprocess_exec(
                    "squeue", "--me", "--states=RUNNING",
                    "--format=%j", "--noheader",
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                )
                stdout, _ = await proc.communicate()
                running_jobs = [
                    line for line in stdout.decode().strip().split("\n")
                    if line.strip()
                ]
                nf_jobs = [
                    j for j in running_jobs
                    if any(k in j.lower() for k in ("nf-", "nextflow", "nfcore"))
                ]

                if not nf_jobs:
                    if waited > 0:
                        logger.info("HPC 파이프라인 작업 완료, 토론 시작")
                    return

                # sinfo: 노드 CPU 할당률 체크
                alloc_ratio = await self._get_slurm_cpu_alloc_ratio()

                logger.info(
                    "HPC 파이프라인 작업 %d개 실행 중 "
                    "(CPU 할당률: %.0f%%), "
                    "%d초 후 재확인... (%d/%ds)",
                    len(nf_jobs), alloc_ratio,
                    check_interval, waited, max_wait,
                )

            except Exception as e:
                logger.warning("Slurm 상태 확인 실패: %s, 토론 진행", e)
                return

            await asyncio.sleep(check_interval)
            waited += check_interval

        logger.warning("HPC 대기 타임아웃 (%ds), 토론 강제 시작", max_wait)

    @staticmethod
    async def _get_slurm_cpu_alloc_ratio() -> float:
        """Slurm 노드의 CPU 할당률(%) 반환."""
        try:
            proc = await asyncio.create_subprocess_exec(
                "sinfo", "--Node", "--noheader",
                "--format=%C",  # CPUS(A/I/O/T) 형식
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, _ = await proc.communicate()
            lines = stdout.decode().strip().split("\n")
            total_alloc = 0
            total_cpus = 0
            for line in lines:
                parts = line.strip().split("/")
                if len(parts) == 4:
                    alloc = int(parts[0])
                    total = int(parts[3])
                    total_alloc += alloc
                    total_cpus += total
            if total_cpus > 0:
                return (total_alloc / total_cpus) * 100
        except Exception:
            pass
        return 0.0

    async def _load_cached(self, filename: str) -> dict[str, Any]:
        """캐시 파일 로드 (PMID 서브폴더 → 루트 폴백)"""
        # filename 예: "pubmed_31061532.json" → PMID 추출
        import re
        m = re.search(r'(\d{5,})', filename)
        if m:
            pmid_dir_path = self.config.results_dir / m.group(1) / filename
            if pmid_dir_path.exists():
                with open(pmid_dir_path) as f:
                    return json.load(f)
        # 루트 폴백 (하위 호환)
        cached_file = self.config.results_dir / filename
        if cached_file.exists():
            with open(cached_file) as f:
                return json.load(f)
        return {}

    def _is_step_done(self, pmid: str, step: str) -> bool:
        if self.progress and self.config.enable_resume:
            return self.progress.is_pmid_step_completed(pmid, step)
        return False

    def _mark_step_done(self, pmid: str, step: str):
        if self.progress:
            self.progress.mark_pmid_step_completed(pmid, step)

    def _pmid_dir(self, pmid: str) -> Path:
        """PMID별 결과 서브폴더"""
        d = self.config.results_dir / pmid
        d.mkdir(parents=True, exist_ok=True)
        return d

    async def _save_pmid_result(self, result: PMIDResult):
        pmid_dir = self._pmid_dir(result.pmid)
        output_file = pmid_dir / f"final_report_{result.pmid}.json"
        result_dict = result.to_dict()
        # debate_report 전체 데이터를 JSON에 포함
        if result.debate_report:
            result_dict["debate_report"] = result.debate_report
        with open(output_file, "w") as f:
            json.dump(result_dict, f, indent=2, default=str, ensure_ascii=False)

        # HTML 리포트 자동 생성
        try:
            from core.report_generator import ReportGenerator
            gen = ReportGenerator()
            html_path = pmid_dir / f"report_{result.pmid}.html"
            gen.generate(result_dict, html_path)
            logger.info("HTML report: %s", html_path)
        except Exception as e:
            logger.warning("HTML 리포트 생성 실패: %s", e)

    async def _generate_project_report(self):
        """종합보고서 자동 생성 (2+ PMID)"""
        try:
            from core.report_generator import ReportGenerator

            # 각 PMID의 final_report JSON 로드
            reports = []
            for pmid in self.results:
                json_path = self._pmid_dir(pmid) / f"final_report_{pmid}.json"
                if json_path.exists():
                    with open(json_path) as f:
                        reports.append(json.load(f))

            if len(reports) < 2:
                return

            # 프로젝트 메타데이터 구성
            project_meta = {
                "name": self.config.project_slug or "Analysis",
                "slug": self.config.project_slug or "analysis",
                "description": f"{len(reports)} PMIDs 종합 분석",
                "keywords": [],
                "pmids": list(self.results.keys()),
                "created_at": datetime.now().isoformat(),
            }

            gen = ReportGenerator()
            output = self.config.results_dir / "project_report.html"
            gen.generate_project_report(project_meta, reports, output)
            logger.info("종합보고서 생성: %s (%d PMIDs)", output, len(reports))
        except Exception as e:
            logger.warning("종합보고서 생성 실패: %s", e)

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

    async def _save_queue_manifest(self):
        """Queue 매니페스트 저장 (웹 대시보드 결과 탐색용)"""
        queue_dir = self.config.results_dir / ".queues"
        queue_dir.mkdir(parents=True, exist_ok=True)

        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        slug = self.config.project_slug or "analysis"
        queue_id = f"{ts}_{slug}"

        completed = sum(
            1 for r in self.results.values()
            if r.status == PipelineStatus.COMPLETED
        )
        failed = sum(
            1 for r in self.results.values()
            if r.status == PipelineStatus.FAILED
        )

        manifest = {
            "queue_id": queue_id,
            "name": self.config.project_slug or f"Analysis {ts[:8]}",
            "pmids": list(self.results.keys()),
            "timestamp": datetime.now().isoformat(),
            "status": "completed" if completed == len(self.results) else "partial",
            "completed": completed,
            "failed": failed,
        }

        output = queue_dir / f"{queue_id}.json"
        with open(output, "w") as f:
            json.dump(manifest, f, indent=2, ensure_ascii=False)


async def main():
    config = PipelineConfig(
        pmids=["40315330", "32416070"],
        results_dir=Path("./results"),
        max_concurrent=3
    )

    pipeline = AsyncPipeline(config)
    results = await pipeline.run()

    print("\n=== Pipeline Complete ===")
    for pmid, result in results.items():
        print(f"PMID {pmid}: {result.status.value} ({result.duration_seconds:.1f}s)")
        if result.debate_report.get("overall_verdict"):
            print(f"  Debate: {result.debate_report['overall_verdict']} "
                  f"(score: {result.debate_report.get('overall_score', 0):.2f})")


if __name__ == "__main__":
    asyncio.run(main())
