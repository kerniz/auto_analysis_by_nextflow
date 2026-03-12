"""
ChromaDB-backed persistent vector document store.
ChromaDB 기반 영구 벡터 문서 저장소.

Stores and retrieves papers, analysis results, and debate reports
using sentence-transformer embeddings for semantic search.
문장 변환기 임베딩을 사용하여 논문, 분석 결과, 토론 보고서를
저장하고 검색합니다.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


class DocumentStore:
    """
    ChromaDB-backed persistent vector document store for bioauto.
    bioauto를 위한 ChromaDB 기반 영구 벡터 문서 저장소.

    Lazily initializes ChromaDB and sentence-transformers so the module
    can be imported without those dependencies installed.
    ChromaDB와 sentence-transformers를 지연 초기화하여 해당 의존성이
    설치되지 않은 환경에서도 모듈을 임포트할 수 있습니다.
    """

    COLLECTION_NAME = "bioauto_papers"
    EMBEDDING_MODEL = "all-MiniLM-L6-v2"

    def __init__(self, persist_dir: str | Path) -> None:
        """
        Initialize the document store.
        문서 저장소를 초기화합니다.

        Args:
            persist_dir: Directory path for ChromaDB persistent storage.
                         ChromaDB 영구 저장소 디렉토리 경로.
        """
        self.persist_dir = Path(persist_dir)
        self._client = None
        self._collection = None
        self._initialized = False

    def _ensure_initialized(self) -> None:
        """
        Lazily initialize ChromaDB client and collection.
        ChromaDB 클라이언트와 컬렉션을 지연 초기화합니다.

        Raises:
            ImportError: If chromadb or sentence-transformers is not installed.
                         chromadb 또는 sentence-transformers가 설치되지 않은 경우.
        """
        if self._initialized:
            return

        try:
            import chromadb
            from chromadb.utils.embedding_functions import (
                SentenceTransformerEmbeddingFunction,
            )
        except ImportError as e:
            raise ImportError(
                "chromadb and sentence-transformers are required for DocumentStore. "
                "Install them with: pip install chromadb sentence-transformers\n"
                "DocumentStore를 사용하려면 chromadb와 sentence-transformers가 필요합니다. "
                "다음 명령으로 설치하세요: pip install chromadb sentence-transformers"
            ) from e

        self.persist_dir.mkdir(parents=True, exist_ok=True)

        import io as _io
        import sys as _sys
        # HF Hub 인증 경고 + BertModel LOAD REPORT 숨기기 (stderr 직접 출력)
        _saved_stderr = _sys.stderr
        _sys.stderr = _io.StringIO()
        try:
            embedding_fn = SentenceTransformerEmbeddingFunction(
                model_name=self.EMBEDDING_MODEL
            )
        finally:
            _sys.stderr = _saved_stderr

        self._client = chromadb.PersistentClient(path=str(self.persist_dir))
        self._collection = self._client.get_or_create_collection(
            name=self.COLLECTION_NAME,
            embedding_function=embedding_fn,
            metadata={"description": "Bioauto papers, analyses, and debate reports"},
        )
        self._initialized = True
        logger.info(
            "DocumentStore initialized with collection '%s' at %s "
            "(DocumentStore가 '%s' 컬렉션으로 %s에서 초기화되었습니다)",
            self.COLLECTION_NAME,
            self.persist_dir,
            self.COLLECTION_NAME,
            self.persist_dir,
        )

    def add_paper(
        self,
        pmid: str,
        title: str,
        abstract: str,
        year: int | None = None,
        extra_meta: dict[str, Any] | None = None,
    ) -> None:
        """
        Add or update a paper abstract in the store.
        논문 초록을 저장소에 추가하거나 업데이트합니다.

        Args:
            pmid: PubMed ID of the paper. 논문의 PubMed ID.
            title: Paper title. 논문 제목.
            abstract: Paper abstract text. 논문 초록 텍스트.
            year: Publication year (optional). 출판 연도 (선택사항).
            extra_meta: Additional metadata dict (optional). 추가 메타데이터 (선택사항).
        """
        self._ensure_initialized()

        doc_id = f"abstract_{pmid}"
        document = f"{title}\n\n{abstract}"
        metadata: dict[str, Any] = {
            "doc_type": "paper_abstract",
            "pmid": str(pmid),
            "title": title,
        }
        if year is not None:
            metadata["year"] = int(year)
        if extra_meta:
            metadata.update(extra_meta)

        self._collection.upsert(
            ids=[doc_id],
            documents=[document],
            metadatas=[metadata],
        )
        logger.debug(
            "Upserted paper %s (논문 %s 업서트 완료)", doc_id, doc_id
        )

    def add_analysis(
        self,
        pmid: str,
        analysis_text: str,
        rating: str = "UNKNOWN",
        extra_meta: dict[str, Any] | None = None,
    ) -> None:
        """
        Add or update an analysis result in the store.
        분석 결과를 저장소에 추가하거나 업데이트합니다.

        Args:
            pmid: PubMed ID of the analyzed paper. 분석된 논문의 PubMed ID.
            analysis_text: Full analysis text. 전체 분석 텍스트.
            rating: Analysis rating (default: "UNKNOWN"). 분석 등급 (기본값: "UNKNOWN").
            extra_meta: Additional metadata dict (optional). 추가 메타데이터 (선택사항).
        """
        self._ensure_initialized()

        doc_id = f"analysis_{pmid}"
        metadata: dict[str, Any] = {
            "doc_type": "analysis_result",
            "pmid": str(pmid),
            "rating": rating,
        }
        if extra_meta:
            metadata.update(extra_meta)

        self._collection.upsert(
            ids=[doc_id],
            documents=[analysis_text],
            metadatas=[metadata],
        )
        logger.debug(
            "Upserted analysis %s (분석 %s 업서트 완료)", doc_id, doc_id
        )

    def add_debate_report(
        self,
        pmid: str,
        report_text: str,
        verdict: str = "UNDETERMINED",
        score: float = 0.0,
    ) -> None:
        """
        Add or update a debate report in the store.
        토론 보고서를 저장소에 추가하거나 업데이트합니다.

        Args:
            pmid: PubMed ID of the debated paper. 토론된 논문의 PubMed ID.
            report_text: Full debate report text. 전체 토론 보고서 텍스트.
            verdict: Debate verdict (default: "UNDETERMINED"). 토론 판정 (기본값: "UNDETERMINED").
            score: Debate score (default: 0.0). 토론 점수 (기본값: 0.0).
        """
        self._ensure_initialized()

        doc_id = f"debate_{pmid}"
        metadata: dict[str, Any] = {
            "doc_type": "debate_report",
            "pmid": str(pmid),
            "verdict": verdict,
            "score": float(score),
        }

        self._collection.upsert(
            ids=[doc_id],
            documents=[report_text],
            metadatas=[metadata],
        )
        logger.debug(
            "Upserted debate report %s (토론 보고서 %s 업서트 완료)", doc_id, doc_id
        )

    def add_search_record(
        self,
        query: str,
        results_summary: str,
        result_count: int = 0,
        selected_pmids: list[str] | None = None,
    ) -> None:
        """검색 기록을 저장합니다. 사용자의 관심사 프로파일에 활용."""
        self._ensure_initialized()
        import hashlib
        from datetime import datetime

        query_hash = hashlib.md5(query.encode()).hexdigest()[:8]
        doc_id = f"search_{query_hash}_{datetime.now().strftime('%Y%m%d')}"
        document = f"Search: {query}\n\n{results_summary}"
        metadata: dict[str, Any] = {
            "doc_type": "search_record",
            "query": query,
            "result_count": result_count,
            "timestamp": datetime.now().isoformat(),
        }
        if selected_pmids:
            metadata["selected_pmids"] = ",".join(selected_pmids)

        self._collection.upsert(ids=[doc_id], documents=[document], metadatas=[metadata])
        logger.debug("Upserted search record %s", doc_id)

    def add_consult_exchange(
        self,
        user_query: str,
        assistant_response: str,
        topic: str = "",
    ) -> None:
        """상담 대화를 저장합니다. 연구자 관심사 추적에 활용."""
        self._ensure_initialized()
        import hashlib
        from datetime import datetime

        content_hash = hashlib.md5(user_query.encode()).hexdigest()[:8]
        doc_id = f"consult_{content_hash}_{datetime.now().strftime('%Y%m%d%H%M')}"
        document = f"Q: {user_query}\n\nA: {assistant_response}"
        metadata: dict[str, Any] = {
            "doc_type": "consult_exchange",
            "user_query": user_query[:200],
            "timestamp": datetime.now().isoformat(),
        }
        if topic:
            metadata["topic"] = topic

        self._collection.upsert(ids=[doc_id], documents=[document], metadatas=[metadata])
        logger.debug("Upserted consult exchange %s", doc_id)

    def add_enrichment(
        self,
        pmid: str,
        enrichment_text: str,
        top_pathways: list[str] | None = None,
        novelty_score: float = 0.0,
    ) -> None:
        """Enrichment(GSEA/경로) 분석 결과를 저장합니다."""
        self._ensure_initialized()

        doc_id = f"enrichment_{pmid}"
        metadata: dict[str, Any] = {
            "doc_type": "enrichment_result",
            "pmid": str(pmid),
            "novelty_score": float(novelty_score),
        }
        if top_pathways:
            metadata["top_pathways"] = ",".join(top_pathways[:10])

        self._collection.upsert(ids=[doc_id], documents=[enrichment_text], metadatas=[metadata])
        logger.debug("Upserted enrichment %s", doc_id)

    def add_pipeline_run(
        self,
        pmid: str,
        pipeline_type: str,
        params_summary: str,
        success: bool = True,
    ) -> None:
        """파이프라인 실행 메타데이터를 저장합니다."""
        self._ensure_initialized()
        from datetime import datetime

        doc_id = f"pipeline_{pmid}_{datetime.now().strftime('%Y%m%d')}"
        document = (
            f"Pipeline: {pipeline_type}\nPMID: {pmid}\n"
            f"Status: {'SUCCESS' if success else 'FAILED'}\n\n{params_summary}"
        )
        metadata: dict[str, Any] = {
            "doc_type": "pipeline_run",
            "pmid": str(pmid),
            "pipeline_type": pipeline_type,
            "success": success,
            "timestamp": datetime.now().isoformat(),
        }

        self._collection.upsert(ids=[doc_id], documents=[document], metadatas=[metadata])
        logger.debug("Upserted pipeline run %s", doc_id)

    def get_user_interests(self, n_recent: int = 20) -> list[dict[str, Any]]:
        """축적된 검색/상담 기록에서 사용자 관심사 키워드를 추출합니다."""
        self._ensure_initialized()
        interests: list[dict[str, Any]] = []

        for doc_type in ("search_record", "consult_exchange"):
            try:
                results = self._collection.get(
                    where={"doc_type": doc_type},
                    limit=n_recent,
                )
                if results and results["metadatas"]:
                    for meta in results["metadatas"]:
                        entry: dict[str, Any] = {"type": doc_type}
                        if doc_type == "search_record":
                            entry["query"] = meta.get("query", "")
                        else:
                            entry["query"] = meta.get("user_query", "")
                        entry["timestamp"] = meta.get("timestamp", "")
                        interests.append(entry)
            except Exception:
                pass

        interests.sort(key=lambda x: x.get("timestamp", ""), reverse=True)
        return interests[:n_recent]

    def query(
        self,
        query_text: str,
        n_results: int = 5,
        doc_type: str | None = None,
    ) -> list[dict[str, Any]]:
        """
        Query the document store for similar documents.
        유사한 문서를 문서 저장소에서 검색합니다.

        Args:
            query_text: The search query text. 검색 쿼리 텍스트.
            n_results: Maximum number of results to return (default: 5).
                       반환할 최대 결과 수 (기본값: 5).
            doc_type: Filter by document type (optional).
                      문서 유형으로 필터링 (선택사항).
                      One of: "paper_abstract", "analysis_result", "debate_report".

        Returns:
            List of dicts with keys: id, document, metadata, distance.
            id, document, metadata, distance 키를 가진 딕셔너리 리스트.
        """
        self._ensure_initialized()

        where_filter = None
        if doc_type is not None:
            where_filter = {"doc_type": doc_type}

        results = self._collection.query(
            query_texts=[query_text],
            n_results=n_results,
            where=where_filter,
        )

        documents: list[dict[str, Any]] = []
        if results and results["ids"] and results["ids"][0]:
            for i, doc_id in enumerate(results["ids"][0]):
                documents.append(
                    {
                        "id": doc_id,
                        "document": results["documents"][0][i] if results["documents"] else "",
                        "metadata": results["metadatas"][0][i] if results["metadatas"] else {},
                        "distance": results["distances"][0][i] if results["distances"] else 0.0,
                    }
                )

        logger.debug(
            "Query returned %d results (쿼리가 %d개의 결과를 반환했습니다)",
            len(documents),
            len(documents),
        )
        return documents

    def delete_by_ids(self, ids: list[str]) -> int:
        """ID로 문서를 삭제합니다. 삭제된 수 반환."""
        self._ensure_initialized()
        if not ids:
            return 0
        self._collection.delete(ids=ids)
        logger.debug("Deleted %d documents", len(ids))
        return len(ids)

    def delete_by_doc_type(self, doc_type: str) -> int:
        """특정 doc_type의 모든 문서를 삭제합니다."""
        self._ensure_initialized()
        try:
            results = self._collection.get(where={"doc_type": doc_type})
            if results and results["ids"]:
                self._collection.delete(ids=results["ids"])
                count = len(results["ids"])
                logger.debug("Deleted %d documents of type %s", count, doc_type)
                return count
        except Exception as e:
            logger.debug("Delete by doc_type failed: %s", e)
        return 0

    def delete_by_pmid(self, pmid: str) -> int:
        """특정 PMID 관련 모든 문서를 삭제합니다."""
        self._ensure_initialized()
        try:
            results = self._collection.get(where={"pmid": str(pmid)})
            if results and results["ids"]:
                self._collection.delete(ids=results["ids"])
                count = len(results["ids"])
                logger.debug("Deleted %d documents for PMID %s", count, pmid)
                return count
        except Exception as e:
            logger.debug("Delete by PMID failed: %s", e)
        return 0

    def list_documents(
        self, doc_type: str | None = None, limit: int = 50,
    ) -> list[dict[str, Any]]:
        """저장된 문서 목록을 반환합니다."""
        self._ensure_initialized()
        try:
            kwargs: dict[str, Any] = {"limit": limit}
            if doc_type:
                kwargs["where"] = {"doc_type": doc_type}
            results = self._collection.get(**kwargs)
            docs = []
            if results and results["ids"]:
                for i, doc_id in enumerate(results["ids"]):
                    docs.append({
                        "id": doc_id,
                        "document": results["documents"][i][:200] if results["documents"] else "",
                        "metadata": results["metadatas"][i] if results["metadatas"] else {},
                    })
            return docs
        except Exception:
            return []

    def get_stats(self) -> dict[str, Any]:
        """
        Get statistics about the document store.
        문서 저장소의 통계 정보를 반환합니다.

        Returns:
            Dict with 'count' (total documents) and 'doc_types' (breakdown by type).
            'count' (총 문서 수)와 'doc_types' (유형별 분류) 키를 가진 딕셔너리.
        """
        self._ensure_initialized()

        total_count = self._collection.count()

        doc_types: dict[str, int] = {}
        for dtype in (
            "paper_abstract", "analysis_result", "debate_report",
            "search_record", "consult_exchange", "enrichment_result", "pipeline_run",
        ):
            try:
                type_results = self._collection.get(
                    where={"doc_type": dtype},
                )
                doc_types[dtype] = len(type_results["ids"]) if type_results["ids"] else 0
            except Exception:
                doc_types[dtype] = 0

        return {
            "count": total_count,
            "doc_types": doc_types,
        }
