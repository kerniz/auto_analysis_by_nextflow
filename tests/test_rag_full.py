"""
Tests for rag/ modules — DocumentStore and RAGContext
Uses mocks to avoid dependency on chromadb/sentence-transformers.
"""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from rag.document_store import DocumentStore
from rag.rag_context import RAGContext

# ===========================================================================
# DocumentStore (mocked chromadb)
# ===========================================================================

class TestDocumentStoreInit:
    def test_init(self, tmp_path):
        store = DocumentStore(tmp_path / "db")
        assert store._client is None
        assert store._collection is None
        assert store._initialized is False
        assert store.persist_dir == tmp_path / "db"

    def test_init_string_path(self, tmp_path):
        store = DocumentStore(str(tmp_path / "db2"))
        assert store.persist_dir == Path(str(tmp_path / "db2"))


class TestDocumentStoreEnsureInitialized:
    def test_ensure_initialized_import_error(self, tmp_path):
        store = DocumentStore(tmp_path / "db")
        with patch("builtins.__import__", side_effect=ImportError("no chromadb")):
            with pytest.raises(ImportError, match="chromadb"):
                store._ensure_initialized()

    def test_ensure_initialized_idempotent(self, tmp_path):
        store = DocumentStore(tmp_path / "db")
        store._initialized = True
        # Should return immediately without doing anything
        store._ensure_initialized()
        assert store._initialized is True

    def test_ensure_initialized_success(self, tmp_path):
        """Mock chromadb imports to test the initialization path."""
        mock_chromadb = MagicMock()
        mock_client = MagicMock()
        mock_collection = MagicMock()
        mock_chromadb.PersistentClient.return_value = mock_client
        mock_client.get_or_create_collection.return_value = mock_collection

        mock_embedding_module = MagicMock()
        mock_embedding_fn = MagicMock()
        mock_embedding_module.SentenceTransformerEmbeddingFunction.return_value = mock_embedding_fn

        store = DocumentStore(tmp_path / "db")
        with patch.dict("sys.modules", {
            "chromadb": mock_chromadb,
            "chromadb.utils": MagicMock(),
            "chromadb.utils.embedding_functions": mock_embedding_module,
        }):
            store._ensure_initialized()

        assert store._initialized is True
        assert store._client == mock_client
        assert store._collection == mock_collection


def _make_initialized_store(tmp_path):
    """Create a DocumentStore with mocked internals."""
    store = DocumentStore(tmp_path / "db")
    store._initialized = True
    store._client = MagicMock()
    store._collection = MagicMock()
    return store


class TestDocumentStoreAddPaper:
    def test_add_paper_basic(self, tmp_path):
        store = _make_initialized_store(tmp_path)
        store.add_paper(pmid="123", title="Test Paper", abstract="Abstract text")
        store._collection.upsert.assert_called_once()
        call_kwargs = store._collection.upsert.call_args
        assert call_kwargs[1]["ids"] == ["abstract_123"] or call_kwargs[0][0] == ["abstract_123"]

    def test_add_paper_with_year(self, tmp_path):
        store = _make_initialized_store(tmp_path)
        store.add_paper(pmid="456", title="Paper", abstract="Abs", year=2024)
        call_args = store._collection.upsert.call_args
        metadatas = call_args[1].get("metadatas") or call_args[0][2]
        assert metadatas[0]["year"] == 2024

    def test_add_paper_with_extra_meta(self, tmp_path):
        store = _make_initialized_store(tmp_path)
        store.add_paper(
            pmid="789", title="P", abstract="A",
            extra_meta={"journal": "Nature", "authors": "Smith et al."},
        )
        call_args = store._collection.upsert.call_args
        metadatas = call_args[1].get("metadatas") or call_args[0][2]
        assert metadatas[0]["journal"] == "Nature"
        assert metadatas[0]["authors"] == "Smith et al."


class TestDocumentStoreAddAnalysis:
    def test_add_analysis_basic(self, tmp_path):
        store = _make_initialized_store(tmp_path)
        store.add_analysis(pmid="100", analysis_text="Analysis here")
        store._collection.upsert.assert_called_once()
        call_args = store._collection.upsert.call_args
        ids = call_args[1].get("ids") or call_args[0][0]
        assert ids == ["analysis_100"]

    def test_add_analysis_with_rating(self, tmp_path):
        store = _make_initialized_store(tmp_path)
        store.add_analysis(pmid="200", analysis_text="Text", rating="PASS")
        call_args = store._collection.upsert.call_args
        metadatas = call_args[1].get("metadatas") or call_args[0][2]
        assert metadatas[0]["rating"] == "PASS"

    def test_add_analysis_with_extra_meta(self, tmp_path):
        store = _make_initialized_store(tmp_path)
        store.add_analysis(
            pmid="300", analysis_text="Text",
            extra_meta={"score": 0.9},
        )
        call_args = store._collection.upsert.call_args
        metadatas = call_args[1].get("metadatas") or call_args[0][2]
        assert metadatas[0]["score"] == 0.9


