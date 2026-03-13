"""
Tests for OrganismDetector
생물 종 감지 및 게놈 매핑 테스트
"""

from core.organism_detector import OrganismDetector


class TestDetectOrganism:

    def test_detect_human_from_abstract(self):
        metadata = {
            "title": "Cancer treatment study",
            "abstract": "patients with cancer underwent treatment",
            "mesh_terms": [],
            "keywords": [],
        }
        result = OrganismDetector.detect_organism(metadata)
        assert result["organism"] == "homo sapiens"
        assert result["genome"] == "GRCh38"
        assert result["confidence"] > 0.0

    def test_detect_mouse(self):
        metadata = {
            "title": "Mus musculus gene expression",
            "abstract": "We studied mus musculus embryonic development",
            "mesh_terms": [],
            "keywords": [],
        }
        result = OrganismDetector.detect_organism(metadata)
        assert result["organism"] == "mus musculus"
        assert result["genome"] == "GRCm38"

    def test_detect_mouse_alias(self):
        metadata = {
            "title": "Murine model of disease",
            "abstract": "We used a murine model to study",
            "mesh_terms": [],
            "keywords": [],
        }
        result = OrganismDetector.detect_organism(metadata)
        assert result["organism"] == "mus musculus"
        assert result["genome"] == "GRCm38"
        assert result["confidence"] > 0.0

    def test_detect_zebrafish(self):
        metadata = {
            "title": "Danio rerio development",
            "abstract": "danio rerio embryos were analyzed",
            "mesh_terms": [],
            "keywords": [],
        }
        result = OrganismDetector.detect_organism(metadata)
        assert result["organism"] == "danio rerio"
        assert result["genome"] == "GRCz11"

    def test_detect_from_mesh_terms(self):
        metadata = {
            "title": "Gene expression study",
            "abstract": "We analyzed gene expression",
            "mesh_terms": ["Mus musculus"],
            "keywords": [],
        }
        result = OrganismDetector.detect_organism(metadata)
        assert result["organism"] == "mus musculus"
        assert result["confidence"] == 0.95

    def test_detect_drosophila(self):
        metadata = {
            "title": "Drosophila melanogaster genetics",
            "abstract": "drosophila melanogaster was used as model organism",
            "mesh_terms": [],
            "keywords": [],
        }
        result = OrganismDetector.detect_organism(metadata)
        assert result["organism"] == "drosophila melanogaster"
        assert result["genome"] == "BDGP6"

    def test_no_organism(self):
        metadata = {}
        result = OrganismDetector.detect_organism(metadata)
        assert result["organism"] == "unknown"
        assert result["genome"] is None
        assert result["confidence"] == 0.0

    def test_detect_from_keywords(self):
        metadata = {
            "title": "Gene expression study",
            "abstract": "We analyzed gene expression patterns",
            "mesh_terms": [],
            "keywords": ["Homo sapiens"],
        }
        result = OrganismDetector.detect_organism(metadata)
        assert result["organism"] == "homo sapiens"
        assert result["genome"] == "GRCh38"


class TestGetGenomeForOrganism:

    def test_direct_lookup_human(self):
        assert OrganismDetector.get_genome_for_organism("Homo sapiens") == "GRCh38"

    def test_direct_lookup_mouse(self):
        assert OrganismDetector.get_genome_for_organism("Mus musculus") == "GRCm38"

    def test_alias_lookup(self):
        assert OrganismDetector.get_genome_for_organism("murine") == "GRCm38"

    def test_unknown_organism(self):
        assert OrganismDetector.get_genome_for_organism("unknown organism") is None

    def test_case_insensitive(self):
        assert OrganismDetector.get_genome_for_organism("HOMO SAPIENS") == "GRCh38"


class TestListSupportedOrganisms:

    def test_returns_non_empty(self):
        result = OrganismDetector.list_supported_organisms()
        assert len(result) > 0

    def test_expected_fields(self):
        result = OrganismDetector.list_supported_organisms()
        for entry in result:
            assert "organism" in entry
            assert "genome" in entry

    def test_contains_human(self):
        result = OrganismDetector.list_supported_organisms()
        genomes = [e["genome"] for e in result]
        assert "GRCh38" in genomes

    def test_unique_genomes(self):
        result = OrganismDetector.list_supported_organisms()
        genomes = [e["genome"] for e in result]
        assert len(genomes) == len(set(genomes))
