"""
Tests for New Sequencing Type Plugins
Sarek, MethylSeq, CutAndRun, RnaFusion 플러그인 테스트
"""

from plugins import (
    CutAndRunPlugin,
    MethylSeqPlugin,
    PluginRegistry,
    RnaFusionPlugin,
    SarekPlugin,
    register_default_plugins,
)


class TestSarekPlugin:

    def test_sarek_properties(self):
        plugin = SarekPlugin()
        assert plugin.name == "wgs_wes"
        assert plugin.display_name == "WGS/WES Variant Calling"
        assert plugin.priority == 25
        assert plugin.pipeline.nf_core_name == "nf-core/sarek"
        assert plugin.pipeline.analysis_type == "variant"

    def test_sarek_high_score(self):
        plugin = SarekPlugin()
        text = "whole genome sequencing variant calling somatic mutation"
        score, evidence = plugin.calculate_score(text.lower(), {})
        assert score > 0.5
        assert len(evidence) > 0

    def test_sarek_low_score(self):
        plugin = SarekPlugin()
        text = "we performed single-cell rna sequencing analysis"
        score, evidence = plugin.calculate_score(text.lower(), {})
        assert score < 0.3

    def test_sarek_sra_metadata(self):
        plugin = SarekPlugin()
        metadata = {
            "pmid": "test",
            "title": "Whole genome sequencing of tumor samples",
            "abstract": "We performed WGS variant calling analysis",
            "keywords": ["wgs", "variant calling"],
        }
        sra = {
            "SRR111": {
                "LibStrategy": "WGS",
                "LibSource": "GENOMIC",
            }
        }
        result = plugin.detect(metadata, sra)
        assert result.sequencing_type == "wgs_wes"
        assert result.confidence > 0.5
        assert result.sra_metadata_match is True

    def test_sarek_exclude(self):
        plugin = SarekPlugin()
        metadata = {
            "pmid": "test",
            "title": "RNA-seq and variant analysis",
            "abstract": "We performed rna-seq with variant calling",
            "keywords": ["rna-seq"],
        }
        result = plugin.detect(metadata, {})
        assert result.confidence == 0.0

    def test_sarek_context_patterns(self):
        plugin = SarekPlugin()
        text = "tumor-normal paired variant detection cancer genomics"
        score, evidence = plugin.calculate_score(text.lower(), {})
        assert score > 0.3


class TestMethylSeqPlugin:

    def test_methylseq_properties(self):
        plugin = MethylSeqPlugin()
        assert plugin.name == "methylseq"
        assert plugin.display_name == "DNA Methylation (Bisulfite-seq)"
        assert plugin.priority == 18
        assert plugin.pipeline.nf_core_name == "nf-core/methylseq"
        assert plugin.pipeline.analysis_type == "methylation"

    def test_methylseq_high_score(self):
        plugin = MethylSeqPlugin()
        text = "bisulfite sequencing dna methylation wgbs"
        score, evidence = plugin.calculate_score(text.lower(), {})
        assert score > 0.5
        assert len(evidence) > 0

    def test_methylseq_low_score(self):
        plugin = MethylSeqPlugin()
        text = "we performed whole genome sequencing of tumor samples"
        score, evidence = plugin.calculate_score(text.lower(), {})
        assert score < 0.3

    def test_methylseq_sra_metadata(self):
        plugin = MethylSeqPlugin()
        metadata = {
            "pmid": "test",
            "title": "Bisulfite sequencing reveals methylation patterns",
            "abstract": "We performed WGBS to analyze DNA methylation",
            "keywords": ["methylation", "bisulfite"],
        }
        sra = {
            "SRR222": {
                "LibStrategy": "BISULFITE-SEQ",
                "LibSource": "GENOMIC",
            }
        }
        result = plugin.detect(metadata, sra)
        assert result.sequencing_type == "methylseq"
        assert result.confidence > 0.5
        assert result.sra_metadata_match is True

    def test_methylseq_exclude(self):
        plugin = MethylSeqPlugin()
        metadata = {
            "pmid": "test",
            "title": "ChIP-seq and methylation",
            "abstract": "We combined chip-seq with methylation analysis",
            "keywords": ["chip-seq"],
        }
        result = plugin.detect(metadata, {})
        assert result.confidence == 0.0

    def test_methylseq_context_patterns(self):
        plugin = MethylSeqPlugin()
        text = "differentially methylated region cpg methylation"
        score, evidence = plugin.calculate_score(text.lower(), {})
        assert score > 0.3


