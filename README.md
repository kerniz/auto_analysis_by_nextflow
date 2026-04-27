# bioauto

**One-stop bioinformatics research automation — from a topic or PMID to paper metadata collection, sequencing data analysis, multi-LLM consensus, multi-agent debate, and HTML report generation.**

---

## Features

| Command | Description |
|---------|-------------|
| `bioauto run <PMIDs>` | Paper metadata + LLM analysis + debate → report |
| `bioauto run <PMIDs> --execute-pipeline` | + Sequencing data download → nf-core analysis → R/Python downstream |
| `bioauto search "keyword"` | 4-source parallel search → select → run pipeline |
| `bioauto consult` | LLM consultation → topic refinement → search → pipeline |
| `bioauto report --all` | Regenerate HTML reports from existing results |
| `bioauto web` | Start web dashboard server (SSE real-time monitoring) |
| `bioauto stop` | Stop all running services |
| `bioauto stop web` | Stop web server only |
| `bioauto stop pipeline` | Stop pipeline only |
| `bioauto prereqs` | Validate execution environment |
| `bioauto backends` | Check LLM backend status |
| `bioauto setup-slurm` | Auto-detect and configure Slurm HPC |
| `bioauto uninstall` | Completely remove bioauto (preserves source and results) |

---

## Pipeline Flow

```
Input: PMID / keyword / research topic
  │
  ├─ Stage 1: PubMed metadata collection
  ├─ Stage 2: SRA/GEO metadata collection
  ├─ Stage 3: Sequencing type auto-detection (scRNA-seq / Bulk RNA / ATAC / ChIP)
  │
  │  ┌─ --execute-pipeline only ──────────────────────────────────────┐
  │  │ Stage 3.5: nf-core/fetchngs → SRA data download               │
  │  │ Stage 3.6: nf-core pipeline (rnaseq/scrnaseq/...)             │
  │  │ Stage 3.7: R/Python downstream analysis (DESeq2/Seurat/...)   │
  │  └────────────────────────────────────────────────────────────────┘
  │
  ├─ Stage 4: External data integration (Semantic Scholar + Europe PMC + TCGA)
  ├─ Stage 5: Gene pathway analysis (GSEA/Enrichr)
  ├─ Stage 6: Multi-LLM consensus analysis (all backends queried simultaneously)
  ├─ Stage 7: Multi-agent debate (PhD · undergraduate · layperson panel)
  └─ Stage 8: Report generation + RAG indexing

Output: JSON + HTML report in results/{PMID}/
        2+ PMIDs → combined report (project_report.html) auto-generated
```

---

## Installation

```bash
# Basic
git clone git@github.com:kerniz/auto_analysis_by_nextflow.git
cd auto_analysis_by_nextflow
pip install -e .

# Development
pip install -e ".[dev]"

# Full features (RAG + analysis)
pip install -e ".[all,analysis]"
```

### Optional extras

```bash
pip install -e ".[openai]"       # OpenAI backend
pip install -e ".[anthropic]"    # Anthropic backend
pip install -e ".[enrichment]"   # GSEA/pathway analysis
pip install -e ".[rag]"          # ChromaDB RAG
pip install -e ".[analysis]"     # scanpy (Python scRNA-seq)
pip install -e ".[web]"          # Web dashboard (FastAPI)
pip install -e ".[tui]"          # TUI dashboard (Textual)
```

---

## Requirements

### Required

| Item | Minimum Version |
|------|----------------|
| Python | 3.10+ |

### LLM Backend (at least one required)

| Backend | Setup |
|---------|-------|
| Ollama (local, free) | `ollama serve` then `ollama pull qwen3:30b` |
| OpenAI | `export OPENAI_API_KEY=sk-...` |
| Anthropic | `export ANTHROPIC_API_KEY=sk-ant-...` |

### Additional requirements for `--execute-pipeline`

| Item | Minimum Version |
|------|----------------|
| Nextflow | 23.04+ |
| Java | 11+ |
| Docker / Singularity / Apptainer / Podman | — |
| Disk space | 10 GB+ (50–200 GB recommended depending on pipeline) |

> **Note**: If `--genome` is not specified, the organism is auto-detected from paper metadata and mapped to a genome (15 species supported).

### Downstream analysis extras

| R package | Purpose |
|-----------|---------|
| DESeq2 | Bulk RNA-seq differential expression |
| Seurat | scRNA-seq clustering |
| ggplot2, pheatmap | Visualization |

```bash
bioauto prereqs   # validate full environment
```

---

## Usage

### 1. Single PMID analysis

```bash
bioauto run 40315330
```

→ Report generated in `results/40315330/`

### 2. Multiple PMIDs

```bash
bioauto run 40315330 32416070 31061532
```

→ Individual reports + combined report (`results/project_report.html`)

### 3. Full pipeline execution (Nextflow + R)

```bash
# Docker + GRCh38
bioauto run 40315330 --execute-pipeline

# Singularity + mouse genome
bioauto run 40315330 --execute-pipeline --container-runtime singularity --genome mm10

# Resource limits
bioauto run 40315330 --execute-pipeline --max-cpus 8 --max-memory 32.GB
```

### 4. Paper search → analysis

```bash
# 4-source parallel search (PubMed, Semantic Scholar, Europe PMC, Brave)
bioauto search "spatial transcriptomics cancer"

# Search then auto-run pipeline
bioauto search "CRISPR screen" --auto-run
```

