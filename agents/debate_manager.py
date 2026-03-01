"""
Debate Manager
토론 관리자 - 다중 에이전트 토론 오케스트레이터

여러 에이전트의 독립적 평가, 교차 검토, 합의 도출을 관리합니다.
"""

import asyncio
import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from backends.router import LLMRouter

from .base import (
    AgentResponse,
    AgentRole,
    DebateAgent,
    DebateRound,
)
from .layperson import LaypersonAgent
from .phd_expert import PhDExpertAgent
from .undergraduate import UndergraduateAgent

logger = logging.getLogger(__name__)


# 에이전트 역할별 가중치 (PhD가 가장 높은 가중치)
ROLE_WEIGHTS: dict[AgentRole, float] = {
    AgentRole.PHD_EXPERT: 0.5,
    AgentRole.UNDERGRADUATE: 0.3,
    AgentRole.LAYPERSON: 0.2,
}


@dataclass
class DebateConfig:
    """
    토론 설정 / Debate configuration.

    Attributes:
        num_rounds: 총 토론 라운드 수 (기본: 3)
        consensus_threshold: 합의 도달 기준 (기본: 0.7)
        enable_cross_examination: 교차 검토 활성화 여부
        timeout_per_agent: 에이전트별 타임아웃 (초)
        parallel_assessment: 병렬 평가 활성화 여부
    """
    num_rounds: int = 3
    consensus_threshold: float = 0.7
    enable_cross_examination: bool = True
    timeout_per_agent: int = 120
    parallel_assessment: bool = True


@dataclass
class DebateResult:
    """
    토론 결과 / Final debate result.

    Attributes:
        rounds: 모든 토론 라운드 목록
        final_consensus: 최종 합의 정보
        per_agent_scores: 에이전트별 최종 점수
        overall_verdict: 종합 판정 (PASS/WARN/FAIL)
        overall_score: 종합 점수 (0.0~1.0)
        dissenting_opinions: 소수 의견 목록
    """
    rounds: list[DebateRound]
    final_consensus: dict[str, Any]
    per_agent_scores: dict[str, float]
    overall_verdict: str
    overall_score: float
    dissenting_opinions: list[str]

    def to_dict(self) -> dict[str, Any]:
        """딕셔너리로 변환 / Convert to dictionary."""
        return {
            "rounds": [r.to_dict() for r in self.rounds],
            "final_consensus": self.final_consensus,
            "per_agent_scores": self.per_agent_scores,
            "overall_verdict": self.overall_verdict,
            "overall_score": self.overall_score,
            "dissenting_opinions": self.dissenting_opinions,
        }


