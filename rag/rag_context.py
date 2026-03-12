"""
RAG Context Builder for bioauto platform.
bioauto 플랫폼을 위한 RAG 컨텍스트 빌더.

Builds formatted context strings from the vector document store
to augment LLM prompts with relevant prior knowledge.
벡터 문서 저장소에서 포맷된 컨텍스트 문자열을 생성하여
관련 사전 지식으로 LLM 프롬프트를 보강합니다.
"""

from __future__ import annotations

import logging
from typing import Any

from .document_store import DocumentStore

logger = logging.getLogger(__name__)


class RAGContext:
    """
    RAG Context Builder that queries the document store and assembles
    formatted context for LLM prompts.
    문서 저장소를 쿼리하고 LLM 프롬프트를 위한 포맷된 컨텍스트를
    조립하는 RAG 컨텍스트 빌더.
    """

    # Approximate ratio of tokens per word (used for truncation).
    # 단어당 토큰의 대략적 비율 (잘라내기에 사용).
    TOKENS_PER_WORD_RATIO = 0.75

    def __init__(self, store: DocumentStore, max_tokens: int = 1500) -> None:
        """
        Initialize the RAG context builder.
        RAG 컨텍스트 빌더를 초기화합니다.

        Args:
            store: DocumentStore instance to query from.
                   쿼리할 DocumentStore 인스턴스.
            max_tokens: Maximum approximate token count for the context (default: 1500).
                        컨텍스트의 최대 근사 토큰 수 (기본값: 1500).
        """
        self.store = store
        self.max_tokens = max_tokens

    def build_context(self, query: str, n_results: int = 3) -> str:
        """
        Build a formatted context string from relevant documents.
        관련 문서로부터 포맷된 컨텍스트 문자열을 생성합니다.

        Queries the store for all three document types (papers, analyses,
        debate reports) and assembles them into a structured context string
        suitable for LLM prompt augmentation.
        세 가지 문서 유형(논문, 분석, 토론 보고서) 모두에 대해 저장소를
        쿼리하고 LLM 프롬프트 보강에 적합한 구조화된 컨텍스트 문자열로
        조립합니다.

        Args:
            query: The search query to find relevant documents.
                   관련 문서를 찾기 위한 검색 쿼리.
            n_results: Number of results per document type (default: 3).
                       문서 유형당 결과 수 (기본값: 3).

        Returns:
            Formatted context string with sections for each document type.
            각 문서 유형에 대한 섹션이 포함된 포맷된 컨텍스트 문자열.
        """
        sections: list[str] = []

        # Query for related papers / 관련 논문 검색
        papers = self.store.query(
            query_text=query, n_results=n_results, doc_type="paper_abstract"
        )
        if papers:
            section = self._format_papers_section(papers)
            sections.append(section)

        # Query for prior analyses / 이전 분석 검색
        analyses = self.store.query(
            query_text=query, n_results=n_results, doc_type="analysis_result"
        )
        if analyses:
            section = self._format_analyses_section(analyses)
            sections.append(section)

        # Query for debate reports / 토론 보고서 검색
        debates = self.store.query(
            query_text=query, n_results=n_results, doc_type="debate_report"
        )
        if debates:
            section = self._format_debates_section(debates)
            sections.append(section)

        # Query for enrichment results / 농축 분석 결과 검색
        enrichments = self.store.query(
            query_text=query, n_results=n_results, doc_type="enrichment_result"
        )
        if enrichments:
            section = self._format_enrichment_section(enrichments)
            sections.append(section)

        # Query for past search interests / 과거 검색 관심사
        searches = self.store.query(
            query_text=query, n_results=n_results, doc_type="search_record"
        )
        if searches:
            section = self._format_search_section(searches)
            sections.append(section)

        if not sections:
            return ""

        full_context = "\n\n".join(sections)
        truncated = self._truncate_to_tokens(full_context)

        logger.debug(
            "Built RAG context: %d chars, ~%d tokens "
            "(RAG 컨텍스트 생성: %d자, 약 %d 토큰)",
            len(truncated),
            self._estimate_tokens(truncated),
            len(truncated),
            self._estimate_tokens(truncated),
        )

        return truncated

    def _format_papers_section(self, papers: list[dict[str, Any]]) -> str:
        """
        Format the Related Papers section.
        관련 논문 섹션을 포맷합니다.
        """
        lines = ["=== Related Papers (관련 논문) ==="]
        for doc in papers:
            meta = doc.get("metadata", {})
            title = meta.get("title", "Unknown")
            pmid = meta.get("pmid", "N/A")
            year = meta.get("year", "N/A")
            distance = doc.get("distance", 0.0)
            # Truncate document text for the bullet point
            text_preview = doc.get("document", "")[:200]
            if len(doc.get("document", "")) > 200:
                text_preview += "..."
            lines.append(
                f"  - [{pmid}] {title} ({year}) [distance: {distance:.3f}]\n"
                f"    {text_preview}"
            )
        return "\n".join(lines)

    def _format_analyses_section(self, analyses: list[dict[str, Any]]) -> str:
        """
        Format the Prior Analyses section.
        이전 분석 섹션을 포맷합니다.
        """
        lines = ["=== Prior Analyses (이전 분석) ==="]
        for doc in analyses:
            meta = doc.get("metadata", {})
            pmid = meta.get("pmid", "N/A")
            rating = meta.get("rating", "UNKNOWN")
            distance = doc.get("distance", 0.0)
            text_preview = doc.get("document", "")[:200]
            if len(doc.get("document", "")) > 200:
                text_preview += "..."
            lines.append(
                f"  - [Analysis {pmid}] Rating: {rating} [distance: {distance:.3f}]\n"
                f"    {text_preview}"
            )
        return "\n".join(lines)

    def _format_debates_section(self, debates: list[dict[str, Any]]) -> str:
        """
        Format the Debate Reports section.
        토론 보고서 섹션을 포맷합니다.
        """
        lines = ["=== Debate Reports (토론 보고서) ==="]
        for doc in debates:
            meta = doc.get("metadata", {})
            pmid = meta.get("pmid", "N/A")
            verdict = meta.get("verdict", "UNDETERMINED")
            score = meta.get("score", 0.0)
            distance = doc.get("distance", 0.0)
            text_preview = doc.get("document", "")[:200]
            if len(doc.get("document", "")) > 200:
                text_preview += "..."
            lines.append(
                f"  - [Debate {pmid}] Verdict: {verdict}, Score: {score} "
                f"[distance: {distance:.3f}]\n"
                f"    {text_preview}"
            )
        return "\n".join(lines)

    def _format_enrichment_section(self, enrichments: list[dict[str, Any]]) -> str:
        """Format the Enrichment Results section."""
        lines = ["=== Enrichment Results (농축 분석) ==="]
        for doc in enrichments:
            meta = doc.get("metadata", {})
            pmid = meta.get("pmid", "N/A")
            novelty = meta.get("novelty_score", 0.0)
            pathways = meta.get("top_pathways", "")
            lines.append(
                f"  - [Enrichment {pmid}] Novelty: {novelty:.2f}"
                + (f" Pathways: {pathways}" if pathways else "")
            )
        return "\n".join(lines)

    def _format_search_section(self, searches: list[dict[str, Any]]) -> str:
        """Format the Search History section."""
        lines = ["=== Research Interests (연구 관심사) ==="]
        for doc in searches:
            meta = doc.get("metadata", {})
            query = meta.get("query", "N/A")
            count = meta.get("result_count", 0)
            lines.append(f"  - Query: \"{query}\" ({count} results)")
        return "\n".join(lines)

    def _truncate_to_tokens(self, text: str) -> str:
        """
        Truncate text to approximate token limit using word count ratio.
        단어 수 비율을 사용하여 텍스트를 근사 토큰 제한으로 잘라냅니다.

        Uses the approximation: tokens ~ words * TOKENS_PER_WORD_RATIO.
        근사값 사용: 토큰 수 ~ 단어 수 * TOKENS_PER_WORD_RATIO.

        Args:
            text: The text to potentially truncate. 잘라낼 텍스트.

        Returns:
            Truncated text if it exceeds the token limit, otherwise the original.
            토큰 제한을 초과하면 잘라낸 텍스트, 그렇지 않으면 원본.
        """
        estimated_tokens = self._estimate_tokens(text)
        if estimated_tokens <= self.max_tokens:
            return text

        # Calculate max words allowed / 허용되는 최대 단어 수 계산
        max_words = int(self.max_tokens / self.TOKENS_PER_WORD_RATIO)
        words = text.split()
        if len(words) <= max_words:
            return text

        truncated = " ".join(words[:max_words])
        truncated += "\n... [truncated / 잘림]"
        return truncated

    def _estimate_tokens(self, text: str) -> int:
        """
        Estimate the number of tokens in text.
        텍스트의 토큰 수를 추정합니다.

        Args:
            text: Input text. 입력 텍스트.

        Returns:
            Estimated token count. 추정 토큰 수.
        """
        word_count = len(text.split())
        return int(word_count / self.TOKENS_PER_WORD_RATIO)
