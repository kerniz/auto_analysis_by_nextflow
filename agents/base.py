"""
Debate Agent Base Classes
토론 에이전트 기본 클래스 및 데이터 구조

Multi-agent debate system의 핵심 추상 기본 클래스와 데이터 구조를 정의합니다.
"""

import json
import re
import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any
from datetime import datetime
from enum import Enum

from backends.router import LLMRouter

logger = logging.getLogger(__name__)


class AgentRole(Enum):
    """
    에이전트 역할 정의
    Agent role enumeration for the multi-agent debate system.
    """
    LAYPERSON = "layperson"
    UNDERGRADUATE = "undergraduate"
    PHD_EXPERT = "phd_expert"


@dataclass
class AgentResponse:
    """
    에이전트 응답 데이터 구조
    Standardized response from a debate agent after assessing research data.

    Attributes:
        agent_role: 에이전트의 역할 (AgentRole enum)
        agent_name: 에이전트 표시 이름
        assessment: 주요 평가 텍스트
        score: 종합 점수 (0.0 ~ 1.0)
        confidence: 확신도 (0.0 ~ 1.0)
        key_points: 핵심 포인트 목록
        concerns: 우려 사항 목록
        questions: 다른 에이전트에게 묻는 질문 목록
        rebuttal_to: 반론 대상 에이전트 이름 (교차 검토 시)
        round_number: 토론 라운드 번호
        timestamp: 응답 생성 시각
        raw_llm_response: LLM 원본 응답 텍스트
    """
    agent_role: AgentRole
    agent_name: str
    assessment: str
    score: float
    confidence: float
    key_points: List[str]
    concerns: List[str]
    questions: List[str]
    rebuttal_to: Optional[str]
    round_number: int
    timestamp: datetime
    raw_llm_response: str

    def to_dict(self) -> Dict[str, Any]:
        """딕셔너리로 변환 / Convert to dictionary."""
        return {
            "agent_role": self.agent_role.value,
            "agent_name": self.agent_name,
            "assessment": self.assessment,
            "score": self.score,
            "confidence": self.confidence,
            "key_points": self.key_points,
            "concerns": self.concerns,
            "questions": self.questions,
            "rebuttal_to": self.rebuttal_to,
            "round_number": self.round_number,
            "timestamp": self.timestamp.isoformat(),
            "raw_llm_response": self.raw_llm_response,
        }


@dataclass
class DebateRound:
    """
    토론 라운드 데이터 구조
    Contains all agent responses from a single round of debate.

    Attributes:
        round_number: 라운드 번호
        responses: 해당 라운드의 에이전트 응답 목록
        consensus_score: 합의 점수 (에이전트 간 점수 일치도)
    """
    round_number: int
    responses: List[AgentResponse]
    consensus_score: Optional[float] = None

    def to_dict(self) -> Dict[str, Any]:
        """딕셔너리로 변환 / Convert to dictionary."""
        return {
            "round_number": self.round_number,
            "responses": [r.to_dict() for r in self.responses],
            "consensus_score": self.consensus_score,
        }


