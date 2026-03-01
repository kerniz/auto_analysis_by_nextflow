"""
Debate Report Generator
토론 보고서 생성기

토론 결과를 기반으로 구조화된 보고서를 JSON 및 Markdown 형식으로 생성합니다.
"""

import json
import logging
import os
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from .base import AgentResponse
from .debate_manager import DebateResult

logger = logging.getLogger(__name__)


@dataclass
class DebateReport:
    """
    토론 보고서 데이터 구조 / Debate report data structure.

    Attributes:
        pmid: PubMed 논문 ID
        debate_result: 토론 결과
        executive_summary: 핵심 요약
        per_agent_summaries: 에이전트별 요약
        consensus_narrative: 합의 서술
        key_strengths: 주요 강점 목록
        key_weaknesses: 주요 약점 목록
        recommendations: 권고 사항 목록
        generated_at: 보고서 생성 시각
    """
    pmid: str
    debate_result: DebateResult
    executive_summary: str
    per_agent_summaries: dict[str, str]
    consensus_narrative: str
    key_strengths: list[str]
    key_weaknesses: list[str]
    recommendations: list[str]
    generated_at: datetime = field(default_factory=datetime.now)

    def to_dict(self) -> dict[str, Any]:
        """딕셔너리로 변환 / Convert to dictionary."""
        return {
            "pmid": self.pmid,
            "debate_result": self.debate_result.to_dict(),
            "executive_summary": self.executive_summary,
            "per_agent_summaries": self.per_agent_summaries,
            "consensus_narrative": self.consensus_narrative,
            "key_strengths": self.key_strengths,
            "key_weaknesses": self.key_weaknesses,
            "recommendations": self.recommendations,
            "generated_at": self.generated_at.isoformat(),
        }

    def to_markdown(self) -> str:
        """
        Markdown 형식으로 변환 / Convert to Markdown format.

        Returns:
            str: Markdown 형식의 보고서 문자열
        """
        result = self.debate_result
        lines: list[str] = []

        # 헤더
        lines.append("# 연구 논문 토론 보고서 (Research Paper Debate Report)")
        lines.append(f"**PMID:** {self.pmid}")
        lines.append(f"**생성일:** {self.generated_at.strftime('%Y-%m-%d %H:%M:%S')}")
        lines.append("")

        # 종합 판정
        verdict_emoji_map = {"PASS": "PASS", "WARN": "WARN", "FAIL": "FAIL"}
        verdict_label = verdict_emoji_map.get(result.overall_verdict, result.overall_verdict)

        lines.append("---")
        lines.append(f"## 종합 판정 (Overall Verdict): **{verdict_label}**")
        lines.append(f"- **종합 점수 (Overall Score):** {result.overall_score:.2f} / 1.00")
        lines.append("")

        # Executive Summary
        lines.append("## 핵심 요약 (Executive Summary)")
        lines.append(self.executive_summary)
        lines.append("")

        # 에이전트별 점수
        lines.append("## 에이전트별 점수 (Per-Agent Scores)")
        lines.append("| 에이전트 (Agent) | 점수 (Score) |")
        lines.append("|---|---|")
        for agent_name, score in result.per_agent_scores.items():
            lines.append(f"| {agent_name} | {score:.2f} |")
        lines.append("")

        # 에이전트별 요약
        lines.append("## 에이전트별 상세 평가 (Per-Agent Summaries)")
        for agent_name, summary in self.per_agent_summaries.items():
            lines.append(f"### {agent_name}")
            lines.append(summary)
            lines.append("")

        # 합의 서술
        lines.append("## 합의 분석 (Consensus Analysis)")
        lines.append(self.consensus_narrative)
        lines.append("")

        # 주요 강점
        if self.key_strengths:
            lines.append("## 주요 강점 (Key Strengths)")
            for strength in self.key_strengths:
                lines.append(f"- {strength}")
            lines.append("")

        # 주요 약점
        if self.key_weaknesses:
            lines.append("## 주요 약점 (Key Weaknesses)")
            for weakness in self.key_weaknesses:
                lines.append(f"- {weakness}")
            lines.append("")

        # 소수 의견
        if result.dissenting_opinions:
            lines.append("## 소수 의견 (Dissenting Opinions)")
            for opinion in result.dissenting_opinions:
                lines.append(f"- {opinion}")
            lines.append("")

        # 권고 사항
        if self.recommendations:
            lines.append("## 권고 사항 (Recommendations)")
            for rec in self.recommendations:
                lines.append(f"- {rec}")
            lines.append("")

        # 라운드별 세부 정보
        lines.append("## 라운드별 세부 정보 (Round Details)")
        for debate_round in result.rounds:
            lines.append(f"### 라운드 {debate_round.round_number}")
            if debate_round.consensus_score is not None:
                lines.append(
                    f"**합의도 (Consensus Score):** {debate_round.consensus_score:.2f}"
                )
            lines.append("")
            for response in debate_round.responses:
                lines.append(
                    f"#### {response.agent_name} "
                    f"(점수: {response.score:.2f}, 확신도: {response.confidence:.2f})"
                )
                lines.append(f"**평가:** {response.assessment}")
                if response.key_points:
                    lines.append("**핵심 포인트:**")
                    for kp in response.key_points:
                        lines.append(f"  - {kp}")
                if response.concerns:
                    lines.append("**우려 사항:**")
                    for concern in response.concerns:
                        lines.append(f"  - {concern}")
                if response.questions:
                    lines.append("**질문:**")
                    for question in response.questions:
                        lines.append(f"  - {question}")
                lines.append("")

        # 푸터
        lines.append("---")
        lines.append(
            "*이 보고서는 다중 에이전트 토론 시스템에 의해 자동 생성되었습니다.*"
        )
        lines.append(
            "*This report was auto-generated by the multi-agent debate system.*"
        )

        return "\n".join(lines)


