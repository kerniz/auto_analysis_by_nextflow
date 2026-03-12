"""
Meta-Agent
메타 에이전트 — 종합 판정자

토론 참여자가 아닌 독립 종합 판정자로서,
7인 에이전트 토론 결과 + RES 6차원 점수를 바탕으로
Go/Revise/Drop 최종 판정을 내립니다.
"""

import json
import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from backends.router import LLMRouter
from core.json_utils import extract_json_from_llm

logger = logging.getLogger(__name__)


@dataclass
class MetaAgentVerdict:
    """메타 에이전트 종합 판정 결과"""
    verdict: str                    # "GO" / "REVISE" / "DROP"
    confidence: float               # 0.0-1.0
    narrative: str                  # 한국어 종합 서술
    key_recommendations: list[str]
    risk_factors: list[str]
    res_score: float                # 0-100 (RES 총점)
    debate_score: float             # 0.0-1.0 (토론 합의 점수)
    timestamp: datetime = field(default_factory=datetime.now)
    raw_llm_response: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "verdict": self.verdict,
            "confidence": round(self.confidence, 3),
            "narrative": self.narrative,
            "key_recommendations": self.key_recommendations,
            "risk_factors": self.risk_factors,
            "res_score": round(self.res_score, 2),
            "debate_score": round(self.debate_score, 3),
            "timestamp": self.timestamp.isoformat(),
        }


