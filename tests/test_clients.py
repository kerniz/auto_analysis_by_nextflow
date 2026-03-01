"""
Tests for Data Source Clients
데이터 소스 클라이언트 테스트
"""


import pytest

from clients import ClientConfig, ClientResponse
from clients.annotation_client import AnnotationClient
from clients.data_aggregator import AggregatedResult, DataAggregator
from clients.europe_pmc_client import EuropePMCClient
from clients.semantic_scholar_client import SemanticScholarClient
from clients.tcga_client import TCGAClient


class TestClientConfig:
    def test_default_config(self):
        config = ClientConfig(base_url="https://api.example.com")
        assert config.timeout == 30
        assert config.max_retries == 3
        assert config.rate_limit_delay == 0.5
        assert config.cache_enabled is True
        assert config.api_key is None

    def test_custom_config(self):
        config = ClientConfig(
            base_url="https://api.example.com",
            timeout=60,
            api_key="test-key",
            rate_limit_delay=1.0,
        )
        assert config.timeout == 60
        assert config.api_key == "test-key"
        assert config.rate_limit_delay == 1.0


class TestClientResponse:
    def test_success_response(self):
        resp = ClientResponse(
            success=True,
            data={"key": "value"},
            source="test",
            query="test_query",
        )
        assert resp.success is True
        assert resp.data == {"key": "value"}

    def test_error_response(self):
        resp = ClientResponse(
            success=False,
            data=None,
            source="test",
            query="",
            error_message="Connection failed",
        )
        assert resp.success is False
        assert resp.error_message == "Connection failed"

    def test_to_dict(self):
        resp = ClientResponse(
            success=True,
            data={"result": 42},
            source="semantic_scholar",
            query="TP53",
            latency_ms=150.5,
        )
        d = resp.to_dict()
        assert d["success"] is True
        assert d["source"] == "semantic_scholar"
        assert d["latency_ms"] == 150.5


class TestSemanticScholarClient:
    def test_init_default(self):
        client = SemanticScholarClient()
        assert client.name == "semantic_scholar"

    def test_init_custom_config(self):
        config = ClientConfig(
            base_url="https://custom.api.com",
            api_key="S2_KEY",
        )
        client = SemanticScholarClient(config=config)
        assert client.config.api_key == "S2_KEY"


class TestEuropePMCClient:
    def test_init_default(self):
        client = EuropePMCClient()
        assert client.name == "europe_pmc"

    def test_init_custom(self):
        config = ClientConfig(base_url="https://custom.ebi.ac.uk")
        client = EuropePMCClient(config=config)
        assert client.config.base_url == "https://custom.ebi.ac.uk"


class TestAnnotationClient:
    def test_init_default(self):
        client = AnnotationClient()
        assert client.name == "annotation"

    def test_has_multiple_apis(self):
        client = AnnotationClient()
        assert hasattr(client, "QUICKGO_BASE")
        assert hasattr(client, "KEGG_BASE")
        assert hasattr(client, "ENSEMBL_BASE")


class TestTCGAClient:
    def test_init_default(self):
        client = TCGAClient()
        assert client.name == "tcga_gdc"


class TestAggregatedResult:
    def test_default(self):
        result = AggregatedResult(pmid="12345")
        assert result.pmid == "12345"
        assert result.sources_succeeded == []
        assert result.sources_failed == []

    def test_to_dict(self):
        result = AggregatedResult(
            pmid="12345",
            sources_succeeded=["semantic_scholar"],
            sources_failed=["tcga"],
        )
        d = result.to_dict()
        assert d["pmid"] == "12345"
        assert "semantic_scholar" in d["sources_succeeded"]


class TestDataAggregator:
    def test_init(self):
        agg = DataAggregator()
        assert agg._initialized is False

    @pytest.mark.asyncio
    async def test_initialize(self):
        agg = DataAggregator()
        await agg.initialize()
        assert agg._initialized is True
        assert agg.ss_client is not None
        assert agg.epmc_client is not None
        assert agg.annotation_client is not None
        assert agg.tcga_client is not None
        await agg.close()