class DebateManager:
    """
    다중 에이전트 토론 관리자 / Multi-agent debate orchestrator.

    여러 토론 에이전트를 조율하여 다라운드 토론을 진행하고,
    최종 합의와 판정을 도출합니다.

    Orchestrates multi-round debates between agents, manages
    cross-examination, and synthesizes final consensus.

    토론 흐름 / Debate Flow:
    1. 라운드 1: 모든 에이전트가 독립적으로 평가 (병렬)
    2. 라운드 2+: 교차 검토 (이전 응답 참조)
    3. 합의 도달 시 조기 종료 가능
    4. 최종 결과 종합
    """

    def __init__(
        self,
        agents: list[DebateAgent],
        config: DebateConfig | None = None,
    ):
        """
        토론 관리자 초기화 / Initialize the debate manager.

        Args:
            agents: 토론에 참여할 에이전트 목록
            config: 토론 설정 (기본값 사용 가능)
        """
        self.agents = agents
        self.config = config or DebateConfig()

    @classmethod
    def create_default_panel(
        cls,
        llm_router: LLMRouter,
        config: DebateConfig | None = None,
    ) -> "DebateManager":
        """
        기본 토론 패널 생성 / Create a default debate panel with all three agents.

        일반인, 학사전공, 박사급 에이전트를 모두 포함하는 기본 패널을 생성합니다.

        Args:
            llm_router: LLM 라우터 인스턴스
            config: 토론 설정 (선택사항)

        Returns:
            DebateManager: 기본 패널이 구성된 토론 관리자
        """
        agents: list[DebateAgent] = [
            LaypersonAgent(llm_router),
            UndergraduateAgent(llm_router),
            PhDExpertAgent(llm_router),
        ]
        return cls(agents=agents, config=config)

    async def run_debate(
        self,
        research_data: dict[str, Any],
    ) -> DebateResult:
        """
        토론 실행 / Run the full multi-round debate.

        라운드 1에서 독립 평가 후, 교차 검토 라운드를 진행합니다.
        합의에 도달하면 조기 종료합니다.

        Args:
            research_data: 논문 정보 및 분석 결과

        Returns:
            DebateResult: 최종 토론 결과
        """
        logger.info(
            "토론 시작: %d 에이전트, %d 라운드",
            len(self.agents), self.config.num_rounds,
        )

        rounds: list[DebateRound] = []
        all_previous_responses: list[AgentResponse] | None = None

        for round_num in range(1, self.config.num_rounds + 1):
            logger.info("라운드 %d 시작", round_num)

            try:
                debate_round = await self._run_round(
                    research_data=research_data,
                    round_number=round_num,
                    previous_responses=all_previous_responses,
                )
            except Exception as e:
                logger.error("라운드 %d 실행 중 오류: %s", round_num, str(e))
                # 라운드 실패 시 빈 라운드 기록
                debate_round = DebateRound(
                    round_number=round_num,
                    responses=[],
                    consensus_score=None,
                )

            rounds.append(debate_round)

            # 합의 점수 확인 - 조기 종료
            if (
                debate_round.consensus_score is not None
                and debate_round.consensus_score >= self.config.consensus_threshold
                and round_num > 1
            ):
                logger.info(
                    "합의 도달 (consensus_score=%.2f >= threshold=%.2f), 라운드 %d에서 조기 종료",
                    debate_round.consensus_score,
                    self.config.consensus_threshold,
                    round_num,
                )
                break

            # 교차 검토를 위해 현재 라운드 응답 저장
            if self.config.enable_cross_examination and debate_round.responses:
                all_previous_responses = debate_round.responses

        # 최종 결과 종합
        final_consensus = self._synthesize_consensus(rounds)
        per_agent_scores = self._calculate_per_agent_scores(rounds)
        overall_score = self._calculate_overall_score(per_agent_scores)
        overall_verdict = self._determine_verdict(overall_score)
        dissenting_opinions = self._find_dissenting_opinions(rounds)

        result = DebateResult(
            rounds=rounds,
            final_consensus=final_consensus,
            per_agent_scores=per_agent_scores,
            overall_verdict=overall_verdict,
            overall_score=overall_score,
            dissenting_opinions=dissenting_opinions,
        )

        logger.info(
            "토론 완료: verdict=%s, score=%.2f, rounds=%d",
            overall_verdict, overall_score, len(rounds),
        )

        return result

    async def _run_round(
        self,
        research_data: dict[str, Any],
        round_number: int,
        previous_responses: list[AgentResponse] | None = None,
    ) -> DebateRound:
        """
        단일 토론 라운드 실행 / Execute a single round of debate.

        라운드 1에서는 독립 평가, 이후 라운드에서는 교차 검토를 수행합니다.

        Args:
            research_data: 논문 정보 및 분석 결과
            round_number: 라운드 번호
            previous_responses: 이전 라운드 응답 목록 (교차 검토용)

        Returns:
            DebateRound: 라운드 결과
        """
        responses: list[AgentResponse] = []

        if self.config.parallel_assessment:
            # 병렬 평가: asyncio.gather로 모든 에이전트 동시 실행
            tasks = []
            for agent in self.agents:
                task = self._assess_with_timeout(
                    agent=agent,
                    research_data=research_data,
                    round_number=round_number,
                    previous_responses=previous_responses,
                )
                tasks.append(task)

            results = await asyncio.gather(*tasks, return_exceptions=True)

            for agent, result in zip(self.agents, results):
                if isinstance(result, Exception):
                    logger.error(
                        "에이전트 %s 평가 실패: %s", agent.name, str(result)
                    )
                    # 실패한 에이전트에 대해 기본 응답 생성
                    responses.append(
                        self._create_error_response(agent, round_number, str(result))
                    )
                else:
                    responses.append(result)
        else:
            # 순차 평가
            for agent in self.agents:
                try:
                    response = await self._assess_with_timeout(
                        agent=agent,
                        research_data=research_data,
                        round_number=round_number,
                        previous_responses=previous_responses,
                    )
                    responses.append(response)
                except Exception as e:
                    logger.error(
                        "에이전트 %s 평가 실패: %s", agent.name, str(e)
                    )
                    responses.append(
                        self._create_error_response(agent, round_number, str(e))
                    )

        # 합의 점수 계산
        consensus_score = self._calculate_round_consensus(responses)

        return DebateRound(
            round_number=round_number,
            responses=responses,
            consensus_score=consensus_score,
        )

    async def _assess_with_timeout(
        self,
        agent: DebateAgent,
        research_data: dict[str, Any],
        round_number: int,
        previous_responses: list[AgentResponse] | None = None,
    ) -> AgentResponse:
        """
        타임아웃이 적용된 에이전트 평가 실행 / Run agent assessment with timeout.

        Args:
            agent: 토론 에이전트
            research_data: 논문 정보 및 분석 결과
            round_number: 라운드 번호
            previous_responses: 이전 라운드 응답

        Returns:
            AgentResponse: 에이전트 응답

        Raises:
            asyncio.TimeoutError: 타임아웃 초과 시
        """
        return await asyncio.wait_for(
            agent.assess(
                research_data=research_data,
                round_number=round_number,
                previous_responses=previous_responses,
            ),
            timeout=self.config.timeout_per_agent,
        )

    def _calculate_round_consensus(
        self,
        responses: list[AgentResponse],
    ) -> float | None:
        """
        라운드 합의 점수 계산 / Calculate consensus score for a round.

        에이전트 간 점수의 일치도를 0.0~1.0으로 계산합니다.
        표준편차가 작을수록 합의도가 높습니다.

        Args:
            responses: 라운드의 에이전트 응답 목록

        Returns:
            Optional[float]: 합의 점수 (응답이 없으면 None)
        """
        if not responses:
            return None

        scores = [r.score for r in responses if r.confidence > 0.0]

        if len(scores) < 2:
            return None

        # 표준편차 기반 합의도 계산
        mean_score = sum(scores) / len(scores)
        variance = sum((s - mean_score) ** 2 for s in scores) / len(scores)
        std_dev = variance ** 0.5

        # 표준편차가 0이면 완전 합의, 0.5면 합의 없음
        # 합의 점수 = 1.0 - (2 * std_dev), 0.0 이상으로 클램프
        consensus = max(0.0, 1.0 - (2.0 * std_dev))

        return round(consensus, 4)

    def _synthesize_consensus(
        self,
        rounds: list[DebateRound],
    ) -> dict[str, Any]:
        """
        최종 합의 종합 / Synthesize final consensus from all rounds.

        모든 라운드의 결과를 종합하여 최종 합의 정보를 생성합니다.

        Args:
            rounds: 모든 토론 라운드 목록

        Returns:
            Dict[str, Any]: 합의 정보 딕셔너리
        """
        if not rounds:
            return {
                "achieved": False,
                "final_consensus_score": 0.0,
                "summary": "토론이 진행되지 않았습니다.",
                "rounds_completed": 0,
            }

        last_round = rounds[-1]
        all_scores: list[float] = []
        all_key_points: list[str] = []
        all_concerns: list[str] = []

        # 마지막 라운드의 응답에서 정보 수집
        for response in last_round.responses:
            if response.confidence > 0.0:
                all_scores.append(response.score)
            all_key_points.extend(response.key_points)
            all_concerns.extend(response.concerns)

        consensus_score = last_round.consensus_score or 0.0
        mean_score = sum(all_scores) / len(all_scores) if all_scores else 0.0

        # 중복 제거
        unique_key_points = list(dict.fromkeys(all_key_points))
        unique_concerns = list(dict.fromkeys(all_concerns))

        return {
            "achieved": consensus_score >= self.config.consensus_threshold,
            "final_consensus_score": consensus_score,
            "mean_agent_score": round(mean_score, 4),
            "key_points": unique_key_points[:10],  # 상위 10개
            "concerns": unique_concerns[:10],
            "rounds_completed": len(rounds),
            "summary": (
                f"{'합의 도달' if consensus_score >= self.config.consensus_threshold else '합의 미도달'} "
                f"(합의도: {consensus_score:.2f}, 평균 점수: {mean_score:.2f}, "
                f"완료 라운드: {len(rounds)})"
            ),
        }

    def _calculate_per_agent_scores(
        self,
        rounds: list[DebateRound],
    ) -> dict[str, float]:
        """
        에이전트별 최종 점수 계산 / Calculate per-agent final scores.

        최신 라운드에 더 높은 가중치를 부여하여 에이전트별 최종 점수를 계산합니다.

        Args:
            rounds: 모든 토론 라운드 목록

        Returns:
            Dict[str, float]: 에이전트 이름 -> 최종 점수 매핑
        """
        if not rounds:
            return {}

        agent_scores: dict[str, list[tuple]] = {}  # name -> [(round_num, score)]

        for debate_round in rounds:
            for response in debate_round.responses:
                if response.agent_name not in agent_scores:
                    agent_scores[response.agent_name] = []
                agent_scores[response.agent_name].append(
                    (debate_round.round_number, response.score)
                )

        # 최신 라운드 가중치 적용
        total_rounds = len(rounds)
        per_agent_final: dict[str, float] = {}

        for agent_name, score_list in agent_scores.items():
            weighted_sum = 0.0
            weight_total = 0.0

            for round_num, score in score_list:
                # 라운드 번호가 클수록 높은 가중치
                weight = round_num / total_rounds
                weighted_sum += score * weight
                weight_total += weight

            if weight_total > 0:
                per_agent_final[agent_name] = round(
                    weighted_sum / weight_total, 4
                )
            else:
                per_agent_final[agent_name] = 0.5

        return per_agent_final

    def _calculate_overall_score(
        self,
        per_agent_scores: dict[str, float],
    ) -> float:
        """
        종합 점수 계산 / Calculate weighted overall score.

        에이전트 역할별 가중치를 적용하여 종합 점수를 산출합니다.
        가중치: PhD=0.5, Undergraduate=0.3, Layperson=0.2

        Args:
            per_agent_scores: 에이전트별 최종 점수

        Returns:
            float: 종합 점수 (0.0~1.0)
        """
        if not per_agent_scores:
            return 0.0

        # 에이전트 이름에서 역할 매핑
        role_map: dict[str, AgentRole] = {}
        for agent in self.agents:
            role_map[agent.name] = agent.role

        weighted_sum = 0.0
        weight_total = 0.0

        for agent_name, score in per_agent_scores.items():
            role = role_map.get(agent_name)
            if role is not None:
                weight = ROLE_WEIGHTS.get(role, 0.2)
            else:
                weight = 0.2  # 알 수 없는 역할의 기본 가중치

            weighted_sum += score * weight
            weight_total += weight

        if weight_total > 0:
            return round(weighted_sum / weight_total, 4)

        return 0.0

    def _determine_verdict(self, score: float) -> str:
        """
        종합 판정 결정 / Determine overall verdict based on score.

        Args:
            score: 종합 점수 (0.0~1.0)

        Returns:
            str: "PASS" (>=0.8), "WARN" (>=0.5), "FAIL" (<0.5)
        """
        if score >= 0.8:
            return "PASS"
        elif score >= 0.5:
            return "WARN"
        else:
            return "FAIL"

    def _find_dissenting_opinions(
        self,
        rounds: list[DebateRound],
    ) -> list[str]:
        """
        소수 의견 식별 / Find dissenting opinions across rounds.

        마지막 라운드에서 평균 점수와 크게 차이나는 에이전트의 의견을 식별합니다.

        Args:
            rounds: 모든 토론 라운드 목록

        Returns:
            List[str]: 소수 의견 설명 목록
        """
        if not rounds:
            return []

        last_round = rounds[-1]
        if not last_round.responses:
            return []

        # 마지막 라운드의 점수 수집
        scores = [r.score for r in last_round.responses if r.confidence > 0.0]
        if not scores:
            return []

        mean_score = sum(scores) / len(scores)
        dissenting: list[str] = []

        for response in last_round.responses:
            if response.confidence <= 0.0:
                continue

            deviation = abs(response.score - mean_score)
            # 평균에서 0.2 이상 벗어나면 소수 의견으로 판정
            if deviation >= 0.2:
                direction = "높게" if response.score > mean_score else "낮게"
                dissenting.append(
                    f"{response.agent_name}: 평균 대비 {direction} 평가 "
                    f"(점수: {response.score:.2f} vs 평균: {mean_score:.2f}). "
                    f"근거: {response.assessment[:200]}..."
                    if len(response.assessment) > 200
                    else f"{response.agent_name}: 평균 대비 {direction} 평가 "
                    f"(점수: {response.score:.2f} vs 평균: {mean_score:.2f}). "
                    f"근거: {response.assessment}"
                )

        return dissenting

    @staticmethod
    def _create_error_response(
        agent: DebateAgent,
        round_number: int,
        error_message: str,
    ) -> AgentResponse:
        """
        오류 시 기본 응답 생성 / Create a fallback response for a failed agent.

        Args:
            agent: 실패한 에이전트
            round_number: 라운드 번호
            error_message: 오류 메시지

        Returns:
            AgentResponse: 기본값이 포함된 응답
        """
        return AgentResponse(
            agent_role=agent.role,
            agent_name=agent.name,
            assessment=f"에이전트 평가 실패: {error_message}",
            score=0.5,
            confidence=0.0,
            key_points=[],
            concerns=[f"에이전트 오류 (Agent error): {error_message}"],
            questions=[],
            rebuttal_to=None,
            round_number=round_number,
            timestamp=datetime.now(),
            raw_llm_response="",
        )
