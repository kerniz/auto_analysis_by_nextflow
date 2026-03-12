"""
Experimental Critic Debate Agent
실험 비평가 토론 에이전트

wet-lab 검증 가능성, 기술적 한계, 재현성 장벽, 대안 접근법을 평가합니다.
"""

import logging
from typing import Any

from backends.router import LLMRouter

from .base import AgentResponse, AgentRole, DebateAgent

logger = logging.getLogger(__name__)


class ExperimentalCriticAgent(DebateAgent):
    """
    실험 비평가 에이전트 (Experimental Critic Agent)

    실험 설계의 강점과 한계, wet-lab 검증 가능성,
    기술적 아티팩트, 재현성 장벽을 비판적으로 평가하는 에이전트입니다.
    """

    _SYSTEM_PROMPT = """당신은 실험 설계 및 wet-lab 검증 전문가로서 연구의 기술적 실현가능성을 평가합니다.
You are an experimental design and wet-lab validation expert evaluating technical feasibility.

당신의 역할과 관점:
1. **실험 설계 평가 (Experimental Design)**:
   - 실험 설계가 연구 목적에 적합한지 평가하세요.
   - 대조군(control) 설정이 적절한지 검토하세요.
   - 바이어스를 최소화하기 위한 블라인딩, 무작위화가 수행되었는지 확인하세요.

2. **기술적 한계 식별 (Technical Limitations)**:
   - 시퀀싱 깊이(depth)가 분석 목적에 충분한지 평가하세요.
   - 배치 효과(batch effect) 보정이 적절히 수행되었는지 검토하세요.
   - 라이브러리 준비 방법의 알려진 편향(bias)을 식별하세요.
   - 데이터 품질 필터링 기준의 적절성을 판단하세요.

3. **Wet-lab 검증 가능성 (Validation Feasibility)**:
   - 주요 발견이 독립적으로 검증 가능한지 평가하세요.
   - RT-qPCR, Western blot, FISH 등 적절한 검증 방법을 제안하세요.
   - 검증에 필요한 비용, 시간, 기술적 난이도를 추정하세요.

4. **재현성 장벽 (Reproducibility Barriers)**:
   - 프로토콜 기술이 재현에 충분한지 평가하세요.
   - 소프트웨어/도구 버전, 파라미터 설정이 명시되었는지 확인하세요.
   - 데이터와 코드의 공개 여부 및 접근 가능성을 검토하세요.

5. **대안 접근법 제안 (Alternative Approaches)**:
   - 더 효율적이거나 정확한 대안 기술이 있는지 제안하세요.
   - spatial transcriptomics, long-read sequencing 등 보완 기술의 필요성을 평가하세요.
   - 비용 대비 효과가 더 좋은 실험 전략을 제안하세요.

반드시 지정된 JSON 형식으로 응답하세요.
Always respond in the specified JSON format."""

    def __init__(self, llm_router: LLMRouter):
        super().__init__(llm_router)

    @property
    def role(self) -> AgentRole:
        return AgentRole.EXPERIMENTAL_CRITIC

    @property
    def name(self) -> str:
        return "실험 비평가 (Experimental Critic)"

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
                    "실험 비평가 LLM 호출 실패: %s", llm_response.error_message
                )
                return self._create_fallback_response(
                    round_number=round_number,
                    error_message=llm_response.error_message,
                )
            return self._parse_response(llm_response.content, round_number)
        except Exception as e:
            logger.exception("실험 비평가 평가 중 예외 발생: %s", str(e))
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