class TestCutAndRunPlugin:

    def test_cutandrun_properties(self):
        plugin = CutAndRunPlugin()
        assert plugin.name == "cutandrun"
        assert plugin.display_name == "CUT&RUN / CUT&Tag"
        assert plugin.priority == 17
        assert plugin.pipeline.nf_core_name == "nf-core/cutandrun"
        assert plugin.pipeline.analysis_type == "peak_diff"

    def test_cutandrun_high_score(self):
        plugin = CutAndRunPlugin()
        text = "cut&run cleavage under targets chromatin profiling"
        score, evidence = plugin.calculate_score(text.lower(), {})
        assert score > 0.5
        assert len(evidence) > 0

    def test_cutandrun_low_score(self):
        plugin = CutAndRunPlugin()
        text = "we performed bulk rna sequencing analysis"
        score, evidence = plugin.calculate_score(text.lower(), {})
        assert score < 0.3

    def test_cutandrun_sra_metadata(self):
        plugin = CutAndRunPlugin()
        metadata = {
            "pmid": "test",
            "title": "CUT&RUN profiling of histone modifications",
            "abstract": "We used cut&run to map histone modification",
            "keywords": ["cut&run", "histone"],
        }
        sra = {
            "SRR333": {
                "LibStrategy": "OTHER",
                "LibSource": "GENOMIC",
            }
        }
        result = plugin.detect(metadata, sra)
        assert result.sequencing_type == "cutandrun"
        assert result.confidence > 0.5
        assert result.sra_metadata_match is True

    def test_cutandrun_exclude(self):
        plugin = CutAndRunPlugin()
        metadata = {
            "pmid": "test",
            "title": "ChIP-seq analysis of chromatin",
            "abstract": "chip-seq was performed for histone marks",
            "keywords": ["chip-seq"],
        }
        result = plugin.detect(metadata, {})
        assert result.confidence == 0.0

    def test_cutandrun_context_patterns(self):
        plugin = CutAndRunPlugin()
        text = "histone modification transcription factor binding"
        score, evidence = plugin.calculate_score(text.lower(), {})
        assert score > 0.3


class TestRnaFusionPlugin:

    def test_rnafusion_properties(self):
        plugin = RnaFusionPlugin()
        assert plugin.name == "rnafusion"
        assert plugin.display_name == "RNA Fusion Gene Detection"
        assert plugin.priority == 12
        assert plugin.pipeline.nf_core_name == "nf-core/rnafusion"
        assert plugin.pipeline.analysis_type == "fusion"

    def test_rnafusion_high_score(self):
        plugin = RnaFusionPlugin()
        text = "gene fusion rna fusion chimeric transcript"
        score, evidence = plugin.calculate_score(text.lower(), {})
        assert score > 0.5
        assert len(evidence) > 0

    def test_rnafusion_low_score(self):
        plugin = RnaFusionPlugin()
        text = "we performed whole genome sequencing of healthy tissue"
        score, evidence = plugin.calculate_score(text.lower(), {})
        assert score < 0.3

    def test_rnafusion_sra_metadata(self):
        plugin = RnaFusionPlugin()
        metadata = {
            "pmid": "test",
            "title": "Gene fusion detection in leukemia",
            "abstract": "We detected gene fusion events using RNA fusion analysis",
            "keywords": ["gene fusion", "leukemia"],
        }
        sra = {
            "SRR444": {
                "LibStrategy": "RNA-SEQ",
                "LibSource": "TRANSCRIPTOMIC",
            }
        }
        result = plugin.detect(metadata, sra)
        assert result.sequencing_type == "rnafusion"
        assert result.confidence > 0.5
        assert result.sra_metadata_match is True

    def test_rnafusion_exclude(self):
        plugin = RnaFusionPlugin()
        metadata = {
            "pmid": "test",
            "title": "Single-cell analysis of fusion genes",
            "abstract": "single-cell sequencing was used for fusion detection",
            "keywords": ["single-cell"],
        }
        result = plugin.detect(metadata, {})
        assert result.confidence == 0.0

    def test_rnafusion_context_patterns(self):
        plugin = RnaFusionPlugin()
        text = "fusion detection structural rearrangement oncogenic fusion"
        score, evidence = plugin.calculate_score(text.lower(), {})
        assert score > 0.5

    def test_rnafusion_known_fusions(self):
        plugin = RnaFusionPlugin()
        text = "bcr-abl positive chronic myeloid leukemia"
        score, evidence = plugin.calculate_score(text.lower(), {})
        assert score > 0.2


class TestRegistryWithAllPlugins:

    def test_all_eight_plugins_registered(self):
        registry = PluginRegistry()
        registry.clear()
        registry = register_default_plugins()

        plugins = registry.list_plugins()
        assert len(plugins) == 8
        assert "scrna_seq" in plugins
        assert "bulk_rna_seq" in plugins
        assert "atac_seq" in plugins
        assert "chip_seq" in plugins
        assert "wgs_wes" in plugins
        assert "methylseq" in plugins
        assert "cutandrun" in plugins
        assert "rnafusion" in plugins

    def test_detect_sarek_from_registry(self):
        registry = PluginRegistry()
        registry.clear()
        registry = register_default_plugins()

        metadata = {
            "pmid": "test",
            "title": "Whole genome sequencing variant calling analysis",
            "abstract": (
                "We performed whole genome sequencing to identify "
                "somatic mutation and germline variant in tumor samples"
            ),
            "keywords": ["wgs", "variant calling"],
        }
        sra = {
            "SRR111": {
                "LibStrategy": "WGS",
                "LibSource": "GENOMIC",
            }
        }
        result, name = registry.detect(metadata, sra)
        assert name == "wgs_wes"
        assert result.confidence > 0.5
