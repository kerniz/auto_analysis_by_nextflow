"""
Tests for New Analysis Routes and Fusion Analysis
신규 분석 라우트 (variant, methylation, fusion) 테스트
"""

from analysis.orchestrator import (
    ANALYSIS_ROUTES,
    OUTPUT_TO_ARGS_MAP,
    AnalysisOrchestrator,
)


class TestNewAnalysisRoutes:

    def test_variant_route_exists(self):
        assert "variant" in ANALYSIS_ROUTES
        route = ANALYSIS_ROUTES["variant"]
        assert route["runner"] == "r"
        assert "script" in route
        assert "r_packages" in route

    def test_methylation_route_exists(self):
        assert "methylation" in ANALYSIS_ROUTES
        route = ANALYSIS_ROUTES["methylation"]
        assert route["runner"] == "r"
        assert "script" in route
        assert "r_packages" in route

    def test_fusion_route_exists(self):
        assert "fusion" in ANALYSIS_ROUTES
        route = ANALYSIS_ROUTES["fusion"]
        assert route["runner"] == "python"
        assert "script" in route
        assert "python_packages" in route
        assert "pandas" in route["python_packages"]

    def test_all_new_routes_have_descriptions(self):
        for name in ("variant", "methylation", "fusion"):
            assert "description" in ANALYSIS_ROUTES[name]


class TestNewOutputToArgsMap:

    def test_variant_mapping(self):
        assert "variant" in OUTPUT_TO_ARGS_MAP
        mapping = OUTPUT_TO_ARGS_MAP["variant"]
        assert "vcf_files" in mapping
        assert mapping["vcf_files"] == "--vcf_file"

    def test_methylation_mapping(self):
        assert "methylation" in OUTPUT_TO_ARGS_MAP
        mapping = OUTPUT_TO_ARGS_MAP["methylation"]
        assert "coverage_files" in mapping
        assert mapping["coverage_files"] == "--coverage_file"

    def test_fusion_mapping(self):
        assert "fusion" in OUTPUT_TO_ARGS_MAP
        mapping = OUTPUT_TO_ARGS_MAP["fusion"]
        assert "fusion_results" in mapping
        assert mapping["fusion_results"] == "--fusion_results"


class TestMapOutputsNewTypes:

    def test_map_outputs_variant(self):
        orch = AnalysisOrchestrator()
        args = orch._map_outputs_to_args("variant", {
            "vcf_files": ["/data/variants.vcf"],
            "annotation": ["/data/annotation.tsv"],
        })
        assert args["--vcf_file"] == "/data/variants.vcf"
        assert args["--annotation_file"] == "/data/annotation.tsv"

    def test_map_outputs_methylation(self):
        orch = AnalysisOrchestrator()
        args = orch._map_outputs_to_args("methylation", {
            "coverage_files": ["/data/coverage.bismark.cov"],
        })
        assert args["--coverage_file"] == "/data/coverage.bismark.cov"

    def test_map_outputs_fusion(self):
        orch = AnalysisOrchestrator()
        args = orch._map_outputs_to_args("fusion", {
            "fusion_results": ["/data/fusions.tsv"],
        })
        assert args["--fusion_results"] == "/data/fusions.tsv"


class TestFindKeyFilesNewTypes:

    def test_variant_key_files(self, tmp_path):
        orch = AnalysisOrchestrator()
        (tmp_path / "filtered_variants.csv").touch()
        (tmp_path / "variant_stats.csv").touch()
        (tmp_path / "summary.json").write_text('{"success": true}')

        found = orch._find_key_files("variant", tmp_path)
        assert "filtered_variants" in found
        assert "variant_stats" in found
        assert "summary" in found

    def test_methylation_key_files(self, tmp_path):
        orch = AnalysisOrchestrator()
        (tmp_path / "methylation_stats.csv").touch()
        (tmp_path / "summary.json").write_text('{"success": true}')

        found = orch._find_key_files("methylation", tmp_path)
        assert "methylation_stats" in found
        assert "summary" in found

    def test_fusion_key_files(self, tmp_path):
        orch = AnalysisOrchestrator()
        (tmp_path / "filtered_fusions.csv").touch()
        (tmp_path / "fusion_summary.csv").touch()
        (tmp_path / "summary.json").write_text('{"success": true}')

        found = orch._find_key_files("fusion", tmp_path)
        assert "filtered_fusions" in found
        assert "fusion_summary" in found
        assert "summary" in found

    def test_fusion_key_files_empty(self, tmp_path):
        orch = AnalysisOrchestrator()
        found = orch._find_key_files("fusion", tmp_path)
        assert found == {}


class TestFusionAnalysisHelpers:
    """Test helper functions from fusion_analysis.py module."""

    def test_parse_confidence(self):
        from analysis.python_scripts.fusion_analysis import parse_confidence
        assert parse_confidence("high") == 2
        assert parse_confidence("medium") == 1
        assert parse_confidence("low") == 0
        assert parse_confidence("unknown") == -1

    def test_classify_fusion_type_inter(self):
        from analysis.python_scripts.fusion_analysis import classify_fusion_type
        result = classify_fusion_type("chr1", "chr2", "GENE_A", "GENE_B")
        assert result == "interchromosomal"

    def test_classify_fusion_type_intra(self):
        from analysis.python_scripts.fusion_analysis import classify_fusion_type
        result = classify_fusion_type("chr1", "chr1", "GENE_A", "GENE_B")
        assert result == "intrachromosomal"
