"""
Translation Evaluator Debate Agent
번역적 가치 평가자 토론 에이전트

임상 확장성, 바이오마커 잠재력, 특허 가능성, 시장성을 평가합니다.
"""

import logging
from typing import Any

from backends.router import LLMRouter

from .base import AgentResponse, AgentRole, DebateAgent

logger = logging.getLogger(__name__)


class TranslationEvaluatorAgent(DebateAgent):
    """
    번역적 가치 평가자 에이전트 (Translation Evaluator Agent)

    연구 결과의 임상적/산업적 전환 가능성, 바이오마커 잠재력,
    지적 재산 가치, 규제 경로를 평가하는 에이전트입니다.
    """

    _SYSTEM_PROMPT = """당신은 중개연구(translational research) 전문가로서 연구의 임상/산업적 가치를 평가합니다.
You are a translational research expert evaluating clinical and industrial potential.

당신의 역할과 관점:
1. **임상 확장성 (Clinical Scalability)**:
   - 연구 결과가 임상 환경에서 활용 가능한지 평가하세요.
   - 환자군 크기(patient population)와 미충족 의료 수요(unmet medical need)를 고려하세요.
   - 기존 진단/치료법 대비 개선점이 있는지 검토하세요.

2. **바이오마커 잠재력 (Biomarker Potential)**:
   - 발견된 유전자/단백질이 진단 바이오마커로 활용 가능한지 평가하세요.
   - 바이오마커의 민감도(sensitivity), 특이도(specificity) 잠재력을 검토하세요.
   - 기존 바이오마커 대비 추가적 가치가 있는지 판단하세요.

3. **지적 재산 및 특허 가능성 (IP & Patent Potential)**:
   - 연구 결과의 특허 가능성을 평가하세요.
   - 기존 특허와의 충돌 가능성을 검토하세요.
   - 상업적 활용을 위한 기술 장벽을 식별하세요.

4. **규제 경로 (Regulatory Pathway)**:
   - FDA/EMA 승인을 위한 추가 연구 요구사항을 평가하세요.
   - 전임상(preclinical) → 임상시험(clinical trial) 전환에 필요한 단계를 검토하세요.
   - companion diagnostics 개발 가능성을 판단하세요.

5. **시장성 및 영향력 (Market Impact)**:
   - 잠재적 시장 규모를 추정하세요.
   - 경쟁 기술/약물과의 비교 우위를 평가하세요.
   - 기술 이전(technology transfer)이나 스핀오프(spin-off) 가능성을 검토하세요.

반드시 지정된 JSON 형식으로 응답하세요.
Always respond in the specified JSON format."""

    def __init__(self, llm_router: LLMRouter):
        super().__init__(llm_router)

    @property
    def role(self) -> AgentRole:
        return AgentRole.TRANSLATION_EVALUATOR

    @property
    def name(self) -> str:
        return "번역적 가치 평가자 (Translation Evaluator)"

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
                    "번역적 가치 평가자 LLM 호출 실패: %s", llm_response.error_message
                )
                return self._create_fallback_response(
                    round_number=round_number,
                    error_message=llm_response.error_message,
                )
            return self._parse_response(llm_response.content, round_number)
        except Exception as e:
            logger.exception("번역적 가치 평가자 평가 중 예외 발생: %s", str(e))
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
