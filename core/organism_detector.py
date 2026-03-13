"""Organism detection from PubMed metadata and genome mapping."""
from __future__ import annotations

# Organism → nf-core genome mapping
ORGANISM_GENOME_MAP = {
    # Human
    "homo sapiens": "GRCh38",
    "human": "GRCh38",
    # Mouse
    "mus musculus": "GRCm38",
    "mouse": "GRCm38",
    # Rat
    "rattus norvegicus": "Rnor_6.0",
    "rat": "Rnor_6.0",
    # Zebrafish
    "danio rerio": "GRCz11",
    "zebrafish": "GRCz11",
    # Fruit fly
    "drosophila melanogaster": "BDGP6",
    "fruit fly": "BDGP6",
    "drosophila": "BDGP6",
    # C. elegans
    "caenorhabditis elegans": "WBcel235",
    "c. elegans": "WBcel235",
    # Yeast
    "saccharomyces cerevisiae": "R64-1-1",
    "yeast": "R64-1-1",
    # Chicken
    "gallus gallus": "GRCg6a",
    "chicken": "GRCg6a",
    # Pig
    "sus scrofa": "Sscrofa11.1",
    "pig": "Sscrofa11.1",
    # Dog
    "canis familiaris": "CanFam3.1",
    "canis lupus familiaris": "CanFam3.1",
    "dog": "CanFam3.1",
    # Cow
    "bos taurus": "UMD3.1",
    "cow": "UMD3.1",
    # Arabidopsis
    "arabidopsis thaliana": "TAIR10",
    "arabidopsis": "TAIR10",
    # Rice
    "oryza sativa": "IRGSP-1.0",
    "rice": "IRGSP-1.0",
    # Macaque
    "macaca mulatta": "Mmul_10",
    "rhesus macaque": "Mmul_10",
}

# Common aliases (case-insensitive matching)
ORGANISM_ALIASES = {
    "mice": "mus musculus",
    "murine": "mus musculus",
    "rats": "rattus norvegicus",
    "humans": "homo sapiens",
    "patients": "homo sapiens",
    "clinical": "homo sapiens",
    "xenopus": "xenopus tropicalis",
    "frog": "xenopus tropicalis",
    "nematode": "caenorhabditis elegans",
    "worm": "caenorhabditis elegans",
    "macaque": "macaca mulatta",
    "monkey": "macaca mulatta",
    "primate": "homo sapiens",
    "canine": "canis familiaris",
    "bovine": "bos taurus",
    "porcine": "sus scrofa",
    "avian": "gallus gallus",
}


class OrganismDetector:
    """Detect organism from PubMed metadata and map to genome reference."""

    @staticmethod
    def detect_organism(pubmed_metadata: dict) -> dict:
        """
        Detect organism from PubMed metadata.

        Returns dict with:
          - organism: str (detected organism name)
          - genome: str | None (nf-core genome reference)
          - confidence: float (0-1)
          - evidence: list[str]
        """
        text_sources: list[str] = []

        # Collect text from metadata
        title = pubmed_metadata.get("title", "")
        abstract = pubmed_metadata.get("abstract", "")
        mesh_terms = pubmed_metadata.get("mesh_terms", [])
        keywords = pubmed_metadata.get("keywords", [])

        if title:
            text_sources.append(title)
        if abstract:
            text_sources.append(abstract)
        if isinstance(mesh_terms, list):
            text_sources.extend(str(t) for t in mesh_terms)
        if isinstance(keywords, list):
            text_sources.extend(str(k) for k in keywords)

        combined_text = " ".join(text_sources).lower()

        # Score each organism
        scores: dict[str, tuple[float, str]] = {}

        # Direct organism name matching
        for organism, genome in ORGANISM_GENOME_MAP.items():
            if organism in combined_text:
                score = 0.9 if len(organism.split()) > 1 else 0.7
                if organism not in scores or scores[organism][0] < score:
                    scores[organism] = (
                        score,
                        f"Direct match: '{organism}'",
                    )

        # Alias matching
        for alias, organism in ORGANISM_ALIASES.items():
            if alias in combined_text:
                score = 0.6
                canonical = organism
                if canonical not in scores or scores[canonical][0] < score:
                    scores[canonical] = (
                        score,
                        f"Alias match: '{alias}' → {canonical}",
                    )

        # MeSH term matching (higher confidence)
        mesh_text = (
            " ".join(str(t) for t in mesh_terms).lower()
            if mesh_terms
            else ""
        )
        for organism in ORGANISM_GENOME_MAP:
            if organism in mesh_text:
                scores[organism] = (
                    0.95,
                    f"MeSH term match: '{organism}'",
                )

        if not scores:
            return {
                "organism": "unknown",
                "genome": None,
                "confidence": 0.0,
                "evidence": ["No organism detected from metadata"],
            }

        # Pick highest scoring
        best_organism = max(scores, key=lambda x: scores[x][0])
        best_score, best_evidence = scores[best_organism]

        # Map to genome
        genome = ORGANISM_GENOME_MAP.get(best_organism)
        if not genome:
            # Try canonical lookup via aliases
            canonical = ORGANISM_ALIASES.get(best_organism, best_organism)
            genome = ORGANISM_GENOME_MAP.get(canonical)

        return {
            "organism": best_organism,
            "genome": genome,
            "confidence": best_score,
            "evidence": [best_evidence],
        }

    @staticmethod
    def get_genome_for_organism(organism: str) -> str | None:
        """Direct lookup: organism name → genome reference."""
        key = organism.lower().strip()
        if key in ORGANISM_GENOME_MAP:
            return ORGANISM_GENOME_MAP[key]
        # Try alias
        canonical = ORGANISM_ALIASES.get(key)
        if canonical:
            return ORGANISM_GENOME_MAP.get(canonical)
        return None

    @staticmethod
    def list_supported_organisms() -> list[dict]:
        """List all supported organisms and their genomes."""
        seen: set[str] = set()
        result: list[dict] = []
        for organism, genome in ORGANISM_GENOME_MAP.items():
            if genome not in seen:
                seen.add(genome)
                result.append({"organism": organism, "genome": genome})
        return result
