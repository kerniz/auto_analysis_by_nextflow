"""
Tests for agents/report.py — DebateReport and DebateReportGenerator
"""

import json
import os
from datetime import datetime

import pytest

from agents.base import AgentResponse, AgentRole, DebateRound
from agents.debate_manager import DebateResult
from agents.report import DebateReport, DebateReportGenerator

# ---------------------------------------------------------------------------
# Helpers / fixtures
# ---------------------------------------------------------------------------

def _make_response(
    agent_name="TestAgent",
    role=AgentRole.PHD_EXPERT,
    score=0.8,
    confidence=0.9,
    key_points=None,
    concerns=None,
    questions=None,
    assessment="Good paper",
    round_number=1,
):
    return AgentResponse(
        agent_role=role,
        agent_name=agent_name,
        assessment=assessment,
        score=score,
        confidence=confidence,
        key_points=key_points or ["Point A"],
        concerns=concerns or ["Concern X"],
        questions=questions or ["Question?"],
        rebuttal_to=None,
        round_number=round_number,
        timestamp=datetime(2025, 1, 1, 12, 0, 0),
        raw_llm_response="raw",
    )


def _make_debate_result(
    overall_verdict="PASS",
    overall_score=0.85,
    consensus_achieved=True,
    num_rounds=2,
    dissenting=None,
    responses_per_round=None,
):
    """Build a minimal DebateResult for testing."""
    rounds = []
    for rn in range(1, num_rounds + 1):
        if responses_per_round:
            resps = responses_per_round.get(rn, [])
        else:
            resps = [
                _make_response("PhD Expert", AgentRole.PHD_EXPERT, 0.85, round_number=rn),
                _make_response("Undergraduate", AgentRole.UNDERGRADUATE, 0.75, round_number=rn),
                _make_response("Layperson", AgentRole.LAYPERSON, 0.70, round_number=rn),
            ]
        rounds.append(DebateRound(round_number=rn, responses=resps, consensus_score=0.8))

    return DebateResult(
        rounds=rounds,
        final_consensus={
            "achieved": consensus_achieved,
            "final_consensus_score": 0.80,
            "mean_agent_score": 0.77,
            "rounds_completed": num_rounds,
            "key_points": ["Solid methodology"],
            "concerns": ["Small sample size"],
        },
        per_agent_scores={"PhD Expert": 0.85, "Undergraduate": 0.75, "Layperson": 0.70},
        overall_verdict=overall_verdict,
        overall_score=overall_score,
        dissenting_opinions=dissenting or [],
    )


@pytest.fixture
def generator():
    return DebateReportGenerator()


@pytest.fixture
def pass_result():
    return _make_debate_result("PASS", 0.85)


@pytest.fixture
def warn_result():
    return _make_debate_result("WARN", 0.65, consensus_achieved=False)


@pytest.fixture
def fail_result():
    return _make_debate_result(
        "FAIL", 0.35,
        consensus_achieved=False,
        dissenting=["PhD Expert disagreed"],
    )


# ---------------------------------------------------------------------------
# DebateReport tests
# ---------------------------------------------------------------------------

