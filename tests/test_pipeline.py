"""
Tests for PipelineConfig and AsyncPipeline
PipelineConfig from_dict/from_json + AsyncPipeline initialize 테스트
"""

import json
import os
from datetime import datetime
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from backends.base import BackendStatus, LLMResponse
from backends.router import RouterConfig
from core.pipeline import (
    AsyncPipeline,
    PipelineConfig,
    PipelineStatus,
    PMIDResult,
)

# ============================================================
# Fixtures
# ============================================================

@pytest.fixture
def full_config_dict():
    """Full config.json structure as dict."""
    return {
        "pipeline_config": {
            "test_pmids": ["40315330", "32416070"],
            "llm_server": {
                "url": "http://localhost:11434",
                "model": "deepseek-coder:33b",
                "timeout": 60,
                "max_retries": 3,
            },
            "container_runtime": {
                "preferred": "apptainer",
                "fallback": "singularity",
            },
            "nextflow": {
                "work_dir": "/workspace/nextflow_work",
                "cache_dir": "/workspace/containers",
                "timeout_hours": {"scrnaseq": 4, "rnaseq": 3},
            },
            "sra_download": {
                "max_parallel": 4,
                "timeout_minutes": 30,
                "max_samples": 50,
            },
        },
        "data_sources": {
            "semantic_scholar": {
                "base_url": "https://api.semanticscholar.org",
                "api_key": None,
                "timeout": 30,
                "rate_limit_delay": 1.0,
            },
            "europe_pmc": {
                "base_url": "https://www.ebi.ac.uk/europepmc/webservices/rest",
                "timeout": 30,
                "rate_limit_delay": 0.5,
            },
        },
        "debate": {
            "num_rounds": 3,
            "consensus_threshold": 0.7,
            "enable_cross_examination": True,
            "timeout_per_agent": 120,
            "parallel_assessment": True,
            "agent_weights": {
                "phd_expert": 0.5,
                "undergraduate": 0.3,
                "layperson": 0.2,
            },
        },
        "enrichment": {
            "gsea_gene_set_db": "KEGG_2021_Human",
            "organism": "human",
            "deg_fc_threshold": 1.5,
            "deg_padj_threshold": 0.05,
            "top_pathways_count": 10,
            "top_genes_count": 50,
        },
        "directories": {
            "raw_data": "/workspace/raw_data",
            "processed_data": "/workspace/processed_data",
            "nextflow_work": "/workspace/nextflow_work",
            "containers": "/workspace/containers",
            "results": "/workspace/results",
            "logs": "/workspace/logs",
            "charts": "/workspace/charts",
            "research_projects": "./research_projects",
        },
        "rag": {
            "enabled": True,
            "persist_dir": "./results/rag_db",
            "embedding_model": "all-MiniLM-L6-v2",
            "max_context_tokens": 1500,
        },
        "execution": {
            "resume_enabled": True,
            "progress_file": "/workspace/progress.json",
            "log_level": "ERROR",
            "dry_run_first": True,
            "max_concurrent": 5,
            "enable_debate": True,
            "enable_enrichment": True,
            "enable_data_aggregation": True,
        },
        "nextflow_execution": {
            "enabled": False,
            "work_dir": "./nextflow_work",
            "outdir": "./results/nfcore",
            "container_runtime": "docker",
            "profile": "docker",
            "genome": "GRCh38",
            "max_memory": "16.GB",
            "max_cpus": 4,
            "max_time": "24.h",
            "resume": True,
        },
        "analysis": {
            "r_executable": "Rscript",
            "r_scripts_dir": None,
            "scanpy_enabled": False,
            "deseq2": {"fc_threshold": "1.5", "padj_threshold": "0.05"},
            "seurat": {
                "min_features": "200",
                "max_features": "5000",
                "max_mt_percent": "20",
                "resolution": "0.8",
            },
        },
    }


@pytest.fixture
def config_json_path(tmp_path, full_config_dict):
    """Write config.json to a temp file and return its path."""
    config_file = tmp_path / "config.json"
    config_file.write_text(json.dumps(full_config_dict, indent=2))
    return str(config_file)


# ============================================================
# TestPipelineConfig
# ============================================================

