"""
Automatic RAG Collector — 사용자 모르게 지식 DB를 축적하는 레이어.

연구자가 search, consult, run 등을 사용할 때마다
자동으로 ChromaDB에 기록을 축적합니다.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


class AutoRAGCollector:
    """
    자동 RAG 수집기.

    CLI 각 명령의 핵심 지점에서 호출되어 사용자 활동을 자동 인덱싱합니다.
    ChromaDB 미설치 시 조용히 무시합니다 (graceful degradation).
    """

    def __init__(self, rag_dir: str | Path | None = None) -> None:
        self._store = None
        self._rag_dir = Path(rag_dir) if rag_dir else Path("./results/rag_db")
        self._init_failed = False

    def _ensure_store(self) -> bool:
        """DocumentStore 초기화 시도. 실패하면 False 반환."""
        if self._init_failed:
            return False
        if self._store is not None:
            return True
        try:
            from rag.document_store import DocumentStore
            self._store = DocumentStore(self._rag_dir)
            self._store._ensure_initialized()
            return True
        except (ImportError, Exception) as e:
            logger.debug("AutoRAGCollector 비활성: %s", e)
            self._init_failed = True
            return False

    # ── 검색 기록 ──

    def collect_search(
        self,
        query: str,
        results: list[Any],
        selected_pmids: list[str] | None = None,
    ) -> None:
        """검색 쿼리와 결과 요약을 자동 저장."""
        if not self._ensure_store():
            return
        try:
            summaries = []
            for i, r in enumerate(results[:10], 1):
                title = getattr(r, "title", str(r)) if not isinstance(r, dict) else r.get("title", "")
                pmid = getattr(r, "pmid", None) if not isinstance(r, dict) else r.get("pmid")
                summaries.append(f"{i}. [{pmid or 'N/A'}] {title}")
            summary_text = "\n".join(summaries)

            self._store.add_search_record(
                query=query,
                results_summary=summary_text,
                result_count=len(results),
                selected_pmids=selected_pmids,
            )
            logger.debug("Auto-collected search: %s (%d results)", query, len(results))
        except Exception as e:
            logger.debug("Search collection failed: %s", e)

    # ── 상담 대화 ──

    def collect_consult(
        self,
        user_query: str,
        assistant_response: str,
        topic: str = "",
    ) -> None:
        """상담 모드 Q&A를 자동 저장."""
        if not self._ensure_store():
            return
        try:
            self._store.add_consult_exchange(
                user_query=user_query,
                assistant_response=assistant_response,
                topic=topic,
            )
            logger.debug("Auto-collected consult exchange")
        except Exception as e:
            logger.debug("Consult collection failed: %s", e)

    # ── Enrichment 결과 ──

    def collect_enrichment(
        self,
        pmid: str,
        enrichment_data: dict[str, Any],
    ) -> None:
        """Enrichment(GSEA/경로) 분석 결과를 자동 저장."""
        if not self._ensure_store():
            return
        try:
            text = json.dumps(enrichment_data, ensure_ascii=False, default=str)
            top_pathways = []
            if "top_pathways" in enrichment_data:
                top_pathways = [
                    p.get("name", str(p)) if isinstance(p, dict) else str(p)
                    for p in enrichment_data["top_pathways"][:10]
                ]
            novelty = enrichment_data.get("novelty_score", 0.0)

            self._store.add_enrichment(
                pmid=pmid,
                enrichment_text=text,
                top_pathways=top_pathways,
                novelty_score=float(novelty) if novelty else 0.0,
            )
            logger.debug("Auto-collected enrichment for %s", pmid)
        except Exception as e:
            logger.debug("Enrichment collection failed: %s", e)

    # ── 파이프라인 실행 기록 ──

    def collect_pipeline_run(
        self,
        pmid: str,
        pipeline_type: str,
        params: dict[str, Any] | None = None,
        success: bool = True,
    ) -> None:
        """파이프라인 실행 설정과 결과를 자동 저장."""
        if not self._ensure_store():
            return
        try:
            params_text = json.dumps(params or {}, ensure_ascii=False, default=str)
            self._store.add_pipeline_run(
                pmid=pmid,
                pipeline_type=pipeline_type,
                params_summary=params_text,
                success=success,
            )
            logger.debug("Auto-collected pipeline run for %s", pmid)
        except Exception as e:
            logger.debug("Pipeline run collection failed: %s", e)

    # ── 논문 자동 인덱싱 (search 결과에서) ──

    def collect_papers_from_search(self, results: list[Any]) -> None:
        """검색 결과의 논문들을 자동으로 벡터 DB에 인덱싱."""
        if not self._ensure_store():
            return
        try:
            indexed = 0
            for r in results:
                pmid = getattr(r, "pmid", None) if not isinstance(r, dict) else r.get("pmid")
                title = getattr(r, "title", "") if not isinstance(r, dict) else r.get("title", "")
                abstract = getattr(r, "abstract", "") if not isinstance(r, dict) else r.get("abstract", "")
                year = getattr(r, "year", None) if not isinstance(r, dict) else r.get("year")

                if pmid and title and abstract:
                    self._store.add_paper(pmid=pmid, title=title, abstract=abstract, year=year)
                    indexed += 1
            logger.debug("Auto-indexed %d papers from search results", indexed)
        except Exception as e:
            logger.debug("Paper indexing from search failed: %s", e)

    # ── 통계 ──

    def get_knowledge_stats(self) -> dict[str, Any] | None:
        """축적된 지식 DB 통계를 반환."""
        if not self._ensure_store():
            return None
        try:
            return self._store.get_stats()
        except Exception:
            return None

    # ── 관심사 조회 ──

    def get_interests(self) -> list[dict[str, Any]]:
        """사용자 관심사 키워드 반환."""
        if not self._ensure_store():
            return []
        try:
            return self._store.get_user_interests()
        except Exception:
            return []

    # ── 관련 과거 연구 조회 ──

    def find_related(self, query: str, n_results: int = 3) -> list[dict[str, Any]]:
        """쿼리와 관련된 과거 분석/검색을 찾습니다."""
        if not self._ensure_store():
            return []
        try:
            return self._store.query(query_text=query, n_results=n_results)
        except Exception:
            return []

    # ── 삭제 ──

    def delete_by_ids(self, ids: list[str]) -> int:
        """ID로 문서를 삭제합니다."""
        if not self._ensure_store():
            return 0
        try:
            return self._store.delete_by_ids(ids)
        except Exception:
            return 0

    def delete_by_type(self, doc_type: str) -> int:
        """특정 유형의 모든 문서를 삭제합니다."""
        if not self._ensure_store():
            return 0
        try:
            return self._store.delete_by_doc_type(doc_type)
        except Exception:
            return 0

    def delete_by_pmid(self, pmid: str) -> int:
        """특정 PMID 관련 모든 문서를 삭제합니다."""
        if not self._ensure_store():
            return 0
        try:
            return self._store.delete_by_pmid(pmid)
        except Exception:
            return 0

    def list_documents(
        self, doc_type: str | None = None, limit: int = 50,
    ) -> list[dict[str, Any]]:
        """저장된 문서 목록을 반환합니다."""
        if not self._ensure_store():
            return []
        try:
            return self._store.list_documents(doc_type=doc_type, limit=limit)
        except Exception:
            return []