class DebateReportGenerator:
    """
    토론 보고서 생성기 / Debate report generator.

    토론 결과를 분석하여 구조화된 보고서를 생성하고,
    JSON 및 Markdown 파일로 저장합니다.

    Generates structured reports from debate results and saves
    them as JSON and Markdown files.
    """

    def generate_report(
        self,
        pmid: str,
        debate_result: DebateResult,
        research_data: dict[str, Any] | None = None,
    ) -> DebateReport:
        """
        토론 보고서 생성 / Generate a debate report.

        Args:
            pmid: PubMed 논문 ID
            debate_result: 토론 결과
            research_data: 논문 정보 및 분석 결과 (선택사항)

        Returns:
            DebateReport: 생성된 보고서
        """
        executive_summary = self._generate_executive_summary(debate_result)

        # 에이전트별 요약 생성
        per_agent_summaries: dict[str, str] = {}
        if debate_result.rounds:
            last_round = debate_result.rounds[-1]
            for response in last_round.responses:
                per_agent_summaries[response.agent_name] = (
                    self._generate_agent_summary([response])
                )

        consensus_narrative = self._generate_consensus_narrative(debate_result)
        key_strengths = self._extract_key_strengths(debate_result)
        key_weaknesses = self._extract_key_weaknesses(debate_result)
        recommendations = self._generate_recommendations(
            debate_result, research_data
        )

        return DebateReport(
            pmid=pmid,
            debate_result=debate_result,
            executive_summary=executive_summary,
            per_agent_summaries=per_agent_summaries,
            consensus_narrative=consensus_narrative,
            key_strengths=key_strengths,
            key_weaknesses=key_weaknesses,
            recommendations=recommendations,
        )

    def _generate_executive_summary(
        self,
        debate_result: DebateResult,
    ) -> str:
        """
        핵심 요약 생성 / Generate executive summary.

        Args:
            debate_result: 토론 결과

        Returns:
            str: 핵심 요약 텍스트
        """
        verdict = debate_result.overall_verdict
        score = debate_result.overall_score
        num_rounds = len(debate_result.rounds)
        consensus = debate_result.final_consensus

        verdict_descriptions = {
            "PASS": "연구 품질이 우수하며 신뢰할 수 있는 결과로 판단됩니다.",
            "WARN": "연구에 일부 우려 사항이 있으며 추가 검토가 필요합니다.",
            "FAIL": "연구에 심각한 문제가 발견되었으며 결과의 신뢰성에 의문이 있습니다.",
        }

        summary_parts = [
            f"종합 판정: {verdict} (점수: {score:.2f}/1.00)",
            verdict_descriptions.get(
                verdict, "판정을 내릴 수 없습니다."
            ),
            f"\n{num_rounds}회의 토론 라운드가 진행되었으며, "
            f"{'합의에 도달' if consensus.get('achieved', False) else '합의에 도달하지 못'}했습니다.",
        ]

        # 에이전트별 점수 요약
        if debate_result.per_agent_scores:
            summary_parts.append("\n에이전트별 최종 점수:")
            for agent_name, agent_score in debate_result.per_agent_scores.items():
                summary_parts.append(f"  - {agent_name}: {agent_score:.2f}")

        # 소수 의견 언급
        if debate_result.dissenting_opinions:
            summary_parts.append(
                f"\n{len(debate_result.dissenting_opinions)}건의 소수 의견이 있습니다."
            )

        return "\n".join(summary_parts)

    def _generate_agent_summary(
        self,
        agent_responses: list[AgentResponse],
    ) -> str:
        """
        에이전트별 요약 생성 / Generate summary for an agent's responses.

        Args:
            agent_responses: 특정 에이전트의 응답 목록

        Returns:
            str: 에이전트 요약 텍스트
        """
        if not agent_responses:
            return "해당 에이전트의 응답이 없습니다."

        # 가장 최근 응답 사용
        response = agent_responses[-1]

        parts = [
            f"**점수:** {response.score:.2f} (확신도: {response.confidence:.2f})",
            f"\n**평가:** {response.assessment}",
        ]

        if response.key_points:
            parts.append("\n**핵심 포인트:**")
            for kp in response.key_points:
                parts.append(f"- {kp}")

        if response.concerns:
            parts.append("\n**우려 사항:**")
            for concern in response.concerns:
                parts.append(f"- {concern}")

        if response.questions:
            parts.append("\n**질문:**")
            for question in response.questions:
                parts.append(f"- {question}")

        return "\n".join(parts)

    def _generate_consensus_narrative(
        self,
        debate_result: DebateResult,
    ) -> str:
        """
        합의 서술 생성 / Generate consensus narrative.

        Args:
            debate_result: 토론 결과

        Returns:
            str: 합의 분석 서술 텍스트
        """
        consensus = debate_result.final_consensus
        achieved = consensus.get("achieved", False)
        consensus_score = consensus.get("final_consensus_score", 0.0)
        mean_score = consensus.get("mean_agent_score", 0.0)
        rounds_completed = consensus.get("rounds_completed", 0)

        if achieved:
            narrative = (
                f"에이전트들은 {rounds_completed}회의 토론 라운드를 거쳐 "
                f"합의에 도달했습니다 (합의도: {consensus_score:.2f}). "
                f"평균 평가 점수는 {mean_score:.2f}입니다."
            )
        else:
            narrative = (
                f"{rounds_completed}회의 토론 라운드 후에도 에이전트들 간 "
                f"완전한 합의에 도달하지 못했습니다 (합의도: {consensus_score:.2f}). "
                f"평균 평가 점수는 {mean_score:.2f}이며, "
                f"에이전트들 간 평가에 유의미한 차이가 있습니다."
            )

        # 합의 핵심 포인트
        key_points = consensus.get("key_points", [])
        concerns = consensus.get("concerns", [])

        if key_points:
            narrative += "\n\n합의된 핵심 포인트:"
            for kp in key_points[:5]:
                narrative += f"\n- {kp}"

        if concerns:
            narrative += "\n\n공통 우려 사항:"
            for concern in concerns[:5]:
                narrative += f"\n- {concern}"

        return narrative

    def _extract_key_strengths(
        self,
        debate_result: DebateResult,
    ) -> list[str]:
        """
        주요 강점 추출 / Extract key strengths from debate result.

        모든 에이전트의 핵심 포인트에서 긍정적 평가를 추출합니다.

        Args:
            debate_result: 토론 결과

        Returns:
            List[str]: 주요 강점 목록
        """
        strengths: list[str] = []

        if not debate_result.rounds:
            return strengths

        # 마지막 라운드에서 높은 점수(>=0.7)를 준 에이전트의 핵심 포인트 수집
        last_round = debate_result.rounds[-1]
        for response in last_round.responses:
            if response.score >= 0.7 and response.key_points:
                for kp in response.key_points:
                    if kp not in strengths:
                        strengths.append(kp)

        # 모든 에이전트가 공통으로 언급한 포인트 우선
        if not strengths:
            for response in last_round.responses:
                for kp in response.key_points:
                    if kp not in strengths:
                        strengths.append(kp)

        return strengths[:10]  # 상위 10개

    def _extract_key_weaknesses(
        self,
        debate_result: DebateResult,
    ) -> list[str]:
        """
        주요 약점 추출 / Extract key weaknesses from debate result.

        모든 에이전트의 우려 사항에서 주요 약점을 추출합니다.

        Args:
            debate_result: 토론 결과

        Returns:
            List[str]: 주요 약점 목록
        """
        weaknesses: list[str] = []

        if not debate_result.rounds:
            return weaknesses

        last_round = debate_result.rounds[-1]
        for response in last_round.responses:
            if response.concerns:
                for concern in response.concerns:
                    if concern not in weaknesses:
                        weaknesses.append(concern)

        return weaknesses[:10]  # 상위 10개

    def _generate_recommendations(
        self,
        debate_result: DebateResult,
        research_data: dict[str, Any] | None = None,
    ) -> list[str]:
        """
        권고 사항 생성 / Generate recommendations based on debate result.

        토론 결과를 기반으로 실행 가능한 권고 사항을 생성합니다.

        Args:
            debate_result: 토론 결과
            research_data: 논문 정보 (선택사항)

        Returns:
            List[str]: 권고 사항 목록
        """
        recommendations: list[str] = []
        verdict = debate_result.overall_verdict

        if verdict == "FAIL":
            recommendations.append(
                "이 연구의 결과를 참고할 때 극도의 주의가 필요합니다. "
                "독립적인 검증 없이 결과를 인용하지 마십시오."
            )
            recommendations.append(
                "우려 사항으로 지적된 방법론적 문제를 면밀히 검토하십시오."
            )
        elif verdict == "WARN":
            recommendations.append(
                "이 연구의 결과를 인용할 때 식별된 제한 사항을 함께 언급하십시오."
            )
            recommendations.append(
                "에이전트들이 지적한 우려 사항에 대한 추가 분석을 수행하십시오."
            )
        else:  # PASS
            recommendations.append(
                "이 연구는 전반적으로 양호한 품질로 평가됩니다. "
                "후속 연구에 참고할 수 있습니다."
            )

        # 소수 의견이 있으면 추가 권고
        if debate_result.dissenting_opinions:
            recommendations.append(
                "에이전트들 간 의견 불일치가 있습니다. "
                "소수 의견의 관점도 고려하십시오."
            )

        # 에이전트 질문에서 미해결 이슈 추출
        if debate_result.rounds:
            last_round = debate_result.rounds[-1]
            unresolved_questions: list[str] = []
            for response in last_round.responses:
                unresolved_questions.extend(response.questions)

            if unresolved_questions:
                recommendations.append(
                    "다음 미해결 질문에 대한 추가 조사를 권고합니다: "
                    + "; ".join(unresolved_questions[:3])
                )

        return recommendations

    def save_report(
        self,
        report: DebateReport,
        output_dir: str,
    ) -> str:
        """
        보고서 저장 / Save report as JSON and Markdown files.

        Args:
            report: 토론 보고서
            output_dir: 출력 디렉토리 경로

        Returns:
            str: 저장된 보고서 기본 경로 (확장자 제외)
        """
        os.makedirs(output_dir, exist_ok=True)

        timestamp_str = report.generated_at.strftime("%Y%m%d_%H%M%S")
        base_name = f"debate_report_{report.pmid}_{timestamp_str}"
        base_path = os.path.join(output_dir, base_name)

        # JSON 저장
        json_path = f"{base_path}.json"
        try:
            with open(json_path, "w", encoding="utf-8") as f:
                json.dump(
                    report.to_dict(),
                    f,
                    ensure_ascii=False,
                    indent=2,
                    default=str,
                )
            logger.info("JSON 보고서 저장 완료: %s", json_path)
        except Exception as e:
            logger.error("JSON 보고서 저장 실패: %s", str(e))

        # Markdown 저장
        md_path = f"{base_path}.md"
        try:
            with open(md_path, "w", encoding="utf-8") as f:
                f.write(report.to_markdown())
            logger.info("Markdown 보고서 저장 완료: %s", md_path)
        except Exception as e:
            logger.error("Markdown 보고서 저장 실패: %s", str(e))

        return base_path