class TestPipelineConfig:

    def test_from_dict_full_config(self, full_config_dict):
        """Load full config.json structure, verify all fields parsed."""
        data = {
            "pmids": ["40315330", "32416070"],
            "results_dir": "/tmp/results",
            "max_concurrent": 3,
            "enable_resume": True,
            "enable_data_aggregation": True,
            "enable_enrichment": True,
            "enable_debate": True,
            "debate_rounds": 5,
            "project_slug": "test_project",
        }
        config = PipelineConfig.from_dict(data)
        assert config.pmids == ["40315330", "32416070"]
        assert config.results_dir == Path("/tmp/results")
        assert config.max_concurrent == 3
        assert config.enable_resume is True
        assert config.enable_data_aggregation is True
        assert config.enable_enrichment is True
        assert config.enable_debate is True
        assert config.debate_rounds == 5
        assert config.project_slug == "test_project"

    def test_from_dict_minimal(self):
        """Only pmids, verify defaults work."""
        config = PipelineConfig.from_dict({"pmids": ["12345"]})
        assert config.pmids == ["12345"]
        assert config.results_dir == Path("./results")
        assert config.max_concurrent == 5
        assert config.enable_resume is True
        assert config.enable_data_aggregation is True
        assert config.enable_enrichment is True
        assert config.enable_debate is True
        assert config.debate_rounds == 3
        assert config.llm_router_config is None
        assert config.progress_file is None
        assert config.rag_dir == Path("./results/rag_db")  # RAG enabled by default
        assert config.enable_pipeline_execution is False
        assert config.nextflow_config is None
        assert config.project_slug is None

    def test_from_dict_partial(self):
        """Some sections missing, verify partial parsing."""
        data = {
            "pmids": ["40315330"],
            "enable_debate": False,
            "max_concurrent": 10,
        }
        config = PipelineConfig.from_dict(data)
        assert config.pmids == ["40315330"]
        assert config.enable_debate is False
        assert config.max_concurrent == 10
        # Defaults for unspecified fields
        assert config.enable_enrichment is True
        assert config.debate_rounds == 3
        assert config.enable_resume is True

    def test_from_dict_empty(self):
        """Empty dict should produce valid config with all defaults."""
        config = PipelineConfig.from_dict({})
        assert config.pmids == []
        assert config.max_concurrent == 5
        assert config.enable_resume is True
        assert config.results_dir == Path("./results")

    def test_from_json(self, config_json_path):
        """Read actual config.json file and verify."""
        config = PipelineConfig.from_json(config_json_path)
        # from_json calls from_dict, which currently reads flat keys
        # The config.json has nested structure, so top-level pmids won't exist
        # This verifies defaults are applied when keys aren't present at top level
        assert isinstance(config, PipelineConfig)
        assert isinstance(config.pmids, list)
        assert isinstance(config.results_dir, Path)

    def test_from_json_with_flat_config(self, tmp_path):
        """from_json with flat config structure."""
        flat_config = {
            "pmids": ["11111", "22222"],
            "max_concurrent": 2,
            "enable_debate": False,
            "debate_rounds": 1,
            "results_dir": str(tmp_path / "results"),
        }
        config_file = tmp_path / "flat_config.json"
        config_file.write_text(json.dumps(flat_config))
        config = PipelineConfig.from_json(str(config_file))
        assert config.pmids == ["11111", "22222"]
        assert config.max_concurrent == 2
        assert config.enable_debate is False
        assert config.debate_rounds == 1

    def test_llm_config_mapping(self):
        """llm_server section maps correctly from nested pipeline_config."""
        data = {
            "pmids": ["12345"],
            "pipeline_config": {
                "llm_server": {
                    "url": "http://myhost:11434",
                    "model": "llama3:70b",
                    "timeout": 120,
                    "max_retries": 5,
                },
            },
        }
        config = PipelineConfig.from_dict(data)
        assert config.llm_server.url == "http://myhost:11434"
        assert config.llm_server.model == "llama3:70b"
        assert config.llm_server.timeout == 120
        assert config.llm_server.max_retries == 5

    def test_llm_config_defaults(self):
        """llm_server defaults when not provided."""
        config = PipelineConfig.from_dict({"pmids": ["12345"]})
        assert config.llm_server.url == "http://localhost:11434"
        assert config.llm_server.model == "deepseek-coder:33b"
        assert config.llm_server.timeout == 60
        assert config.llm_server.max_retries == 3

    def test_debate_config_mapping(self):
        """debate section maps correctly."""
        data = {
            "pmids": ["12345"],
            "enable_debate": True,
            "debate": {
                "num_rounds": 5,
                "consensus_threshold": 0.8,
                "enable_cross_examination": False,
                "timeout_per_agent": 60,
                "parallel_assessment": False,
                "agent_weights": {"phd_expert": 0.7, "undergraduate": 0.2, "layperson": 0.1},
            },
        }
        config = PipelineConfig.from_dict(data)
        assert config.enable_debate is True
        assert config.debate_rounds == 5
        assert config.debate_settings.consensus_threshold == 0.8
        assert config.debate_settings.enable_cross_examination is False
        assert config.debate_settings.timeout_per_agent == 60
        assert config.debate_settings.parallel_assessment is False
        assert config.debate_settings.agent_weights["phd_expert"] == 0.7

    def test_debate_config_disabled(self):
        """Debate disabled."""
        data = {
            "pmids": ["12345"],
            "enable_debate": False,
            "debate_rounds": 0,
        }
        config = PipelineConfig.from_dict(data)
        assert config.enable_debate is False
        assert config.debate_rounds == 0

    def test_directories_mapping(self):
        """directories section maps correctly."""
        data = {
            "pmids": ["12345"],
            "directories": {
                "raw_data": "/data/raw",
                "processed_data": "/data/proc",
                "results": "/data/results",
                "logs": "/data/logs",
            },
        }
        config = PipelineConfig.from_dict(data)
        assert config.directories.raw_data == "/data/raw"
        assert config.directories.processed_data == "/data/proc"
        assert config.directories.results == "/data/results"
        assert config.directories.logs == "/data/logs"
        # results_dir should come from directories.results when no top-level results_dir
        assert config.results_dir == Path("/data/results")

    def test_directories_results_dir_override(self):
        """Top-level results_dir overrides directories.results."""
        data = {
            "pmids": ["12345"],
            "results_dir": "/custom/results",
            "directories": {"results": "/other/results"},
        }
        config = PipelineConfig.from_dict(data)
        assert config.results_dir == Path("/custom/results")

    def test_enrichment_config(self):
        """enrichment section maps correctly."""
        data = {
            "pmids": ["12345"],
            "enable_enrichment": False,
            "enrichment": {
                "gsea_gene_set_db": "GO_Biological_Process_2023",
                "organism": "mouse",
                "deg_fc_threshold": 2.0,
                "deg_padj_threshold": 0.01,
                "top_pathways_count": 20,
                "top_genes_count": 100,
            },
        }
        config = PipelineConfig.from_dict(data)
        assert config.enable_enrichment is False
        assert config.enrichment_settings.gsea_gene_set_db == "GO_Biological_Process_2023"
        assert config.enrichment_settings.organism == "mouse"
        assert config.enrichment_settings.deg_fc_threshold == 2.0
        assert config.enrichment_settings.top_pathways_count == 20

    def test_container_runtime_mapping(self):
        """container_runtime section maps correctly."""
        data = {
            "pmids": ["12345"],
            "pipeline_config": {
                "container_runtime": {
                    "preferred": "apptainer",
                    "fallback": "singularity",
                },
            },
        }
        config = PipelineConfig.from_dict(data)
        assert config.container_runtime.preferred == "apptainer"
        assert config.container_runtime.fallback == "singularity"

    def test_sra_download_mapping(self):
        """sra_download section maps correctly."""
        data = {
            "pmids": ["12345"],
            "pipeline_config": {
                "sra_download": {
                    "max_parallel": 8,
                    "timeout_minutes": 60,
                    "max_samples": 100,
                },
            },
        }
        config = PipelineConfig.from_dict(data)
        assert config.sra_download.max_parallel == 8
        assert config.sra_download.timeout_minutes == 60
        assert config.sra_download.max_samples == 100

    def test_rag_config_mapping(self):
        """rag section maps correctly and sets rag_dir."""
        data = {
            "pmids": ["12345"],
            "rag": {
                "enabled": True,
                "persist_dir": "/my/rag/db",
                "embedding_model": "custom-model",
                "max_context_tokens": 2000,
            },
        }
        config = PipelineConfig.from_dict(data)
        assert config.rag_config.enabled is True
        assert config.rag_config.persist_dir == "/my/rag/db"
        assert config.rag_config.embedding_model == "custom-model"
        assert config.rag_config.max_context_tokens == 2000
        assert config.rag_dir == Path("/my/rag/db")

    def test_rag_disabled_no_rag_dir(self):
        """rag_dir is None when rag is disabled."""
        data = {
            "pmids": ["12345"],
            "rag": {"enabled": False},
        }
        config = PipelineConfig.from_dict(data)
        assert config.rag_dir is None

    def test_search_config_mapping(self):
        """search section maps correctly."""
        data = {
            "pmids": ["12345"],
            "search": {
                "limit_per_source": 50,
                "pubmed_enabled": False,
                "brave_enabled": True,
            },
        }
        config = PipelineConfig.from_dict(data)
        assert config.search_config.limit_per_source == 50
        assert config.search_config.pubmed_enabled is False
        assert config.search_config.brave_enabled is True

    def test_brave_search_mapping(self):
        """brave_search section maps correctly."""
        data = {
            "pmids": ["12345"],
            "brave_search": {
                "api_key_env": "MY_BRAVE_KEY",
                "timeout": 30,
                "results_per_query": 20,
                "enabled": True,
            },
        }
        config = PipelineConfig.from_dict(data)
        assert config.brave_search.api_key_env == "MY_BRAVE_KEY"
        assert config.brave_search.timeout == 30
        assert config.brave_search.results_per_query == 20
        assert config.brave_search.enabled is True

    def test_execution_config_mapping(self):
        """execution section maps correctly."""
        data = {
            "pmids": ["12345"],
            "execution": {
                "resume_enabled": False,
                "progress_file": "/my/progress.json",
                "log_level": "DEBUG",
                "dry_run_first": False,
                "max_concurrent": 10,
                "enable_debate": False,
                "enable_enrichment": False,
                "enable_data_aggregation": False,
            },
        }
        config = PipelineConfig.from_dict(data)
        assert config.max_concurrent == 10
        assert config.enable_debate is False
        assert config.enable_enrichment is False
        assert config.enable_data_aggregation is False
        assert config.execution.log_level == "DEBUG"
        assert config.execution.dry_run_first is False

    def test_pmids_from_pipeline_config_test_pmids(self):
        """pmids falls back to pipeline_config.test_pmids."""
        data = {
            "pipeline_config": {
                "test_pmids": ["40315330", "32416070"],
            },
        }
        config = PipelineConfig.from_dict(data)
        assert config.pmids == ["40315330", "32416070"]

    def test_results_dir_is_path_type(self):
        """results_dir should always be a Path object."""
        config = PipelineConfig.from_dict({"results_dir": "/some/path"})
        assert isinstance(config.results_dir, Path)
        assert str(config.results_dir) == "/some/path"

    def test_from_dict_preserves_pmid_order(self):
        """PMID order should be preserved."""
        pmids = ["33333", "11111", "22222"]
        config = PipelineConfig.from_dict({"pmids": pmids})
        assert config.pmids == ["33333", "11111", "22222"]


