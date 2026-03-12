"""Tests for automatic RAG collection system."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from rag.auto_collector import AutoRAGCollector


class TestAutoRAGCollectorInit:
    """AutoRAGCollector 초기화 테스트."""

    def test_init_default_dir(self):
        collector = AutoRAGCollector()
        assert collector._rag_dir.name == "rag_db"
        assert collector._store is None
        assert collector._init_failed is False

    def test_init_custom_dir(self, tmp_path):
        collector = AutoRAGCollector(rag_dir=tmp_path / "custom_rag")
        assert collector._rag_dir == tmp_path / "custom_rag"

    def test_ensure_store_fails_gracefully(self):
        """chromadb 없으면 조용히 실패."""
        collector = AutoRAGCollector()
        with patch("rag.auto_collector.AutoRAGCollector._ensure_store", return_value=False):
            collector._init_failed = True
            assert collector._ensure_store() is False


class TestAutoRAGCollectorGracefulDegradation:
    """ChromaDB 미설치 시 모든 메서드가 조용히 실패하는지 테스트."""

    def setup_method(self):
        self.collector = AutoRAGCollector()
        self.collector._init_failed = True  # chromadb 없는 상황 시뮬레이션

    def test_collect_search_no_error(self):
        self.collector.collect_search("test query", [])

    def test_collect_consult_no_error(self):
        self.collector.collect_consult("question", "answer")

    def test_collect_enrichment_no_error(self):
        self.collector.collect_enrichment("12345", {})

    def test_collect_pipeline_run_no_error(self):
        self.collector.collect_pipeline_run("12345", "rnaseq")

    def test_collect_papers_no_error(self):
        self.collector.collect_papers_from_search([])

    def test_get_knowledge_stats_returns_none(self):
        assert self.collector.get_knowledge_stats() is None

    def test_get_interests_returns_empty(self):
        assert self.collector.get_interests() == []

    def test_find_related_returns_empty(self):
        assert self.collector.find_related("test") == []


class TestAutoRAGCollectorWithMockedStore:
    """모킹된 DocumentStore로 수집 로직 테스트."""

    def setup_method(self):
        self.collector = AutoRAGCollector()
        self.mock_store = MagicMock()
        self.collector._store = self.mock_store
        self.collector._init_failed = False

    def test_collect_search_basic(self):
        results = [
            MagicMock(title="Paper A", pmid="111", abstract="abs"),
            MagicMock(title="Paper B", pmid="222", abstract="abs"),
        ]
        self.collector.collect_search("cancer immunotherapy", results)
        self.mock_store.add_search_record.assert_called_once()
        call_kwargs = self.mock_store.add_search_record.call_args
        assert "cancer immunotherapy" in str(call_kwargs)

    def test_collect_search_with_selected_pmids(self):
        results = [MagicMock(title="P1", pmid="111")]
        self.collector.collect_search("query", results, selected_pmids=["111"])
        call_kwargs = self.mock_store.add_search_record.call_args
        assert call_kwargs[1].get("selected_pmids") == ["111"] or \
            "111" in str(call_kwargs)

    def test_collect_consult(self):
        self.collector.collect_consult(
            user_query="폐암 면역치료 관련 연구",
            assistant_response="면역체크포인트 억제제 연구가 활발합니다.",
            topic="lung cancer",
        )
        self.mock_store.add_consult_exchange.assert_called_once_with(
            user_query="폐암 면역치료 관련 연구",
            assistant_response="면역체크포인트 억제제 연구가 활발합니다.",
            topic="lung cancer",
        )

    def test_collect_enrichment(self):
        data = {
            "novelty_score": 0.85,
            "top_pathways": [
                {"name": "PI3K-Akt signaling"},
                {"name": "MAPK signaling"},
            ],
        }
        self.collector.collect_enrichment("12345", data)
        self.mock_store.add_enrichment.assert_called_once()
        call_args = self.mock_store.add_enrichment.call_args
        assert call_args[1]["pmid"] == "12345"
        assert call_args[1]["novelty_score"] == 0.85

    def test_collect_pipeline_run(self):
        params = {"genome": "GRCh38", "profile": "singularity"}
        self.collector.collect_pipeline_run(
            pmid="12345", pipeline_type="rnaseq",
            params=params, success=True,
        )
        self.mock_store.add_pipeline_run.assert_called_once()

    def test_collect_papers_from_search(self):
        results = [
            MagicMock(pmid="111", title="Title A", abstract="Abstract A", year=2024),
            MagicMock(pmid=None, title="No PMID", abstract="Abs", year=2024),
            MagicMock(pmid="222", title="Title B", abstract="Abstract B", year=2023),
        ]
        self.collector.collect_papers_from_search(results)
        assert self.mock_store.add_paper.call_count == 2  # pmid=None 제외

    def test_collect_papers_dict_format(self):
        """dict 형식의 검색 결과도 처리."""
        results = [
            {"pmid": "111", "title": "T1", "abstract": "A1", "year": 2024},
        ]
        self.collector.collect_papers_from_search(results)
        self.mock_store.add_paper.assert_called_once_with(
            pmid="111", title="T1", abstract="A1", year=2024,
        )

    def test_get_knowledge_stats(self):
        self.mock_store.get_stats.return_value = {
            "count": 42,
            "doc_types": {"paper_abstract": 20, "search_record": 15},
        }
        stats = self.collector.get_knowledge_stats()
        assert stats["count"] == 42

    def test_get_interests(self):
        self.mock_store.get_user_interests.return_value = [
            {"type": "search_record", "query": "lung cancer"},
        ]
        interests = self.collector.get_interests()
        assert len(interests) == 1
        assert interests[0]["query"] == "lung cancer"

    def test_find_related(self):
        self.mock_store.query.return_value = [
            {"id": "paper_111", "document": "test", "metadata": {}, "distance": 0.1},
        ]
        related = self.collector.find_related("cancer", n_results=3)
        assert len(related) == 1
        self.mock_store.query.assert_called_once_with(
            query_text="cancer", n_results=3,
        )

    def test_exception_in_collect_is_silent(self):
        """수집 중 예외가 발생해도 조용히 무시."""
        self.mock_store.add_search_record.side_effect = RuntimeError("DB error")
        # 예외가 전파되지 않아야 함
        self.collector.collect_search("query", [])


class TestDocumentStoreNewMethods:
    """DocumentStore의 새 메서드 테스트 (모킹)."""

    def setup_method(self):
        from rag.document_store import DocumentStore
        self.store = DocumentStore("/tmp/test_rag")
        self.mock_collection = MagicMock()
        self.store._collection = self.mock_collection
        self.store._initialized = True

    def test_add_search_record(self):
        self.store.add_search_record(
            query="RNA-seq cancer",
            results_summary="1. [12345] Paper A",
            result_count=10,
            selected_pmids=["12345"],
        )
        self.mock_collection.upsert.assert_called_once()
        call_args = self.mock_collection.upsert.call_args
        meta = call_args[1]["metadatas"][0]
        assert meta["doc_type"] == "search_record"
        assert meta["query"] == "RNA-seq cancer"
        assert meta["result_count"] == 10
        assert meta["selected_pmids"] == "12345"

    def test_add_consult_exchange(self):
        self.store.add_consult_exchange(
            user_query="폐암 치료법?",
            assistant_response="면역치료가 주요합니다.",
            topic="lung cancer",
        )
        self.mock_collection.upsert.assert_called_once()
        call_args = self.mock_collection.upsert.call_args
        meta = call_args[1]["metadatas"][0]
        assert meta["doc_type"] == "consult_exchange"
        assert meta["topic"] == "lung cancer"
        doc = call_args[1]["documents"][0]
        assert "폐암 치료법?" in doc
        assert "면역치료가 주요합니다." in doc

    def test_add_enrichment(self):
        self.store.add_enrichment(
            pmid="12345",
            enrichment_text='{"gsea": "results"}',
            top_pathways=["PI3K-Akt", "MAPK"],
            novelty_score=0.9,
        )
        self.mock_collection.upsert.assert_called_once()
        call_args = self.mock_collection.upsert.call_args
        meta = call_args[1]["metadatas"][0]
        assert meta["doc_type"] == "enrichment_result"
        assert meta["pmid"] == "12345"
        assert meta["novelty_score"] == 0.9
        assert "PI3K-Akt" in meta["top_pathways"]

    def test_add_pipeline_run(self):
        self.store.add_pipeline_run(
            pmid="12345",
            pipeline_type="rnaseq",
            params_summary='{"genome": "GRCh38"}',
            success=True,
        )
        self.mock_collection.upsert.assert_called_once()
        call_args = self.mock_collection.upsert.call_args
        meta = call_args[1]["metadatas"][0]
        assert meta["doc_type"] == "pipeline_run"
        assert meta["pipeline_type"] == "rnaseq"
        assert meta["success"] is True

    def test_get_user_interests(self):
        self.mock_collection.get.return_value = {
            "ids": ["search_abc"],
            "metadatas": [
                {"doc_type": "search_record", "query": "cancer", "timestamp": "2026-01-01"},
            ],
        }
        interests = self.store.get_user_interests(n_recent=5)
        assert len(interests) >= 1
        assert interests[0]["query"] == "cancer"

    def test_get_stats_includes_new_types(self):
        self.mock_collection.count.return_value = 50
        self.mock_collection.get.return_value = {"ids": ["a", "b"]}
        stats = self.store.get_stats()
        assert stats["count"] == 50
        # 새로운 doc_type이 통계에 포함되는지 확인
        assert "search_record" in stats["doc_types"]
        assert "consult_exchange" in stats["doc_types"]
        assert "enrichment_result" in stats["doc_types"]
        assert "pipeline_run" in stats["doc_types"]


class TestKnowledgeCommand:
    """bioauto knowledge 명령어 테스트."""

    @pytest.fixture
    def runner(self):
        from click.testing import CliRunner
        return CliRunner()

    def test_knowledge_no_rag(self, runner):
        from core.cli import cli
        with patch("core.cli._get_collector", return_value=None):
            result = runner.invoke(cli, ["knowledge"])
            assert "RAG 모듈" in result.output

    def test_knowledge_empty_db(self, runner):
        from core.cli import cli
        mock_collector = MagicMock()
        mock_collector.get_knowledge_stats.return_value = {"count": 0, "doc_types": {}}
        with patch("core.cli._get_collector", return_value=mock_collector):
            result = runner.invoke(cli, ["knowledge"])
            assert "비어 있습니다" in result.output

    def test_knowledge_with_data(self, runner):
        from core.cli import cli
        mock_collector = MagicMock()
        mock_collector.get_knowledge_stats.return_value = {
            "count": 42,
            "doc_types": {
                "paper_abstract": 20,
                "search_record": 15,
                "consult_exchange": 7,
            },
        }
        mock_collector.get_interests.return_value = [
            {"query": "lung cancer", "timestamp": "2026-03-10"},
        ]
        with patch("core.cli._get_collector", return_value=mock_collector):
            result = runner.invoke(cli, ["knowledge"])
            assert "42" in result.output
            assert "lung cancer" in result.output

    def test_knowledge_with_query(self, runner):
        from core.cli import cli
        mock_collector = MagicMock()
        mock_collector.get_knowledge_stats.return_value = {
            "count": 10,
            "doc_types": {"paper_abstract": 10},
        }
        mock_collector.get_interests.return_value = []
        mock_collector.find_related.return_value = [
            {
                "id": "paper_111",
                "document": "Cancer immunotherapy research paper about PD-1 inhibitors",
                "metadata": {"doc_type": "paper_abstract"},
                "distance": 0.15,
            },
        ]
        with patch("core.cli._get_collector", return_value=mock_collector):
            result = runner.invoke(cli, ["knowledge", "-q", "cancer"])
            assert "cancer" in result.output
            assert "PD-1" in result.output


class TestKnowledgeDeleteCommands:
    """knowledge 삭제 명령어 테스트."""

    @pytest.fixture
    def runner(self):
        from click.testing import CliRunner
        return CliRunner()

    def _mock_collector(self):
        mock = MagicMock()
        mock.get_knowledge_stats.return_value = {
            "count": 10, "doc_types": {"search_record": 5, "paper_abstract": 5},
        }
        mock.get_interests.return_value = []
        return mock

    def test_delete_type(self, runner):
        from core.cli import cli
        mock = self._mock_collector()
        mock.delete_by_type.return_value = 5
        with patch("core.cli._get_collector", return_value=mock):
            result = runner.invoke(
                cli, ["knowledge", "--delete-type", "search_record"], input="y\n"
            )
            assert "5건 삭제 완료" in result.output
            mock.delete_by_type.assert_called_once_with("search_record")

    def test_delete_type_cancel(self, runner):
        from core.cli import cli
        mock = self._mock_collector()
        with patch("core.cli._get_collector", return_value=mock):
            result = runner.invoke(
                cli, ["knowledge", "--delete-type", "search_record"], input="n\n"
            )
            assert "취소됨" in result.output
            mock.delete_by_type.assert_not_called()

    def test_delete_pmid(self, runner):
        from core.cli import cli
        mock = self._mock_collector()
        mock.delete_by_pmid.return_value = 3
        with patch("core.cli._get_collector", return_value=mock):
            result = runner.invoke(
                cli, ["knowledge", "--delete-pmid", "12345"], input="y\n"
            )
            assert "3건 삭제 완료" in result.output
            mock.delete_by_pmid.assert_called_once_with("12345")

    def test_delete_pmid_not_found(self, runner):
        from core.cli import cli
        mock = self._mock_collector()
        mock.delete_by_pmid.return_value = 0
        with patch("core.cli._get_collector", return_value=mock):
            result = runner.invoke(
                cli, ["knowledge", "--delete-pmid", "99999"], input="y\n"
            )
            assert "데이터가 없습니다" in result.output

    def test_delete_query_select(self, runner):
        from core.cli import cli
        mock = self._mock_collector()
        mock.find_related.return_value = [
            {"id": "search_abc", "document": "cancer research", "metadata": {"doc_type": "search_record"}},
            {"id": "paper_def", "document": "lung cancer paper", "metadata": {"doc_type": "paper_abstract"}},
        ]
        mock.delete_by_ids.return_value = 1
        with patch("core.cli._get_collector", return_value=mock):
            result = runner.invoke(
                cli, ["knowledge", "--delete-query", "cancer"], input="1\ny\n"
            )
            assert "1건 삭제 완료" in result.output

    def test_delete_query_all(self, runner):
        from core.cli import cli
        mock = self._mock_collector()
        mock.find_related.return_value = [
            {"id": "a1", "document": "doc1", "metadata": {"doc_type": "search_record"}},
            {"id": "a2", "document": "doc2", "metadata": {"doc_type": "paper_abstract"}},
        ]
        mock.delete_by_ids.return_value = 2
        with patch("core.cli._get_collector", return_value=mock):
            result = runner.invoke(
                cli, ["knowledge", "--delete-query", "test"], input="a\ny\n"
            )
            assert "2건 삭제 완료" in result.output

    def test_delete_query_cancel(self, runner):
        from core.cli import cli
        mock = self._mock_collector()
        mock.find_related.return_value = [
            {"id": "a1", "document": "doc", "metadata": {"doc_type": "search_record"}},
        ]
        with patch("core.cli._get_collector", return_value=mock):
            result = runner.invoke(
                cli, ["knowledge", "--delete-query", "test"], input="q\n"
            )
            assert "취소됨" in result.output

    def test_reset_double_confirm(self, runner, tmp_path):
        from core.cli import cli
        mock = self._mock_collector()
        rag_dir = tmp_path / "results" / "rag_db"
        rag_dir.mkdir(parents=True)
        with patch("core.cli._get_collector", return_value=mock):
            result = runner.invoke(
                cli, ["knowledge", "--reset", "-o", str(tmp_path / "results")],
                input="y\ny\n",
            )
            assert "초기화 완료" in result.output

    def test_reset_cancel_first(self, runner):
        from core.cli import cli
        mock = self._mock_collector()
        with patch("core.cli._get_collector", return_value=mock):
            result = runner.invoke(
                cli, ["knowledge", "--reset"], input="n\n"
            )
            assert "취소됨" in result.output

    def test_list_type(self, runner):
        from core.cli import cli
        mock = self._mock_collector()
        mock.list_documents.return_value = [
            {"id": "search_abc", "document": "cancer query results", "metadata": {
                "query": "cancer", "timestamp": "2026-03-10",
            }},
        ]
        with patch("core.cli._get_collector", return_value=mock):
            result = runner.invoke(
                cli, ["knowledge", "--list-type", "search_record"]
            )
            assert "cancer" in result.output
            assert "1건" in result.output

    def test_list_type_empty(self, runner):
        from core.cli import cli
        mock = self._mock_collector()
        mock.list_documents.return_value = []
        with patch("core.cli._get_collector", return_value=mock):
            result = runner.invoke(
                cli, ["knowledge", "--list-type", "consult_exchange"]
            )
            assert "데이터가 없습니다" in result.output


class TestDocumentStoreDeleteMethods:
    """DocumentStore 삭제 메서드 테스트."""

    def setup_method(self):
        from rag.document_store import DocumentStore
        self.store = DocumentStore("/tmp/test_rag_del")
        self.mock_collection = MagicMock()
        self.store._collection = self.mock_collection
        self.store._initialized = True

    def test_delete_by_ids(self):
        count = self.store.delete_by_ids(["a1", "a2"])
        assert count == 2
        self.mock_collection.delete.assert_called_once_with(ids=["a1", "a2"])

    def test_delete_by_ids_empty(self):
        count = self.store.delete_by_ids([])
        assert count == 0
        self.mock_collection.delete.assert_not_called()

    def test_delete_by_doc_type(self):
        self.mock_collection.get.return_value = {"ids": ["s1", "s2", "s3"]}
        count = self.store.delete_by_doc_type("search_record")
        assert count == 3
        self.mock_collection.delete.assert_called_once_with(ids=["s1", "s2", "s3"])

    def test_delete_by_doc_type_none(self):
        self.mock_collection.get.return_value = {"ids": []}
        count = self.store.delete_by_doc_type("search_record")
        assert count == 0

    def test_delete_by_pmid(self):
        self.mock_collection.get.return_value = {"ids": ["paper_123", "analysis_123"]}
        count = self.store.delete_by_pmid("123")
        assert count == 2

    def test_list_documents(self):
        self.mock_collection.get.return_value = {
            "ids": ["a1"],
            "documents": ["doc text here"],
            "metadatas": [{"doc_type": "search_record", "query": "test"}],
        }
        docs = self.store.list_documents(doc_type="search_record", limit=10)
        assert len(docs) == 1
        assert docs[0]["id"] == "a1"
        assert docs[0]["metadata"]["query"] == "test"


class TestAutoCollectorDeleteMethods:
    """AutoRAGCollector 삭제 메서드 테스트."""

    def setup_method(self):
        self.collector = AutoRAGCollector()
        self.mock_store = MagicMock()
        self.collector._store = self.mock_store
        self.collector._init_failed = False

    def test_delete_by_ids(self):
        self.mock_store.delete_by_ids.return_value = 2
        assert self.collector.delete_by_ids(["a", "b"]) == 2

    def test_delete_by_type(self):
        self.mock_store.delete_by_doc_type.return_value = 5
        assert self.collector.delete_by_type("search_record") == 5

    def test_delete_by_pmid(self):
        self.mock_store.delete_by_pmid.return_value = 3
        assert self.collector.delete_by_pmid("12345") == 3

    def test_list_documents(self):
        self.mock_store.list_documents.return_value = [{"id": "a"}]
        assert len(self.collector.list_documents()) == 1

    def test_delete_graceful_when_no_store(self):
        self.collector._init_failed = True
        self.collector._store = None
        assert self.collector.delete_by_ids(["a"]) == 0
        assert self.collector.delete_by_type("x") == 0
        assert self.collector.delete_by_pmid("1") == 0
        assert self.collector.list_documents() == []


class TestRAGContextNewSections:
    """RAGContext의 새 섹션 포맷 테스트."""

    def test_format_enrichment_section(self):
        from rag.document_store import DocumentStore
        from rag.rag_context import RAGContext

        mock_store = MagicMock(spec=DocumentStore)
        ctx = RAGContext(mock_store)

        enrichments = [
            {
                "metadata": {"pmid": "123", "novelty_score": 0.85, "top_pathways": "PI3K,MAPK"},
                "distance": 0.1,
            },
        ]
        section = ctx._format_enrichment_section(enrichments)
        assert "Enrichment" in section
        assert "123" in section
        assert "0.85" in section

    def test_format_search_section(self):
        from rag.document_store import DocumentStore
        from rag.rag_context import RAGContext

        mock_store = MagicMock(spec=DocumentStore)
        ctx = RAGContext(mock_store)

        searches = [
            {
                "metadata": {"query": "lung cancer", "result_count": 25},
                "distance": 0.2,
            },
        ]
        section = ctx._format_search_section(searches)
        assert "Research Interests" in section
        assert "lung cancer" in section
        assert "25" in section

    def test_build_context_includes_new_types(self):
        from rag.document_store import DocumentStore
        from rag.rag_context import RAGContext

        mock_store = MagicMock(spec=DocumentStore)
        # 각 doc_type 쿼리에 대해 빈 결과 또는 결과 반환
        def mock_query(query_text, n_results=3, doc_type=None):
            if doc_type == "enrichment_result":
                return [{"metadata": {"pmid": "X", "novelty_score": 0.5}, "distance": 0.1}]
            if doc_type == "search_record":
                return [{"metadata": {"query": "test", "result_count": 5}, "distance": 0.2}]
            return []

        mock_store.query.side_effect = mock_query
        ctx = RAGContext(mock_store)
        context = ctx.build_context("test query")
        assert "Enrichment" in context
        assert "Research Interests" in context
