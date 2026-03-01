"""
Undergraduate Expert Debate Agent
학사전공 토론 에이전트

방법론 및 통계 전문가의 관점에서 연구를 평가합니다.
교과서적 프로토콜 검증, 통계적 유효성, 실험 설계 평가에 중점을 둡니다.
"""

import logging
from typing import Any

from backends.router import LLMRouter

from .base import AgentResponse, AgentRole, DebateAgent

logger = logging.getLogger(__name__)


class UndergraduateAgent(DebateAgent):
    """
    학사전공 에이전트 (Undergraduate Expert Agent)

    생명과학/생물정보학 학부 전공자의 관점에서 연구 방법론과 통계를 평가합니다.
    A debate agent representing an undergraduate-level expert who evaluates
    research methodology, statistical rigor, and experimental design.

    주요 역할 / Key Responsibilities:
    - 교과서적 프로토콜 대비 검증 (Check against textbook protocols)
    - 통계적 유효성 평가 (Evaluate statistical validity)
    - 실험 설계 검증 (Verify experimental design)
    - 과학적 엄밀성 점검 (Check scientific rigor)
    - 파이프라인 적절성 평가 (Evaluate pipeline appropriateness)
    """

    _SYSTEM_PROMPT = """당신은 생명과학/생물정보학 학부 전공자로서 연구 방법론과 통계를 평가하는 전문가입니다.
You are an undergraduate-level expert in life sciences/bioinformatics evaluating research methodology and statistics.

당신의 역할과 관점:
1. **교과서적 프로토콜 검증**: 연구 방법이 표준 프로토콜과 일치하는지 확인하세요.
   시퀀싱 깊이, 레플리케이트 수, 품질 관리 기준이 교과서적 기준을 충족하는지 점검하세요.
   RNA-seq라면 최소 3개 이상의 생물학적 반복이 있는지, 적절한 정규화가 적용되었는지 확인하세요.
2. **통계적 유효성 평가**: p-value, FDR 보정, 효과 크기, 검정력 분석이 적절한지 평가하세요.
   다중 비교 보정이 적용되었는지, 통계 검정 방법이 데이터 분포에 적합한지 확인하세요.
   표본 크기가 통계적 검정력을 확보하기에 충분한지 검토하세요.
3. **실험 설계 검증**: 대조군 설정, 무작위화, 블라인딩이 적절한지 확인하세요.
   교란 변수(confounders)가 적절히 통제되었는지, 배치 효과(batch effect)가 고려되었는지 점검하세요.
4. **과학적 엄밀성 점검**: 결론이 데이터로부터 논리적으로 도출되었는지 평가하세요.
   과잉 해석(over-interpretation)이 없는지, 한계점이 적절히 논의되었는지 확인하세요.
5. **파이프라인 적절성 평가**: 사용된 분석 파이프라인이 데이터 유형과 연구 목적에 적합한지 평가하세요.
   nf-core 파이프라인 선택이 적절한지, 파라미터 설정이 합리적인지 검토하세요.

Your perspective and role:
1. **Textbook protocol check**: Verify methods follow standard protocols (sequencing depth, replicates, QC).
2. **Statistical validity**: Evaluate p-values, FDR correction, effect sizes, power analysis.
3. **Experimental design**: Check controls, randomization, blinding, confounders, batch effects.
4. **Scientific rigor**: Ensure conclusions logically follow from data, no over-interpretation.
5. **Pipeline appropriateness**: Assess if the bioinformatics pipeline matches data type and study goals.

평가 기준:
- 표본 크기가 충분한가? (n >= 3 생물학적 반복?)
- 적절한 통계 검정이 사용되었는가?
- 다중 비교 보정이 적용되었는가?
- 실험 설계에 대조군이 포함되어 있는가?
- 분석 파이프라인이 데이터 유형에 적합한가?
- 품질 관리(QC) 단계가 포함되어 있는가?

반드시 지정된 JSON 형식으로 응답하세요.
Always respond in the specified JSON format."""

    def __init__(self, llm_router: LLMRouter):
        """
        학사전공 에이전트 초기화 / Initialize the Undergraduate agent.

        Args:
            llm_router: LLM 라우터 인스턴스
        """
        super().__init__(llm_router)

    @property
    def role(self) -> AgentRole:
        """에이전트 역할 반환 / Return agent role."""
        return AgentRole.UNDERGRADUATE

    @property
    def name(self) -> str:
        """에이전트 이름 반환 / Return agent display name."""
        return "학사전공 Agent (Undergraduate Expert)"

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
        연구 데이터를 방법론/통계 관점에서 평가 / Assess research methodology and statistics.

        Args:
            research_data: 논문 정보 및 분석 결과
            round_number: 현재 토론 라운드 번호
            previous_responses: 이전 라운드의 에이전트 응답 목록

        Returns:
            AgentResponse: 방법론/통계 관점의 평가 응답
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
                    "학사전공 에이전트 LLM 호출 실패: %s", llm_response.error_message
                )
                return self._create_fallback_response(
                    round_number=round_number,
                    error_message=llm_response.error_message,
                )

            # 응답 파싱
            return self._parse_response(llm_response.content, round_number)

        except Exception as e:
            logger.exception("학사전공 에이전트 평가 중 예외 발생: %s", str(e))
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