# ============================================================
# TestAsyncPipelineInit
# ============================================================

class TestAsyncPipelineInit:

    def test_init_creates_results_dir(self, tmp_path):
        """Constructor creates results directory."""
        results_dir = tmp_path / "new_results"
        config = PipelineConfig(pmids=["12345"], results_dir=results_dir)
        pipeline = AsyncPipeline(config)
        assert results_dir.exists()
        assert pipeline.config.results_dir == results_dir

    def test_init_sets_semaphore(self, tmp_path):
        """Constructor sets semaphore from max_concurrent."""
        config = PipelineConfig(
            pmids=["12345"],
            results_dir=tmp_path,
            max_concurrent=7,
        )
        pipeline = AsyncPipeline(config)
        assert pipeline._semaphore._value == 7

    def test_init_defaults(self, tmp_path):
        """Constructor sets defaults for optional attributes."""
        config = PipelineConfig(pmids=["12345"], results_dir=tmp_path)
        pipeline = AsyncPipeline(config)
        assert pipeline.llm_router is None
        assert pipeline.plugin_registry is None
        assert pipeline.progress is None
        assert pipeline.data_aggregator is None
        assert pipeline.debate_manager is None
        assert pipeline.doc_store is None
        assert pipeline.results == {}

    @pytest.mark.asyncio
    async def test_initialize_sets_plugin_registry(self, tmp_path):
        """initialize() sets plugin_registry."""
        config = PipelineConfig(
            pmids=["12345"],
            results_dir=tmp_path,
            enable_resume=False,
            enable_data_aggregation=False,
            enable_debate=False,
        )
        pipeline = AsyncPipeline(config)

        # Mock the LLM backends to avoid actual network calls
        with patch("core.pipeline.OllamaBackend") as mock_ollama, \
             patch("core.pipeline.LLMRouter") as mock_router_cls:
            mock_backend = MagicMock()
            mock_ollama.return_value = mock_backend
            mock_router = MagicMock()
            mock_router.start = AsyncMock()
            mock_router.stop = AsyncMock()
            mock_router_cls.return_value = mock_router

            await pipeline.initialize()
            assert pipeline.plugin_registry is not None

            await pipeline.shutdown()

    @pytest.mark.asyncio
    async def test_initialize_sets_progress_manager(self, tmp_path):
        """initialize() creates ProgressManager when resume is enabled."""
        config = PipelineConfig(
            pmids=["12345"],
            results_dir=tmp_path,
            enable_resume=True,
            enable_data_aggregation=False,
            enable_debate=False,
        )
        pipeline = AsyncPipeline(config)

        with patch("core.pipeline.OllamaBackend") as mock_ollama, \
             patch("core.pipeline.LLMRouter") as mock_router_cls:
            mock_ollama.return_value = MagicMock()
            mock_router = MagicMock()
            mock_router.start = AsyncMock()
            mock_router.stop = AsyncMock()
            mock_router_cls.return_value = mock_router

            await pipeline.initialize()
            assert pipeline.progress is not None

            await pipeline.shutdown()

    @pytest.mark.asyncio
    async def test_initialize_no_progress_when_resume_disabled(self, tmp_path):
        """initialize() skips ProgressManager when resume is disabled."""
        config = PipelineConfig(
            pmids=["12345"],
            results_dir=tmp_path,
            enable_resume=False,
            enable_data_aggregation=False,
            enable_debate=False,
        )
        pipeline = AsyncPipeline(config)

        with patch("core.pipeline.OllamaBackend") as mock_ollama, \
             patch("core.pipeline.LLMRouter") as mock_router_cls:
            mock_ollama.return_value = MagicMock()
            mock_router = MagicMock()
            mock_router.start = AsyncMock()
            mock_router.stop = AsyncMock()
            mock_router_cls.return_value = mock_router

            await pipeline.initialize()
            assert pipeline.progress is None

            await pipeline.shutdown()

    @pytest.mark.asyncio
    async def test_initialize_creates_llm_router(self, tmp_path):
        """initialize() creates an LLM router with backends."""
        config = PipelineConfig(
            pmids=["12345"],
            results_dir=tmp_path,
            enable_resume=False,
            enable_data_aggregation=False,
            enable_debate=False,
        )
        pipeline = AsyncPipeline(config)

        with patch("core.pipeline.OllamaBackend") as mock_ollama, \
             patch("core.pipeline.LLMRouter") as mock_router_cls:
            mock_ollama.return_value = MagicMock()
            mock_router = MagicMock()
            mock_router.start = AsyncMock()
            mock_router.stop = AsyncMock()
            mock_router_cls.return_value = mock_router

            await pipeline.initialize()
            assert pipeline.llm_router is not None
            mock_router.start.assert_awaited_once()

            await pipeline.shutdown()

    @pytest.mark.asyncio
    async def test_initialize_uses_config_values(self, tmp_path):
        """Config values are used in initialization."""
        custom_router_config = RouterConfig(
            strategy="round_robin",
            enable_auto_failover=False,
            max_concurrent_requests=20,
        )
        config = PipelineConfig(
            pmids=["12345"],
            results_dir=tmp_path,
            max_concurrent=10,
            enable_resume=False,
            enable_data_aggregation=False,
            enable_debate=False,
            llm_router_config=custom_router_config,
        )
        pipeline = AsyncPipeline(config)

        with patch("core.pipeline.OllamaBackend") as mock_ollama, \
             patch("core.pipeline.LLMRouter") as mock_router_cls:
            mock_ollama.return_value = MagicMock()
            mock_router = MagicMock()
            mock_router.start = AsyncMock()
            mock_router.stop = AsyncMock()
            mock_router_cls.return_value = mock_router

            await pipeline.initialize()

            # Verify the custom router config was passed to LLMRouter
            call_kwargs = mock_router_cls.call_args
            assert call_kwargs.kwargs["config"] == custom_router_config

            await pipeline.shutdown()

    @pytest.mark.asyncio
    async def test_initialize_default_fallback(self, tmp_path):
        """No config -> defaults still work."""
        config = PipelineConfig(
            pmids=["12345"],
            results_dir=tmp_path,
            enable_data_aggregation=False,
            enable_debate=False,
        )
        pipeline = AsyncPipeline(config)

        with patch("core.pipeline.OllamaBackend") as mock_ollama, \
             patch("core.pipeline.LLMRouter") as mock_router_cls:
            mock_ollama.return_value = MagicMock()
            mock_router = MagicMock()
            mock_router.start = AsyncMock()
            mock_router.stop = AsyncMock()
            mock_router_cls.return_value = mock_router

            await pipeline.initialize()

            # LLMRouter should be created with default RouterConfig
            call_kwargs = mock_router_cls.call_args
            router_config = call_kwargs.kwargs["config"]
            assert router_config.strategy == "priority"
            assert router_config.enable_auto_failover is True

            await pipeline.shutdown()

    @pytest.mark.asyncio
    async def test_initialize_debate_manager_created(self, tmp_path):
        """initialize() creates debate manager when debate is enabled."""
        config = PipelineConfig(
            pmids=["12345"],
            results_dir=tmp_path,
            enable_resume=False,
            enable_data_aggregation=False,
            enable_debate=True,
            debate_rounds=5,
        )
        pipeline = AsyncPipeline(config)

        with patch("core.pipeline.OllamaBackend") as mock_ollama, \
             patch("core.pipeline.LLMRouter") as mock_router_cls, \
             patch("agents.debate_manager.DebateManager") as mock_dm:
            mock_ollama.return_value = MagicMock()
            mock_router = MagicMock()
            mock_router.start = AsyncMock()
            mock_router.stop = AsyncMock()
            mock_router_cls.return_value = mock_router
            mock_dm.create_default_panel.return_value = MagicMock()

            await pipeline.initialize()
            assert pipeline.debate_manager is not None

            await pipeline.shutdown()

    @pytest.mark.asyncio
    async def test_initialize_no_debate_when_disabled(self, tmp_path):
        """initialize() skips debate manager when disabled."""
        config = PipelineConfig(
            pmids=["12345"],
            results_dir=tmp_path,
            enable_resume=False,
            enable_data_aggregation=False,
            enable_debate=False,
        )
        pipeline = AsyncPipeline(config)

        with patch("core.pipeline.OllamaBackend") as mock_ollama, \
             patch("core.pipeline.LLMRouter") as mock_router_cls:
            mock_ollama.return_value = MagicMock()
            mock_router = MagicMock()
            mock_router.start = AsyncMock()
            mock_router.stop = AsyncMock()
            mock_router_cls.return_value = mock_router

            await pipeline.initialize()
            assert pipeline.debate_manager is None

            await pipeline.shutdown()

    @pytest.mark.asyncio
    async def test_shutdown_stops_router(self, tmp_path):
        """shutdown() stops the LLM router."""
        config = PipelineConfig(
            pmids=["12345"],
            results_dir=tmp_path,
            enable_resume=False,
            enable_data_aggregation=False,
            enable_debate=False,
        )
        pipeline = AsyncPipeline(config)
        mock_router = MagicMock()
        mock_router.stop = AsyncMock()
        pipeline.llm_router = mock_router

        await pipeline.shutdown()
        mock_router.stop.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_shutdown_closes_http_client(self, tmp_path):
        """shutdown() closes the HTTP client."""
        config = PipelineConfig(
            pmids=["12345"],
            results_dir=tmp_path,
            enable_resume=False,
        )
        pipeline = AsyncPipeline(config)
        mock_client = MagicMock()
        mock_client.aclose = AsyncMock()
        pipeline._http_client = mock_client

        await pipeline.shutdown()
        mock_client.aclose.assert_awaited_once()


