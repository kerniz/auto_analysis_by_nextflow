"""
Tests for RAG Package
RAG 패키지 테스트
"""


import pytest

from rag.document_store import DocumentStore
from rag.rag_context import RAGContext


class TestDocumentStoreImport:
    """chromadb 없이도 임포트 가능한지 확인"""

    def test_import(self):
        from rag import DocumentStore, RAGContext
        assert DocumentStore is not None
        assert RAGContext is not None

    def test_init_no_error(self, tmp_path):
        store = DocumentStore(tmp_path / "test_db")
        assert store._client is None  # lazy init


@pytest.fixture
def doc_store(tmp_path):
    """ChromaDB가 설치된 경우에만 작동하는 fixture"""
    try:
        import importlib.util
        if importlib.util.find_spec("chromadb") is None:
            raise ImportError("chromadb not installed")
        store = DocumentStore(tmp_path / "test_rag_db")
        store._ensure_initialized()
        return store
    except ImportError:
        pytest.skip("chromadb not installed")


class TestDocumentStore:
    def test_add_paper(self, doc_store):
        doc_store.add_paper(
            pmid="12345",
            title="Test Paper Title",
            abstract="This is a test paper about bioinformatics.",
            year=2024,
        )
        stats = doc_store.get_stats()
        assert stats["count"] >= 1

    def test_add_analysis(self, doc_store):
        doc_store.add_analysis(
            pmid="12345",
            analysis_text="The analysis shows PASS rating with high confidence.",
            rating="PASS",
        )
        stats = doc_store.get_stats()
        assert stats["count"] >= 1

    def test_add_debate_report(self, doc_store):
        doc_store.add_debate_report(
            pmid="12345",
            report_text="The debate concluded with PASS verdict.",
            verdict="PASS",
            score=0.85,
        )
        stats = doc_store.get_stats()
        assert stats["count"] >= 1

    def test_query_basic(self, doc_store):
        doc_store.add_paper(
            pmid="99999",
            title="Spatial Transcriptomics in Cancer",
            abstract="This paper uses spatial transcriptomics to study cancer heterogeneity.",
        )
        results = doc_store.query("spatial transcriptomics", n_results=5)
        assert len(results) >= 1
        assert "document" in results[0]
        assert "metadata" in results[0]

    def test_query_by_doc_type(self, doc_store):
        doc_store.add_paper(
            pmid="11111", title="Paper", abstract="Paper abstract",
        )
        doc_store.add_analysis(
            pmid="11111", analysis_text="Analysis text", rating="PASS",
        )
        paper_results = doc_store.query(
            "paper", n_results=10, doc_type="paper_abstract"
        )
        analysis_results = doc_store.query(
            "analysis", n_results=10, doc_type="analysis_result"
        )
        # 각 타입 필터가 작동하는지 확인
        for r in paper_results:
            assert r["metadata"].get("doc_type") == "paper_abstract"
        for r in analysis_results:
            assert r["metadata"].get("doc_type") == "analysis_result"

    def test_upsert(self, doc_store):
        doc_store.add_paper(
            pmid="55555", title="Original", abstract="Original abstract",
        )
        doc_store.add_paper(
            pmid="55555", title="Updated", abstract="Updated abstract",
        )
        results = doc_store.query("Updated abstract", n_results=1)
        assert len(results) >= 1

    def test_get_stats(self, doc_store):
        stats = doc_store.get_stats()
        assert "count" in stats


class TestRAGContext:
    def test_build_context_empty(self, doc_store):
        ctx = RAGContext(doc_store)
        result = ctx.build_context("nonexistent topic xyz")
        assert isinstance(result, str)

    def test_build_context_with_data(self, doc_store):
        doc_store.add_paper(
            pmid="77777",
            title="scRNA-seq Study",
            abstract="Single-cell RNA sequencing reveals cell types.",
        )
        doc_store.add_analysis(
            pmid="77777",
            analysis_text="Analysis: high quality scRNA-seq data.",
            rating="PASS",
        )
        ctx = RAGContext(doc_store)
        result = ctx.build_context("scRNA-seq analysis")
        assert len(result) > 0

    def test_truncate(self, doc_store):
        ctx = RAGContext(doc_store, max_tokens=10)
        long_text = " ".join(["word"] * 100)
        truncated = ctx._truncate_to_tokens(long_text)
        assert len(truncated.split()) < 100