class TestDebateReport:
    def test_to_dict(self, pass_result):
        report = DebateReport(
            pmid="12345",
            debate_result=pass_result,
            executive_summary="All good",
            per_agent_summaries={"PhD Expert": "Excellent"},
            consensus_narrative="Agreed",
            key_strengths=["Strong design"],
            key_weaknesses=["Small n"],
            recommendations=["Replicate"],
        )
        d = report.to_dict()
        assert d["pmid"] == "12345"
        assert d["executive_summary"] == "All good"
        assert isinstance(d["debate_result"], dict)
        assert "generated_at" in d
        assert d["key_strengths"] == ["Strong design"]
        assert d["key_weaknesses"] == ["Small n"]
        assert d["recommendations"] == ["Replicate"]
        assert d["per_agent_summaries"] == {"PhD Expert": "Excellent"}
        assert d["consensus_narrative"] == "Agreed"

    def test_to_markdown_contains_sections(self, pass_result):
        report = DebateReport(
            pmid="99999",
            debate_result=pass_result,
            executive_summary="Summary text",
            per_agent_summaries={"PhD Expert": "Agent summary"},
            consensus_narrative="Consensus text",
            key_strengths=["Strength A"],
            key_weaknesses=["Weakness B"],
            recommendations=["Rec C"],
        )
        md = report.to_markdown()
        assert "# 연구 논문 토론 보고서" in md
        assert "PMID:" in md
        assert "99999" in md
        assert "Summary text" in md
        assert "PhD Expert" in md
        assert "Agent summary" in md
        assert "Consensus text" in md
        assert "Strength A" in md
        assert "Weakness B" in md
        assert "Rec C" in md
        assert "라운드" in md  # round details
        assert "0.85" in md or "0.80" in md  # scores appear

    def test_to_markdown_dissenting_opinions(self):
        result = _make_debate_result(
            "WARN", 0.6,
            dissenting=["Agent X: low score"],
        )
        report = DebateReport(
            pmid="11111",
            debate_result=result,
            executive_summary="Warn",
            per_agent_summaries={},
            consensus_narrative="Mixed",
            key_strengths=[],
            key_weaknesses=[],
            recommendations=[],
        )
        md = report.to_markdown()
        assert "소수 의견" in md
        assert "Agent X: low score" in md

    def test_to_markdown_no_strengths_weaknesses_recs(self):
        result = _make_debate_result("PASS", 0.9)
        report = DebateReport(
            pmid="00000",
            debate_result=result,
            executive_summary="Great",
            per_agent_summaries={},
            consensus_narrative="All agree",
            key_strengths=[],
            key_weaknesses=[],
            recommendations=[],
        )
        md = report.to_markdown()
        # These sections should not appear when empty
        assert "주요 강점" not in md
        assert "주요 약점" not in md
        assert "권고 사항" not in md

    def test_to_markdown_response_details(self):
        """Verify that key_points, concerns, questions appear in round details."""
        resp = _make_response(
            "Expert", score=0.9, key_points=["KP1"], concerns=["C1"], questions=["Q1"]
        )
        dr = DebateResult(
            rounds=[DebateRound(round_number=1, responses=[resp], consensus_score=0.9)],
            final_consensus={"achieved": True, "final_consensus_score": 0.9,
                             "mean_agent_score": 0.9, "rounds_completed": 1},
            per_agent_scores={"Expert": 0.9},
            overall_verdict="PASS",
            overall_score=0.9,
            dissenting_opinions=[],
        )
        report = DebateReport(
            pmid="22222",
            debate_result=dr,
            executive_summary="X",
            per_agent_summaries={},
            consensus_narrative="Y",
            key_strengths=[],
            key_weaknesses=[],
            recommendations=[],
        )
        md = report.to_markdown()
        assert "KP1" in md
        assert "C1" in md
        assert "Q1" in md

    def test_to_markdown_unknown_verdict(self):
        """Verdict not in emoji map falls back to raw string."""
        dr = _make_debate_result("UNKNOWN", 0.5)
        report = DebateReport(
            pmid="33333",
            debate_result=dr,
            executive_summary="x",
            per_agent_summaries={},
            consensus_narrative="y",
            key_strengths=[],
            key_weaknesses=[],
            recommendations=[],
        )
        md = report.to_markdown()
        assert "UNKNOWN" in md

    def test_to_markdown_consensus_score_none(self):
        """Round with consensus_score=None should still render."""
        resp = _make_response("A")
        dr = DebateResult(
            rounds=[DebateRound(round_number=1, responses=[resp], consensus_score=None)],
            final_consensus={"achieved": False, "final_consensus_score": 0.0,
                             "mean_agent_score": 0.5, "rounds_completed": 1},
            per_agent_scores={"A": 0.5},
            overall_verdict="WARN",
            overall_score=0.5,
            dissenting_opinions=[],
        )
        report = DebateReport(
            pmid="44444",
            debate_result=dr,
            executive_summary="w",
            per_agent_summaries={},
            consensus_narrative="z",
            key_strengths=[],
            key_weaknesses=[],
            recommendations=[],
        )
        md = report.to_markdown()
        assert "라운드 1" in md
        # consensus score line should NOT appear since it's None
        assert "합의도 (Consensus Score):" not in md


# ---------------------------------------------------------------------------
# DebateReportGenerator tests
# ---------------------------------------------------------------------------