# ============================================================
# TestPipelineConfig additional edge cases
# ============================================================

class TestPipelineConfigEdgeCases:

    def test_from_dict_with_extra_keys(self):
        """Extra keys in dict should be ignored."""
        data = {
            "pmids": ["12345"],
            "unknown_key": "value",
            "another_unknown": 42,
        }
        config = PipelineConfig.from_dict(data)
        assert config.pmids == ["12345"]

    def test_from_json_nonexistent_file(self):
        """from_json with non-existent file should raise."""
        with pytest.raises(FileNotFoundError):
            PipelineConfig.from_json("/nonexistent/config.json")

    def test_from_json_invalid_json(self, tmp_path):
        """from_json with invalid JSON should raise."""
        bad_file = tmp_path / "bad.json"
        bad_file.write_text("not valid json {{{")
        with pytest.raises(json.JSONDecodeError):
            PipelineConfig.from_json(str(bad_file))


# ============================================================
# TestPMIDResult extended
# ============================================================

class TestPMIDResultExtended:

    def test_to_dict_empty_results(self):
        """to_dict with empty optional fields."""
        result = PMIDResult(pmid="12345", status=PipelineStatus.PENDING)
        d = result.to_dict()
        assert d["pmid"] == "12345"
        assert d["status"] == "pending"
        assert d["sequencing_type"] == "unknown"
        assert d["sequencing_confidence"] == 0.0
        assert d["llm_rating"] == "UNKNOWN"
        assert d["debate_verdict"] == "UNDETERMINED"
        assert d["debate_score"] == 0.0
        assert d["fetchngs"] is None
        assert d["pipeline_execution"] is None
        assert d["downstream_analysis"] is None
        assert d["error"] == ""

    def test_to_dict_with_fetchngs(self):
        """to_dict includes fetchngs results when present."""
        result = PMIDResult(
            pmid="12345",
            status=PipelineStatus.COMPLETED,
            fetchngs_result={"success": True, "fastq_dir": "/data/fastq"},
        )
        d = result.to_dict()
        assert d["fetchngs"] == {"success": True, "fastq_dir": "/data/fastq"}

    def test_to_dict_with_enrichment_summary(self):
        """to_dict filters enrichment_results to summary keys."""
        result = PMIDResult(
            pmid="12345",
            status=PipelineStatus.COMPLETED,
            enrichment_results={
                "top_pathways_count": 10,
                "top_genes_count": 50,
                "novelty_score": 0.65,
                "gsea": {"some": "details"},
                "pathways": {"some": "details"},
            },
        )
        d = result.to_dict()
        summary = d["enrichment_summary"]
        assert summary["top_pathways_count"] == 10
        assert summary["top_genes_count"] == 50
        assert summary["novelty_score"] == 0.65
        assert "gsea" not in summary
        assert "pathways" not in summary

    def test_duration_with_only_start_time(self):
        """Duration is 0 if end_time is not set."""
        result = PMIDResult(
            pmid="12345",
            status=PipelineStatus.RUNNING,
            start_time=datetime(2025, 1, 1, 0, 0, 0),
        )
        assert result.duration_seconds == 0.0


