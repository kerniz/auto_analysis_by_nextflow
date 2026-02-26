"""
Search Result Ranker and Deduplicator
검색 결과 랭킹 및 중복 제거

여러 소스에서 수집된 SearchResult를 정규화하고,
인용수/최신성/소스 중복도를 가중 결합하여 최종 순위를 매깁니다.
"""

import math
from datetime import datetime
from typing import Dict, List, Optional

from .topic_searcher import SearchResult


class ResultRanker:
    """
    검색 결과 랭킹기

    가중 점수 = 인용수(40%) + 검색순위(35%) + 최신성(15%) + 소스중복(10%)
    """

    CITATION_WEIGHT = 0.40
    RANK_WEIGHT = 0.35
    RECENCY_WEIGHT = 0.15
    BREADTH_WEIGHT = 0.10
    RECENCY_CUTOFF_YEARS = 3

    def rank(
        self,
        results: List[SearchResult],
        current_year: Optional[int] = None,
    ) -> List[SearchResult]:
        """
        검색 결과 중복 제거, 점수 계산, 정렬

        Args:
            results: 여러 소스에서 수집된 SearchResult 목록
            current_year: 현재 연도 (기본: datetime.now().year)

        Returns:
            relevance_score 내림차순 정렬된 SearchResult 목록
        """
        if not results:
            return []

        if current_year is None:
            current_year = datetime.now().year

        deduped = self._deduplicate(results)
        total = len(deduped)

        scored = []
        for rank_pos, result in enumerate(deduped):
            scored_result = self._score(
                result, total, rank_pos, current_year
            )
            scored.append(scored_result)

        return sorted(
            scored, key=lambda r: r.relevance_score, reverse=True
        )

    def _deduplicate(self, results: List[SearchResult]) -> List[SearchResult]:
        """
        PMID 기반 중복 제거, 소스 병합

        같은 PMID를 가진 결과는 하나로 합치고 sources를 병합합니다.
        PMID가 없는 결과(Brave 등)는 제목 기반으로 중복 검사합니다.
        """
        by_pmid: Dict[str, SearchResult] = {}
        by_title: Dict[str, SearchResult] = {}
        no_id: List[SearchResult] = []

        for result in results:
            if result.pmid:
                if result.pmid in by_pmid:
                    existing = by_pmid[result.pmid]
                    existing.sources = list(
                        set(existing.sources + result.sources)
                    )
                    # 더 나은 데이터로 보완
                    if not existing.abstract and result.abstract:
                        existing.abstract = result.abstract
                    if result.citation_count > existing.citation_count:
                        existing.citation_count = result.citation_count
                    if result.year and not existing.year:
                        existing.year = result.year
                    if result.doi and not existing.doi:
                        existing.doi = result.doi
                else:
                    by_pmid[result.pmid] = result
            else:
                # 제목 기반 중복 검사
                title_key = result.title.lower().strip()[:100]
                if title_key and title_key in by_title:
                    existing = by_title[title_key]
                    existing.sources = list(
                        set(existing.sources + result.sources)
                    )
                elif title_key:
                    by_title[title_key] = result
                else:
                    no_id.append(result)

        return list(by_pmid.values()) + list(by_title.values()) + no_id

    def _score(
        self,
        result: SearchResult,
        total: int,
        rank_position: int,
        current_year: int,
    ) -> SearchResult:
        """개별 결과 점수 계산"""
        # 인용수 점수 (log10 스케일, 0~1)
        citation_score = min(
            math.log10(result.citation_count + 1) / 5.0, 1.0
        )

        # 검색 순위 점수
        rank_score = 1.0 - (rank_position / max(total, 1))

        # 최신성 점수
        recency_score = 0.5  # 연도 정보 없으면 중간값
        if result.year:
            age = current_year - result.year
            if age <= 0:
                recency_score = 1.0
            elif age <= self.RECENCY_CUTOFF_YEARS:
                recency_score = 1.0 - (age / (self.RECENCY_CUTOFF_YEARS * 2))
            else:
                recency_score = max(
                    0.1, 0.5 - (age - self.RECENCY_CUTOFF_YEARS) * 0.05
                )

        # 소스 중복도 보너스
        breadth_score = min(len(result.sources) * 0.33, 1.0)

        # 가중 종합
        result.relevance_score = round(
            citation_score * self.CITATION_WEIGHT
            + rank_score * self.RANK_WEIGHT
            + recency_score * self.RECENCY_WEIGHT
            + breadth_score * self.BREADTH_WEIGHT,
            4,
        )

        return result
