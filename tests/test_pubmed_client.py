"""
Tests for core/pubmed_client.py
"""

import json
from unittest.mock import MagicMock, mock_open, patch

from core.pubmed_client import PubMedClient


class TestPubMedClientInit:
    def test_default_email(self):
        with patch("core.pubmed_client.Entrez") as mock_entrez:
            PubMedClient()
            assert mock_entrez.email == "your.email@example.com"

    def test_custom_email(self):
        with patch("core.pubmed_client.Entrez") as mock_entrez:
            PubMedClient(email="test@test.com")
            assert mock_entrez.email == "test@test.com"


class TestFetchPaperMetadata:
    @patch("core.pubmed_client.Entrez")
    def test_success(self, mock_entrez):
        c = PubMedClient()
        # Mock _fetch_summary
        summary = {
            "Title": "Test Paper",
            "Authors": ["Author A"],
            "Source": "Nature",
            "PubDate": "2024 Jan",
            "DOI": "10.1234/test",
            "ArticleIds": {"doi": "10.1234/test"},
        }
        with patch.object(c, "_fetch_summary", return_value=summary), \
             patch.object(c, "_fetch_abstract", return_value="Abstract text"), \
             patch.object(c, "_find_sra_links", return_value=["SRR123"]), \
             patch.object(c, "_find_geo_links", return_value=["GSE456"]), \
             patch.object(c, "_extract_keywords", return_value=["rna-seq"]):

            meta = c.fetch_paper_metadata("12345")
            assert meta is not None
            assert meta["pmid"] == "12345"
            assert meta["title"] == "Test Paper"
            assert meta["sra_links"] == ["SRR123"]
            assert meta["geo_links"] == ["GSE456"]

    @patch("core.pubmed_client.Entrez")
    def test_summary_none(self, mock_entrez):
        c = PubMedClient()
        with patch.object(c, "_fetch_summary", return_value=None):
            meta = c.fetch_paper_metadata("12345")
            assert meta is None

    @patch("core.pubmed_client.Entrez")
    def test_exception(self, mock_entrez):
        c = PubMedClient()
        with patch.object(c, "_fetch_summary", side_effect=Exception("err")):
            meta = c.fetch_paper_metadata("12345")
            assert meta is None


class TestFetchSummary:
    @patch("core.pubmed_client.Entrez")
    def test_success(self, mock_entrez):
        c = PubMedClient()
        mock_handle = MagicMock()
        mock_entrez.esummary.return_value = mock_handle
        mock_entrez.read.return_value = {"12345": {"Title": "T"}}

        result = c._fetch_summary("12345")
        assert result is not None
        assert result["Title"] == "T"
        mock_handle.close.assert_called_once()

    @patch("core.pubmed_client.Entrez")
    def test_not_found(self, mock_entrez):
        c = PubMedClient()
        mock_handle = MagicMock()
        mock_entrez.esummary.return_value = mock_handle
        mock_entrez.read.return_value = {}

        result = c._fetch_summary("12345")
        assert result is None

    @patch("core.pubmed_client.Entrez")
    def test_exception(self, mock_entrez):
        c = PubMedClient()
        mock_entrez.esummary.side_effect = Exception("err")
        result = c._fetch_summary("12345")
        assert result is None