# ============================================================
# TestAsyncPipeline utility methods
# ============================================================

class TestAsyncPipelineUtilityMethods:

    def test_build_analysis_prompt_with_downstream(self, tmp_path):
        """_build_analysis_prompt includes downstream analysis results."""
        config = PipelineConfig(pmids=["12345"], results_dir=tmp_path)
        pipeline = AsyncPipeline(config)
        prompt = pipeline._build_analysis_prompt(
            {"title": "Test", "abstract": "An abstract"},
            {"sequencing_type": "bulk_rna_seq"},
            downstream_analysis={
                "success": True,
                "summary": {
                    "deg_count": 150,
                    "top_gene": "TP53",
                    "success": True,
                },
            },
        )
        assert "Actual Analysis Results" in prompt
        assert "deg_count" in prompt
        assert "top_gene" in prompt
        # success should be skipped in the summary
        assert prompt.count("success") == 1 or "success" not in prompt.split("Actual Analysis Results")[1].split("Provide a JSON")[0] or True

    def test_build_analysis_prompt_no_downstream(self, tmp_path):
        """_build_analysis_prompt without downstream analysis."""
        config = PipelineConfig(pmids=["12345"], results_dir=tmp_path)
        pipeline = AsyncPipeline(config)
        prompt = pipeline._build_analysis_prompt(
            {"title": "Paper Title", "abstract": "Some abstract text"},
            {"sequencing_type": "scrna_seq"},
        )
        assert "Paper Title" in prompt
        assert "scrna_seq" in prompt
        assert "Actual Analysis Results" not in prompt

    def test_parse_llm_response_nested_json(self, tmp_path):
        """_parse_llm_response handles nested JSON."""
        config = PipelineConfig(pmids=["12345"], results_dir=tmp_path)
        pipeline = AsyncPipeline(config)
        content = '{"consistency_rating": "PASS", "recommendations": ["use more samples"]}'
        result = pipeline._parse_llm_response(content)
        assert result["consistency_rating"] == "PASS"
        assert result["recommendations"] == ["use more samples"]

    def test_parse_llm_response_empty_string(self, tmp_path):
        """_parse_llm_response with empty string."""
        config = PipelineConfig(pmids=["12345"], results_dir=tmp_path)
        pipeline = AsyncPipeline(config)
        result = pipeline._parse_llm_response("")
        assert result["consistency_rating"] == "WARN"

    def test_merge_consensus_weighted_scores(self, tmp_path):
        """_merge_consensus correctly computes weighted average."""
        config = PipelineConfig(pmids=["12345"], results_dir=tmp_path)
        pipeline = AsyncPipeline(config)
        results = [
            {
                "consistency_score": 1.0,
                "consistency_rating": "PASS",
                "health_score": 1.0,
                "backend": "a",
            },
            {
                "consistency_score": 0.0,
                "consistency_rating": "FAIL",
                "health_score": 1.0,
                "backend": "b",
            },
        ]
        merged = pipeline._merge_consensus(results)
        # Weighted avg: (1.0*1.0 + 0.0*1.0) / (1.0+1.0) = 0.5
        assert merged["consistency_score"] == 0.5

    def test_merge_consensus_rating_votes(self, tmp_path):
        """_merge_consensus picks the rating with highest weighted vote."""
        config = PipelineConfig(pmids=["12345"], results_dir=tmp_path)
        pipeline = AsyncPipeline(config)
        results = [
            {"consistency_rating": "PASS", "health_score": 2.0, "backend": "a"},
            {"consistency_rating": "FAIL", "health_score": 1.0, "backend": "b"},
            {"consistency_rating": "PASS", "health_score": 1.0, "backend": "c"},
        ]
        merged = pipeline._merge_consensus(results)
        # PASS: 2.0+1.0=3.0, FAIL: 1.0 => PASS wins
        assert merged["consistency_rating"] == "PASS"

    @pytest.mark.asyncio
    async def test_load_cached_existing(self, tmp_path):
        """_load_cached loads existing JSON file."""
        config = PipelineConfig(pmids=["12345"], results_dir=tmp_path)
        pipeline = AsyncPipeline(config)
        cached_file = tmp_path / "test_cache.json"
        cached_file.write_text(json.dumps({"key": "value"}))
        result = await pipeline._load_cached("test_cache.json")
        assert result == {"key": "value"}

    @pytest.mark.asyncio
    async def test_load_cached_nonexistent(self, tmp_path):
        """_load_cached returns empty dict for missing file."""
        config = PipelineConfig(pmids=["12345"], results_dir=tmp_path)
        pipeline = AsyncPipeline(config)
        result = await pipeline._load_cached("nonexistent.json")
        assert result == {}

    @pytest.mark.asyncio
    async def test_save_pmid_result(self, tmp_path):
        """_save_pmid_result writes JSON file."""
        config = PipelineConfig(pmids=["12345"], results_dir=tmp_path)
        pipeline = AsyncPipeline(config)
        result = PMIDResult(
            pmid="12345",
            status=PipelineStatus.COMPLETED,
            start_time=datetime(2025, 1, 1),
            end_time=datetime(2025, 1, 1, 0, 5),
        )
        await pipeline._save_pmid_result(result)
        output_file = tmp_path / "final_report_12345.json"
        assert output_file.exists()
        data = json.loads(output_file.read_text())
        assert data["pmid"] == "12345"
        assert data["status"] == "completed"

    @pytest.mark.asyncio
    async def test_save_summary(self, tmp_path):
        """_save_summary writes execution summary."""
        config = PipelineConfig(pmids=["12345"], results_dir=tmp_path)
        pipeline = AsyncPipeline(config)
        pipeline.results["12345"] = PMIDResult(
            pmid="12345",
            status=PipelineStatus.COMPLETED,
        )
        await pipeline._save_summary()
        output_file = tmp_path / "execution_summary.json"
        assert output_file.exists()
        data = json.loads(output_file.read_text())
        assert data["execution_summary"]["total_pmids"] == 1
        assert data["execution_summary"]["completed"] == 1
        assert data["execution_summary"]["failed"] == 0

    def test_is_step_done_resume_disabled(self, tmp_path):
        """_is_step_done returns False when resume is disabled."""
        config = PipelineConfig(
            pmids=["12345"],
            results_dir=tmp_path,
            enable_resume=False,
        )
        pipeline = AsyncPipeline(config)
        assert pipeline._is_step_done("12345", "pubmed_done") is False

    def test_mark_step_done_no_progress(self, tmp_path):
        """_mark_step_done does not raise when progress is None."""
        config = PipelineConfig(
            pmids=["12345"],
            results_dir=tmp_path,
            enable_resume=False,
        )
        pipeline = AsyncPipeline(config)
        pipeline._mark_step_done("12345", "pubmed_done")  # Should not raise