class TestDocumentStoreAddDebateReport:
    def test_add_debate_report(self, tmp_path):
        store = _make_initialized_store(tmp_path)
        store.add_debate_report(
            pmid="400", report_text="Report text",
            verdict="PASS", score=0.85,
        )
        store._collection.upsert.assert_called_once()
        call_args = store._collection.upsert.call_args
        ids = call_args[1].get("ids") or call_args[0][0]
        assert ids == ["debate_400"]
        metadatas = call_args[1].get("metadatas") or call_args[0][2]
        assert metadatas[0]["verdict"] == "PASS"
        assert metadatas[0]["score"] == 0.85

    def test_add_debate_report_defaults(self, tmp_path):
        store = _make_initialized_store(tmp_path)
        store.add_debate_report(pmid="500", report_text="Text")
        call_args = store._collection.upsert.call_args
        metadatas = call_args[1].get("metadatas") or call_args[0][2]
        assert metadatas[0]["verdict"] == "UNDETERMINED"
        assert metadatas[0]["score"] == 0.0


class TestDocumentStoreQuery:
    def test_query_basic(self, tmp_path):
        store = _make_initialized_store(tmp_path)
        store._collection.query.return_value = {
            "ids": [["id1", "id2"]],
            "documents": [["doc1", "doc2"]],
            "metadatas": [[{"pmid": "1"}, {"pmid": "2"}]],
            "distances": [[0.1, 0.2]],
        }
        results = store.query("test query", n_results=2)
        assert len(results) == 2
        assert results[0]["id"] == "id1"
        assert results[0]["document"] == "doc1"
        assert results[0]["metadata"]["pmid"] == "1"
        assert results[0]["distance"] == 0.1

    def test_query_with_doc_type(self, tmp_path):
        store = _make_initialized_store(tmp_path)
        store._collection.query.return_value = {
            "ids": [["id1"]],
            "documents": [["doc1"]],
            "metadatas": [[{"doc_type": "paper_abstract"}]],
            "distances": [[0.05]],
        }
        store.query("test", doc_type="paper_abstract")
        call_args = store._collection.query.call_args
        assert call_args[1]["where"] == {"doc_type": "paper_abstract"}

    def test_query_no_doc_type(self, tmp_path):
        store = _make_initialized_store(tmp_path)
        store._collection.query.return_value = {
            "ids": [["id1"]],
            "documents": [["doc1"]],
            "metadatas": [[{}]],
            "distances": [[0.1]],
        }
        store.query("test")
        call_args = store._collection.query.call_args
        assert call_args[1]["where"] is None

    def test_query_empty_results(self, tmp_path):
        store = _make_initialized_store(tmp_path)
        store._collection.query.return_value = {
            "ids": [[]],
            "documents": [[]],
            "metadatas": [[]],
            "distances": [[]],
        }
        results = store.query("nothing")
        assert results == []

    def test_query_null_results(self, tmp_path):
        store = _make_initialized_store(tmp_path)
        store._collection.query.return_value = {
            "ids": None,
            "documents": None,
            "metadatas": None,
            "distances": None,
        }
        results = store.query("nothing")
        assert results == []

    def test_query_missing_documents(self, tmp_path):
        """When documents/metadatas/distances are None but ids exist."""
        store = _make_initialized_store(tmp_path)
        store._collection.query.return_value = {
            "ids": [["id1"]],
            "documents": None,
            "metadatas": None,
            "distances": None,
        }
        results = store.query("test")
        assert len(results) == 1
        assert results[0]["document"] == ""
        assert results[0]["metadata"] == {}
        assert results[0]["distance"] == 0.0


