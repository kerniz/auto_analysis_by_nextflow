"""
Test Configuration
pytest 설정 및 공통 픽스처
"""

import asyncio
import pytest
from typing import AsyncGenerator, Generator
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))


@pytest.fixture(scope="session")
def event_loop() -> Generator[asyncio.AbstractEventLoop, None, None]:
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest.fixture
def mock_httpx_response():
    def _create_response(json_data=None, text="", status_code=200):
        response = MagicMock()
        response.json.return_value = json_data or {}
        response.text = text
        response.status_code = status_code
        return response
    return _create_response


@pytest.fixture
def sample_pubmed_metadata():
    return {
        "pmid": "40315330",
        "title": "Single-cell RNA sequencing reveals cellular heterogeneity",
        "abstract": (
            "We performed single-cell RNA sequencing using 10x Genomics "
            "platform to analyze cellular composition. Our analysis identified "
            "distinct cell populations using UMI-based counting."
        ),
        "keywords": ["single-cell", "RNA-seq", "10x Genomics"],
    }


@pytest.fixture
def sample_sra_metadata():
    return {
        "SRR123456": {
            "LibStrategy": "SINGLE_CELL",
            "LibSource": "TRANSCRIPTOMIC",
            "LibSelection": "cDNA",
        }
    }


@pytest.fixture
def sample_bulk_pubmed_metadata():
    return {
        "pmid": "32416070",
        "title": "Bulk RNA-seq analysis of gene expression changes",
        "abstract": (
            "We performed bulk RNA sequencing with polyA selection "
            "to analyze gene expression changes. Total RNA was extracted "
            "and sequenced using Illumina platform."
        ),
        "keywords": ["RNA-seq", "gene expression", "polyA"],
    }


@pytest.fixture
def sample_bulk_sra_metadata():
    return {
        "SRR789012": {
            "LibStrategy": "RNA-SEQ",
            "LibSource": "TRANSCRIPTOMIC",
            "LibSelection": "POLY_A",
        }
    }


# ===== Multi-Agent Debate Fixtures =====

@pytest.fixture
def mock_llm_router():
    from backends.base import LLMResponse
    router = MagicMock()
    router.generate = AsyncMock(return_value=LLMResponse(
        content='{"assessment": "Test assessment", "score": 0.7, "confidence": 0.8, '
                '"key_points": ["Point 1"], "concerns": ["Concern 1"], "questions": ["Q1"]}',
        model="test-model",
        backend_name="test-backend",
        success=True,
        latency_ms=100,
    ))
    router.backends = {}
    return router


@pytest.fixture
def sample_research_data():
    return {
        "paper": {
            "pmid": "40315330",
            "title": "Single-cell RNA sequencing reveals cellular heterogeneity",
            "abstract": "We performed single-cell RNA sequencing...",
        },
        "sequencing": {
            "sequencing_type": "scrna_seq",
            "confidence": 0.85,
        },
        "aggregated": {},
        "enrichment": {},
        "llm_analysis": {"consistency_rating": "PASS"},
    }


@pytest.fixture
def sample_aggregated_result():
    from clients.data_aggregator import AggregatedResult
    return AggregatedResult(
        pmid="40315330",
        sources_succeeded=["semantic_scholar", "europe_pmc"],
        sources_failed=["tcga_gdc"],
        semantic_scholar_data={
            "title": "Single-cell RNA sequencing reveals cellular heterogeneity",
            "citation_count": 15,
        },
        europe_pmc_data={
            "text_mined_terms": [
                {"type": "Gene", "name": "TP53"},
                {"type": "Gene", "name": "BRCA1"},
            ],
        },
    )


@pytest.fixture
def sample_enrichment_result():
    return {
        "gsea": {
            "significant_terms": [
                {"term": "p53 signaling pathway", "pvalue": 0.001, "overlap": 10},
                {"term": "Novel pathway X", "pvalue": 0.005, "overlap": 5},
            ],
            "gene_count": 50,
        },
        "pathways": {
            "kegg_results": [],
        },
        "top_pathways_count": 2,
        "top_genes_count": 50,
        "novelty_score": 0.65,
        "novelty_factors": {
            "topic_novelty": 0.5,
            "methodology_novelty": 0.75,
            "finding_novelty": 0.6,
        },
    }