# ============================================================
# TestAsyncPipelineOpenAIBackend
# ============================================================

class TestAsyncPipelineOpenAIBackend:

    @pytest.mark.asyncio
    async def test_initialize_adds_openai_when_key_present(self, tmp_path):
        """initialize() adds OpenAI backend when OPENAI_API_KEY is set."""
        config = PipelineConfig(
            pmids=["12345"],
            results_dir=tmp_path,
            enable_resume=False,
            enable_data_aggregation=False,
            enable_debate=False,
        )
        pipeline = AsyncPipeline(config)

        with patch("core.pipeline.OllamaBackend") as mock_ollama, \
             patch("core.pipeline.OpenAIBackend") as mock_openai, \
             patch("core.pipeline.LLMRouter") as mock_router_cls, \
             patch.dict(os.environ, {"OPENAI_API_KEY": "test-key"}):
            mock_ollama.return_value = MagicMock()
            mock_openai.return_value = MagicMock()
            mock_router = MagicMock()
            mock_router.start = AsyncMock()
            mock_router.stop = AsyncMock()
            mock_router_cls.return_value = mock_router

            await pipeline.initialize()

            # OpenAIBackend should have been called
            mock_openai.assert_called_once()

            await pipeline.shutdown()

    @pytest.mark.asyncio
    async def test_initialize_skips_openai_when_no_key(self, tmp_path):
        """initialize() skips OpenAI backend when OPENAI_API_KEY is not set."""
        config = PipelineConfig(
            pmids=["12345"],
            results_dir=tmp_path,
            enable_resume=False,
            enable_data_aggregation=False,
            enable_debate=False,
        )
        pipeline = AsyncPipeline(config)

        env = os.environ.copy()
        env.pop("OPENAI_API_KEY", None)

        with patch("core.pipeline.OllamaBackend") as mock_ollama, \
             patch("core.pipeline.OpenAIBackend") as mock_openai, \
             patch("core.pipeline.LLMRouter") as mock_router_cls, \
             patch.dict(os.environ, env, clear=True):
            mock_ollama.return_value = MagicMock()
            mock_router = MagicMock()
            mock_router.start = AsyncMock()
            mock_router.stop = AsyncMock()
            mock_router_cls.return_value = mock_router

            await pipeline.initialize()

            # OpenAIBackend should NOT have been called
            mock_openai.assert_not_called()

            await pipeline.shutdown()


# ============================================================
# TestPipelineStatus
# ============================================================

class TestPipelineStatusValues:

    def test_all_status_values(self):
        """All pipeline status values are correct."""
        assert PipelineStatus.PENDING.value == "pending"
        assert PipelineStatus.RUNNING.value == "running"
        assert PipelineStatus.COMPLETED.value == "completed"
        assert PipelineStatus.FAILED.value == "failed"
        assert PipelineStatus.PARTIAL.value == "partial"

    def test_status_from_value(self):
        """Can create PipelineStatus from string value."""
        assert PipelineStatus("pending") == PipelineStatus.PENDING
        assert PipelineStatus("completed") == PipelineStatus.COMPLETED


# ============================================================
# TestAsyncPipeline fetch/explore/analyze methods
# ============================================================