### 5. Research consultation mode

```bash
bioauto consult
```

Chat with an LLM to refine your research topic → generate search queries → auto-search → pipeline

### 6. Regenerate reports

```bash
# Specific PMID
bioauto report 40315330

# All results
bioauto report --all
```

### 7. Run options

```bash
# Disable debate (faster)
bioauto run 40315330 --no-debate

# Minimal run (disable debate, enrichment, and aggregation)
bioauto run 40315330 --no-debate --no-enrichment --no-aggregate

# Environment checks
bioauto prereqs
bioauto backends
```

---

## Output Structure

```
results/
├── {PMID}/                        # Per-PMID results subfolder
│   ├── final_report_{PMID}.json   # Final report (JSON)
│   ├── report_{PMID}.html         # HTML report
│   ├── pubmed_{PMID}.json         # PubMed cache
│   ├── sra_exploration_{PMID}.json# SRA cache
│   │
│   ├── fetchngs/                  # [--execute-pipeline] FASTQ files
│   ├── pipeline/                  # [--execute-pipeline] nf-core results
│   └── analysis/                  # [--execute-pipeline] downstream analysis
│
├── project_report.html            # Combined report (auto-generated for 2+ PMIDs)
├── execution_summary.json         # Execution summary
└── progress.json                  # Checkpoint (for resume)
```

### Auto-Detection Mapping

| Detected sequencing | nf-core pipeline | Downstream analysis | Key outputs |
|---------------------|-----------------|--------------------|-----------  |
| scRNA-seq | nf-core/scrnaseq | Seurat (R) / scanpy (Python) | UMAP, cluster markers |
| Bulk RNA-seq | nf-core/rnaseq | DESeq2 (R) | DEG list, Volcano plot |
| ATAC-seq | nf-core/atacseq | Peak analysis (R) | Differential peaks, annotation |
| ChIP-seq | nf-core/chipseq | Peak analysis (R) | Differential peaks, annotation |
| WGS/WES | nf-core/sarek | SnpEff/VEP variant analysis | VCF, variant stats |
| Bisulfite-seq | nf-core/methylseq | Methylation analysis (R) | CpG stats, DMR |
| CUT&RUN/CUT&Tag | nf-core/cutandrun | Peak analysis (R) | Differential peaks, annotation |
| RNA-fusion | nf-core/rnafusion | Fusion gene analysis | Fusion gene list |

---

## Configuration

### config.json

```jsonc
{
  // LLM server
  "pipeline_config": {
    "llm_server": {
      "url": "http://localhost:11434",
      "model": "qwen3:30b"
    }
  },

  // Nextflow pipeline execution
  "nextflow_execution": {
    "enabled": false,
    "genome": "GRCh38",
    "container_runtime": "docker"
  },

  // Debate settings
  "debate": {
    "num_rounds": 3,
    "consensus_threshold": 0.7,
    "agent_weights": {
      "phd_expert": 0.5,
      "undergraduate": 0.3,
      "layperson": 0.2
    }
  }
}
```

### Environment Variables

| Variable | Purpose | Required |
|----------|---------|---------|
| `OPENAI_API_KEY` | OpenAI backend | Optional |
| `ANTHROPIC_API_KEY` | Anthropic backend | Optional |
| `BRAVE_API_KEY` | Brave Search web search | Optional |
| `NCBI_EMAIL` | PubMed API | Recommended |
| `BIOAUTO_LOCALE` | UI locale (`en` or `ko`) | Optional |

---

## Project Structure

```
bioauto/
├── core/                   # Core orchestration
│   ├── cli.py              #   Click CLI entry point
│   ├── pipeline.py         #   Async pipeline orchestrator
│   ├── pubmed_client.py    #   PubMed API client
│   ├── sra_explorer.py     #   SRA metadata exploration
│   ├── report_generator.py #   HTML report generator
│   ├── json_utils.py       #   LLM response JSON parser
│   └── progress_manager.py #   Checkpoint/resume
│
├── backends/               # LLM backends (Ollama, OpenAI, Anthropic)
├── plugins/                # Sequencing type detection plugins
├── agents/                 # Multi-agent debate (PhD, undergraduate, layperson)
├── clients/                # External API clients (SS, EPMC, TCGA)
├── enrichment/             # GSEA pathway analysis
├── search/                 # Paper search (4-source fanout)
├── mcp/                    # Brave Search integration
├── rag/                    # RAG vector DB (ChromaDB)
├── nextflow/               # Nextflow execution layer
├── analysis/               # R/Python downstream analysis
├── locales/                # i18n locale files (en/ko/de/ja)
│
├── config.json             # Global configuration
├── pyproject.toml          # Project metadata + dependencies
├── nextflow.config         # Nextflow configuration
├── tests/                  # Tests (1518 passed, ~90% coverage)
└── docs/                   # Architecture, development history
    └── README.ko.md        # Korean README
```

---

## Testing

```bash
pip install -e ".[dev]"

# All tests
python3 -m pytest tests/ -v

# Specific module
python3 -m pytest tests/test_pipeline.py -v
python3 -m pytest tests/test_report_generator.py -v

# Coverage
python3 -m pytest tests/ --cov=. --cov-report=html

# Lint
python3 -m ruff check .
```

Current: **1518 passed, 10 skipped** — ~90% coverage

---

## License

MIT
