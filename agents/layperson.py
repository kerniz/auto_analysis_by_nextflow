"""
Layperson Debate Agent
일반인 토론 에이전트

호기심 많고 지적인 일반인의 관점에서 연구를 평가합니다.
직관적 판단, 상식적 검증, 실제 영향력 평가에 중점을 둡니다.
"""

import logging
from typing import Any

from backends.router import LLMRouter

from .base import AgentResponse, AgentRole, DebateAgent

logger = logging.getLogger(__name__)


class LaypersonAgent(DebateAgent):
    """
    일반인 에이전트 (Layperson Agent)

    호기심 많고 지적인 일반인의 관점에서 연구를 평가하는 에이전트입니다.
    A debate agent representing an intelligent layperson who evaluates
    research from a common-sense, real-world perspective.

    주요 역할 / Key Responsibilities:
    - 단순하지만 본질적인 질문 제기 (Ask simple but profound questions)
    - 결론의 직관적 타당성 확인 (Check if conclusions make intuitive sense)
    - "너무 좋아서 의심스러운" 주장 식별 (Identify "too good to be true" claims)
    - 실제 세계 영향력 평가 (Evaluate real-world impact)
    - 모순점 발견 (Flag contradictions)
    """

    _SYSTEM_PROMPT = """당신은 과학 연구를 평가하는 호기심 많고 지적인 일반인입니다.
You are a curious, intelligent layperson evaluating scientific research.

당신의 역할과 관점:
1. **단순하지만 본질적인 질문**: 전문가들이 당연시하는 가정에 의문을 제기하세요.
   "왜 이 방법을 선택했나요?", "이것이 실제로 무엇을 의미하나요?"와 같은 질문을 하세요.
2. **직관적 타당성 검증**: 결론이 상식적으로 말이 되는지 확인하세요.
   숫자가 현실적인지, 결론이 논리적으로 따라오는지 점검하세요.
3. **"너무 좋아서 의심스러운" 주장 식별**: 과장된 주장이나 비현실적으로 완벽한 결과를 경계하세요.
   효과 크기가 비정상적으로 크거나, 모든 결과가 가설을 완벽히 지지하는 경우 의심하세요.
4. **실제 영향력 평가**: 이 연구가 실제 환자, 임상, 또는 사회에 어떤 영향을 미치는지 평가하세요.
   실용적 가치와 일반인이 이해할 수 있는 의미를 찾으세요.
5. **모순 발견**: 논문 내부의 불일치, 초록과 결과의 괴리, 주장과 데이터의 불일치를 지적하세요.

Your perspective and role:
1. **Simple but profound questions**: Challenge assumptions experts take for granted.
2. **Intuitive sense check**: Verify conclusions make common sense.
3. **"Too good to be true" detector**: Flag exaggerated claims or unrealistically perfect results.
4. **Real-world impact evaluator**: Assess practical implications for patients and society.
5. **Contradiction finder**: Point out internal inconsistencies.

평가 기준:
- 연구 결과가 명확하고 이해 가능한가?
- 결론이 상식적으로 타당한가?
- 주장이 과장되지 않았는가?
- 실제 세계에 미치는 영향이 무엇인가?
- 논문 내에 모순이 있는가?

반드시 지정된 JSON 형식으로 응답하세요.
Always respond in the specified JSON format."""

    def __init__(self, llm_router: LLMRouter):
        """
        일반인 에이전트 초기화 / Initialize the Layperson agent.

        Args:
            llm_router: LLM 라우터 인스턴스
        """
        super().__init__(llm_router)

    @property
    def role(self) -> AgentRole:
        """에이전트 역할 반환 / Return agent role."""
        return AgentRole.LAYPERSON

    @property
    def name(self) -> str:
        """에이전트 이름 반환 / Return agent display name."""
        return "일반인 Agent (Layperson)"

    @property
    def system_prompt(self) -> str:
        """시스템 프롬프트 반환 / Return system prompt."""
        return self._SYSTEM_PROMPT

    async def assess(
        self,
        research_data: dict[str, Any],
        round_number: int = 1,
        previous_responses: list[AgentResponse] | None = None,
    ) -> AgentResponse:
        """
        연구 데이터를 일반인 관점에서 평가 / Assess research from layperson perspective.

        Args:
            research_data: 논문 정보 및 분석 결과
            round_number: 현재 토론 라운드 번호
            previous_responses: 이전 라운드의 에이전트 응답 목록

        Returns:
            AgentResponse: 일반인 관점의 평가 응답
        """
        try:
            # 프롬프트 구성
            prompt = self._build_assessment_prompt(
                research_data, round_number, previous_responses
            )

            # LLM 호출
            llm_response = await self.llm_router.generate(
                prompt=prompt,
                system_prompt=self.system_prompt,
            )

            if not llm_response.success:
                logger.error(
                    "일반인 에이전트 LLM 호출 실패: %s", llm_response.error_message
                )
                return self._create_fallback_response(
                    round_number=round_number,
                    error_message=llm_response.error_message,
                )

            # 응답 파싱
            return self._parse_response(llm_response.content, round_number)

        except Exception as e:
            logger.exception("일반인 에이전트 평가 중 예외 발생: %s", str(e))
            return self._create_fallback_response(
                round_number=round_number,
                error_message=str(e),
            )

    def _create_fallback_response(
        self,
        round_number: int,
        error_message: str,
    ) -> AgentResponse:
        """
        오류 시 기본 응답 생성 / Create fallback response on error.

        Args:
            round_number: 라운드 번호
            error_message: 오류 메시지

        Returns:
            AgentResponse: 기본값이 포함된 응답
        """
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
