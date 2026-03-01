"""
Tests for core/report_generator.py
"""

import pytest

from core.report_generator import ReportGenerator


@pytest.fixture
def sample_report():
    return {
        "pmid": "12345",
        "status": "completed",
        "duration_seconds": 500.0,
        "error": "",
        "pubmed_metadata": {
            "pmid": "12345",
            "title": "Test Paper Title",
            "authors": ["Author A", "Author B", "Author C"],
            "journal": "Nature",
            "pub_date": "2024 Jan",
            "doi": "doi: 10.1234/test",
            "abstract": "This is a test abstract about RNA-seq.",
            "keywords": ["rna-seq", "single-cell"],
            "sra_links": [],
            "geo_links": [],
            "article_ids": {"pubmed": "12345", "doi": "10.1234/test"},
        },
        "sra_results": {
            "pmid": "12345",
            "public_sra_ids": ["SRR001", "SRR002"],
            "controlled_sra_ids": [],
            "downloadable": True,
            "total_size_gb": 5.0,
        },
        "sequencing_type": "scrna_seq",
        "sequencing_confidence": 0.95,
        "llm_rating": "PASS",
        "llm_consensus": {"quality": "high", "novelty": "moderate"},
        "aggregated_sources": [
            "ss_citations", "epmc_article", "epmc_references"
        ],
        "enrichment_summary": {
            "novelty_score": 0.75,
            "top_genes_count": 50,
            "top_pathways_count": 10,
        },
        "debate_verdict": "WARN",
        "debate_score": 0.7,
        "debate_report": {
            "overall_verdict": "WARN",
            "overall_score": 0.7,
            "rounds": [
                {
                    "round_number": 1,
                    "consensus_score": 0.6,
                    "responses": [
                        {
                            "agent_name": "PhD Expert",
                            "score": 0.8,
                            "confidence": 0.9,
                            "assessment": "Good quality research.",
                            "key_points": ["Novel approach"],
                            "concerns": ["Small sample"],
                            "questions": [],
                        },
                        {
                            "agent_name": "Undergraduate",
                            "score": 0.65,
                            "confidence": 0.7,
                            "assessment": "Methodology is sound.",
                            "key_points": ["Proper controls"],
                            "concerns": [],
                            "questions": ["What about batch effects?"],
                        },
                    ],
                }
            ],
            "final_consensus": {
                "achieved": False,
                "summary": "No consensus (0.60, mean: 0.72, rounds: 1)",
            },
            "per_agent_scores": {
                "PhD Expert": 0.8,
                "Undergraduate": 0.65,
            },
            "dissenting_opinions": [],
        },
        "fetchngs": None,
        "pipeline_execution": None,
        "downstream_analysis": None,
    }


@pytest.fixture
def minimal_report():
    return {
        "pmid": "99999",
        "status": "completed",
        "duration_seconds": 10.0,
        "error": "",
        "pubmed_metadata": {},
        "sra_results": {},
        "sequencing_type": "unknown",
        "sequencing_confidence": 0.0,
        "llm_rating": "FAIL",
        "llm_consensus": {},
        "aggregated_sources": [],
        "enrichment_summary": {},
        "debate_verdict": "FAIL",
        "debate_score": 0.2,
    }


class TestGenerate:
    def test_creates_html_file(self, sample_report, tmp_path):
        gen = ReportGenerator()
        output = tmp_path / "report_12345.html"
        result = gen.generate(sample_report, output)

        assert result == output
        assert output.exists()
        content = output.read_text()
        assert "<!DOCTYPE html>" in content
        assert "PMID" in content

    def test_html_contains_paper_info(self, sample_report, tmp_path):
        gen = ReportGenerator()
        output = tmp_path / "report.html"
        gen.generate(sample_report, output)

        content = output.read_text()
        assert "Test Paper Title" in content
        assert "Nature" in content
        assert "Author A" in content
        assert "rna-seq" in content

    def test_html_contains_scores(self, sample_report, tmp_path):
        gen = ReportGenerator()
        output = tmp_path / "report.html"
        gen.generate(sample_report, output)

        content = output.read_text()
        assert "PASS" in content
        assert "WARN" in content
        assert "0.70" in content
        assert "scrna_seq" in content

    def test_html_contains_debate(self, sample_report, tmp_path):
        gen = ReportGenerator()
        output = tmp_path / "report.html"
        gen.generate(sample_report, output)

        content = output.read_text()
        assert "PhD Expert" in content
        assert "Undergraduate" in content
        assert "Round 1" in content
        assert "Good quality research" in content

    def test_html_contains_sra_info(self, sample_report, tmp_path):
        gen = ReportGenerator()
        output = tmp_path / "report.html"
        gen.generate(sample_report, output)

        content = output.read_text()
        assert "SRR001" in content
        assert "Downloadable" in content

    def test_html_contains_enrichment(self, sample_report, tmp_path):
        gen = ReportGenerator()
        output = tmp_path / "report.html"
        gen.generate(sample_report, output)

        content = output.read_text()
        assert "Novelty Score" in content
        assert "0.750" in content

    def test_html_contains_data_sources(self, sample_report, tmp_path):
        gen = ReportGenerator()
        output = tmp_path / "report.html"
        gen.generate(sample_report, output)

        content = output.read_text()
        assert "Semantic Scholar Citations" in content
        assert "EuropePMC" in content

    def test_creates_parent_dirs(self, sample_report, tmp_path):
        gen = ReportGenerator()
        output = tmp_path / "subdir" / "nested" / "report.html"
        gen.generate(sample_report, output)
        assert output.exists()

    def test_minimal_report(self, minimal_report, tmp_path):
        gen = ReportGenerator()
        output = tmp_path / "report.html"
        gen.generate(minimal_report, output)

        content = output.read_text()
        assert "<!DOCTYPE html>" in content
        assert "FAIL" in content

    def test_html_escapes_xss(self, tmp_path):
        gen = ReportGenerator()
        report = {
            "pmid": "12345",
            "status": "completed",
            "duration_seconds": 0,
            "pubmed_metadata": {
                "title": '<script>alert("xss")</script>',
                "authors": [],
                "journal": "",
                "pub_date": "",
                "doi": "",
                "abstract": "",
                "keywords": [],
            },
            "sra_results": {},
            "sequencing_type": "unknown",
            "sequencing_confidence": 0.0,
            "llm_rating": "UNKNOWN",
            "llm_consensus": {},
            "aggregated_sources": [],
            "enrichment_summary": {},
            "debate_verdict": "UNDETERMINED",
            "debate_score": 0.0,
        }
        output = tmp_path / "report.html"
        gen.generate(report, output)
        content = output.read_text()
        assert "<script>" not in content
        assert "&lt;script&gt;" in content


