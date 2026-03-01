"""
Tests for clients/annotation_client.py
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from clients.annotation_client import AnnotationClient
from clients.base import ClientConfig


def _make_client(**cfg_overrides):
    cfg = ClientConfig(
        base_url="https://www.ebi.ac.uk/QuickGO/services",
        rate_limit_delay=0,
        max_retries=1,
        **cfg_overrides,
    )
    return AnnotationClient(config=cfg)


def _mock_kegg_response(text="", status_code=200):
    r = MagicMock()
    r.status_code = status_code
    r.text = text
    r.raise_for_status = MagicMock()
    return r


def _mock_ensembl_response(json_data=None, status_code=200):
    r = MagicMock()
    r.status_code = status_code
    r.json.return_value = json_data or {}
    r.raise_for_status = MagicMock()
    return r


class TestAnnotationInit:
    def test_default_config(self):
        c = AnnotationClient()
        assert c.name == "annotation"
        assert c.config.rate_limit_delay == 0.35

    def test_custom_config(self):
        cfg = ClientConfig(base_url="https://custom.url")
        c = AnnotationClient(config=cfg)
        assert c.config.base_url == "https://custom.url"


class TestGetGoTerms:
    @pytest.mark.asyncio
    async def test_success(self):
        c = _make_client()
        raw = {"results": [
            {"goId": "GO:0001", "goName": "apoptosis"},
            {"goId": "GO:0002", "goName": "cell cycle"},
        ]}
        with patch.object(c, "_request_with_retry", new_callable=AsyncMock, return_value=raw):
            resp = await c.get_go_terms("P04637")
            assert resp.success is True
            assert len(resp.data) == 2
            assert resp.data[0]["goId"] == "GO:0001"

    @pytest.mark.asyncio
    async def test_cached(self):
        c = _make_client()
        raw = {"results": [{"goId": "GO:0001"}]}
        mock_retry = AsyncMock(return_value=raw)
        with patch.object(c, "_request_with_retry", mock_retry):
            await c.get_go_terms("P04637", limit=50)
            await c.get_go_terms("P04637", limit=50)
            assert mock_retry.await_count == 1

    @pytest.mark.asyncio
    async def test_failure(self):
        c = _make_client()
        with patch.object(c, "_request_with_retry", new_callable=AsyncMock, side_effect=Exception("timeout")):
            resp = await c.get_go_terms("P04637")
            assert resp.success is False
            assert "실패" in resp.error_message


class TestGetGoEnrichment:
    @pytest.mark.asyncio
    async def test_success(self):
        c = _make_client()
        raw = {"results": [{"goId": "GO:0001"}, {"goId": "GO:0001"}]}
        with patch.object(c, "_request_with_retry", new_callable=AsyncMock, return_value=raw):
            resp = await c.get_go_enrichment(["P04637", "Q9Y6K9"])
            assert resp.success is True
            assert "gene_annotations" in resp.data
            assert resp.data["total_genes_queried"] == 2
            assert len(resp.data["enriched_terms"]) > 0

    @pytest.mark.asyncio
    async def test_with_exception_result(self):
        c = _make_client()
        raw_ok = {"results": [{"goId": "GO:0001"}]}
        call_count = 0

        async def side_effect(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count <= 1:
                return raw_ok
            raise Exception("fail")

        with patch.object(c, "_request_with_retry", new_callable=AsyncMock, side_effect=side_effect):
            resp = await c.get_go_enrichment(["P04637", "BAD_ID"])
            assert resp.success is True
            assert "P04637" in resp.data["gene_annotations"]

    @pytest.mark.asyncio
    async def test_with_failed_response(self):
        c = _make_client()
        with patch.object(c, "_request_with_retry", new_callable=AsyncMock, side_effect=Exception("all fail")):
            resp = await c.get_go_enrichment(["P04637"])
            assert resp.success is True
            ann = resp.data["gene_annotations"]["P04637"]
            assert "error" in ann

    @pytest.mark.asyncio
    async def test_complete_failure(self):
        c = _make_client()
        with patch.object(c, "get_go_terms", side_effect=Exception("fatal")):
            resp = await c.get_go_enrichment(["P04637"])
            assert resp.success is True
            assert "error" in resp.data["gene_annotations"]["P04637"]


class TestGetKeggPathways:
    @pytest.mark.asyncio
    async def test_success(self):
        c = _make_client()
        resp_mock = _mock_kegg_response("hsa:7157\tpath:hsa04110\nhsa:7157\tpath:hsa04115\n")
        mock_kegg = AsyncMock()
        mock_kegg.get = AsyncMock(return_value=resp_mock)
        mock_kegg.is_closed = False
        with patch.object(c, "_get_kegg_client", new_callable=AsyncMock, return_value=mock_kegg):
            resp = await c.get_kegg_pathways("7157")
            assert resp.success is True
            assert len(resp.data) == 2
            assert resp.data[0]["pathway_id"] == "path:hsa04110"

    @pytest.mark.asyncio
    async def test_empty_response(self):
        c = _make_client()
        resp_mock = _mock_kegg_response("")
        mock_kegg = AsyncMock()
        mock_kegg.get = AsyncMock(return_value=resp_mock)
        mock_kegg.is_closed = False
        with patch.object(c, "_get_kegg_client", new_callable=AsyncMock, return_value=mock_kegg):
            resp = await c.get_kegg_pathways("99999")
            assert resp.success is True
            assert resp.data == []

    @pytest.mark.asyncio
    async def test_cached(self):
        c = _make_client()
        resp_mock = _mock_kegg_response("hsa:7157\tpath:hsa04110\n")
        mock_kegg = AsyncMock()
        mock_kegg.get = AsyncMock(return_value=resp_mock)
        mock_kegg.is_closed = False
        with patch.object(c, "_get_kegg_client", new_callable=AsyncMock, return_value=mock_kegg):
            await c.get_kegg_pathways("7157")
            await c.get_kegg_pathways("7157")
            assert mock_kegg.get.await_count == 1

    @pytest.mark.asyncio
    async def test_failure(self):
        c = _make_client()
        mock_kegg = AsyncMock()
        mock_kegg.get = AsyncMock(side_effect=Exception("err"))
        mock_kegg.is_closed = False
        with patch.object(c, "_get_kegg_client", new_callable=AsyncMock, return_value=mock_kegg):
            resp = await c.get_kegg_pathways("7157")
            assert resp.success is False


class TestGetKeggPathwayInfo:
    @pytest.mark.asyncio
    async def test_success(self):
        c = _make_client()
        flat_text = (
            "ENTRY       hsa04110\n"
            "NAME        Cell cycle\n"
            "DESCRIPTION Cell cycle regulation\n"
            "///\n"
        )
        resp_mock = _mock_kegg_response(flat_text)
        mock_kegg = AsyncMock()
        mock_kegg.get = AsyncMock(return_value=resp_mock)
        mock_kegg.is_closed = False
        with patch.object(c, "_get_kegg_client", new_callable=AsyncMock, return_value=mock_kegg):
            resp = await c.get_kegg_pathway_info("hsa04110")
            assert resp.success is True
            assert resp.data["pathway_id"] == "hsa04110"
            assert "entry" in resp.data
            assert "name" in resp.data

    @pytest.mark.asyncio
    async def test_failure(self):
        c = _make_client()
        mock_kegg = AsyncMock()
        mock_kegg.get = AsyncMock(side_effect=Exception("err"))
        mock_kegg.is_closed = False
        with patch.object(c, "_get_kegg_client", new_callable=AsyncMock, return_value=mock_kegg):
            resp = await c.get_kegg_pathway_info("hsa04110")
            assert resp.success is False


class TestParseKeggFlat:
    def test_basic(self):
        text = "ENTRY       hsa04110\nNAME        Cell cycle\n///\n"
        result = AnnotationClient._parse_kegg_flat(text)
        assert result["entry"] == "hsa04110"
        assert result["name"] == "Cell cycle"

    def test_multiline_value(self):
        text = "GENE        7157  TP53\n            675  BRCA2\n///\n"
        result = AnnotationClient._parse_kegg_flat(text)
        assert "TP53" in result["gene"]
        assert "BRCA2" in result["gene"]

    def test_empty(self):
        result = AnnotationClient._parse_kegg_flat("")
        assert result == {}

    def test_no_terminator(self):
        text = "ENTRY       hsa04110\nNAME        Cell cycle\n"
        result = AnnotationClient._parse_kegg_flat(text)
        assert "entry" in result


class TestGetGeneInfo:
    @pytest.mark.asyncio
    async def test_success(self):
        c = _make_client()
        gene_data = {
            "id": "ENSG00000141510",
            "display_name": "TP53",
            "biotype": "protein_coding",
        }
        resp_mock = _mock_ensembl_response(gene_data)
        mock_ensembl = AsyncMock()
        mock_ensembl.get = AsyncMock(return_value=resp_mock)
        mock_ensembl.is_closed = False
        with patch.object(c, "_get_ensembl_client", new_callable=AsyncMock, return_value=mock_ensembl):
            resp = await c.get_gene_info("ENSG00000141510")
            assert resp.success is True
            assert resp.data["display_name"] == "TP53"

    @pytest.mark.asyncio
    async def test_failure(self):
        c = _make_client()
        mock_ensembl = AsyncMock()
        mock_ensembl.get = AsyncMock(side_effect=Exception("err"))
        mock_ensembl.is_closed = False
        with patch.object(c, "_get_ensembl_client", new_callable=AsyncMock, return_value=mock_ensembl):
            resp = await c.get_gene_info("ENSG00000141510")
            assert resp.success is False


class TestGetGeneBySymbol:
    @pytest.mark.asyncio
    async def test_success(self):
        c = _make_client()
        gene_data = {"id": "ENSG00000141510", "display_name": "TP53"}
        resp_mock = _mock_ensembl_response(gene_data)
        mock_ensembl = AsyncMock()
        mock_ensembl.get = AsyncMock(return_value=resp_mock)
        mock_ensembl.is_closed = False
        with patch.object(c, "_get_ensembl_client", new_callable=AsyncMock, return_value=mock_ensembl):
            resp = await c.get_gene_by_symbol("TP53")
            assert resp.success is True

    @pytest.mark.asyncio
    async def test_custom_species(self):
        c = _make_client()
        gene_data = {"id": "ENSMUSG00000059552"}
        resp_mock = _mock_ensembl_response(gene_data)
        mock_ensembl = AsyncMock()
        mock_ensembl.get = AsyncMock(return_value=resp_mock)
        mock_ensembl.is_closed = False
        with patch.object(c, "_get_ensembl_client", new_callable=AsyncMock, return_value=mock_ensembl):
            resp = await c.get_gene_by_symbol("Trp53", species="mus_musculus")
            assert resp.success is True

    @pytest.mark.asyncio
    async def test_failure(self):
        c = _make_client()
        mock_ensembl = AsyncMock()
        mock_ensembl.get = AsyncMock(side_effect=Exception("err"))
        mock_ensembl.is_closed = False
        with patch.object(c, "_get_ensembl_client", new_callable=AsyncMock, return_value=mock_ensembl):
            resp = await c.get_gene_by_symbol("TP53")
            assert resp.success is False


class TestSearchDelegation:
    @pytest.mark.asyncio
    async def test_search_delegates_to_gene_by_symbol(self):
        c = _make_client()
        gene_data = {"id": "ENSG00000141510"}
        resp_mock = _mock_ensembl_response(gene_data)
        mock_ensembl = AsyncMock()
        mock_ensembl.get = AsyncMock(return_value=resp_mock)
        mock_ensembl.is_closed = False
        with patch.object(c, "_get_ensembl_client", new_callable=AsyncMock, return_value=mock_ensembl):
            resp = await c.search("TP53")
            assert resp.success is True

    @pytest.mark.asyncio
    async def test_search_with_species(self):
        c = _make_client()
        gene_data = {"id": "ENSMUSG00000059552"}
        resp_mock = _mock_ensembl_response(gene_data)
        mock_ensembl = AsyncMock()
        mock_ensembl.get = AsyncMock(return_value=resp_mock)
        mock_ensembl.is_closed = False
        with patch.object(c, "_get_ensembl_client", new_callable=AsyncMock, return_value=mock_ensembl):
            resp = await c.search("Trp53", species="mus_musculus")
            assert resp.success is True


class TestFetchById:
    @pytest.mark.asyncio
    async def test_delegates_to_gene_info(self):
        c = _make_client()
        gene_data = {"id": "ENSG00000141510"}
        resp_mock = _mock_ensembl_response(gene_data)
        mock_ensembl = AsyncMock()
        mock_ensembl.get = AsyncMock(return_value=resp_mock)
        mock_ensembl.is_closed = False
        with patch.object(c, "_get_ensembl_client", new_callable=AsyncMock, return_value=mock_ensembl):
            resp = await c.fetch_by_id("ENSG00000141510")
            assert resp.success is True


class TestGetOrthologs:
    @pytest.mark.asyncio
    async def test_success(self):
        c = _make_client()
        raw = {"data": [{"homologies": [
            {"type": "ortholog_one2one", "target": {"id": "ENSMUSG00000059552"}},
        ]}]}
        resp_mock = _mock_ensembl_response(raw)
        mock_ensembl = AsyncMock()
        mock_ensembl.get = AsyncMock(return_value=resp_mock)
        mock_ensembl.is_closed = False
        with patch.object(c, "_get_ensembl_client", new_callable=AsyncMock, return_value=mock_ensembl):
            resp = await c.get_orthologs("ENSG00000141510")
            assert resp.success is True
            assert len(resp.data) == 1

    @pytest.mark.asyncio
    async def test_empty_data(self):
        c = _make_client()
        raw = {"data": []}
        resp_mock = _mock_ensembl_response(raw)
        mock_ensembl = AsyncMock()
        mock_ensembl.get = AsyncMock(return_value=resp_mock)
        mock_ensembl.is_closed = False
        with patch.object(c, "_get_ensembl_client", new_callable=AsyncMock, return_value=mock_ensembl):
            resp = await c.get_orthologs("ENSG00000141510")
            assert resp.success is True
            assert resp.data == []

    @pytest.mark.asyncio
    async def test_failure(self):
        c = _make_client()
        mock_ensembl = AsyncMock()
        mock_ensembl.get = AsyncMock(side_effect=Exception("err"))
        mock_ensembl.is_closed = False
        with patch.object(c, "_get_ensembl_client", new_callable=AsyncMock, return_value=mock_ensembl):
            resp = await c.get_orthologs("ENSG00000141510")
            assert resp.success is False


class TestClose:
    @pytest.mark.asyncio
    async def test_close_all_clients(self):
        c = AnnotationClient()
        mock_kegg = AsyncMock()
        mock_kegg.is_closed = False
        c._kegg_client = mock_kegg
        mock_ensembl = AsyncMock()
        mock_ensembl.is_closed = False
        c._ensembl_client = mock_ensembl
        await c.close()
        mock_kegg.aclose.assert_awaited_once()
        mock_ensembl.aclose.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_close_already_closed(self):
        c = AnnotationClient()
        await c.close()


class TestHealthCheck:
    @pytest.mark.asyncio
    async def test_all_healthy(self):
        c = _make_client()
        ok_resp = MagicMock()
        ok_resp.status_code = 200
        mock_quickgo = AsyncMock()
        mock_quickgo.get = AsyncMock(return_value=ok_resp)
        mock_quickgo.is_closed = False
        mock_ensembl = AsyncMock()
        mock_ensembl.get = AsyncMock(return_value=ok_resp)
        mock_ensembl.is_closed = False
        mock_kegg = AsyncMock()
        mock_kegg.get = AsyncMock(return_value=ok_resp)
        mock_kegg.is_closed = False
        with patch.object(c, "_get_client", new_callable=AsyncMock, return_value=mock_quickgo), \
             patch.object(c, "_get_ensembl_client", new_callable=AsyncMock, return_value=mock_ensembl), \
             patch.object(c, "_get_kegg_client", new_callable=AsyncMock, return_value=mock_kegg):
            assert await c.health_check() is True

    @pytest.mark.asyncio
    async def test_partial_healthy(self):
        c = _make_client()
        ok_resp = MagicMock()
        ok_resp.status_code = 200
        mock_quickgo = AsyncMock()
        mock_quickgo.get = AsyncMock(side_effect=Exception("down"))
        mock_quickgo.is_closed = False
        mock_ensembl = AsyncMock()
        mock_ensembl.get = AsyncMock(return_value=ok_resp)
        mock_ensembl.is_closed = False
        mock_kegg = AsyncMock()
        mock_kegg.get = AsyncMock(side_effect=Exception("down"))
        mock_kegg.is_closed = False
        with patch.object(c, "_get_client", new_callable=AsyncMock, return_value=mock_quickgo), \
             patch.object(c, "_get_ensembl_client", new_callable=AsyncMock, return_value=mock_ensembl), \
             patch.object(c, "_get_kegg_client", new_callable=AsyncMock, return_value=mock_kegg):
            assert await c.health_check() is True

    @pytest.mark.asyncio
    async def test_all_unhealthy(self):
        c = _make_client()
        mock_quickgo = AsyncMock()
        mock_quickgo.get = AsyncMock(side_effect=Exception("down"))
        mock_quickgo.is_closed = False
        mock_ensembl = AsyncMock()
        mock_ensembl.get = AsyncMock(side_effect=Exception("down"))
        mock_ensembl.is_closed = False
        mock_kegg = AsyncMock()
        mock_kegg.get = AsyncMock(side_effect=Exception("down"))
        mock_kegg.is_closed = False
        with patch.object(c, "_get_client", new_callable=AsyncMock, return_value=mock_quickgo), \
             patch.object(c, "_get_ensembl_client", new_callable=AsyncMock, return_value=mock_ensembl), \
             patch.object(c, "_get_kegg_client", new_callable=AsyncMock, return_value=mock_kegg):
            assert await c.health_check() is False


class TestGetKeggClient:
    @pytest.mark.asyncio
    async def test_creates_kegg_client(self):
        import httpx as real_httpx
        c = AnnotationClient()
        c._kegg_client = None
        mock_async = MagicMock()
        mock_async.is_closed = False
        with patch.object(real_httpx, "AsyncClient", return_value=mock_async):
            client = await c._get_kegg_client()
            assert client is mock_async

    @pytest.mark.asyncio
    async def test_reuses_kegg_client(self):
        c = AnnotationClient()
        mock_kegg = MagicMock()
        mock_kegg.is_closed = False
        c._kegg_client = mock_kegg
        client = await c._get_kegg_client()
        assert client is mock_kegg


class TestGetEnsemblClient:
    @pytest.mark.asyncio
    async def test_creates_ensembl_client(self):
        import httpx as real_httpx
        c = AnnotationClient()
        c._ensembl_client = None
        mock_async = MagicMock()
        mock_async.is_closed = False
        with patch.object(real_httpx, "AsyncClient", return_value=mock_async):
            client = await c._get_ensembl_client()
            assert client is mock_async

    @pytest.mark.asyncio
    async def test_reuses_ensembl_client(self):
        c = AnnotationClient()
        mock_ensembl = MagicMock()
        mock_ensembl.is_closed = False
        c._ensembl_client = mock_ensembl
        client = await c._get_ensembl_client()
        assert client is mock_ensembl