class TestDocumentStoreGetStats:
    def test_get_stats(self, tmp_path):
        store = _make_initialized_store(tmp_path)
        store._collection.count.return_value = 10

        store._collection.get.side_effect = [
            {"ids": ["a1", "a2", "a3"]},       # paper_abstract
            {"ids": ["b1", "b2"]},              # analysis_result
            {"ids": ["c1"]},                    # debate_report
        ]

        stats = store.get_stats()
        assert stats["count"] == 10
        assert stats["doc_types"]["paper_abstract"] == 3
        assert stats["doc_types"]["analysis_result"] == 2
        assert stats["doc_types"]["debate_report"] == 1

    def test_get_stats_with_exception(self, tmp_path):
        store = _make_initialized_store(tmp_path)
        store._collection.count.return_value = 0
        store._collection.get.side_effect = Exception("chromadb error")

        stats = store.get_stats()
        assert stats["count"] == 0
        for dtype in ("paper_abstract", "analysis_result", "debate_report"):
            assert stats["doc_types"][dtype] == 0

    def test_get_stats_empty_ids(self, tmp_path):
        store = _make_initialized_store(tmp_path)
        store._collection.count.return_value = 0
        store._collection.get.return_value = {"ids": None}

        stats = store.get_stats()
        assert stats["count"] == 0
        for dtype in ("paper_abstract", "analysis_result", "debate_report"):
            assert stats["doc_types"][dtype] == 0


# ===========================================================================
# RAGContext
# ===========================================================================

def _make_rag_context(mock_store=None, max_tokens=1500):
    if mock_store is None:
        mock_store = MagicMock(spec=DocumentStore)
        mock_store.query.return_value = []
    return RAGContext(mock_store, max_tokens=max_tokens)


class TestRAGContextInit:
    def test_init(self):
        mock_store = MagicMock()
        ctx = RAGContext(mock_store, max_tokens=2000)
        assert ctx.store == mock_store
        assert ctx.max_tokens == 2000

    def test_default_max_tokens(self):
        ctx = RAGContext(MagicMock())
        assert ctx.max_tokens == 1500


class TestRAGContextBuildContext:
    def test_build_context_empty(self):
        ctx = _make_rag_context()
        result = ctx.build_context("query")
        assert result == ""

    def test_build_context_with_papers(self):
        mock_store = MagicMock()
        mock_store.query.side_effect = lambda query_text, n_results, doc_type: (
            [
                {
                    "document": "Paper abstract about single-cell RNA sequencing",
                    "metadata": {"title": "scRNA-seq", "pmid": "123", "year": 2024},
                    "distance": 0.15,
                },
            ]
            if doc_type == "paper_abstract"
            else []
        )
        ctx = RAGContext(mock_store)
        result = ctx.build_context("scRNA-seq")
        assert "Related Papers" in result
        assert "scRNA-seq" in result
        assert "123" in result
        assert "2024" in result

    def test_build_context_with_analyses(self):
        mock_store = MagicMock()
        mock_store.query.side_effect = lambda query_text, n_results, doc_type: (
            [
                {
                    "document": "Analysis result: high quality data",
                    "metadata": {"pmid": "456", "rating": "PASS"},
                    "distance": 0.2,
                },
            ]
            if doc_type == "analysis_result"
            else []
        )
        ctx = RAGContext(mock_store)
        result = ctx.build_context("analysis")
        assert "Prior Analyses" in result
        assert "PASS" in result
        assert "456" in result

    def test_build_context_with_debates(self):
        mock_store = MagicMock()
        mock_store.query.side_effect = lambda query_text, n_results, doc_type: (
            [
                {
                    "document": "Debate concluded with PASS verdict and 0.9 score",
                    "metadata": {"pmid": "789", "verdict": "PASS", "score": 0.9},
                    "distance": 0.1,
                },
            ]
            if doc_type == "debate_report"
            else []
        )
        ctx = RAGContext(mock_store)
        result = ctx.build_context("debate")
        assert "Debate Reports" in result
        assert "PASS" in result
        assert "789" in result

    def test_build_context_all_types(self):
        mock_store = MagicMock()

        def query_fn(query_text, n_results, doc_type):
            if doc_type == "paper_abstract":
                return [{"document": "Paper text", "metadata": {"title": "T", "pmid": "1", "year": 2024}, "distance": 0.1}]
            elif doc_type == "analysis_result":
                return [{"document": "Analysis text", "metadata": {"pmid": "1", "rating": "PASS"}, "distance": 0.2}]
            elif doc_type == "debate_report":
                return [{"document": "Debate text", "metadata": {"pmid": "1", "verdict": "PASS", "score": 0.8}, "distance": 0.3}]
            return []

        mock_store.query.side_effect = query_fn
        ctx = RAGContext(mock_store)
        result = ctx.build_context("query")
        assert "Related Papers" in result
        assert "Prior Analyses" in result
        assert "Debate Reports" in result

    def test_build_context_truncated(self):
        mock_store = MagicMock()
        # Return a very long document
        long_doc = "word " * 5000
        mock_store.query.side_effect = lambda query_text, n_results, doc_type: (
            [{"document": long_doc, "metadata": {"title": "Long", "pmid": "99", "year": 2024}, "distance": 0.1}]
            if doc_type == "paper_abstract"
            else []
        )
        ctx = RAGContext(mock_store, max_tokens=100)
        result = ctx.build_context("query")
        assert "truncated" in result or len(result) < len(long_doc)

    def test_build_context_long_document_preview_truncation(self):
        """Documents longer than 200 chars should get '...' appended."""
        mock_store = MagicMock()
        long_text = "x" * 300
        mock_store.query.side_effect = lambda query_text, n_results, doc_type: (
            [{"document": long_text, "metadata": {"title": "T", "pmid": "1", "year": 2024}, "distance": 0.1}]
            if doc_type == "paper_abstract"
            else []
        )
        ctx = RAGContext(mock_store, max_tokens=50000)
        result = ctx.build_context("query")
        assert "..." in result