class DebateAgent(ABC):
    """
    토론 에이전트 추상 기본 클래스
    Abstract base class for all debate agents in the multi-agent system.

    모든 토론 에이전트(Layperson, Undergraduate, PhD Expert)는
    이 클래스를 상속받아 구현해야 합니다.

    All debate agents must inherit from this class and implement
    the abstract properties and methods.
    """

    def __init__(self, llm_router: LLMRouter):
        """
        에이전트 초기화 / Initialize the debate agent.

        Args:
            llm_router: LLM 라우터 인스턴스 (LLM 호출에 사용)
        """
        self.llm_router = llm_router

    @property
    @abstractmethod
    def role(self) -> AgentRole:
        """에이전트 역할 / Agent's role in the debate."""
        pass

    @property
    @abstractmethod
    def name(self) -> str:
        """에이전트 이름 / Agent's display name."""
        pass

    @property
    @abstractmethod
    def system_prompt(self) -> str:
        """시스템 프롬프트 / System prompt defining the agent's persona."""
        pass

    @abstractmethod
    async def assess(
        self,
        research_data: Dict[str, Any],
        round_number: int = 1,
        previous_responses: Optional[List[AgentResponse]] = None,
    ) -> AgentResponse:
        """
        연구 데이터 평가 / Assess the research data.

        Args:
            research_data: 논문 정보 및 분석 결과가 포함된 딕셔너리
            round_number: 현재 토론 라운드 번호
            previous_responses: 이전 라운드의 에이전트 응답 목록 (교차 검토용)

        Returns:
            AgentResponse: 에이전트의 평가 응답
        """
        pass

    def _build_assessment_prompt(
        self,
        research_data: Dict[str, Any],
        round_number: int,
        previous_responses: Optional[List[AgentResponse]] = None,
    ) -> str:
        """
        평가 프롬프트 생성 / Build the assessment prompt for the LLM.

        논문 정보, 분석 결과를 포함한 상세 프롬프트를 구성합니다.
        라운드 2 이상에서는 이전 응답을 포함하여 교차 검토를 유도합니다.

        Args:
            research_data: 논문 정보 및 분석 결과
            round_number: 현재 라운드 번호
            previous_responses: 이전 응답 목록

        Returns:
            str: 완성된 프롬프트 문자열
        """
        # --- 논문 기본 정보 구성 ---
        paper_info = research_data.get("paper_info", {})
        analysis_results = research_data.get("analysis_results", {})
        sequencing_type = research_data.get("sequencing_type", "Unknown")
        pipeline_info = research_data.get("pipeline_info", {})

        prompt_parts = []

        prompt_parts.append("=== 연구 논문 평가 요청 (Research Paper Assessment Request) ===\n")

        # 논문 정보
        prompt_parts.append("## 논문 정보 (Paper Information)")
        prompt_parts.append(f"- PMID: {paper_info.get('pmid', 'N/A')}")
        prompt_parts.append(f"- 제목 (Title): {paper_info.get('title', 'N/A')}")
        prompt_parts.append(f"- 저자 (Authors): {paper_info.get('authors', 'N/A')}")
        prompt_parts.append(f"- 저널 (Journal): {paper_info.get('journal', 'N/A')}")
        prompt_parts.append(f"- 발행일 (Publication Date): {paper_info.get('pub_date', 'N/A')}")
        prompt_parts.append(f"- 초록 (Abstract): {paper_info.get('abstract', 'N/A')}")
        prompt_parts.append("")

        # 시퀀싱 정보
        prompt_parts.append("## 시퀀싱 정보 (Sequencing Information)")
        prompt_parts.append(f"- 시퀀싱 타입 (Sequencing Type): {sequencing_type}")
        if pipeline_info:
            prompt_parts.append(f"- 파이프라인 (Pipeline): {pipeline_info.get('name', 'N/A')}")
            prompt_parts.append(
                f"- 파이프라인 파라미터 (Parameters): "
                f"{json.dumps(pipeline_info.get('parameters', {}), indent=2)}"
            )
        prompt_parts.append("")

        # 분석 결과
        if analysis_results:
            prompt_parts.append("## 분석 결과 (Analysis Results)")
            for key, value in analysis_results.items():
                if isinstance(value, dict):
                    prompt_parts.append(f"### {key}")
                    for sub_key, sub_value in value.items():
                        prompt_parts.append(f"  - {sub_key}: {sub_value}")
                else:
                    prompt_parts.append(f"- {key}: {value}")
            prompt_parts.append("")

        # --- 라운드별 지시 ---
        if round_number == 1:
            prompt_parts.append("## 지시사항 (Instructions)")
            prompt_parts.append(
                "이것은 첫 번째 평가 라운드입니다. 독립적으로 연구를 평가해 주십시오."
            )
            prompt_parts.append(
                "This is Round 1. Please assess the research independently."
            )
        else:
            prompt_parts.append(f"## 라운드 {round_number} - 교차 검토 (Cross-Examination)")
            prompt_parts.append(
                "이전 라운드의 다른 에이전트 평가를 참고하여 교차 검토해 주십시오."
            )
            prompt_parts.append(
                "Review the previous responses from other agents and provide "
                "your updated assessment."
            )
            prompt_parts.append("")

            if previous_responses:
                prompt_parts.append("### 이전 라운드 응답 (Previous Responses)")
                for resp in previous_responses:
                    prompt_parts.append(f"\n--- {resp.agent_name} (점수: {resp.score}) ---")
                    prompt_parts.append(f"평가: {resp.assessment}")
                    prompt_parts.append(f"핵심 포인트: {', '.join(resp.key_points)}")
                    prompt_parts.append(f"우려 사항: {', '.join(resp.concerns)}")
                    if resp.questions:
                        prompt_parts.append(f"질문: {', '.join(resp.questions)}")
                prompt_parts.append("")

                # 자신에게 온 질문 강조
                my_questions = []
                for resp in previous_responses:
                    if resp.agent_role != self.role and resp.questions:
                        my_questions.extend(resp.questions)

                if my_questions:
                    prompt_parts.append("### 당신에게 제기된 질문 (Questions for You)")
                    for i, q in enumerate(my_questions, 1):
                        prompt_parts.append(f"  {i}. {q}")
                    prompt_parts.append(
                        "\n위 질문들에 대해 반드시 답변해 주십시오. "
                        "Please address these questions in your response."
                    )
                    prompt_parts.append("")

        # --- 응답 형식 지시 ---
        prompt_parts.append("## 응답 형식 (Response Format)")
        prompt_parts.append(
            "반드시 아래 JSON 형식으로만 응답하십시오. "
            "Respond ONLY in the following JSON format:"
        )
        prompt_parts.append("")
        prompt_parts.append("```json")
        prompt_parts.append(json.dumps({
            "assessment": "종합적인 평가 내용 (Comprehensive assessment text)",
            "score": 0.75,
            "confidence": 0.85,
            "key_points": [
                "핵심 포인트 1 (Key point 1)",
                "핵심 포인트 2 (Key point 2)",
            ],
            "concerns": [
                "우려 사항 1 (Concern 1)",
                "우려 사항 2 (Concern 2)",
            ],
            "questions": [
                "다른 에이전트에게 묻는 질문 (Question for other agents)",
            ],
            "rebuttal_to": "반론 대상 에이전트 이름 또는 null",
        }, indent=2, ensure_ascii=False))
        prompt_parts.append("```")
        prompt_parts.append("")
        prompt_parts.append(
            "score는 0.0(매우 낮음)~1.0(매우 높음) 사이의 값입니다. "
            "confidence는 당신의 평가에 대한 확신도(0.0~1.0)입니다."
        )

        return "\n".join(prompt_parts)

    def _parse_response(
        self,
        llm_content: str,
        round_number: int,
    ) -> AgentResponse:
        """
        LLM 응답 파싱 / Parse the LLM response into an AgentResponse.

        JSON 파싱을 시도하고, 실패 시 기본값으로 폴백합니다.

        Args:
            llm_content: LLM이 반환한 텍스트 응답
            round_number: 현재 라운드 번호

        Returns:
            AgentResponse: 파싱된 에이전트 응답
        """
        parsed = None

        # JSON 블록 추출 시도
        try:
            # ```json ... ``` 블록에서 추출
            json_match = re.search(
                r"```(?:json)?\s*\n?(.*?)\n?\s*```",
                llm_content,
                re.DOTALL,
            )
            if json_match:
                parsed = json.loads(json_match.group(1))
            else:
                # 순수 JSON으로 파싱 시도
                # 중괄호로 시작하는 부분 찾기
                brace_match = re.search(r"\{.*\}", llm_content, re.DOTALL)
                if brace_match:
                    parsed = json.loads(brace_match.group(0))
                else:
                    parsed = json.loads(llm_content)
        except (json.JSONDecodeError, AttributeError) as e:
            logger.warning(
                "JSON 파싱 실패 (agent=%s, round=%d): %s",
                self.name, round_number, str(e),
            )

        if parsed and isinstance(parsed, dict):
            # 점수 범위 검증 및 클램프
            raw_score = parsed.get("score", 0.5)
            try:
                score = max(0.0, min(1.0, float(raw_score)))
            except (TypeError, ValueError):
                score = 0.5

            raw_confidence = parsed.get("confidence", 0.5)
            try:
                confidence = max(0.0, min(1.0, float(raw_confidence)))
            except (TypeError, ValueError):
                confidence = 0.5

            return AgentResponse(
                agent_role=self.role,
                agent_name=self.name,
                assessment=str(parsed.get("assessment", "")),
                score=score,
                confidence=confidence,
                key_points=self._ensure_str_list(parsed.get("key_points", [])),
                concerns=self._ensure_str_list(parsed.get("concerns", [])),
                questions=self._ensure_str_list(parsed.get("questions", [])),
                rebuttal_to=parsed.get("rebuttal_to"),
                round_number=round_number,
                timestamp=datetime.now(),
                raw_llm_response=llm_content,
            )

        # 파싱 완전 실패 시 기본값 반환
        logger.warning(
            "LLM 응답 파싱 완전 실패, 기본값 사용 (agent=%s, round=%d)",
            self.name, round_number,
        )
        return AgentResponse(
            agent_role=self.role,
            agent_name=self.name,
            assessment=llm_content if llm_content else "평가를 생성할 수 없습니다.",
            score=0.5,
            confidence=0.0,
            key_points=[],
            concerns=["LLM 응답 파싱 실패 (Failed to parse LLM response)"],
            questions=[],
            rebuttal_to=None,
            round_number=round_number,
            timestamp=datetime.now(),
            raw_llm_response=llm_content,
        )

    @staticmethod
    def _ensure_str_list(value: Any) -> List[str]:
        """
        값을 문자열 리스트로 변환 / Ensure value is a list of strings.

        Args:
            value: 변환할 값

        Returns:
            List[str]: 문자열 리스트
        """
        if isinstance(value, list):
            return [str(item) for item in value]
        if isinstance(value, str):
            return [value]
        return []
