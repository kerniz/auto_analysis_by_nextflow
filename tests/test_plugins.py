"""
Tests for Sequencing Type Plugins
시퀀싱 타입 감지 플러그인 테스트
"""

from plugins import (
    AtacSeqPlugin,
    BulkRnaSeqPlugin,
    ChIPSeqPlugin,
    PluginRegistry,
    ScRnaSeqPlugin,
    register_default_plugins,
)


class TestScRnaSeqPlugin:

    def test_plugin_properties(self):
        plugin = ScRnaSeqPlugin()
        assert plugin.name == "scrna_seq"
        assert plugin.display_name == "scRNA-seq"
        assert len(plugin.keywords) > 0
        assert plugin.priority == 10

    def test_detect_scrna_paper(self, sample_pubmed_metadata, sample_sra_metadata):
        plugin = ScRnaSeqPlugin()
        result = plugin.detect(sample_pubmed_metadata, sample_sra_metadata)

        assert result.sequencing_type == "scrna_seq"
        assert result.confidence > 0.5
        assert len(result.evidence) > 0
        assert result.sra_metadata_match is True

    def test_detect_non_scrna_paper(self, sample_bulk_pubmed_metadata, sample_bulk_sra_metadata):
        plugin = ScRnaSeqPlugin()
        result = plugin.detect(sample_bulk_pubmed_metadata, sample_bulk_sra_metadata)

        assert result.sequencing_type == "scrna_seq"
        assert result.confidence < 0.3

    def test_keywords_matching(self):
        plugin = ScRnaSeqPlugin()

        high_match_text = "We used 10x Genomics single-cell RNA sequencing with UMI"
        score, evidence = plugin.calculate_score(high_match_text.lower(), {})
        assert score > 0.5
        assert len(evidence) > 0

        low_match_text = "We performed whole genome sequencing"
        score, evidence = plugin.calculate_score(low_match_text.lower(), {})
        assert score < 0.2


class TestBulkRnaSeqPlugin:

    def test_plugin_properties(self):
        plugin = BulkRnaSeqPlugin()
        assert plugin.name == "bulk_rna_seq"
        assert plugin.display_name == "Bulk RNA-seq"
        assert len(plugin.keywords) > 0

    def test_detect_bulk_paper(self, sample_bulk_pubmed_metadata, sample_bulk_sra_metadata):
        plugin = BulkRnaSeqPlugin()
        result = plugin.detect(sample_bulk_pubmed_metadata, sample_bulk_sra_metadata)

        assert result.sequencing_type == "bulk_rna_seq"
        assert result.confidence > 0.3
        assert result.sra_metadata_match is True

    def test_exclude_scrna_keywords(self):
        plugin = BulkRnaSeqPlugin()

        mixed_text = "We performed RNA-seq using single-cell 10x Genomics"
        metadata = {"pmid": "test", "title": mixed_text, "abstract": "", "keywords": []}
        sra = {}

        result = plugin.detect(metadata, sra)
        assert result.confidence < 0.5


class TestAtacSeqPlugin:

    def test_plugin_properties(self):
        plugin = AtacSeqPlugin()
        assert plugin.name == "atac_seq"
        assert plugin.display_name == "ATAC-seq"
        assert plugin.pipeline.nf_core_name == "nf-core/atacseq"

    def test_detect_atac_paper(self):
        plugin = AtacSeqPlugin()

        metadata = {
            "pmid": "test",
            "title": "ATAC-seq reveals chromatin accessibility",
            "abstract": "We used ATAC-seq to profile open chromatin regions",
            "keywords": ["atac-seq", "chromatin"]
        }

        result = plugin.detect(metadata, {})
        assert result.sequencing_type == "atac_seq"
        assert result.confidence > 0.5


class TestChIPSeqPlugin:

    def test_plugin_properties(self):
        plugin = ChIPSeqPlugin()
        assert plugin.name == "chip_seq"
        assert plugin.display_name == "ChIP-seq"
        assert plugin.pipeline.nf_core_name == "nf-core/chipseq"

    def test_detect_chipseq_paper(self):
        plugin = ChIPSeqPlugin()

        metadata = {
            "pmid": "test",
            "title": "ChIP-seq analysis of H3K4me3 histone mark",
            "abstract": "Chromatin immunoprecipitation sequencing was performed",
            "keywords": ["chip-seq", "histone"]
        }

        result = plugin.detect(metadata, {})
        assert result.sequencing_type == "chip_seq"
        assert result.confidence > 0.5


class TestPluginRegistry:

    def test_singleton(self):
        registry1 = PluginRegistry()
        registry2 = PluginRegistry()
        assert registry1 is registry2

    def test_register_plugin(self):
        registry = PluginRegistry()
        registry.clear()

        plugin = ScRnaSeqPlugin()
        registry.register(plugin)

        assert "scrna_seq" in registry.list_plugins()
        assert registry.get("scrna_seq") is plugin

    def test_unregister_plugin(self):
        registry = PluginRegistry()
        registry.clear()

        registry.register(ScRnaSeqPlugin())
        assert "scrna_seq" in registry.list_plugins()

        result = registry.unregister("scrna_seq")
        assert result is True
        assert "scrna_seq" not in registry.list_plugins()

    def test_detect_best_match(self, sample_pubmed_metadata, sample_sra_metadata):
        registry = PluginRegistry()
        registry.clear()
        registry.register(ScRnaSeqPlugin())
        registry.register(BulkRnaSeqPlugin())

        result, name = registry.detect(sample_pubmed_metadata, sample_sra_metadata)

        assert name == "scrna_seq"
        assert result.confidence > 0.3

    def test_register_default_plugins(self):
        registry = register_default_plugins()
        registry.clear()
        registry = register_default_plugins()

        plugins = registry.list_plugins()
        assert "scrna_seq" in plugins
        assert "bulk_rna_seq" in plugins
        assert "atac_seq" in plugins
        assert "chip_seq" in plugins


