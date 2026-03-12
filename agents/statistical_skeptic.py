"""
Statistical Skeptic Debate Agent
통계 회의론자 토론 에이전트

통계적 엄밀성, p-hacking 감지, 샘플 크기 평가, effect size 검토에 중점을 둡니다.
"""

import logging
from typing import Any

from backends.router import LLMRouter

from .base import AgentResponse, AgentRole, DebateAgent

logger = logging.getLogger(__name__)


class StatisticalSkepticAgent(DebateAgent):
    """
    통계 회의론자 에이전트 (Statistical Skeptic Agent)

    통계적 방법론, 검정력, 다중 비교 보정, effect size의 적절성을
    비판적으로 평가하는 에이전트입니다.
    """

    _SYSTEM_PROMPT = """당신은 생물통계학 전문가로서 연구의 통계적 엄밀성을 비판적으로 평가합니다.
You are a biostatistics expert critically evaluating the statistical rigor of research.

당신의 역할과 관점:
1. **p-hacking 및 다중 비교 문제 감지**:
   - 다중 비교 보정(FDR, Bonferroni)이 적절히 적용되었는지 확인하세요.
   - 선택적 보고(cherry-picking)의 징후가 있는지 검토하세요.
   - HARKing (Hypothesizing After Results are Known)의 가능성을 평가하세요.

2. **샘플 크기 및 검정력 평가**:
   - 샘플 크기가 통계적 검정력(power)을 확보하기에 충분한지 판단하세요.
   - 생물학적 반복(biological replicates)과 기술적 반복(technical replicates)을 구분하세요.
   - 효과 크기(effect size) 대비 샘플 크기의 적절성을 평가하세요.

3. **통계 방법 적절성 검토**:
   - 데이터 분포에 맞는 통계 검정이 사용되었는지 확인하세요.
   - 정규성 가정, 등분산 가정 등 전제 조건이 충족되는지 검토하세요.
   - DEG 분석(DESeq2, edgeR 등)의 모델 선택이 적절한지 평가하세요.

4. **Effect Size 및 실질적 유의성**:
   - 통계적 유의성과 실질적 유의성(practical significance)을 구분하세요.
   - fold change 임계값의 적절성을 평가하세요.
   - 신뢰구간(confidence interval)의 폭과 해석을 검토하세요.

5. **재현성 및 견고성**:
   - 교차 검증(cross-validation)이나 holdout 검증이 수행되었는지 확인하세요.
   - 결과의 견고성(robustness)을 다른 방법으로 확인했는지 검토하세요.
   - 민감도 분석(sensitivity analysis)의 필요성을 평가하세요.

반드시 지정된 JSON 형식으로 응답하세요.
Always respond in the specified JSON format."""

    def __init__(self, llm_router: LLMRouter):
        super().__init__(llm_router)

    @property
    def role(self) -> AgentRole:
        return AgentRole.STATISTICAL_SKEPTIC

    @property
    def name(self) -> str:
        return "통계 회의론자 (Statistical Skeptic)"

    @property
    def system_prompt(self) -> str:
        return self._SYSTEM_PROMPT

    async def assess(
        self,
        research_data: dict[str, Any],
        round_number: int = 1,
        previous_responses: list[AgentResponse] | None = None,
    ) -> AgentResponse:
        try:
            prompt = self._build_assessment_prompt(
                research_data, round_number, previous_responses
            )
            llm_response = await self.llm_router.generate(
                prompt=prompt,
                system_prompt=self.system_prompt,
            )
            if not llm_response.success:
                logger.error(
                    "통계 회의론자 LLM 호출 실패: %s", llm_response.error_message
                )
                return self._create_fallback_response(
                    round_number=round_number,
                    error_message=llm_response.error_message,
                )
            return self._parse_response(llm_response.content, round_number)
        except Exception as e:
            logger.exception("통계 회의론자 평가 중 예외 발생: %s", str(e))
            return self._create_fallback_response(
                round_number=round_number,
                error_message=str(e),
            )

    def _create_fallback_response(
        self, round_number: int, error_message: str
    ) -> AgentResponse:
        from datetime import datetime

        return AgentResponse(
            agent_role=self.role,
            agent_name=self.name,
            assessment=f"평가를 완료할 수 없습니다. 오류: {error_message}",
            score=0.5,
            confidence=0.0,
            key_points=[],
            concerns=[f"에이전트 오류 발생 (Agent error): {error_message}"],
            questions=[],
            rebuttal_to=None,
            round_number=round_number,
            timestamp=datetime.now(),
            raw_llm_response="",
        )
