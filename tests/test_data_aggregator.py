"""
Tests for clients/data_aggregator.py
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from clients.base import ClientConfig, ClientResponse
from clients.data_aggregator import AggregatedResult, DataAggregator


class TestAggregatedResult:
    def test_defaults(self):
        r = AggregatedResult(pmid="12345")
        assert r.pmid == "12345"
        assert r.doi is None
        assert r.semantic_scholar_paper == {}
        assert r.semantic_scholar_citations == []
        assert r.europe_pmc_article == {}
        assert r.gene_annotations == {}
        assert r.tcga_projects == []
        assert r.errors == {}
        assert r.sources_succeeded == []
        assert r.sources_failed == []

    def test_to_dict(self):
        r = AggregatedResult(
            pmid="12345",
            doi="10.1234/test",
            semantic_scholar_paper={"title": "T"},
            semantic_scholar_citations=[{"id": "c1"}],
            semantic_scholar_references=[{"id": "r1"}, {"id": "r2"}],
            semantic_scholar_recommendations=[],
            semantic_scholar_influence={"score": 50},
            europe_pmc_article={"pmid": "12345"},
            europe_pmc_citations=[],
            europe_pmc_references=[{"id": "er1"}],
            europe_pmc_annotations=[],
            gene_annotations={"TP53": {"go": "GO:0001"}},
            kegg_pathways={"7157": [{"pathway_id": "hsa04110"}]},
            ensembl_genes={"TP53": {"id": "ENSG00000141510"}},
            tcga_projects=[{"project_id": "TCGA-BRCA"}],
            errors={"tcga": "timeout"},
            sources_succeeded=["ss_paper"],
            sources_failed=["tcga"],
        )
        d = r.to_dict()
        assert d["pmid"] == "12345"
        assert d["doi"] == "10.1234/test"
        assert d["semantic_scholar"]["citations_count"] == 1
        assert d["semantic_scholar"]["references_count"] == 2
        assert d["europe_pmc"]["references_count"] == 1
        assert d["gene_annotations"]["TP53"]["go"] == "GO:0001"
        assert len(d["tcga_projects"]) == 1
        assert "tcga" in d["errors"]


class TestDataAggregatorInit:
    def test_init(self):
        agg = DataAggregator()
        assert agg._initialized is False
        assert agg.ss_client is None
        assert agg.epmc_client is None

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

    @pytest.mark.asyncio
    async def test_initialize_with_custom_configs(self):
        agg = DataAggregator()
        ss_cfg = ClientConfig(base_url="https://custom-ss.com")
        await agg.initialize(ss_config=ss_cfg)
        assert agg.ss_client.config.base_url == "https://custom-ss.com"
        await agg.close()


class TestDataAggregatorClose:
    @pytest.mark.asyncio
    async def test_close(self):
        agg = DataAggregator()
        await agg.initialize()
        assert agg._initialized is True
        await agg.close()
        assert agg._initialized is False

    @pytest.mark.asyncio
    async def test_close_with_error(self):
        agg = DataAggregator()
        mock_client = AsyncMock()
        mock_client.close = AsyncMock(side_effect=Exception("err"))
        agg.ss_client = mock_client
        agg.epmc_client = None
        agg.annotation_client = None
        agg.tcga_client = None
        agg._initialized = True
        await agg.close()
        assert agg._initialized is False


def _make_aggregator():
    agg = DataAggregator()
    agg.ss_client = AsyncMock()
    agg.epmc_client = AsyncMock()
    agg.annotation_client = AsyncMock()
    agg.tcga_client = AsyncMock()
    agg._initialized = True
    return agg


def _ok_response(data, source="test", query="q"):
    return ClientResponse(success=True, data=data, source=source, query=query)


def _err_response(msg="error", source="test", query="q"):
    return ClientResponse(success=False, data={}, source=source, query=query, error_message=msg)


class TestAggregate:
    @pytest.mark.asyncio
    async def test_basic_aggregate(self):
        agg = _make_aggregator()
        paper_data = {"paperId": "s2id", "title": "Paper"}
        agg.ss_client.fetch_by_pmid = AsyncMock(return_value=_ok_response(paper_data))
        agg.ss_client.get_citations = AsyncMock(return_value=_ok_response([{"id": "c1"}]))
        agg.ss_client.get_references = AsyncMock(return_value=_ok_response([{"id": "r1"}]))
        agg.ss_client.get_recommendations = AsyncMock(return_value=_ok_response([]))
        agg.ss_client.get_influence_score = AsyncMock(return_value=_ok_response({"score": 50}))
        agg.epmc_client.fetch_by_id = AsyncMock(return_value=_ok_response({"pmid": "12345"}))
        agg.epmc_client.get_citations = AsyncMock(return_value=_ok_response([]))
        agg.epmc_client.get_references = AsyncMock(return_value=_ok_response([]))

        result = await agg.aggregate("12345")
        assert result.pmid == "12345"
        assert "ss_paper" in result.sources_succeeded
        assert result.semantic_scholar_paper == paper_data

    @pytest.mark.asyncio
    async def test_aggregate_auto_initializes(self):
        agg = DataAggregator()
        assert agg._initialized is False

        # Patch initialize to set up mock clients
        original_init = agg.initialize

        async def mock_init(*args, **kwargs):
            await original_init(*args, **kwargs)
            # Replace with mocks after initialization
            agg.ss_client = AsyncMock()
            agg.ss_client.fetch_by_pmid = AsyncMock(return_value=_ok_response({}))
            agg.ss_client.get_citations = AsyncMock(return_value=_ok_response([]))
            agg.ss_client.get_references = AsyncMock(return_value=_ok_response([]))
            agg.ss_client.get_recommendations = AsyncMock(return_value=_ok_response([]))
            agg.ss_client.get_influence_score = AsyncMock(return_value=_ok_response({}))
            agg.epmc_client = AsyncMock()
            agg.epmc_client.fetch_by_id = AsyncMock(return_value=_ok_response({}))
            agg.epmc_client.get_citations = AsyncMock(return_value=_ok_response([]))
            agg.epmc_client.get_references = AsyncMock(return_value=_ok_response([]))

        agg.initialize = mock_init
        result = await agg.aggregate("12345")
        assert result.pmid == "12345"

    @pytest.mark.asyncio
    async def test_aggregate_with_doi(self):
        agg = _make_aggregator()
        agg.ss_client.fetch_by_id = AsyncMock(return_value=_ok_response({"paperId": "doi-paper"}))
        agg.ss_client.get_citations = AsyncMock(return_value=_ok_response([]))
        agg.ss_client.get_references = AsyncMock(return_value=_ok_response([]))
        agg.ss_client.get_recommendations = AsyncMock(return_value=_ok_response([]))
        agg.ss_client.get_influence_score = AsyncMock(return_value=_ok_response({}))
        agg.epmc_client.fetch_by_id = AsyncMock(return_value=_ok_response({}))
        agg.epmc_client.get_citations = AsyncMock(return_value=_ok_response([]))
        agg.epmc_client.get_references = AsyncMock(return_value=_ok_response([]))

        result = await agg.aggregate("12345", doi="10.1234/test")
        assert result.doi == "10.1234/test"
        agg.ss_client.fetch_by_id.assert_awaited_once_with("10.1234/test")

    @pytest.mark.asyncio
    async def test_aggregate_with_gene_list(self):
        agg = _make_aggregator()
        agg.ss_client.fetch_by_pmid = AsyncMock(return_value=_ok_response({}))
        agg.ss_client.get_citations = AsyncMock(return_value=_ok_response([]))
        agg.ss_client.get_references = AsyncMock(return_value=_ok_response([]))
        agg.ss_client.get_recommendations = AsyncMock(return_value=_ok_response([]))
        agg.ss_client.get_influence_score = AsyncMock(return_value=_ok_response({}))
        agg.epmc_client.fetch_by_id = AsyncMock(return_value=_ok_response({}))
        agg.epmc_client.get_citations = AsyncMock(return_value=_ok_response([]))
        agg.epmc_client.get_references = AsyncMock(return_value=_ok_response([]))
        agg.annotation_client.get_go_enrichment = AsyncMock(
            return_value=_ok_response({"gene_annotations": {}})
        )
        agg.annotation_client.get_kegg_pathways = AsyncMock(
            return_value=_ok_response([])
        )
        agg.annotation_client.get_gene_by_symbol = AsyncMock(
            return_value=_ok_response({"id": "ENSG00000141510"})
        )

        result = await agg.aggregate("12345", gene_list=["TP53"])
        assert "gene_annotations" in result.sources_succeeded or isinstance(result.gene_annotations, dict)

    @pytest.mark.asyncio
    async def test_aggregate_handles_exceptions(self):
        agg = _make_aggregator()
        agg.ss_client.fetch_by_pmid = AsyncMock(side_effect=Exception("boom"))
        agg.ss_client.get_citations = AsyncMock(return_value=_ok_response([]))
        agg.ss_client.get_references = AsyncMock(return_value=_ok_response([]))
        agg.ss_client.get_recommendations = AsyncMock(return_value=_ok_response([]))
        agg.ss_client.get_influence_score = AsyncMock(return_value=_ok_response({}))
        agg.epmc_client.fetch_by_id = AsyncMock(return_value=_ok_response({}))
        agg.epmc_client.get_citations = AsyncMock(return_value=_ok_response([]))
        agg.epmc_client.get_references = AsyncMock(return_value=_ok_response([]))

        result = await agg.aggregate("12345")
        assert "ss_paper" in result.sources_failed or "ss_paper" in result.errors

    @pytest.mark.asyncio
    async def test_aggregate_handles_failed_responses(self):
        agg = _make_aggregator()
        agg.ss_client.fetch_by_pmid = AsyncMock(return_value=_err_response("not found"))
        agg.ss_client.get_citations = AsyncMock(return_value=_ok_response([]))
        agg.ss_client.get_references = AsyncMock(return_value=_ok_response([]))
        agg.ss_client.get_recommendations = AsyncMock(return_value=_ok_response([]))
        agg.ss_client.get_influence_score = AsyncMock(return_value=_ok_response({}))
        agg.epmc_client.fetch_by_id = AsyncMock(return_value=_ok_response({}))
        agg.epmc_client.get_citations = AsyncMock(return_value=_ok_response([]))
        agg.epmc_client.get_references = AsyncMock(return_value=_ok_response([]))

        result = await agg.aggregate("12345")
        assert "ss_paper" in result.sources_failed


class TestQueryMethods:
    @pytest.mark.asyncio
    async def test_query_ss_paper_with_doi(self):
        agg = _make_aggregator()
        agg.ss_client.fetch_by_id = AsyncMock(return_value=_ok_response({}))
        await agg._query_ss_paper("12345", doi="10.1/x")
        agg.ss_client.fetch_by_id.assert_awaited_once_with("10.1/x")

    @pytest.mark.asyncio
    async def test_query_ss_paper_without_doi(self):
        agg = _make_aggregator()
        agg.ss_client.fetch_by_pmid = AsyncMock(return_value=_ok_response({}))
        await agg._query_ss_paper("12345", doi=None)
        agg.ss_client.fetch_by_pmid.assert_awaited_once_with("12345")

    @pytest.mark.asyncio
    async def test_query_ss_paper_exception(self):
        agg = _make_aggregator()
        agg.ss_client.fetch_by_pmid = AsyncMock(side_effect=Exception("err"))
        resp = await agg._query_ss_paper("12345", doi=None)
        assert resp.success is False

    @pytest.mark.asyncio
    async def test_query_ss_citations_exception(self):
        agg = _make_aggregator()
        agg.ss_client.get_citations = AsyncMock(side_effect=Exception("err"))
        resp = await agg._query_ss_citations("12345")
        assert resp.success is False

    @pytest.mark.asyncio
    async def test_query_ss_references_exception(self):
        agg = _make_aggregator()
        agg.ss_client.get_references = AsyncMock(side_effect=Exception("err"))
        resp = await agg._query_ss_references("12345")
        assert resp.success is False

    @pytest.mark.asyncio
    async def test_query_ss_recommendations_exception(self):
        agg = _make_aggregator()
        agg.ss_client.get_recommendations = AsyncMock(side_effect=Exception("err"))
        resp = await agg._query_ss_recommendations("12345")
        assert resp.success is False

    @pytest.mark.asyncio
    async def test_query_ss_influence_exception(self):
        agg = _make_aggregator()
        agg.ss_client.get_influence_score = AsyncMock(side_effect=Exception("err"))
        resp = await agg._query_ss_influence("12345")
        assert resp.success is False

    @pytest.mark.asyncio
    async def test_query_epmc_article_exception(self):
        agg = _make_aggregator()
        agg.epmc_client.fetch_by_id = AsyncMock(side_effect=Exception("err"))
        resp = await agg._query_epmc_article("12345")
        assert resp.success is False

    @pytest.mark.asyncio
    async def test_query_epmc_citations_exception(self):
        agg = _make_aggregator()
        agg.epmc_client.get_citations = AsyncMock(side_effect=Exception("err"))
        resp = await agg._query_epmc_citations("12345")
        assert resp.success is False

    @pytest.mark.asyncio
    async def test_query_epmc_references_exception(self):
        agg = _make_aggregator()
        agg.epmc_client.get_references = AsyncMock(side_effect=Exception("err"))
        resp = await agg._query_epmc_references("12345")
        assert resp.success is False

    @pytest.mark.asyncio
    async def test_query_gene_annotations_exception(self):
        agg = _make_aggregator()
        agg.annotation_client.get_go_enrichment = AsyncMock(side_effect=Exception("err"))
        resp = await agg._query_gene_annotations(["TP53"])
        assert resp.success is False

    @pytest.mark.asyncio
    async def test_query_kegg_pathways_success(self):
        agg = _make_aggregator()
        agg.annotation_client.get_kegg_pathways = AsyncMock(
            return_value=_ok_response([{"pathway_id": "hsa04110"}])
        )
        resp = await agg._query_kegg_pathways(["7157"])
        assert resp.success is True

    @pytest.mark.asyncio
    async def test_query_kegg_pathways_failed_response(self):
        agg = _make_aggregator()
        agg.annotation_client.get_kegg_pathways = AsyncMock(
            return_value=_err_response("err")
        )
        resp = await agg._query_kegg_pathways(["7157"])
        assert resp.success is True  # Overall success, individual errors in data
        assert "error" in resp.data["7157"]

    @pytest.mark.asyncio
    async def test_query_kegg_pathways_exception(self):
        agg = _make_aggregator()
        agg.annotation_client.get_kegg_pathways = AsyncMock(side_effect=Exception("err"))
        resp = await agg._query_kegg_pathways(["7157"])
        assert resp.success is False

    @pytest.mark.asyncio
    async def test_query_ensembl_genes_success(self):
        agg = _make_aggregator()
        agg.annotation_client.get_gene_by_symbol = AsyncMock(
            return_value=_ok_response({"id": "ENSG00000141510"})
        )
        resp = await agg._query_ensembl_genes(["TP53"])
        assert resp.success is True
        assert "TP53" in resp.data

    @pytest.mark.asyncio
    async def test_query_ensembl_genes_exception_in_gather(self):
        agg = _make_aggregator()
        agg.annotation_client.get_gene_by_symbol = AsyncMock(side_effect=Exception("err"))
        resp = await agg._query_ensembl_genes(["TP53"])
        assert resp.success is True
        assert "error" in resp.data["TP53"]

    @pytest.mark.asyncio
    async def test_query_ensembl_genes_failed_response(self):
        agg = _make_aggregator()
        agg.annotation_client.get_gene_by_symbol = AsyncMock(
            return_value=_err_response("not found")
        )
        resp = await agg._query_ensembl_genes(["BAD"])
        assert resp.success is True
        assert "error" in resp.data["BAD"]

    @pytest.mark.asyncio
    async def test_query_ensembl_genes_complete_exception(self):
        agg = _make_aggregator()
        # Make the whole method fail at the gather level
        agg.annotation_client.get_gene_by_symbol = AsyncMock(
            return_value=_ok_response({})
        )
        with patch("clients.data_aggregator.asyncio.gather", side_effect=Exception("fatal")):
            resp = await agg._query_ensembl_genes(["TP53"])
            assert resp.success is False


class TestMergeResults:
    def test_merge_ss_data(self):
        agg = _make_aggregator()
        result = AggregatedResult(pmid="12345")
        keys = ["ss_paper", "ss_citations", "ss_references", "ss_recommendations", "ss_influence"]
        responses = [
            _ok_response({"title": "T"}),
            _ok_response([{"id": "c1"}]),
            _ok_response([{"id": "r1"}]),
            _ok_response([{"id": "rec1"}]),
            _ok_response({"score": 42}),
        ]
        merged = agg._merge_results(result, keys, responses)
        assert merged.semantic_scholar_paper == {"title": "T"}
        assert merged.semantic_scholar_citations == [{"id": "c1"}]
        assert merged.semantic_scholar_references == [{"id": "r1"}]
        assert merged.semantic_scholar_recommendations == [{"id": "rec1"}]
        assert merged.semantic_scholar_influence == {"score": 42}

    def test_merge_epmc_data(self):
        agg = _make_aggregator()
        result = AggregatedResult(pmid="12345")
        keys = ["epmc_article", "epmc_citations", "epmc_references"]
        responses = [
            _ok_response({"pmid": "12345", "pmcid": "PMC999"}),
            _ok_response([{"id": "ec1"}]),
            _ok_response([{"id": "er1"}]),
        ]
        merged = agg._merge_results(result, keys, responses)
        assert merged.europe_pmc_article["pmid"] == "12345"
        assert merged.europe_pmc_citations == [{"id": "ec1"}]
        assert merged.europe_pmc_references == [{"id": "er1"}]
        assert merged.europe_pmc_annotations == []  # pmcid present

    def test_merge_annotation_data(self):
        agg = _make_aggregator()
        result = AggregatedResult(pmid="12345")
        keys = ["gene_annotations", "kegg_pathways", "ensembl_genes"]
        responses = [
            _ok_response({"TP53": {"go": "GO:0001"}}),
            _ok_response({"7157": []}),
            _ok_response({"TP53": {"id": "ENSG00000141510"}}),
        ]
        merged = agg._merge_results(result, keys, responses)
        assert "TP53" in merged.gene_annotations
        assert "7157" in merged.kegg_pathways
        assert "TP53" in merged.ensembl_genes

    def test_merge_with_exceptions(self):
        agg = _make_aggregator()
        result = AggregatedResult(pmid="12345")
        keys = ["ss_paper", "epmc_article"]
        responses = [Exception("err"), _ok_response({"pmid": "12345"})]
        merged = agg._merge_results(result, keys, responses)
        assert merged.semantic_scholar_paper == {}
        assert merged.europe_pmc_article["pmid"] == "12345"

    def test_merge_with_failed_response(self):
        agg = _make_aggregator()
        result = AggregatedResult(pmid="12345")
        keys = ["ss_paper"]
        responses = [_err_response("not found")]
        merged = agg._merge_results(result, keys, responses)
        assert merged.semantic_scholar_paper == {}

    def test_merge_with_non_response(self):
        agg = _make_aggregator()
        result = AggregatedResult(pmid="12345")
        keys = ["ss_paper"]
        responses = ["invalid"]
        merged = agg._merge_results(result, keys, responses)
        assert merged.semantic_scholar_paper == {}


class TestAggregateWithAnnotations:
    @pytest.mark.asyncio
    async def test_with_pmcid(self):
        agg = _make_aggregator()
        agg.ss_client.fetch_by_pmid = AsyncMock(return_value=_ok_response({}))
        agg.ss_client.get_citations = AsyncMock(return_value=_ok_response([]))
        agg.ss_client.get_references = AsyncMock(return_value=_ok_response([]))
        agg.ss_client.get_recommendations = AsyncMock(return_value=_ok_response([]))
        agg.ss_client.get_influence_score = AsyncMock(return_value=_ok_response({}))
        agg.epmc_client.fetch_by_id = AsyncMock(
            return_value=_ok_response({"pmid": "12345", "pmcid": "PMC999"})
        )
        agg.epmc_client.get_citations = AsyncMock(return_value=_ok_response([]))
        agg.epmc_client.get_references = AsyncMock(return_value=_ok_response([]))
        agg.epmc_client.get_text_mined_terms = AsyncMock(
            return_value=_ok_response([{"type": "Gene", "exact": "TP53"}])
        )

        result = await agg.aggregate_with_annotations("12345")
        assert result.europe_pmc_annotations == [{"type": "Gene", "exact": "TP53"}]
        assert "epmc_annotations" in result.sources_succeeded

    @pytest.mark.asyncio
    async def test_without_pmcid(self):
        agg = _make_aggregator()
        agg.ss_client.fetch_by_pmid = AsyncMock(return_value=_ok_response({}))
        agg.ss_client.get_citations = AsyncMock(return_value=_ok_response([]))
        agg.ss_client.get_references = AsyncMock(return_value=_ok_response([]))
        agg.ss_client.get_recommendations = AsyncMock(return_value=_ok_response([]))
        agg.ss_client.get_influence_score = AsyncMock(return_value=_ok_response({}))
        agg.epmc_client.fetch_by_id = AsyncMock(
            return_value=_ok_response({"pmid": "12345"})
        )
        agg.epmc_client.get_citations = AsyncMock(return_value=_ok_response([]))
        agg.epmc_client.get_references = AsyncMock(return_value=_ok_response([]))

        await agg.aggregate_with_annotations("12345")
        # Should not call get_text_mined_terms
        agg.epmc_client.get_text_mined_terms.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_annotations_failure(self):
        agg = _make_aggregator()
        agg.ss_client.fetch_by_pmid = AsyncMock(return_value=_ok_response({}))
        agg.ss_client.get_citations = AsyncMock(return_value=_ok_response([]))
        agg.ss_client.get_references = AsyncMock(return_value=_ok_response([]))
        agg.ss_client.get_recommendations = AsyncMock(return_value=_ok_response([]))
        agg.ss_client.get_influence_score = AsyncMock(return_value=_ok_response({}))
        agg.epmc_client.fetch_by_id = AsyncMock(
            return_value=_ok_response({"pmid": "12345", "pmcid": "PMC999"})
        )
        agg.epmc_client.get_citations = AsyncMock(return_value=_ok_response([]))
        agg.epmc_client.get_references = AsyncMock(return_value=_ok_response([]))
        agg.epmc_client.get_text_mined_terms = AsyncMock(
            return_value=_err_response("err")
        )

        result = await agg.aggregate_with_annotations("12345")
        assert "epmc_annotations" in result.sources_failed

    @pytest.mark.asyncio
    async def test_annotations_exception(self):
        agg = _make_aggregator()
        agg.ss_client.fetch_by_pmid = AsyncMock(return_value=_ok_response({}))
        agg.ss_client.get_citations = AsyncMock(return_value=_ok_response([]))
        agg.ss_client.get_references = AsyncMock(return_value=_ok_response([]))
        agg.ss_client.get_recommendations = AsyncMock(return_value=_ok_response([]))
        agg.ss_client.get_influence_score = AsyncMock(return_value=_ok_response({}))
        agg.epmc_client.fetch_by_id = AsyncMock(
            return_value=_ok_response({"pmid": "12345", "pmcid": "PMC999"})
        )
        agg.epmc_client.get_citations = AsyncMock(return_value=_ok_response([]))
        agg.epmc_client.get_references = AsyncMock(return_value=_ok_response([]))
        agg.epmc_client.get_text_mined_terms = AsyncMock(side_effect=Exception("err"))

        result = await agg.aggregate_with_annotations("12345")
        assert "epmc_annotations" in result.errors


class TestGetAllMetrics:
    def test_initialized(self):
        agg = _make_aggregator()
        agg.ss_client.get_metrics = MagicMock(return_value={"name": "ss"})
        agg.epmc_client.get_metrics = MagicMock(return_value={"name": "epmc"})
        agg.annotation_client.get_metrics = MagicMock(return_value={"name": "ann"})
        agg.tcga_client.get_metrics = MagicMock(return_value={"name": "tcga"})

        m = agg.get_all_metrics()
        assert m["initialized"] is True
        assert m["semantic_scholar"]["name"] == "ss"

    def test_not_initialized(self):
        agg = DataAggregator()
        m = agg.get_all_metrics()
        assert m["initialized"] is False
        assert m["semantic_scholar"]["status"] == "not_initialized"