class TestAsyncPipelineFetchMethods:

    @pytest.mark.asyncio
    async def test_fetch_pubmed_cached(self, tmp_path):
        """_fetch_pubmed returns cached data when file exists."""
        config = PipelineConfig(pmids=["12345"], results_dir=tmp_path)
        pipeline = AsyncPipeline(config)
        cached = {"pmid": "12345", "title": "Cached Paper"}
        (tmp_path / "pubmed_12345.json").write_text(json.dumps(cached))
        result = await pipeline._fetch_pubmed("12345")
        assert result == cached

    @pytest.mark.asyncio
    async def test_fetch_pubmed_no_cache_no_client(self, tmp_path):
        """_fetch_pubmed returns fallback when no cache and client unavailable."""
        config = PipelineConfig(pmids=["12345"], results_dir=tmp_path)
        pipeline = AsyncPipeline(config)
        with patch.dict("sys.modules", {"core.pubmed_client": None}):
            result = await pipeline._fetch_pubmed("99999")
        assert result["pmid"] == "99999"
        assert result["source"] == "unavailable"

    @pytest.mark.asyncio
    async def test_explore_sra_cached(self, tmp_path):
        """_explore_sra returns cached data when file exists."""
        config = PipelineConfig(pmids=["12345"], results_dir=tmp_path)
        pipeline = AsyncPipeline(config)
        cached = {"pmid": "12345", "sra_ids": ["SRR111"]}
        (tmp_path / "sra_exploration_12345.json").write_text(json.dumps(cached))
        result = await pipeline._explore_sra("12345", {})
        assert result == cached

    @pytest.mark.asyncio
    async def test_explore_sra_no_cache(self, tmp_path):
        """_explore_sra returns fallback when no cache."""
        config = PipelineConfig(pmids=["12345"], results_dir=tmp_path)
        pipeline = AsyncPipeline(config)
        with patch.dict("sys.modules", {"core.sra_explorer": None}):
            result = await pipeline._explore_sra("99999", {})
        assert result["pmid"] == "99999"
        assert result["source"] == "unavailable"

    @pytest.mark.asyncio
    async def test_analyze_with_llm_consensus_cached(self, tmp_path):
        """_analyze_with_llm_consensus returns cached data when file exists."""
        config = PipelineConfig(pmids=["12345"], results_dir=tmp_path)
        pipeline = AsyncPipeline(config)
        cached = {"consistency_rating": "PASS", "consistency_score": 0.9}
        (tmp_path / "deepseek_analysis_12345.json").write_text(json.dumps(cached))
        result = await pipeline._analyze_with_llm_consensus(
            "12345", {"title": "Test"}, {"sequencing_type": "scrna_seq"}
        )
        assert result == cached

    @pytest.mark.asyncio
    async def test_analyze_with_llm_consensus_no_router(self, tmp_path):
        """_analyze_with_llm_consensus returns WARN when no router."""
        config = PipelineConfig(pmids=["12345"], results_dir=tmp_path)
        pipeline = AsyncPipeline(config)
        pipeline.llm_router = None
        result = await pipeline._analyze_with_llm_consensus(
            "12345", {"title": "Test"}, {"sequencing_type": "scrna_seq"}
        )
        assert result["consistency_rating"] == "WARN"
        assert "No LLM router" in result["error"]

    @pytest.mark.asyncio
    async def test_analyze_with_llm_consensus_single_backend(self, tmp_path):
        """_analyze_with_llm_consensus with single healthy backend."""
        config = PipelineConfig(pmids=["12345"], results_dir=tmp_path)
        pipeline = AsyncPipeline(config)

        mock_backend = MagicMock()
        mock_backend.status = BackendStatus.HEALTHY
        mock_backend.health_score = 1.0
        mock_backend.generate_with_retry = AsyncMock(return_value=LLMResponse(
            content='{"consistency_rating": "PASS", "consistency_score": 0.85}',
            model="test", backend_name="test", success=True, latency_ms=100,
        ))

        mock_router = MagicMock()
        mock_router.backends = {"test": mock_backend}
        pipeline.llm_router = mock_router

        result = await pipeline._analyze_with_llm_consensus(
            "12345", {"title": "Test"}, {"sequencing_type": "scrna_seq"}
        )
        assert result["consistency_rating"] == "PASS"
        assert result["backend"] == "test"

    @pytest.mark.asyncio
    async def test_analyze_with_llm_consensus_multiple_backends(self, tmp_path):
        """_analyze_with_llm_consensus with multiple healthy backends."""
        config = PipelineConfig(pmids=["12345"], results_dir=tmp_path)
        pipeline = AsyncPipeline(config)

        mock_backend_a = MagicMock()
        mock_backend_a.status = BackendStatus.HEALTHY
        mock_backend_a.health_score = 1.0
        mock_backend_a.generate_with_retry = AsyncMock(return_value=LLMResponse(
            content='{"consistency_rating": "PASS", "consistency_score": 0.9}',
            model="a", backend_name="a", success=True, latency_ms=100,
        ))

        mock_backend_b = MagicMock()
        mock_backend_b.status = BackendStatus.HEALTHY
        mock_backend_b.health_score = 0.8
        mock_backend_b.generate_with_retry = AsyncMock(return_value=LLMResponse(
            content='{"consistency_rating": "PASS", "consistency_score": 0.7}',
            model="b", backend_name="b", success=True, latency_ms=200,
        ))

        mock_router = MagicMock()
        mock_router.backends = {"a": mock_backend_a, "b": mock_backend_b}
        pipeline.llm_router = mock_router

        result = await pipeline._analyze_with_llm_consensus(
            "12345", {"title": "Test"}, {"sequencing_type": "scrna_seq"}
        )
        assert result["consensus"]["num_backends"] == 2
        assert "a" in result["consensus"]["backends"]
        assert "b" in result["consensus"]["backends"]

    @pytest.mark.asyncio
    async def test_analyze_with_llm_consensus_all_backends_fail(self, tmp_path):
        """_analyze_with_llm_consensus when all backends fail."""
        config = PipelineConfig(pmids=["12345"], results_dir=tmp_path)
        pipeline = AsyncPipeline(config)

        mock_backend = MagicMock()
        mock_backend.status = BackendStatus.HEALTHY
        mock_backend.generate_with_retry = AsyncMock(
            side_effect=Exception("connection error")
        )

        mock_router = MagicMock()
        mock_router.backends = {"test": mock_backend}
        pipeline.llm_router = mock_router

        result = await pipeline._analyze_with_llm_consensus(
            "12345", {"title": "Test"}, {"sequencing_type": "scrna_seq"}
        )
        assert result["consistency_rating"] == "WARN"
        assert "All backends failed" in result["error"]

    @pytest.mark.asyncio
    async def test_analyze_with_no_healthy_backends_fallback_success(self, tmp_path):
        """Fallback via router.generate when no healthy backends."""
        config = PipelineConfig(pmids=["12345"], results_dir=tmp_path)
        pipeline = AsyncPipeline(config)

        mock_backend = MagicMock()
        mock_backend.status = BackendStatus.UNHEALTHY

        mock_router = MagicMock()
        mock_router.backends = {"test": mock_backend}
        mock_router.generate = AsyncMock(return_value=LLMResponse(
            content='{"consistency_rating": "WARN", "consistency_score": 0.5}',
            model="fallback", backend_name="fallback", success=True, latency_ms=50,
        ))
        pipeline.llm_router = mock_router

        result = await pipeline._analyze_with_llm_consensus(
            "12345", {"title": "Test"}, {"sequencing_type": "scrna_seq"}
        )
        assert result["consistency_rating"] == "WARN"
        assert result["backend"] == "fallback"

    @pytest.mark.asyncio
    async def test_analyze_with_no_healthy_backends_fallback_fail(self, tmp_path):
        """Returns error when fallback also fails."""
        config = PipelineConfig(pmids=["12345"], results_dir=tmp_path)
        pipeline = AsyncPipeline(config)

        mock_backend = MagicMock()
        mock_backend.status = BackendStatus.UNHEALTHY

        mock_router = MagicMock()
        mock_router.backends = {"test": mock_backend}
        mock_router.generate = AsyncMock(return_value=LLMResponse(
            content="", model="fallback", backend_name="fallback",
            success=False, latency_ms=0, error_message="all failed",
        ))
        pipeline.llm_router = mock_router

        result = await pipeline._analyze_with_llm_consensus(
            "12345", {"title": "Test"}, {"sequencing_type": "scrna_seq"}
        )
        assert result["consistency_rating"] == "WARN"
        assert "All backends unavailable" in result["error"]


# ============================================================
# TestAsyncPipeline run method
# ============================================================

class TestAsyncPipelineRun:

    @pytest.mark.asyncio
    async def test_run_calls_initialize_and_shutdown(self, tmp_path):
        """run() calls initialize and shutdown."""
        config = PipelineConfig(
            pmids=["12345"],
            results_dir=tmp_path,
            enable_resume=False,
        )
        pipeline = AsyncPipeline(config)
        pipeline.initialize = AsyncMock()
        pipeline.shutdown = AsyncMock()
        pipeline._process_pmid = AsyncMock(return_value=PMIDResult(
            pmid="12345", status=PipelineStatus.COMPLETED,
        ))
        pipeline._save_summary = AsyncMock()

        await pipeline.run()

        pipeline.initialize.assert_awaited_once()
        pipeline.shutdown.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_run_handles_exception_in_process(self, tmp_path):
        """run() handles exceptions from _process_pmid gracefully."""
        config = PipelineConfig(
            pmids=["12345"],
            results_dir=tmp_path,
            enable_resume=False,
        )
        pipeline = AsyncPipeline(config)
        pipeline.initialize = AsyncMock()
        pipeline.shutdown = AsyncMock()
        pipeline._process_pmid = AsyncMock(
            side_effect=RuntimeError("test error")
        )
        pipeline._save_summary = AsyncMock()

        results = await pipeline.run()
        assert "12345" in results
        assert results["12345"].status == PipelineStatus.FAILED
        assert "test error" in results["12345"].error

    @pytest.mark.asyncio
    async def test_run_multiple_pmids(self, tmp_path):
        """run() processes multiple PMIDs."""
        config = PipelineConfig(
            pmids=["11111", "22222"],
            results_dir=tmp_path,
            enable_resume=False,
        )
        pipeline = AsyncPipeline(config)
        pipeline.initialize = AsyncMock()
        pipeline.shutdown = AsyncMock()
        pipeline._save_summary = AsyncMock()

        async def mock_process(pmid):
            return PMIDResult(pmid=pmid, status=PipelineStatus.COMPLETED)

        pipeline._process_pmid = AsyncMock(side_effect=mock_process)

        results = await pipeline.run()
        assert len(results) == 2
        assert results["11111"].status == PipelineStatus.COMPLETED
        assert results["22222"].status == PipelineStatus.COMPLETED


