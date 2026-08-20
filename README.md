# bioauto

Reproducible bioinformatics research automation from a PMID or research topic to paper retrieval, sequencing metadata interpretation, nf-core execution, downstream analysis, LLM-assisted review, and HTML reports.

> 한국어 문서: [docs/README.ko.md](docs/README.ko.md)
>
> Architecture: [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) · Roadmap: [docs/planning/ROADMAP.md](docs/planning/ROADMAP.md) · Backlog: [docs/planning/BACKLOG.md](docs/planning/BACKLOG.md)

## What it does

| Command | Description |
|---|---|
| `bioauto run <PMID...>` | Collect paper/data metadata, analyze it, and generate reports |
| `bioauto run <PMID...> --execute-pipeline` | Download sequencing data and run the selected nf-core/downstream workflow |
| `bioauto search "keyword"` | Search PubMed, Semantic Scholar, Europe PMC, and optional web sources |
| `bioauto consult` | Refine a research question with an LLM and continue into search/analysis |
| `bioauto report --all` | Regenerate reports from existing results |
| `bioauto setup` | Open the interactive configuration wizard |
| `bioauto doctor [--json]` | Inspect Python, Java, Nextflow, container runtimes, and credentials |
| `bioauto prereqs` | Check pipeline execution prerequisites |
| `bioauto backends` | Show configured LLM backend status |
| `bioauto web` | Start the local monitoring dashboard |
| `bioauto setup-slurm` | Detect and configure a Slurm environment |
| `bioauto stop` | Stop BioAuto services |

## Current workflow

```text
PMID / keyword / research question
  -> PubMed + GEO/SRA metadata
  -> sequencing type detection
  -> optional fetchngs + nf-core pipeline
  -> optional R/Python downstream analysis
  -> literature/database integration
  -> enrichment and LLM-assisted interpretation
  -> multi-agent review
  -> JSON + HTML reports + RAG indexing
```

The approved 5.x direction adds processed spatial transcriptomics first, followed by a verification engine, Perturb-seq, long-read RNA, and other multimodal adapters. These roadmap items are not presented as implemented features.

## Quick start

Python 3.12 is recommended for a new installation. The core package currently supports Python 3.10+, but the modern Scanpy analysis stack requires Python 3.12+.

```bash
git clone https://github.com/kerniz/auto_analysis_by_nextflow.git
cd auto_analysis_by_nextflow

python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e ".[all,analysis]"

bioauto doctor
bioauto setup
bioauto run 40315330
```

For metadata-only use, install the smaller core package:

```bash
python -m pip install -e .
```

### Installer script

The repository includes a user-space installer:

```bash
bash install.sh
```

The current installer accepts a profile through `BIOAUTO_PROFILE`:

```bash
BIOAUTO_PROFILE=core bash install.sh
BIOAUTO_PROFILE=web bash install.sh
BIOAUTO_PROFILE=full bash install.sh
```

Current installer limitations:

- profile selection is environment-variable based; command-line profile flags are planned;
- `full` installs Web/TUI, RAG, and provider clients, but Scanpy must still be installed explicitly with `.[analysis]`;
- Java, Nextflow, R, and container runtimes are diagnosed separately and are not silently installed with elevated privileges;
- some optional dependency failures are not yet strict, so run `bioauto doctor` after installation.

Transactional installation, explicit profiles, rollback, and non-interactive setup are tracked in the [PH-0 backlog](docs/planning/BACKLOG.md).

### Optional extras

```bash
python -m pip install -e ".[openai]"       # OpenAI-compatible backend
python -m pip install -e ".[anthropic]"    # Anthropic backend
python -m pip install -e ".[enrichment]"   # GSEA/pathway analysis
python -m pip install -e ".[rag]"          # ChromaDB RAG
python -m pip install -e ".[analysis]"     # Scanpy/AnnData (Python 3.12+ recommended)
python -m pip install -e ".[web]"          # FastAPI dashboard
python -m pip install -e ".[tui]"          # Textual dashboard/setup wizard
python -m pip install -e ".[dev]"          # Tests, lint, and typing tools
```

## Requirements

| Scope | Requirement |
|---|---|
| Core metadata/search/reporting | Python 3.10+ |
| Modern Python analysis | Python 3.12+ recommended; verify Scanpy/AnnData compatibility |
| nf-core execution | Java 17+, Nextflow, and Docker/Apptainer/Singularity |
| R downstream analysis | R plus workflow-specific packages such as DESeq2 or Seurat |
| Storage | At least 10 GB; real workflows commonly require 50–200+ GB |

Nextflow 25.10+ is the current compatibility target. Nextflow 26.04 enables the strict syntax v2 parser by default, while some pinned nf-core workflows may still require compatibility testing. Do not force syntax v2 globally without testing the selected pipeline.

```bash
bioauto doctor
bioauto prereqs
```

## LLM configuration

At least one usable LLM backend is needed for LLM analysis, consultation, and agent review. Metadata retrieval and diagnostics do not require every provider.

| Backend | Basic setup |
|---|---|
| Ollama | Start Ollama and configure its URL/model in `config.json` |
| OpenAI | Set `OPENAI_API_KEY` and enable the OpenAI backend |
| Anthropic | Set `ANTHROPIC_API_KEY` and enable the Anthropic backend |
| Melchizedek gateway | OpenAI-compatible transport exists; gateway-first defaults and setup are still being completed in PH-0 |

