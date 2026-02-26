"""
Tests for Enrichment Analysis
농축 분석 테스트
"""

import pytest
from enrichment import GSEAAnalyzer, DEGAnalyzer, PathwayAnalyzer, NoveltyScorer


class TestGSEAAnalyzer:
    def test_init_default(self):
        analyzer = GSEAAnalyzer()
        assert analyzer.gene_set_db == "KEGG_2021_Human"
        assert analyzer.organism == "human"

    def test_available_gene_sets(self):
        assert len(GSEAAnalyzer.AVAILABLE_GENE_SETS) >= 5
        assert "KEGG_2021_Human" in GSEAAnalyzer.AVAILABLE_GENE_SETS

    @pytest.mark.asyncio
    async def test_run_enrichr_empty_list(self):
        analyzer = GSEAAnalyzer()
        result = await analyzer.run_enrichr([])
        assert result.get("error") is not None or result.get("gene_count") == 0

    def test_interpret_results_empty(self):
        analyzer = GSEAAnalyzer()
        result = analyzer.interpret_results({"significant_terms": []})
        assert result["top_pathway"] is None
        assert "category_counts" in result


class TestDEGAnalyzer:
    def test_init(self):
        analyzer = DEGAnalyzer()
        assert analyzer.fc_threshold == 1.5
        assert analyzer.padj_threshold == 0.05

    def test_custom_thresholds(self):
        analyzer = DEGAnalyzer(fc_threshold=2.0, padj_threshold=0.01)
        assert analyzer.fc_threshold == 2.0
        assert analyzer.padj_threshold == 0.01

    def test_get_top_genes(self):
        analyzer = DEGAnalyzer()
        deg_results = {
            "top_upregulated": [
                {"gene": "TP53", "log2fc": 3.5, "padj": 0.001},
                {"gene": "MYC", "log2fc": 2.1, "padj": 0.01},
            ],
            "top_downregulated": [
                {"gene": "BRCA1", "log2fc": -4.0, "padj": 0.001},
            ],
        }
        top = analyzer.get_top_genes(deg_results, n=2)
        assert len(top) == 2
        # 절대값 기준 정렬
        assert abs(top[0]["log2fc"]) >= abs(top[1]["log2fc"])

    def test_classify_genes(self):
        analyzer = DEGAnalyzer()
        deg_results = {
            "top_upregulated": [
                {"gene": "TP53", "log2fc": 3.5, "padj": 0.001},
            ],
            "top_downregulated": [
                {"gene": "BRCA1", "log2fc": -4.0, "padj": 0.001},
            ],
        }
        classified = analyzer.classify_genes(deg_results)
        assert "TP53" in classified["upregulated"]
        assert "BRCA1" in classified["downregulated"]

    def test_get_gene_symbols(self):
        analyzer = DEGAnalyzer()
        deg_results = {
            "top_upregulated": [{"gene": "A"}, {"gene": "B"}],
            "top_downregulated": [{"gene": "C"}],
        }
        symbols = analyzer.get_gene_symbols(deg_results)
        assert set(symbols) == {"A", "B", "C"}

    @pytest.mark.asyncio
    async def test_analyze_missing_file(self, tmp_path):
        analyzer = DEGAnalyzer()
        result = await analyzer.analyze_deseq2_output(tmp_path / "nonexistent.csv")
        assert "error" in result


class TestPathwayAnalyzer:
    def test_init(self):
        analyzer = PathwayAnalyzer()
        assert analyzer.annotation_client is None

    def test_identify_key_pathways_empty(self):
        analyzer = PathwayAnalyzer()
        result = analyzer.identify_key_pathways({}, top_n=5)
        assert result == []

    @pytest.mark.asyncio
    async def test_analyze_empty_gene_list(self):
        analyzer = PathwayAnalyzer()
        result = await analyzer.analyze_pathways([])
        assert "error" in result


class TestNoveltyScorer:
    def test_init(self):
        scorer = NoveltyScorer()
        assert scorer.ss_client is None
        assert scorer.epmc_client is None

    @pytest.mark.asyncio
    async def test_score_novelty_basic(self):
        scorer = NoveltyScorer()
        result = await scorer.score_novelty(
            paper_metadata={
                "title": "Novel spatial transcriptomics approach",
                "abstract": "We used spatial transcriptomics and nanopore sequencing...",
            },
            enrichment_results={},
            aggregated_data={},
        )
        assert "score" in result
        assert 0.0 <= result["score"] <= 1.0
        assert "rating" in result
        assert "factors" in result
        assert "explanation" in result

    @pytest.mark.asyncio
    async def test_methodology_novelty_novel(self):
        scorer = NoveltyScorer()
        score = await scorer._assess_methodology_novelty({
            "title": "Spatial transcriptomics with nanopore",
            "abstract": "spatial transcriptomics long-read sequencing nanopore",
        })
        assert score >= 0.7

    @pytest.mark.asyncio
    async def test_methodology_novelty_standard(self):
        scorer = NoveltyScorer()
        score = await scorer._assess_methodology_novelty({
            "title": "RNA-seq analysis",
            "abstract": "rna-seq deseq2 gene expression analysis",
        })
        assert score <= 0.6