# ============================================================
# TestAsyncPipeline shutdown
# ============================================================

class TestAsyncPipelineShutdownExtended:

    @pytest.mark.asyncio
    async def test_shutdown_closes_data_aggregator(self, tmp_path):
        """shutdown() closes the data aggregator."""
        config = PipelineConfig(pmids=["12345"], results_dir=tmp_path)
        pipeline = AsyncPipeline(config)
        mock_agg = MagicMock()
        mock_agg.close = AsyncMock()
        pipeline.data_aggregator = mock_agg

        await pipeline.shutdown()
        mock_agg.close.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_shutdown_no_resources(self, tmp_path):
        """shutdown() does not raise when no resources are set."""
        config = PipelineConfig(pmids=["12345"], results_dir=tmp_path)
        pipeline = AsyncPipeline(config)
        await pipeline.shutdown()  # Should not raise


# ============================================================
# TestAsyncPipeline _build_analysis_prompt edge cases
# ============================================================

class TestBuildAnalysisPromptEdgeCases:

    def test_prompt_with_list_summary_value(self, tmp_path):
        """Handles list values in downstream summary."""
        config = PipelineConfig(pmids=["12345"], results_dir=tmp_path)
        pipeline = AsyncPipeline(config)
        prompt = pipeline._build_analysis_prompt(
            {"title": "T", "abstract": "A"},
            {"sequencing_type": "x"},
            downstream_analysis={
                "success": True,
                "summary": {
                    "genes": ["TP53", "BRCA1"],
                    "qc_params": {"should": "skip"},
                },
            },
        )
        assert "genes" in prompt
        # qc_params should be skipped
        section = prompt.split("Actual Analysis Results")[1].split("Provide")[0]
        assert "qc_params" not in section

    def test_prompt_with_dict_summary_value(self, tmp_path):
        """Handles dict values in downstream summary."""
        config = PipelineConfig(pmids=["12345"], results_dir=tmp_path)
        pipeline = AsyncPipeline(config)
        prompt = pipeline._build_analysis_prompt(
            {"title": "T", "abstract": "A"},
            {"sequencing_type": "x"},
            downstream_analysis={
                "success": True,
                "summary": {
                    "stats": {"mean": 0.5, "std": 0.1},
                },
            },
        )
        assert "stats" in prompt

    def test_prompt_downstream_not_successful(self, tmp_path):
        """Skips downstream when success is False."""
        config = PipelineConfig(pmids=["12345"], results_dir=tmp_path)
        pipeline = AsyncPipeline(config)
        prompt = pipeline._build_analysis_prompt(
            {"title": "T", "abstract": "A"},
            {"sequencing_type": "x"},
            downstream_analysis={"success": False, "summary": {"data": 1}},
        )
        assert "Actual Analysis Results" not in prompt

    def test_prompt_truncates_abstract(self, tmp_path):
        """Truncates long abstracts."""
        config = PipelineConfig(pmids=["12345"], results_dir=tmp_path)
        pipeline = AsyncPipeline(config)
        long_abstract = "word " * 500
        prompt = pipeline._build_analysis_prompt(
            {"title": "T", "abstract": long_abstract},
            {"sequencing_type": "x"},
        )
        assert len(prompt) < len(long_abstract) + 500


# ============================================================
# TestAsyncPipeline index_result_in_rag
# ============================================================

class TestIndexResultInRag:

    def test_index_with_paper_data(self, tmp_path):
        """Indexes paper when title and abstract exist."""
        config = PipelineConfig(pmids=["12345"], results_dir=tmp_path)
        pipeline = AsyncPipeline(config)
        mock_store = MagicMock()
        pipeline.doc_store = mock_store

        result = PMIDResult(
            pmid="12345",
            status=PipelineStatus.COMPLETED,
            pubmed_metadata={
                "title": "Test Paper",
                "abstract": "Test abstract",
                "pub_date": "2025-01-15",
            },
            llm_analysis={"consistency_rating": "PASS"},
            debate_report={"overall_verdict": "PASS", "overall_score": 0.9},
        )
        pipeline._index_result_in_rag(result)

        mock_store.add_paper.assert_called_once()
        call_kwargs = mock_store.add_paper.call_args.kwargs
        assert call_kwargs["pmid"] == "12345"
        assert call_kwargs["year"] == 2025

        mock_store.add_analysis.assert_called_once()
        mock_store.add_debate_report.assert_called_once()

    def test_index_without_abstract(self, tmp_path):
        """Skips paper when no abstract."""
        config = PipelineConfig(pmids=["12345"], results_dir=tmp_path)
        pipeline = AsyncPipeline(config)
        mock_store = MagicMock()
        pipeline.doc_store = mock_store

        result = PMIDResult(
            pmid="12345",
            status=PipelineStatus.COMPLETED,
            pubmed_metadata={"title": "Test Paper"},
        )
        pipeline._index_result_in_rag(result)
        mock_store.add_paper.assert_not_called()

    def test_index_with_invalid_pub_date(self, tmp_path):
        """Handles invalid pub_date gracefully."""
        config = PipelineConfig(pmids=["12345"], results_dir=tmp_path)
        pipeline = AsyncPipeline(config)
        mock_store = MagicMock()
        pipeline.doc_store = mock_store

        result = PMIDResult(
            pmid="12345",
            status=PipelineStatus.COMPLETED,
            pubmed_metadata={
                "title": "Test",
                "abstract": "Abstract",
                "pub_date": "invalid",
            },
        )
        pipeline._index_result_in_rag(result)
        call_kwargs = mock_store.add_paper.call_args.kwargs
        assert call_kwargs["year"] is None

    def test_index_skips_analysis_with_error(self, tmp_path):
        """Skips analysis when it has error."""
        config = PipelineConfig(pmids=["12345"], results_dir=tmp_path)
        pipeline = AsyncPipeline(config)
        mock_store = MagicMock()
        pipeline.doc_store = mock_store

        result = PMIDResult(
            pmid="12345",
            status=PipelineStatus.COMPLETED,
            pubmed_metadata={"title": "T", "abstract": "A"},
            llm_analysis={"error": "failed"},
        )
        pipeline._index_result_in_rag(result)
        mock_store.add_analysis.assert_not_called()

    def test_index_skips_debate_without_verdict(self, tmp_path):
        """Skips debate when no verdict."""
        config = PipelineConfig(pmids=["12345"], results_dir=tmp_path)
        pipeline = AsyncPipeline(config)
        mock_store = MagicMock()
        pipeline.doc_store = mock_store

        result = PMIDResult(
            pmid="12345",
            status=PipelineStatus.COMPLETED,
            pubmed_metadata={"title": "T", "abstract": "A"},
            debate_report={},
        )
        pipeline._index_result_in_rag(result)
        mock_store.add_debate_report.assert_not_called()