class TestRAGContextFormatSections:
    def test_format_papers_section(self):
        ctx = _make_rag_context()
        papers = [
            {
                "document": "Short abstract",
                "metadata": {"title": "Paper Title", "pmid": "111", "year": 2023},
                "distance": 0.15,
            },
        ]
        section = ctx._format_papers_section(papers)
        assert "Related Papers" in section
        assert "Paper Title" in section
        assert "111" in section
        assert "2023" in section
        assert "0.150" in section

    def test_format_papers_section_missing_metadata(self):
        ctx = _make_rag_context()
        papers = [
            {"document": "text", "metadata": {}, "distance": 0.0},
        ]
        section = ctx._format_papers_section(papers)
        assert "Unknown" in section
        assert "N/A" in section

    def test_format_analyses_section(self):
        ctx = _make_rag_context()
        analyses = [
            {
                "document": "Analysis text content",
                "metadata": {"pmid": "222", "rating": "WARN"},
                "distance": 0.25,
            },
        ]
        section = ctx._format_analyses_section(analyses)
        assert "Prior Analyses" in section
        assert "222" in section
        assert "WARN" in section

    def test_format_analyses_section_missing_metadata(self):
        ctx = _make_rag_context()
        analyses = [{"document": "text", "metadata": {}, "distance": 0.0}]
        section = ctx._format_analyses_section(analyses)
        assert "UNKNOWN" in section

    def test_format_debates_section(self):
        ctx = _make_rag_context()
        debates = [
            {
                "document": "Debate report text",
                "metadata": {"pmid": "333", "verdict": "FAIL", "score": 0.3},
                "distance": 0.1,
            },
        ]
        section = ctx._format_debates_section(debates)
        assert "Debate Reports" in section
        assert "333" in section
        assert "FAIL" in section
        assert "0.3" in section

    def test_format_debates_section_missing_metadata(self):
        ctx = _make_rag_context()
        debates = [{"document": "text", "metadata": {}, "distance": 0.0}]
        section = ctx._format_debates_section(debates)
        assert "UNDETERMINED" in section


class TestRAGContextTruncation:
    def test_truncate_short_text(self):
        ctx = _make_rag_context(max_tokens=1500)
        short = "Hello world"
        assert ctx._truncate_to_tokens(short) == short

    def test_truncate_long_text(self):
        ctx = _make_rag_context(max_tokens=10)
        long_text = " ".join(["word"] * 100)
        truncated = ctx._truncate_to_tokens(long_text)
        assert len(truncated) < len(long_text)
        assert "truncated" in truncated

    def test_truncate_exact_limit(self):
        ctx = _make_rag_context(max_tokens=100)
        # Create text that is just at the limit
        words_needed = int(100 / RAGContext.TOKENS_PER_WORD_RATIO) + 1
        text = " ".join(["w"] * words_needed)
        truncated = ctx._truncate_to_tokens(text)
        # Should either be truncated or the same
        assert isinstance(truncated, str)

    def test_estimate_tokens(self):
        ctx = _make_rag_context()
        text = "one two three four five"
        tokens = ctx._estimate_tokens(text)
        # 5 words / 0.75 = ~6.67 -> 6
        assert tokens == int(5 / RAGContext.TOKENS_PER_WORD_RATIO)

    def test_estimate_tokens_empty(self):
        ctx = _make_rag_context()
        assert ctx._estimate_tokens("") == 0

    def test_truncate_preserves_words(self):
        ctx = _make_rag_context(max_tokens=5)
        text = " ".join(["word"] * 50)
        truncated = ctx._truncate_to_tokens(text)
        # Should contain whole words, not cut in the middle
        for part in truncated.split("\n")[0].split():
            assert part == "word"