class TestUnsupportedModalitySafeBlock:
    """미지원 modality(spatial/scATAC/Multiome)가 기존 파이프라인으로
    오분류·실행되지 않고 unknown(safe block)으로 끝나는지 검증 (RFC 0001 F1/F3/F9)."""

    def _registry_detect(self, title, abstract):
        registry = register_default_plugins()
        registry.clear()
        registry = register_default_plugins()
        metadata = {"pmid": "test", "title": title, "abstract": abstract, "keywords": []}
        return registry.detect(metadata, {})

    def test_visium_not_routed_to_scrnaseq(self):
        result, name = self._registry_detect(
            "Visium HD spatial gene expression of human colorectal cancer",
            "We performed 10x Genomics Visium HD spatial transcriptomics "
            "to map single-cell scale gene expression in tissue sections",
        )
        assert name == "unknown"
        assert result.recommended_pipeline is None

    def test_xenium_not_routed_to_scrnaseq(self):
        result, name = self._registry_detect(
            "Xenium in situ analysis of breast cancer",
            "Subcellular spatial transcriptomics using the 10x Xenium platform "
            "revealed single cell neighborhoods",
        )
        assert name == "unknown"

    def test_stereo_seq_not_routed_to_scrnaseq(self):
        result, name = self._registry_detect(
            "Stereo-seq spatial atlas of mouse embryo",
            "Stereo-seq spatially resolved transcriptomics captured "
            "single-cell resolution gene expression",
        )
        assert name == "unknown"

    def test_multiome_not_routed_to_bulk_atacseq(self):
        result, name = self._registry_detect(
            "10x Multiome profiling of chromatin accessibility and gene expression",
            "Single-cell multiome ATAC and RNA sequencing revealed "
            "chromatin accessibility in open chromatin regions",
        )
        assert name == "unknown"

    def test_scatac_not_routed_to_bulk_atacseq(self):
        result, name = self._registry_detect(
            "scATAC-seq of immune cells",
            "Single-cell ATAC-seq chromatin accessibility profiling",
        )
        assert name == "unknown"

    def test_single_nucleus_atac_not_routed_to_bulk_atacseq(self):
        result, name = self._registry_detect(
            "Single-nucleus ATAC-seq of human cortex",
            "Single-nucleus ATAC-seq revealed chromatin accessibility "
            "in open chromatin regions of neuronal subtypes",
        )
        assert name == "unknown"

    def test_spatial_gene_expression_without_platform_name(self):
        result, name = self._registry_detect(
            "Spatial gene expression profiling of tumor sections",
            "We used 10x Genomics spatial gene expression to profile "
            "single-cell resolution transcriptomes in tissue",
        )
        assert name == "unknown"

    def test_seqfish_not_routed_to_scrnaseq(self):
        result, name = self._registry_detect(
            "seqFISH imaging of gene expression in mouse brain",
            "We applied seqFISH to measure single-cell gene expression "
            "in intact tissue",
        )
        assert name == "unknown"

    def test_starmap_not_routed_to_scrnaseq(self):
        result, name = self._registry_detect(
            "STARmap analysis of cortical cell types",
            "STARmap in situ sequencing profiled single-cell "
            "gene expression in tissue volumes",
        )
        assert name == "unknown"

    def test_merfish_cosmx_geomx_not_routed_to_scrnaseq(self):
        for platform in ("MERFISH", "CosMx", "GeoMx"):
            result, name = self._registry_detect(
                f"{platform} profiling of tumor microenvironment",
                f"We used {platform} to measure single-cell gene expression "
                "in tissue sections",
            )
            assert name == "unknown", f"{platform} should not route to a pipeline"

    def test_scrna_with_visium_comparison_is_overblocked(self):
        # 의도된 과차단 (R12): 본편 scRNA + Visium 비교 문장도 unknown.
        # 5.0 AssayDetection[] 다중 감지 도입 전까지 수용된 동작.
        result, name = self._registry_detect(
            "Single-cell RNA sequencing of tumor microenvironment",
            "We used 10x Genomics single-cell RNA sequencing with UMIs. "
            "Results were compared with published Visium data.",
        )
        assert name == "unknown"

    def test_bulk_atac_still_detected(self):
        result, name = self._registry_detect(
            "ATAC-seq reveals chromatin accessibility",
            "We used ATAC-seq to profile open chromatin regions in bulk samples",
        )
        assert name == "atac_seq"

    def test_plain_scrna_still_detected(self):
        result, name = self._registry_detect(
            "Single-cell RNA sequencing of tumor microenvironment",
            "We used 10x Genomics single-cell RNA sequencing with UMIs "
            "and Cell Ranger to identify distinct cell populations",
        )
        assert name == "scrna_seq"