class MetaAgent:
    """
    메타 에이전트 — 독립 종합 판정자

    토론에 직접 참여하지 않고, 모든 에이전트의 최종 의견과
    RES 정량 점수를 종합하여 최종 Go/Revise/Drop 판정을 내림.
    """

    _SYSTEM_PROMPT = """당신은 연구 메타-평가자입니다. 7인의 전문 에이전트 토론 결과와
정량적 연구 평가 점수(RES, 100점 만점)를 종합하여 최종 판정을 내립니다.
You are a research meta-evaluator synthesizing 7-agent debate results and
quantitative Research Evaluation Score (RES, 0-100) into a final verdict.

판정 기준:
- **GO** (≥75점): 후속 연구 또는 재분석 가치가 충분함
- **REVISE** (45~74점): 특정 부분 보완 후 재평가 필요
- **DROP** (<45점): 현재 상태로는 후속 가치 부족

당신의 역할:
1. 7인 에이전트의 점수와 핵심 의견을 종합하세요.
2. RES 6차원 점수를 참고하여 약한 영역을 식별하세요.
3. 에이전트 간 의견 불일치가 있다면 그 원인을 분석하세요.
4. 구체적인 권고사항과 리스크 요인을 제시하세요.
5. 최종 판정은 점수와 토론을 모두 고려하되, 최종 결정은 당신의 독립적 판단입니다.

반드시 아래 JSON 형식으로 응답하세요.
/no_think"""

    def __init__(self, llm_router: LLMRouter):
        self.llm_router = llm_router

    async def synthesize(
        self,
        research_data: dict[str, Any],
        debate_result: dict[str, Any],
        res_result: dict[str, Any] | None = None,
    ) -> MetaAgentVerdict:
        """
        종합 판정 수행.

        Args:
            research_data: 원본 논문 정보
            debate_result: 토론 결과 (DebateResult.to_dict())
            res_result: RES 평가 결과 (ResearchEvaluationResult.to_dict())

        Returns:
            MetaAgentVerdict
        """
        try:
            prompt = self._build_synthesis_prompt(
                research_data, debate_result, res_result
            )
            llm_response = await self.llm_router.generate(
                prompt=prompt,
                system_prompt=self._SYSTEM_PROMPT,
            )

            if not llm_response.success:
                logger.error("메타 에이전트 LLM 호출 실패: %s", llm_response.error_message)
                return self._create_fallback_verdict(
                    debate_result, res_result, llm_response.error_message
                )

            return self._parse_verdict(
                llm_response.content, debate_result, res_result
            )
        except Exception as e:
            logger.exception("메타 에이전트 종합 판정 중 예외: %s", str(e))
            return self._create_fallback_verdict(debate_result, res_result, str(e))

    def _build_synthesis_prompt(
        self,
        research_data: dict[str, Any],
        debate_result: dict[str, Any],
        res_result: dict[str, Any] | None,
    ) -> str:
        parts = []
        parts.append("=== 메타 에이전트 종합 판정 요청 ===\n")

        # 논문 정보
        paper = research_data.get("paper_info", {})
        parts.append("## 논문 정보")
        parts.append(f"- PMID: {paper.get('pmid', 'N/A')}")
        parts.append(f"- 제목: {paper.get('title', 'N/A')}")
        parts.append(f"- 초록: {paper.get('abstract', 'N/A')[:500]}")
        parts.append("")

        # 토론 결과
        parts.append("## 토론 결과")
        parts.append(
            f"- 전체 점수: {debate_result.get('overall_score', 0):.3f}"
        )
        parts.append(f"- 판정: {debate_result.get('overall_verdict', 'N/A')}")

        # 에이전트별 점수
        per_agent = debate_result.get("per_agent_scores", {})
        if per_agent:
            parts.append("\n### 에이전트별 최종 점수")
            for agent_name, score in per_agent.items():
                parts.append(f"  - {agent_name}: {score:.3f}")
        parts.append("")

        # 소수 의견
        dissenting = debate_result.get("dissenting_opinions", [])
        if dissenting:
            parts.append("### 소수 의견")
            for d in dissenting[:3]:
                parts.append(f"  - {d}")
            parts.append("")

        # RES 점수
        if res_result:
            parts.append("## 연구 평가 점수 (RES)")
            parts.append(f"- 총점: {res_result.get('total_score', 0):.1f}/100")
            parts.append(f"- 판정: {res_result.get('verdict', 'N/A')}")
            dims = res_result.get("dimensions", [])
            if dims:
                parts.append("\n### 차원별 점수")
                for d in dims:
                    parts.append(
                        f"  - {d.get('label_ko', d.get('dimension'))}: "
                        f"{d.get('actual_points', 0):.1f}/{d.get('max_points', 0)}"
                    )
            parts.append("")

        # 응답 형식
        parts.append("## 응답 형식")
        parts.append("반드시 아래 JSON 형식으로 응답하세요:\n```json")
        parts.append(json.dumps({
            "verdict": "GO 또는 REVISE 또는 DROP",
            "confidence": 0.85,
            "narrative": "한국어 종합 서술 (2-3 문단)",
            "key_recommendations": [
                "핵심 권고 1", "핵심 권고 2",
            ],
            "risk_factors": [
                "리스크 1", "리스크 2",
            ],
        }, indent=2, ensure_ascii=False))
        parts.append("```")
        parts.append("\n/no_think")

        return "\n".join(parts)

    def _parse_verdict(
        self,
        llm_content: str,
        debate_result: dict[str, Any],
        res_result: dict[str, Any] | None,
    ) -> MetaAgentVerdict:
        parsed = extract_json_from_llm(llm_content)

        debate_score = debate_result.get("overall_score", 0.0)
        res_score = (res_result or {}).get("total_score", 0.0)

        if parsed and isinstance(parsed, dict):
            verdict = str(parsed.get("verdict", "REVISE")).upper()
            if verdict not in ("GO", "REVISE", "DROP"):
                verdict = "REVISE"

            raw_conf = parsed.get("confidence", 0.5)
            try:
                confidence = max(0.0, min(1.0, float(raw_conf)))
            except (TypeError, ValueError):
                confidence = 0.5

            return MetaAgentVerdict(
                verdict=verdict,
                confidence=confidence,
                narrative=str(parsed.get("narrative", "")),
                key_recommendations=self._ensure_str_list(
                    parsed.get("key_recommendations", [])
                ),
                risk_factors=self._ensure_str_list(
                    parsed.get("risk_factors", [])
                ),
                res_score=res_score,
                debate_score=debate_score,
                raw_llm_response=llm_content,
            )

        logger.warning("메타 에이전트 LLM 응답 파싱 실패, 기본값 사용")
        return self._create_fallback_verdict(debate_result, res_result, "파싱 실패")

    def _create_fallback_verdict(
        self,
        debate_result: dict[str, Any],
        res_result: dict[str, Any] | None,
        error_msg: str,
    ) -> MetaAgentVerdict:
        debate_score = debate_result.get("overall_score", 0.0)
        res_score = (res_result or {}).get("total_score", 0.0)

        # 점수 기반 자동 판정
        if res_score >= 75:
            verdict = "GO"
        elif res_score >= 45:
            verdict = "REVISE"
        else:
            verdict = "DROP" if res_score > 0 else "REVISE"

        return MetaAgentVerdict(
            verdict=verdict,
            confidence=0.3,
            narrative=f"메타 에이전트 평가를 완료할 수 없습니다. 오류: {error_msg}",
            key_recommendations=["메타 에이전트 재실행 권장"],
            risk_factors=[f"자동 판정 (LLM 실패): {error_msg}"],
            res_score=res_score,
            debate_score=debate_score,
            raw_llm_response="",
        )

    @staticmethod
    def _ensure_str_list(value: Any) -> list[str]:
        if isinstance(value, list):
            return [str(item) for item in value]
        if isinstance(value, str):
            return [value]
        return []