class TestFetchAbstract:
    @patch("core.pubmed_client.Entrez")
    def test_success_list(self, mock_entrez):
        c = PubMedClient()
        mock_handle = MagicMock()
        mock_entrez.efetch.return_value = mock_handle
        mock_entrez.read.return_value = {
            "PubmedArticle": [{
                "MedlineCitation": {
                    "Article": {
                        "Abstract": {
                            "AbstractText": ["Part one.", "Part two."]
                        }
                    }
                }
            }]
        }

        result = c._fetch_abstract("12345")
        assert result == "Part one. Part two."

    @patch("core.pubmed_client.Entrez")
    def test_success_string(self, mock_entrez):
        c = PubMedClient()
        mock_handle = MagicMock()
        mock_entrez.efetch.return_value = mock_handle
        mock_entrez.read.return_value = {
            "PubmedArticle": [{
                "MedlineCitation": {
                    "Article": {
                        "Abstract": {
                            "AbstractText": "Single string abstract."
                        }
                    }
                }
            }]
        }

        result = c._fetch_abstract("12345")
        assert result == "Single string abstract."

    @patch("core.pubmed_client.Entrez")
    def test_no_articles(self, mock_entrez):
        c = PubMedClient()
        mock_handle = MagicMock()
        mock_entrez.efetch.return_value = mock_handle
        mock_entrez.read.return_value = {"PubmedArticle": []}

        result = c._fetch_abstract("12345")
        assert result == ""

    @patch("core.pubmed_client.Entrez")
    def test_exception(self, mock_entrez):
        c = PubMedClient()
        mock_entrez.efetch.side_effect = Exception("err")
        result = c._fetch_abstract("12345")
        assert result == ""


class TestFindSraLinks:
    @patch("core.pubmed_client.Entrez")
    def test_success(self, mock_entrez):
        c = PubMedClient()
        mock_handle = MagicMock()
        mock_entrez.elink.return_value = mock_handle
        mock_entrez.read.return_value = [
            {"LinkSetDb": [{"Link": [{"Id": "SRR123"}, {"Id": "SRR456"}]}]}
        ]

        result = c._find_sra_links("12345")
        assert result == ["SRR123", "SRR456"]

    @patch("core.pubmed_client.Entrez")
    def test_no_links(self, mock_entrez):
        c = PubMedClient()
        mock_handle = MagicMock()
        mock_entrez.elink.return_value = mock_handle
        mock_entrez.read.return_value = [{}]

        result = c._find_sra_links("12345")
        assert result == []

    @patch("core.pubmed_client.Entrez")
    def test_empty_record(self, mock_entrez):
        c = PubMedClient()
        mock_handle = MagicMock()
        mock_entrez.elink.return_value = mock_handle
        mock_entrez.read.return_value = []

        result = c._find_sra_links("12345")
        assert result == []

    @patch("core.pubmed_client.Entrez")
    def test_exception(self, mock_entrez):
        c = PubMedClient()
        mock_entrez.elink.side_effect = Exception("err")
        result = c._find_sra_links("12345")
        assert result == []


class TestFindGeoLinks:
    @patch("core.pubmed_client.Entrez")
    def test_success(self, mock_entrez):
        c = PubMedClient()
        mock_handle = MagicMock()
        mock_entrez.elink.return_value = mock_handle
        mock_entrez.read.return_value = [
            {"LinkSetDb": [{"Link": [{"Id": "GSE123"}]}]}
        ]

        result = c._find_geo_links("12345")
        assert result == ["GSE123"]

    @patch("core.pubmed_client.Entrez")
    def test_no_links(self, mock_entrez):
        c = PubMedClient()
        mock_handle = MagicMock()
        mock_entrez.elink.return_value = mock_handle
        mock_entrez.read.return_value = [{}]

        result = c._find_geo_links("12345")
        assert result == []

    @patch("core.pubmed_client.Entrez")
    def test_exception(self, mock_entrez):
        c = PubMedClient()
        mock_entrez.elink.side_effect = Exception("err")
        result = c._find_geo_links("12345")
        assert result == []


class TestExtractKeywords:
    @patch("core.pubmed_client.Entrez")
    def test_from_summary(self, mock_entrez):
        c = PubMedClient()
        summary = {"KeywordList": [["keyword1", "keyword2"]]}
        result = c._extract_keywords(summary, "")
        assert "keyword1" in result
        assert "keyword2" in result

    @patch("core.pubmed_client.Entrez")
    def test_from_abstract(self, mock_entrez):
        c = PubMedClient()
        abstract = "We performed single-cell RNA-seq analysis using next-generation sequencing"
        result = c._extract_keywords({}, abstract)
        assert "single-cell" in result
        assert "rna-seq" in result
        assert "next-generation sequencing" in result

    @patch("core.pubmed_client.Entrez")
    def test_deduplication(self, mock_entrez):
        c = PubMedClient()
        summary = {"KeywordList": [["rna-seq"]]}
        abstract = "We used rna-seq technology"
        result = c._extract_keywords(summary, abstract)
        assert result.count("rna-seq") == 1

    @patch("core.pubmed_client.Entrez")
    def test_empty(self, mock_entrez):
        c = PubMedClient()
        result = c._extract_keywords({}, "")
        assert result == []


