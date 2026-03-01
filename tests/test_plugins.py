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
