"""
Tests for Pipeline Integration
파이프라인 통합 테스트
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from pathlib import Path
from datetime import datetime

from async_pipeline import (
    AsyncPipeline, PipelineConfig, PipelineStatus, PMIDResult,
)


class TestPipelineConfig:
    def test_defaults(self):
        config = PipelineConfig(pmids=["12345"])
        assert config.pmids == ["12345"]
        assert config.max_concurrent == 5
        assert config.enable_resume is True
        assert config.enable_data_aggregation is True
        assert config.enable_enrichment is True
        assert config.enable_debate is True
        assert config.debate_rounds == 3

    def test_from_dict(self):
        data = {
            "pmids": ["40315330", "32416070"],
            "results_dir": "/tmp/test_results",
            "max_concurrent": 3,
            "enable_debate": False,
            "debate_rounds": 2,
        }
        config = PipelineConfig.from_dict(data)
        assert config.pmids == ["40315330", "32416070"]
        assert config.max_concurrent == 3
        assert config.enable_debate is False
        assert config.debate_rounds == 2

    def test_from_dict_defaults(self):
        config = PipelineConfig.from_dict({})
        assert config.pmids == []
        assert config.max_concurrent == 5


class TestPipelineStatus:
    def test_statuses(self):
        assert PipelineStatus.PENDING.value == "pending"
        assert PipelineStatus.RUNNING.value == "running"
        assert PipelineStatus.COMPLETED.value == "completed"
        assert PipelineStatus.FAILED.value == "failed"
        assert PipelineStatus.PARTIAL.value == "partial"


class TestPMIDResult:
    def test_create(self):
        result = PMIDResult(pmid="12345", status=PipelineStatus.PENDING)
        assert result.pmid == "12345"
        assert result.status == PipelineStatus.PENDING
        assert result.error == ""

    def test_duration(self):
        result = PMIDResult(
            pmid="12345",
            status=PipelineStatus.COMPLETED,
            start_time=datetime(2025, 1, 1, 0, 0, 0),
            end_time=datetime(2025, 1, 1, 0, 0, 10),
        )
        assert result.duration_seconds == 10.0

    def test_duration_no_times(self):
        result = PMIDResult(pmid="12345", status=PipelineStatus.PENDING)
        assert result.duration_seconds == 0.0

    def test_to_dict(self):
        result = PMIDResult(
            pmid="40315330",
            status=PipelineStatus.COMPLETED,
            pubmed_metadata={"title": "Test"},
            sequencing_result={"sequencing_type": "scrna_seq", "confidence": 0.9},
            llm_analysis={"consistency_rating": "PASS"},
            debate_report={"overall_verdict": "PASS", "overall_score": 0.85},
            start_time=datetime(2025, 1, 1, 0, 0, 0),
            end_time=datetime(2025, 1, 1, 0, 0, 5),
        )
        d = result.to_dict()
        assert d["pmid"] == "40315330"
        assert d["status"] == "completed"
        assert d["sequencing_type"] == "scrna_seq"
        assert d["llm_rating"] == "PASS"
        assert d["debate_verdict"] == "PASS"
        assert d["duration_seconds"] == 5.0


class TestAsyncPipeline:
    def test_init(self, tmp_path):
        config = PipelineConfig(
            pmids=["12345"],
            results_dir=tmp_path / "results",
        )
        pipeline = AsyncPipeline(config)
        assert pipeline.config == config
        assert pipeline.results == {}
        assert (tmp_path / "results").exists()

    def test_build_analysis_prompt(self, tmp_path):
        config = PipelineConfig(pmids=["12345"], results_dir=tmp_path)
        pipeline = AsyncPipeline(config)
        prompt = pipeline._build_analysis_prompt(
            {"title": "Test Paper", "abstract": "Test abstract"},
            {"sequencing_type": "scrna_seq"},
        )
        assert "Test Paper" in prompt
        assert "scrna_seq" in prompt
        assert "consistency_score" in prompt

    def test_parse_llm_response_valid(self, tmp_path):
        config = PipelineConfig(pmids=["12345"], results_dir=tmp_path)
        pipeline = AsyncPipeline(config)
        result = pipeline._parse_llm_response(
            '{"consistency_rating": "PASS", "consistency_score": 0.9}'
        )
        assert result["consistency_rating"] == "PASS"
        assert result["consistency_score"] == 0.9

    def test_parse_llm_response_invalid(self, tmp_path):
        config = PipelineConfig(pmids=["12345"], results_dir=tmp_path)
        pipeline = AsyncPipeline(config)
        result = pipeline._parse_llm_response("not json at all")
        assert result["consistency_rating"] == "WARN"

    def test_parse_llm_response_embedded_json(self, tmp_path):
        config = PipelineConfig(pmids=["12345"], results_dir=tmp_path)
        pipeline = AsyncPipeline(config)
        result = pipeline._parse_llm_response(
            'Here is the result: {"consistency_rating": "PASS"} and more text'
        )
        assert result["consistency_rating"] == "PASS"

    def test_merge_consensus(self, tmp_path):
        config = PipelineConfig(pmids=["12345"], results_dir=tmp_path)
        pipeline = AsyncPipeline(config)
        results = [
            {
                "consistency_score": 0.8,
                "consistency_rating": "PASS",
                "health_score": 1.0,
                "backend": "ollama",
                "technical_assessment": "Good",
                "recommendations": ["R1"],
            },
            {
                "consistency_score": 0.6,
                "consistency_rating": "WARN",
                "health_score": 0.5,
                "backend": "openai",
                "technical_assessment": "OK",
                "recommendations": ["R2"],
            },
        ]
        merged = pipeline._merge_consensus(results)
        assert "consistency_score" in merged
        assert "consistency_rating" in merged
        assert merged["consensus"]["num_backends"] == 2
        assert "ollama" in merged["consensus"]["backends"]

    def test_merge_consensus_single(self, tmp_path):
        config = PipelineConfig(pmids=["12345"], results_dir=tmp_path)
        pipeline = AsyncPipeline(config)
        results = [
            {
                "consistency_score": 0.9,
                "consistency_rating": "PASS",
                "health_score": 1.0,
                "backend": "ollama",
            },
        ]
        merged = pipeline._merge_consensus(results)
        assert merged["consensus"]["num_backends"] == 1

    def test_extract_genes_from_metadata(self, tmp_path):
        config = PipelineConfig(pmids=["12345"], results_dir=tmp_path)
        pipeline = AsyncPipeline(config)
        result = PMIDResult(
            pmid="12345",
            status=PipelineStatus.RUNNING,
            pubmed_metadata={"keywords": ["TP53", "gene expression", "BRCA1"]},
            aggregated_data={
                "europe_pmc_data": {
                    "text_mined_terms": [
                        {"type": "Gene", "name": "MYC"},
                        {"type": "Disease", "name": "Cancer"},
                    ]
                }
            },
        )
        genes = pipeline._extract_genes_from_metadata(result)
        assert "MYC" in genes
        assert "TP53" in genes
        assert "BRCA1" in genes
        assert "Cancer" not in genes

    def test_extract_genes_empty(self, tmp_path):
        config = PipelineConfig(pmids=["12345"], results_dir=tmp_path)
        pipeline = AsyncPipeline(config)
        result = PMIDResult(
            pmid="12345",
            status=PipelineStatus.RUNNING,
            pubmed_metadata={},
            aggregated_data={},
        )
        genes = pipeline._extract_genes_from_metadata(result)
        assert genes == []


class TestPipelineCheckpoint:
    def test_is_step_done_no_progress(self, tmp_path):
        config = PipelineConfig(
            pmids=["12345"],
            results_dir=tmp_path,
            enable_resume=False,
        )
        pipeline = AsyncPipeline(config)
        assert pipeline._is_step_done("12345", "pubmed_done") is False

    def test_mark_step_done_no_progress(self, tmp_path):
        config = PipelineConfig(
            pmids=["12345"],
            results_dir=tmp_path,
            enable_resume=False,
        )
        pipeline = AsyncPipeline(config)
        # Should not raise
        pipeline._mark_step_done("12345", "pubmed_done")