class TestGenerateFromJson:
    def test_from_json_file(self, sample_report, tmp_path):
        import json

        json_path = tmp_path / "final_report_12345.json"
        json_path.write_text(json.dumps(sample_report))

        gen = ReportGenerator()
        result = gen.generate_from_json(json_path)

        assert result == tmp_path / "report_12345.html"
        assert result.exists()

    def test_custom_output_dir(self, sample_report, tmp_path):
        import json

        json_path = tmp_path / "final_report_12345.json"
        json_path.write_text(json.dumps(sample_report))

        out_dir = tmp_path / "output"
        out_dir.mkdir()

        gen = ReportGenerator()
        result = gen.generate_from_json(json_path, out_dir)

        assert result == out_dir / "report_12345.html"
        assert result.exists()


class TestGenerateSummary:
    def test_summary_report(self, sample_report, minimal_report, tmp_path):
        gen = ReportGenerator()
        output = tmp_path / "summary.html"
        result = gen.generate_summary(
            [sample_report, minimal_report], output
        )

        assert result == output
        assert output.exists()
        content = output.read_text()
        assert "12345" in content
        assert "99999" in content
        assert "Total PMIDs: 2" in content

    def test_summary_links_to_reports(self, sample_report, tmp_path):
        gen = ReportGenerator()
        output = tmp_path / "summary.html"
        gen.generate_summary([sample_report], output)

        content = output.read_text()
        assert "report_12345.html" in content


class TestBadgeClass:
    def test_pass(self):
        assert ReportGenerator._badge_class("PASS") == "pass"
        assert ReportGenerator._badge_class("completed") == "pass"

    def test_warn(self):
        assert ReportGenerator._badge_class("WARN") == "warn"

    def test_fail(self):
        assert ReportGenerator._badge_class("FAIL") == "fail"
        assert ReportGenerator._badge_class("FAILED") == "fail"

    def test_neutral(self):
        assert ReportGenerator._badge_class("UNKNOWN") == "neutral"
        assert ReportGenerator._badge_class("other") == "neutral"


class TestScoreBar:
    def test_high_score(self):
        bar = ReportGenerator._score_bar(0.8)
        assert "80%" in bar
        assert "#2ecc71" in bar  # green

    def test_mid_score(self):
        bar = ReportGenerator._score_bar(0.6)
        assert "60%" in bar
        assert "#f39c12" in bar  # orange

    def test_low_score(self):
        bar = ReportGenerator._score_bar(0.3)
        assert "30%" in bar
        assert "#e74c3c" in bar  # red

    def test_clamp(self):
        bar = ReportGenerator._score_bar(1.5)
        assert "100%" in bar
        bar = ReportGenerator._score_bar(-0.5)
        assert "0%" in bar


class TestPipelineSection:
    def test_no_pipeline(self, tmp_path):
        gen = ReportGenerator()
        data = {
            "pmid": "1",
            "status": "completed",
            "duration_seconds": 0,
            "pubmed_metadata": {},
            "sra_results": {},
            "sequencing_type": "unknown",
            "sequencing_confidence": 0,
            "llm_rating": "UNKNOWN",
            "llm_consensus": {},
            "aggregated_sources": [],
            "enrichment_summary": {},
            "debate_verdict": "UNDETERMINED",
            "debate_score": 0,
            "fetchngs": None,
            "pipeline_execution": None,
            "downstream_analysis": None,
        }
        output = tmp_path / "report.html"
        gen.generate(data, output)
        content = output.read_text()
        assert "--execute-pipeline" in content

    def test_with_pipeline(self, tmp_path):
        gen = ReportGenerator()
        data = {
            "pmid": "1",
            "status": "completed",
            "duration_seconds": 0,
            "pubmed_metadata": {},
            "sra_results": {},
            "sequencing_type": "unknown",
            "sequencing_confidence": 0,
            "llm_rating": "UNKNOWN",
            "llm_consensus": {},
            "aggregated_sources": [],
            "enrichment_summary": {},
            "debate_verdict": "UNDETERMINED",
            "debate_score": 0,
            "fetchngs": {"status": "completed"},
            "pipeline_execution": {
                "pipeline_name": "nf-core/rnaseq",
                "status": "completed",
            },
            "downstream_analysis": {"status": "completed"},
        }
        output = tmp_path / "report.html"
        gen.generate(data, output)
        content = output.read_text()
        assert "nf-core/rnaseq" in content