class TestSearchByTopic:
    @patch("core.pubmed_client.Entrez")
    def test_success(self, mock_entrez):
        c = PubMedClient()
        mock_handle = MagicMock()
        mock_entrez.esearch.return_value = mock_handle
        mock_entrez.read.return_value = {"IdList": ["111", "222"]}

        with patch.object(c, "fetch_paper_metadata") as mock_fetch:
            mock_fetch.return_value = {"pmid": "111", "title": "T"}
            with patch("core.pubmed_client.time"):
                results = c.search_by_topic("cancer", max_results=2)
                assert len(results) == 2

    @patch("core.pubmed_client.Entrez")
    def test_no_results(self, mock_entrez):
        c = PubMedClient()
        mock_handle = MagicMock()
        mock_entrez.esearch.return_value = mock_handle
        mock_entrez.read.return_value = {"IdList": []}

        results = c.search_by_topic("nonexistent xyz")
        assert results == []

    @patch("core.pubmed_client.Entrez")
    def test_exception(self, mock_entrez):
        c = PubMedClient()
        mock_entrez.esearch.side_effect = Exception("err")
        results = c.search_by_topic("cancer")
        assert results == []

    @patch("core.pubmed_client.Entrez")
    def test_partial_metadata_failure(self, mock_entrez):
        c = PubMedClient()
        mock_handle = MagicMock()
        mock_entrez.esearch.return_value = mock_handle
        mock_entrez.read.return_value = {"IdList": ["111", "222"]}

        call_count = 0

        def fetch_side_effect(pmid):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return {"pmid": "111", "title": "T"}
            return None

        with patch.object(c, "fetch_paper_metadata", side_effect=fetch_side_effect):
            with patch("core.pubmed_client.time"):
                results = c.search_by_topic("cancer")
                assert len(results) == 1


class TestSaveMetadata:
    @patch("core.pubmed_client.Entrez")
    def test_save_default_filename(self, mock_entrez):
        c = PubMedClient()
        metadata = {"pmid": "12345", "title": "T"}

        m = mock_open()
        with patch("builtins.open", m):
            result = c.save_metadata(metadata)
            assert result == "/workspace/results/pubmed_12345.json"

    @patch("core.pubmed_client.Entrez")
    def test_save_custom_filename(self, mock_entrez):
        c = PubMedClient()
        metadata = {"pmid": "12345", "title": "T"}

        m = mock_open()
        with patch("builtins.open", m):
            result = c.save_metadata(metadata, filename="/tmp/test.json")
            assert result == "/tmp/test.json"

    @patch("core.pubmed_client.Entrez")
    def test_save_failure(self, mock_entrez):
        c = PubMedClient()
        metadata = {"pmid": "12345"}

        with patch("builtins.open", side_effect=Exception("err")):
            result = c.save_metadata(metadata)
            assert result == ""


class TestLoadMetadata:
    @patch("core.pubmed_client.Entrez")
    def test_success(self, mock_entrez):
        c = PubMedClient()
        data = {"pmid": "12345", "title": "T"}
        m = mock_open(read_data=json.dumps(data))
        with patch("builtins.open", m):
            result = c.load_metadata("12345")
            assert result == data

    @patch("core.pubmed_client.Entrez")
    def test_not_found(self, mock_entrez):
        c = PubMedClient()
        with patch("builtins.open", side_effect=FileNotFoundError()):
            result = c.load_metadata("99999")
            assert result is None