Never commit API keys to `config.json`. Store only the environment-variable name in configuration.

```json
{
  "llm_providers": {
    "backends": {
      "ollama": {
        "enabled": true,
        "url": "http://localhost:11434",
        "model": "auto"
      },
      "openai": {
        "enabled": false,
        "api_key_env": "OPENAI_API_KEY",
        "base_url": null,
        "model": "gpt-4o"
      }
    },
    "router": {
      "strategy": "priority",
      "priority_order": ["ollama", "openai", "anthropic"],
      "enable_auto_failover": true
    }
  }
}
```

These checked-in defaults describe current behavior, not the approved final gateway-first policy. Review the backlog before deploying a custom gateway in production.

## Usage

### Analyze papers

```bash
bioauto run 40315330
bioauto run 40315330 32416070 31061532
```

Per-paper results are written under `results/{PMID}/`. Multi-PMID runs also generate `results/project_report.html`.

### Search or consult

```bash
bioauto search "spatial transcriptomics cancer"
bioauto search "CRISPR screen" --auto-run
bioauto consult
```

### Execute an nf-core workflow

```bash
bioauto run 40315330 --execute-pipeline

bioauto run 40315330 \
  --execute-pipeline \
  --container-runtime apptainer \
  --genome mm10 \
  --max-cpus 8 \
  --max-memory 32.GB
```

Review samples, storage requirements, and parameters before running public sequencing datasets. Downloads and container images can be large.

### Local web dashboard

```bash
# Safe default: http://127.0.0.1:8888
bioauto web
```

Non-loopback binding is blocked unless explicitly enabled:

```bash
bioauto web \
  --host 0.0.0.0 \
  --allow-remote \
  --server-token "$(openssl rand -hex 32)"
```

State-changing API requests must send `X-Server-Token`. The current PH-0 branch does not yet protect every read-only result endpoint, so do not expose the dashboard directly to the public internet. Prefer loopback, Tailnet, or an authenticated reverse proxy.

### Minimal run

```bash
bioauto run 40315330 --no-debate
bioauto run 40315330 --no-debate --no-enrichment --no-aggregate
```

## Output layout

```text
results/
  {PMID}/
    final_report_{PMID}.json
    report_{PMID}.html
    pubmed_{PMID}.json
    sra_exploration_{PMID}.json
    fetchngs/                  # when pipeline execution is enabled
    pipeline/
    analysis/
  project_report.html         # generated for multi-PMID runs
  execution_summary.json
  progress.json
```

## Supported workflow mapping

| Detected data | nf-core workflow | Downstream layer |
|---|---|---|
| scRNA-seq | `nf-core/scrnaseq` | Seurat / Scanpy |
| Bulk RNA-seq | `nf-core/rnaseq` | DESeq2 |
| ATAC-seq | `nf-core/atacseq` | Peak analysis/annotation |
| ChIP-seq | `nf-core/chipseq` | Peak analysis/annotation |
| WGS/WES | `nf-core/sarek` | Variant analysis |
| Bisulfite-seq | `nf-core/methylseq` | Methylation analysis |
| CUT&RUN/CUT&Tag | `nf-core/cutandrun` | Peak analysis/annotation |
| RNA fusion | `nf-core/rnafusion` | Fusion result integration |

Pipeline names do not imply validation against every latest upstream release. Versions remain pinned until their samplesheet, parameters, and output contracts pass compatibility tests.

## Repository map

```text
core/              orchestration, CLI, manifests, reports, progress
backends/          Ollama, OpenAI-compatible, Anthropic, and routing
plugins/           sequencing type detection
clients/           PubMed and external biological data APIs
search/            literature search
agents/            specialist review/debate
rag/               document indexing and retrieval
nextflow/          workflow execution
analysis/          R/Python downstream analysis
web/               FastAPI dashboard
tui/               Textual dashboard and setup wizard
tests/             unit, contract, and integration tests
docs/              architecture, roadmap, RFCs, fixtures, and history
```

## Project status

| Area | Status |
|---|---|
| Bulk/scRNA metadata automation and reports | Available |
| nf-core execution adapters | Available; per-version compatibility work is ongoing |
| Web loopback security and remote mutation token | Implemented on `feat/platform-hardening-gateway` |
| Spatial manifest/workflow-plan foundation | Implemented; processed reader waits for PH-0 |
| Gateway-first routing, automated setup, installer rollback | In progress |
| Spatial/Perturb-seq/long-read multimodal analysis | Roadmap |
| Virtual experiment engine | Long-term roadmap |

For exact completion criteria, use [BACKLOG.md](docs/planning/BACKLOG.md). For product sequencing, use [ROADMAP.md](docs/planning/ROADMAP.md). Planning documents describe future work; this README describes the current usable surface.

## Development

```bash
python -m pip install -e ".[dev]"
python -m pytest tests/ -v
python -m ruff check .
```

Network, LLM quota, large public datasets, and nf-core test-profile checks must remain opt-in integration tests. Unit and contract tests should use synthetic fixtures.

## License

MIT
