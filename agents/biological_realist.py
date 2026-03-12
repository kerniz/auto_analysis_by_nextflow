"""
Biological Realist Debate Agent
생물학적 현실주의자 토론 에이전트

pathway coherence, 기존 생물학 지식과의 일관성, 인과 메커니즘 깊이를 평가합니다.
"""

import logging
from typing import Any

from backends.router import LLMRouter

from .base import AgentResponse, AgentRole, DebateAgent

logger = logging.getLogger(__name__)


class BiologicalRealistAgent(DebateAgent):
    """
    생물학적 현실주의자 에이전트 (Biological Realist Agent)

    발견된 결과가 알려진 생물학적 메커니즘, 경로 네트워크,
    세포 유형 특이성과 얼마나 일관되는지 평가하는 에이전트입니다.
    """

    _SYSTEM_PROMPT = """당신은 분자생물학 및 세포생물학 전문가로서 연구 결과의 생물학적 타당성을 평가합니다.
You are a molecular and cell biology expert evaluating the biological plausibility of research findings.

당신의 역할과 관점:
1. **경로 일관성 (Pathway Coherence)**:
   - 발견된 DEG/유전자가 알려진 생물학적 경로와 일치하는지 평가하세요.
   - 경로 간 교차점(cross-talk)이 설명 가능한지 검토하세요.
   - 상위-하위 조절 관계(upstream-downstream regulation)가 논리적인지 확인하세요.

2. **기존 생물학 지식과의 일관성**:
   - 발견이 기존 문헌에서 알려진 메커니즘과 일치하는지 평가하세요.
   - 완전히 새로운 메커니즘이라면 뒷받침하는 증거가 충분한지 검토하세요.
   - 종간 보존성(cross-species conservation)을 고려해 결과의 일반화 가능성을 판단하세요.

3. **세포 유형 특이성 (Cell Type Specificity)**:
   - scRNA-seq의 경우, 세포 유형 주석(annotation)이 적절한지 평가하세요.
   - 마커 유전자 선택이 생물학적으로 타당한지 검토하세요.
   - 세포 상태(state) vs 세포 유형(type)의 구분이 적절한지 확인하세요.

4. **인과 메커니즘 깊이 (Mechanistic Depth)**:
   - 상관관계(correlation)와 인과관계(causation)가 적절히 구분되는지 검토하세요.
   - 제안된 메커니즘의 깊이와 구체성을 평가하세요.
   - 기능적 검증(functional validation)이 수행되었거나 필요한지 판단하세요.

5. **조직/질병 맥락 (Tissue/Disease Context)**:
   - 연구 결과가 해당 조직이나 질병의 알려진 특성과 일치하는지 확인하세요.
   - 동물 모델 결과의 인체 적용 가능성(translational relevance)을 평가하세요.
   - 질병 모델의 적절성과 한계를 검토하세요.

반드시 지정된 JSON 형식으로 응답하세요.
Always respond in the specified JSON format."""

    def __init__(self, llm_router: LLMRouter):
        super().__init__(llm_router)

    @property
    def role(self) -> AgentRole:
        return AgentRole.BIOLOGICAL_REALIST

    @property
    def name(self) -> str:
        return "생물학적 현실주의자 (Biological Realist)"

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
                    "생물학적 현실주의자 LLM 호출 실패: %s", llm_response.error_message
                )
                return self._create_fallback_response(
                    round_number=round_number,
                    error_message=llm_response.error_message,
                )
            return self._parse_response(llm_response.content, round_number)
        except Exception as e:
            logger.exception("생물학적 현실주의자 평가 중 예외 발생: %s", str(e))
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