class TestDebateReportGenerator:
    # --- generate_report ---

    def test_generate_report_pass(self, generator, pass_result):
        report = generator.generate_report("12345", pass_result)
        assert isinstance(report, DebateReport)
        assert report.pmid == "12345"
        assert "PASS" in report.executive_summary
        assert len(report.key_strengths) > 0 or len(report.key_weaknesses) > 0
        assert len(report.recommendations) > 0
        assert report.consensus_narrative

    def test_generate_report_warn(self, generator, warn_result):
        report = generator.generate_report("22222", warn_result)
        assert "WARN" in report.executive_summary
        assert "합의에 도달하지 못" in report.executive_summary

    def test_generate_report_fail(self, generator, fail_result):
        report = generator.generate_report("33333", fail_result)
        assert "FAIL" in report.executive_summary
        # Dissenting opinions mentioned
        assert "소수 의견" in report.executive_summary

    def test_generate_report_with_research_data(self, generator, pass_result):
        research_data = {"paper_info": {"title": "Test"}}
        report = generator.generate_report("44444", pass_result, research_data)
        assert report.pmid == "44444"

    def test_generate_report_no_rounds(self, generator):
        dr = DebateResult(
            rounds=[],
            final_consensus={"achieved": False},
            per_agent_scores={},
            overall_verdict="FAIL",
            overall_score=0.0,
            dissenting_opinions=[],
        )
        report = generator.generate_report("55555", dr)
        assert report.key_strengths == []
        assert report.key_weaknesses == []

    # --- _generate_executive_summary ---

    def test_executive_summary_pass_with_agent_scores(self, generator, pass_result):
        summary = generator._generate_executive_summary(pass_result)
        assert "PASS" in summary
        assert "PhD Expert" in summary

    def test_executive_summary_consensus_not_achieved(self, generator, warn_result):
        summary = generator._generate_executive_summary(warn_result)
        assert "합의에 도달하지 못" in summary

    def test_executive_summary_consensus_achieved(self, generator, pass_result):
        summary = generator._generate_executive_summary(pass_result)
        assert "합의에 도달" in summary

    # --- _generate_agent_summary ---

    def test_agent_summary_empty_responses(self, generator):
        result = generator._generate_agent_summary([])
        assert "응답이 없습니다" in result

    def test_agent_summary_with_response(self, generator):
        resp = _make_response(
            key_points=["KP"], concerns=["CON"], questions=["Q?"]
        )
        result = generator._generate_agent_summary([resp])
        assert "KP" in result
        assert "CON" in result
        assert "Q?" in result
        assert "0.80" in result  # score
        assert "0.90" in result  # confidence

    def test_agent_summary_no_optional_fields(self, generator):
        resp = AgentResponse(
            agent_role=AgentRole.PHD_EXPERT,
            agent_name="TestAgent",
            assessment="Good paper",
            score=0.8,
            confidence=0.9,
            key_points=[],
            concerns=[],
            questions=[],
            rebuttal_to=None,
            round_number=1,
            timestamp=datetime(2025, 1, 1, 12, 0, 0),
            raw_llm_response="raw",
        )
        result = generator._generate_agent_summary([resp])
        assert "핵심 포인트" not in result
        assert "우려 사항" not in result
        assert "질문" not in result

    # --- _generate_consensus_narrative ---

    def test_consensus_narrative_achieved(self, generator, pass_result):
        narrative = generator._generate_consensus_narrative(pass_result)
        assert "합의에 도달" in narrative
        assert "Solid methodology" in narrative  # key_point from fixture

    def test_consensus_narrative_not_achieved(self, generator, warn_result):
        narrative = generator._generate_consensus_narrative(warn_result)
        assert "합의에 도달하지 못" in narrative

    def test_consensus_narrative_with_concerns(self, generator, pass_result):
        narrative = generator._generate_consensus_narrative(pass_result)
        assert "Small sample size" in narrative  # concern from fixture

    # --- _extract_key_strengths ---

    def test_extract_strengths_high_score(self, generator, pass_result):
        strengths = generator._extract_key_strengths(pass_result)
        assert len(strengths) > 0

    def test_extract_strengths_all_low_score(self, generator):
        """When all scores < 0.7, fall back to collecting all key_points."""
        resp = _make_response(score=0.5, key_points=["Fallback point"])
        dr = _make_debate_result("WARN", 0.5)
        dr.rounds[-1].responses = [resp]
        strengths = generator._extract_key_strengths(dr)
        assert "Fallback point" in strengths

    def test_extract_strengths_no_rounds(self, generator):
        dr = DebateResult(
            rounds=[], final_consensus={}, per_agent_scores={},
            overall_verdict="FAIL", overall_score=0.0, dissenting_opinions=[],
        )
        assert generator._extract_key_strengths(dr) == []

    def test_extract_strengths_dedup(self, generator):
        """Duplicate key_points should be deduplicated."""
        r1 = _make_response("A", score=0.8, key_points=["Same point"])
        r2 = _make_response("B", score=0.8, key_points=["Same point"])
        dr = _make_debate_result("PASS", 0.85)
        dr.rounds[-1].responses = [r1, r2]
        strengths = generator._extract_key_strengths(dr)
        assert strengths.count("Same point") == 1

    def test_extract_strengths_max_10(self, generator):
        resps = [
            _make_response(f"Agent{i}", score=0.9, key_points=[f"P{i}"])
            for i in range(15)
        ]
        dr = _make_debate_result("PASS", 0.9)
        dr.rounds[-1].responses = resps
        strengths = generator._extract_key_strengths(dr)
        assert len(strengths) <= 10

    # --- _extract_key_weaknesses ---

    def test_extract_weaknesses(self, generator, pass_result):
        weaknesses = generator._extract_key_weaknesses(pass_result)
        assert len(weaknesses) > 0

    def test_extract_weaknesses_no_rounds(self, generator):
        dr = DebateResult(
            rounds=[], final_consensus={}, per_agent_scores={},
            overall_verdict="FAIL", overall_score=0.0, dissenting_opinions=[],
        )
        assert generator._extract_key_weaknesses(dr) == []

    def test_extract_weaknesses_dedup(self, generator):
        r1 = _make_response("A", concerns=["Same concern"])
        r2 = _make_response("B", concerns=["Same concern"])
        dr = _make_debate_result("WARN", 0.6)
        dr.rounds[-1].responses = [r1, r2]
        weaknesses = generator._extract_key_weaknesses(dr)
        assert weaknesses.count("Same concern") == 1

    def test_extract_weaknesses_max_10(self, generator):
        resps = [
            _make_response(f"Agent{i}", concerns=[f"C{i}"])
            for i in range(15)
        ]
        dr = _make_debate_result("FAIL", 0.3)
        dr.rounds[-1].responses = resps
        weaknesses = generator._extract_key_weaknesses(dr)
        assert len(weaknesses) <= 10

    # --- _generate_recommendations ---

    def test_recommendations_fail(self, generator, fail_result):
        recs = generator._generate_recommendations(fail_result)
        assert any("극도의 주의" in r for r in recs)
        assert any("방법론적 문제" in r for r in recs)

    def test_recommendations_warn(self, generator, warn_result):
        recs = generator._generate_recommendations(warn_result)
        assert any("제한 사항" in r for r in recs)

    def test_recommendations_pass(self, generator, pass_result):
        recs = generator._generate_recommendations(pass_result)
        assert any("양호한 품질" in r for r in recs)

    def test_recommendations_dissenting(self, generator, fail_result):
        recs = generator._generate_recommendations(fail_result)
        assert any("의견 불일치" in r for r in recs)

    def test_recommendations_unresolved_questions(self, generator):
        resp = _make_response(questions=["Unresolved Q1", "Unresolved Q2"])
        dr = _make_debate_result("PASS", 0.85)
        dr.rounds[-1].responses = [resp]
        recs = generator._generate_recommendations(dr)
        assert any("미해결 질문" in r for r in recs)
        assert any("Unresolved Q1" in r for r in recs)

    def test_recommendations_with_research_data(self, generator, pass_result):
        research_data = {"pipeline": "nf-core/rnaseq"}
        recs = generator._generate_recommendations(pass_result, research_data)
        assert len(recs) > 0  # should still generate recommendations

    # --- save_report ---

    def test_save_report(self, generator, pass_result, tmp_path):
        report = generator.generate_report("12345", pass_result)
        base_path = generator.save_report(report, str(tmp_path))

        assert os.path.exists(f"{base_path}.json")
        assert os.path.exists(f"{base_path}.md")

        # Validate JSON is parseable
        with open(f"{base_path}.json") as f:
            data = json.load(f)
        assert data["pmid"] == "12345"

        # Validate MD has content
        with open(f"{base_path}.md") as f:
            md = f.read()
        assert "12345" in md

    def test_save_report_creates_directory(self, generator, pass_result, tmp_path):
        nested = str(tmp_path / "sub" / "dir")
        report = generator.generate_report("99999", pass_result)
        base_path = generator.save_report(report, nested)
        assert os.path.exists(f"{base_path}.json")

    def test_save_report_filename_format(self, generator, pass_result, tmp_path):
        report = generator.generate_report("12345", pass_result)
        base_path = generator.save_report(report, str(tmp_path))
        base_name = os.path.basename(base_path)
        assert base_name.startswith("debate_report_12345_")
