"""
PhD Expert Debate Agent
박사급 토론 에이전트

심층 도메인 전문가의 관점에서 연구를 평가합니다.
신규성 도전, 생물학적 타당성 평가, 아티팩트 식별, 최신 기술 비교에 중점을 둡니다.
"""

import logging
from typing import Dict, List, Optional, Any

from backends.router import LLMRouter
from .base import DebateAgent, AgentRole, AgentResponse

logger = logging.getLogger(__name__)


class PhDExpertAgent(DebateAgent):
    """
    박사급 에이전트 (PhD Expert Agent)

    해당 분야의 심층 도메인 전문가 관점에서 연구를 평가하는 에이전트입니다.
    A debate agent representing a PhD-level domain expert who provides
    deep, critical evaluation of research quality and novelty.

    주요 역할 / Key Responsibilities:
    - 신규성 도전 (Challenge novelty claims)
    - 생물학적 타당성 평가 (Assess biological plausibility)
    - 아티팩트/교란 변수 식별 (Identify artifacts and confounders)
    - 최신 기술(State-of-the-art) 비교 (Compare with current standards)
    - 피어 리뷰 준비도 판단 (Judge peer review readiness)
    """

    _SYSTEM_PROMPT = """당신은 생물정보학 및 유전체학 분야의 박사급 전문가로서 연구를 심층 평가합니다.
You are a PhD-level expert in bioinformatics and genomics providing deep critical evaluation of research.

당신의 역할과 관점:
1. **신규성 도전 (Challenge Novelty)**:
   - 이 연구가 진정으로 새로운 것인지 비판적으로 평가하세요.
   - 기존 연구와의 차별점이 명확한지, 증분적 발전에 불과한 것은 아닌지 판단하세요.
   - 저자들의 기여도(contribution) 주장이 과장되지 않았는지 검토하세요.
   - 관련 선행 연구가 적절히 인용되고 비교되었는지 확인하세요.

2. **생물학적 타당성 평가 (Biological Plausibility)**:
   - 발견된 결과가 알려진 생물학적 메커니즘과 일치하는지 평가하세요.
   - 유전자 발현 패턴, 경로 분석 결과가 생물학적으로 말이 되는지 확인하세요.
   - 기능적 검증(functional validation)이 충분한지, 후속 실험이 필요한지 판단하세요.
   - 관찰된 효과의 크기가 생물학적으로 의미 있는 수준인지 검토하세요.

3. **아티팩트 및 교란 변수 식별 (Identify Artifacts/Confounders)**:
   - 배치 효과(batch effect), 기술적 아티팩트, 시퀀싱 편향을 식별하세요.
   - 숨겨진 교란 변수(hidden confounders)가 있는지 검토하세요.
   - GC 편향, PCR 중복, 맵핑 편향 등 기술적 문제를 지적하세요.
   - 데이터 전처리 과정에서의 잠재적 정보 손실을 평가하세요.

4. **최신 기술 비교 (State-of-the-Art Comparison)**:
   - 사용된 방법이 현재 최선의 방법(best practices)인지 평가하세요.
   - 더 적합하거나 최신의 대안적 접근법이 있는지 제안하세요.
   - 벤치마크 데이터셋이나 골드 스탠다드와의 비교가 적절한지 판단하세요.
   - 분석 도구의 버전이 최신인지, 알려진 버그가 있는지 점검하세요.

5. **피어 리뷰 준비도 판단 (Peer Review Readiness)**:
   - 이 연구가 고수준 저널의 피어 리뷰를 통과할 수 있는지 판단하세요.
   - 데이터 가용성, 코드 재현성, 방법론 기술의 완전성을 평가하세요.
   - 추가로 필요한 실험이나 분석이 있는지 구체적으로 제안하세요.
   - 논문의 전반적인 완성도와 출판 적합성을 점수화하세요.

Your perspective and role:
1. **Challenge Novelty**: Critically assess whether the research is truly novel or merely incremental.
2. **Biological Plausibility**: Evaluate if findings align with known biological mechanisms.
3. **Identify Artifacts/Confounders**: Spot batch effects, technical artifacts, sequencing biases, hidden confounders.
4. **State-of-the-Art Comparison**: Assess if methods represent current best practices.
5. **Peer Review Readiness**: Judge if the research could pass high-tier journal peer review.

평가 기준:
- 연구의 신규성이 충분한가?
- 결과가 생물학적으로 타당한가?
- 기술적 아티팩트가 적절히 통제되었는가?
- 최신 방법론이 적용되었는가?
- 피어 리뷰를 통과할 수준인가?
- 데이터와 코드의 재현성이 확보되었는가?

반드시 지정된 JSON 형식으로 응답하세요.
Always respond in the specified JSON format."""

    def __init__(self, llm_router: LLMRouter):
        """
        박사급 에이전트 초기화 / Initialize the PhD Expert agent.

        Args:
            llm_router: LLM 라우터 인스턴스
        """
        super().__init__(llm_router)

    @property
    def role(self) -> AgentRole:
        """에이전트 역할 반환 / Return agent role."""
        return AgentRole.PHD_EXPERT

    @property
    def name(self) -> str:
        """에이전트 이름 반환 / Return agent display name."""
        return "박사급 Agent (PhD Expert)"

    @property
    def system_prompt(self) -> str:
        """시스템 프롬프트 반환 / Return system prompt."""
        return self._SYSTEM_PROMPT

    async def assess(
        self,
        research_data: Dict[str, Any],
        round_number: int = 1,
        previous_responses: Optional[List[AgentResponse]] = None,
    ) -> AgentResponse:
        """
        연구 데이터를 박사급 전문가 관점에서 평가 / Assess research from PhD expert perspective.

        Args:
            research_data: 논문 정보 및 분석 결과
            round_number: 현재 토론 라운드 번호
            previous_responses: 이전 라운드의 에이전트 응답 목록

        Returns:
            AgentResponse: 박사급 전문가 관점의 평가 응답
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
                    "박사급 에이전트 LLM 호출 실패: %s", llm_response.error_message
                )
                return self._create_fallback_response(
                    round_number=round_number,
                    error_message=llm_response.error_message,
                )

            # 응답 파싱
            return self._parse_response(llm_response.content, round_number)

        except Exception as e:
            logger.exception("박사급 에이전트 평가 중 예외 발생: %s", str(e))
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
