"""
Tests for clients/tcga_client.py
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from clients.base import ClientConfig
from clients.tcga_client import TCGAClient, _gdc_and, _gdc_filter


class TestGdcFilterHelpers:
    def test_gdc_filter_string(self):
        f = _gdc_filter("disease_type", "BRCA")
        assert f == {"op": "=", "content": {"field": "disease_type", "value": ["BRCA"]}}

    def test_gdc_filter_list(self):
        f = _gdc_filter("primary_site", ["Breast", "Lung"])
        assert f["content"]["value"] == ["Breast", "Lung"]

    def test_gdc_filter_custom_op(self):
        f = _gdc_filter("age", "50", op=">=")
        assert f["op"] == ">="

    def test_gdc_and_single(self):
        f = _gdc_filter("x", "y")
        result = _gdc_and(f)
        assert result == f

    def test_gdc_and_multiple(self):
        f1 = _gdc_filter("a", "1")
        f2 = _gdc_filter("b", "2")
        result = _gdc_and(f1, f2)
        assert result["op"] == "and"
        assert len(result["content"]) == 2

    def test_gdc_and_skips_empty(self):
        f1 = _gdc_filter("a", "1")
        result = _gdc_and(f1, {})
        assert result == f1


def _make_client(**cfg_overrides):
    cfg = ClientConfig(
        base_url="https://api.gdc.cancer.gov",
        rate_limit_delay=0,
        max_retries=1,
        **cfg_overrides,
    )
    return TCGAClient(config=cfg)


class TestTCGAInit:
    def test_default_config(self):
        c = TCGAClient()
        assert c.name == "tcga_gdc"
        assert c.config.timeout == 60

    def test_custom_config(self):
        cfg = ClientConfig(base_url="https://custom.gdc.gov")
        c = TCGAClient(config=cfg)
        assert c.config.base_url == "https://custom.gdc.gov"


class TestSearchProjects:
    @pytest.mark.asyncio
    async def test_search_projects_success(self):
        c = _make_client()
        raw = {"data": {"hits": [
            {"project_id": "TCGA-BRCA", "name": "Breast Cancer"},
        ]}}
        with patch.object(c, "_request_with_retry", new_callable=AsyncMock, return_value=raw):
            resp = await c.search_projects(disease_type="Breast Invasive Carcinoma")
            assert resp.success is True
            assert resp.data[0]["project_id"] == "TCGA-BRCA"

    @pytest.mark.asyncio
    async def test_search_projects_with_primary_site(self):
        c = _make_client()
        raw = {"data": {"hits": []}}
        with patch.object(c, "_request_with_retry", new_callable=AsyncMock, return_value=raw):
            resp = await c.search_projects(disease_type="BRCA", primary_site="Breast")
            assert resp.success is True

    @pytest.mark.asyncio
    async def test_search_projects_no_filters(self):
        c = _make_client()
        raw = {"data": {"hits": [{"project_id": "TCGA-LUAD"}]}}
        with patch.object(c, "_request_with_retry", new_callable=AsyncMock, return_value=raw):
            resp = await c.search_projects()
            assert resp.success is True

    @pytest.mark.asyncio
    async def test_search_projects_cached(self):
        c = _make_client()
        raw = {"data": {"hits": [{"project_id": "TCGA-BRCA"}]}}
        mock_retry = AsyncMock(return_value=raw)
        with patch.object(c, "_request_with_retry", mock_retry):
            await c.search_projects(disease_type="BRCA")
            await c.search_projects(disease_type="BRCA")
            assert mock_retry.await_count == 1

    @pytest.mark.asyncio
    async def test_search_projects_failure(self):
        c = _make_client()
        with patch.object(c, "_request_with_retry", new_callable=AsyncMock, side_effect=Exception("timeout")):
            resp = await c.search_projects(disease_type="BRCA")
            assert resp.success is False


class TestSearch:
    @pytest.mark.asyncio
    async def test_search_delegates_to_search_projects(self):
        c = _make_client()
        raw = {"data": {"hits": [{"project_id": "TCGA-OV"}]}}
        with patch.object(c, "_request_with_retry", new_callable=AsyncMock, return_value=raw):
            resp = await c.search("Ovarian Serous Cystadenocarcinoma", primary_site="Ovary")
            assert resp.success is True


class TestSearchCases:
    @pytest.mark.asyncio
    async def test_search_cases_success(self):
        c = _make_client()
        raw = {"data": {"hits": [
            {"case_id": "uuid-1", "submitter_id": "TCGA-A1-A0SB"},
        ]}}
        with patch.object(c, "_request_with_retry", new_callable=AsyncMock, return_value=raw):
            resp = await c.search_cases("TCGA-BRCA")
            assert resp.success is True
            assert resp.data[0]["case_id"] == "uuid-1"

    @pytest.mark.asyncio
    async def test_search_cases_failure(self):
        c = _make_client()
        with patch.object(c, "_request_with_retry", new_callable=AsyncMock, side_effect=Exception("err")):
            resp = await c.search_cases("TCGA-BRCA")
            assert resp.success is False


class TestSearchFiles:
    @pytest.mark.asyncio
    async def test_search_files_success(self):
        c = _make_client()
        raw = {"data": {"hits": [
            {"file_id": "fid-1", "file_name": "gene_exp.tsv"},
        ]}}
        with patch.object(c, "_request_with_retry", new_callable=AsyncMock, return_value=raw):
            resp = await c.search_files("uuid-1")
            assert resp.success is True
            assert resp.data[0]["file_id"] == "fid-1"

    @pytest.mark.asyncio
    async def test_search_files_custom_category(self):
        c = _make_client()
        raw = {"data": {"hits": []}}
        with patch.object(c, "_request_with_retry", new_callable=AsyncMock, return_value=raw):
            resp = await c.search_files("uuid-1", data_category="Copy Number Variation")
            assert resp.success is True

    @pytest.mark.asyncio
    async def test_search_files_failure(self):
        c = _make_client()
        with patch.object(c, "_request_with_retry", new_callable=AsyncMock, side_effect=Exception("err")):
            resp = await c.search_files("uuid-1")
            assert resp.success is False


class TestGetGeneExpression:
    @pytest.mark.asyncio
    async def test_empty_file_ids(self):
        c = _make_client()
        resp = await c.get_gene_expression([])
        assert resp.success is False
        assert "비어" in resp.error_message

    @pytest.mark.asyncio
    async def test_json_response(self):
        c = _make_client()
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.headers = {"content-type": "application/json"}
        mock_resp.json.return_value = {"data": "expression_data"}
        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=mock_resp)
        mock_client.is_closed = False
        with patch.object(c, "_get_client", new_callable=AsyncMock, return_value=mock_client):
            resp = await c.get_gene_expression(["fid-1"])
            assert resp.success is True
            assert resp.data["data"] == "expression_data"

    @pytest.mark.asyncio
    async def test_binary_response(self):
        c = _make_client()
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.headers = {"content-type": "application/octet-stream"}
        mock_resp.content = b'\x00\x01\x02'
        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=mock_resp)
        mock_client.is_closed = False
        with patch.object(c, "_get_client", new_callable=AsyncMock, return_value=mock_client):
            resp = await c.get_gene_expression(["fid-1", "fid-2"])
            assert resp.success is True
            assert resp.data["content_type"] == "application/octet-stream"
            assert resp.data["file_ids"] == ["fid-1", "fid-2"]

    @pytest.mark.asyncio
    async def test_http_error(self):
        c = _make_client()
        mock_resp = MagicMock()
        mock_resp.status_code = 400
        mock_resp.text = "Bad Request"
        mock_resp.headers = {}
        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=mock_resp)
        mock_client.is_closed = False
        with patch.object(c, "_get_client", new_callable=AsyncMock, return_value=mock_client):
            resp = await c.get_gene_expression(["fid-1"])
            assert resp.success is False
            assert "400" in resp.error_message

    @pytest.mark.asyncio
    async def test_exception(self):
        c = _make_client()
        mock_client = AsyncMock()
        mock_client.post = AsyncMock(side_effect=Exception("conn err"))
        mock_client.is_closed = False
        with patch.object(c, "_get_client", new_callable=AsyncMock, return_value=mock_client):
            resp = await c.get_gene_expression(["fid-1"])
            assert resp.success is False


class TestGetClinicalData:
    @pytest.mark.asyncio
    async def test_clinical_success(self):
        c = _make_client()
        raw = {"data": {
            "case_id": "uuid-1",
            "diagnoses": [{"primary_diagnosis": "Adenocarcinoma"}],
        }}
        with patch.object(c, "_request_with_retry", new_callable=AsyncMock, return_value=raw):
            resp = await c.get_clinical_data("uuid-1")
            assert resp.success is True
            assert resp.data["case_id"] == "uuid-1"

    @pytest.mark.asyncio
    async def test_clinical_no_data_wrapper(self):
        c = _make_client()
        raw = {"case_id": "uuid-1"}
        with patch.object(c, "_request_with_retry", new_callable=AsyncMock, return_value=raw):
            resp = await c.get_clinical_data("uuid-1")
            assert resp.success is True

    @pytest.mark.asyncio
    async def test_clinical_failure(self):
        c = _make_client()
        with patch.object(c, "_request_with_retry", new_callable=AsyncMock, side_effect=Exception("err")):
            resp = await c.get_clinical_data("uuid-1")
            assert resp.success is False


class TestFetchById:
    @pytest.mark.asyncio
    async def test_delegates_to_clinical(self):
        c = _make_client()
        raw = {"data": {"case_id": "uuid-1"}}
        with patch.object(c, "_request_with_retry", new_callable=AsyncMock, return_value=raw):
            resp = await c.fetch_by_id("uuid-1")
            assert resp.success is True


class TestHealthCheck:
    @pytest.mark.asyncio
    async def test_healthy(self):
        c = _make_client()
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"status": "OK"}
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_resp)
        mock_client.is_closed = False
        with patch.object(c, "_get_client", new_callable=AsyncMock, return_value=mock_client):
            assert await c.health_check() is True

    @pytest.mark.asyncio
    async def test_unhealthy_status(self):
        c = _make_client()
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"status": "ERROR"}
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_resp)
        mock_client.is_closed = False
        with patch.object(c, "_get_client", new_callable=AsyncMock, return_value=mock_client):
            assert await c.health_check() is False

    @pytest.mark.asyncio
    async def test_unhealthy_500(self):
        c = _make_client()
        mock_resp = MagicMock()
        mock_resp.status_code = 500
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_resp)
        mock_client.is_closed = False
        with patch.object(c, "_get_client", new_callable=AsyncMock, return_value=mock_client):
            assert await c.health_check() is False

    @pytest.mark.asyncio
    async def test_unhealthy_exception(self):
        c = _make_client()
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(side_effect=Exception("down"))
        mock_client.is_closed = False
        with patch.object(c, "_get_client", new_callable=AsyncMock, return_value=mock_client):
            assert await c.health_check() is False
