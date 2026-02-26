# bioauto

**Bioinformatics Research Automation Platform**

PMID 기반 논문 분석부터 nf-core 파이프라인 실행, R/Python 다운스트림 분석까지 올인원 CLI 도구.

---

## 기능 요약

```
bioauto run <PMIDs>                    → 논문 메타데이터 + LLM 분석 + 토론
bioauto run <PMIDs> --execute-pipeline → + 실제 시퀀싱 데이터 분석
bioauto search "키워드"                → 논문 검색 → 선택 → 파이프라인
bioauto consult                        → LLM 상담 → 주제 정제 → 검색 → 파이프라인
bioauto prereqs                        → 실행 환경 검증
bioauto backends                       → LLM 백엔드 상태 확인
bioauto plugins                        → 시퀀싱 감지 플러그인 목록
bioauto status                         → 이전 실행 결과 확인
```

---

## 설치

### 기본 설치

```bash
git clone git@github.com:kerniz/auto_analysis_by_nextflow.git
cd auto_analysis_by_nextflow
pip install -e .
```

### 개발 환경

```bash
pip install -e ".[dev]"
```

### 전체 기능 (RAG + 분석)

```bash
pip install -e ".[all,analysis]"
```

### 선택적 설치

```bash
pip install -e ".[openai]"       # OpenAI 백엔드
pip install -e ".[anthropic]"    # Anthropic 백엔드
pip install -e ".[enrichment]"   # GSEA/경로 분석
pip install -e ".[rag]"          # ChromaDB RAG
pip install -e ".[analysis]"     # scanpy (Python scRNA-seq)
```

---

## 요구 사항

### 필수

| 항목 | 최소 버전 | 확인 방법 |
|------|-----------|-----------|
| Python | 3.10+ | `python --version` |
| pip packages | - | `pip install -e .` |

### LLM 백엔드 (하나 이상 필요)

| 백엔드 | 설정 |
|--------|------|
| Ollama (로컬, 무료) | `ollama serve` 후 `ollama pull deepseek-coder:33b` |
| OpenAI | `export OPENAI_API_KEY=sk-...` |
| Anthropic | `export ANTHROPIC_API_KEY=sk-ant-...` |

```bash
bioauto backends   # 백엔드 상태 확인
```

### 파이프라인 실행 시 추가 필요 (`--execute-pipeline`)

| 항목 | 최소 버전 | 확인 방법 |
|------|-----------|-----------|
| Nextflow | 23.04+ | `nextflow -version` |
| Java | 11+ | `java -version` |
| Docker 또는 Singularity | - | `docker info` / `singularity --version` |
| 디스크 공간 | 10GB+ | 파이프라인에 따라 50-200GB 권장 |

### 다운스트림 분석 시 추가 필요

| 항목 | R 패키지 | 용도 |
|------|----------|------|
| Rscript | - | R 스크립트 실행 |
| DESeq2 | `BiocManager::install("DESeq2")` | Bulk RNA-seq 차등발현 |
| tximport | `BiocManager::install("tximport")` | Salmon 결과 임포트 |
| Seurat | `install.packages("Seurat")` | scRNA-seq 클러스터링 |
| ggplot2 | `install.packages("ggplot2")` | 시각화 |
| pheatmap | `install.packages("pheatmap")` | 히트맵 |
| optparse | `install.packages("optparse")` | CLI 인자 파싱 |
| jsonlite | `install.packages("jsonlite")` | JSON 출력 |

R 없이 scRNA-seq 분석하려면 scanpy (Python) 사용 가능:
```bash
pip install -e ".[analysis]"
```

```bash
bioauto prereqs   # 전체 환경 검증
```

---

## 사용법

### 1. 논문 분석 (메타데이터 + LLM)

```bash
# 단일 PMID
bioauto run 40315330

# 여러 PMID
bioauto run 40315330 32416070

# 토론 비활성화 (빠른 실행)
bioauto run 40315330 --no-debate

# 최소 실행 (토론, 농축, 데이터통합 모두 끄기)
bioauto run 40315330 --no-debate --no-enrichment --no-aggregate
```

**처리 흐름:**
```
PubMed 메타데이터 수집
  → SRA 메타데이터 수집
  → 시퀀싱 타입 감지 (scRNA-seq / Bulk RNA-seq / ATAC-seq / ChIP-seq)
  → 외부 데이터 통합 (Semantic Scholar + Europe PMC + TCGA)
  → 유전자 경로 분석 (GSEA)
  → LLM 다중 합의 분석 (모든 백엔드 동시 쿼리)
  → 멀티 에이전트 토론 (PhD, 학부생, 일반인 3인 패널)
  → 보고서 생성 + RAG 인덱싱
```

### 2. 실제 파이프라인 실행 (Nextflow + R/Python)

```bash
# 기본 (Docker + GRCh38)
bioauto run 40315330 --execute-pipeline

# Singularity + 마우스 게놈
bioauto run 40315330 --execute-pipeline --container-runtime singularity --genome mm10

# 리소스 제한
bioauto run 40315330 --execute-pipeline --max-cpus 8 --max-memory 32.GB
```

**추가 처리 흐름 (`--execute-pipeline`):**
```
... 시퀀싱 감지 이후 ...
  → nf-core/fetchngs로 SRA 데이터 다운로드 (FASTQ)
  → Samplesheet 자동 생성 (파이프라인별 CSV 포맷)
  → nf-core 파이프라인 실행:
      scRNA-seq  → nf-core/scrnaseq  → Seurat/scanpy 분석
      Bulk RNA   → nf-core/rnaseq    → DESeq2 분석
      ATAC-seq   → nf-core/atacseq   → Peak 차등 분석
      ChIP-seq   → nf-core/chipseq   → Peak 차등 분석
  → R/Python 다운스트림 분석 결과를 LLM 프롬프트에 주입
```

**자동 감지 매핑:**

| 감지된 시퀀싱 | nf-core 파이프라인 | 다운스트림 분석 | 주요 출력 |
|--------------|-------------------|----------------|----------|
| scRNA-seq | nf-core/scrnaseq | Seurat (R) 또는 scanpy (Python) | UMAP, 클러스터 마커 |
| Bulk RNA-seq | nf-core/rnaseq | DESeq2 (R) | DEG 목록, Volcano plot |
| ATAC-seq | nf-core/atacseq | Peak analysis (R) | 차등 피크, 어노테이션 |
| ChIP-seq | nf-core/chipseq | Peak analysis (R) | 차등 피크, 어노테이션 |

### 3. 논문 검색

```bash
# 주제어 검색 (4개 소스 동시: PubMed, Semantic Scholar, Europe PMC, Brave)
bioauto search "spatial transcriptomics cancer"

# 검색 결과 제한
bioauto search "CRISPR screen" --limit 10

# Brave 검색 비활성화
bioauto search "single cell ATAC" --no-brave

# 검색 후 자동 파이프라인 실행
bioauto search "bulk RNA-seq liver" --auto-run
```

**사용 흐름:**
```
키워드 입력 → 4개 소스 팬아웃 검색 → 가중 점수 순위 → 결과 표시
  → 번호 선택 (예: 1,3,5) → 파이프라인 실행
```

### 4. 연구 상담 모드

```bash
bioauto consult
```

**사용 흐름:**
```
LLM이 연구 주제 질문 → 대화형 정제 (2-3턴)
  → LLM이 검색 쿼리 3개 제안 → 선택 → 자동 검색
  → 결과 선택 → 파이프라인 실행
```

### 5. 환경 검증

```bash
bioauto prereqs
```

**출력 예시:**
```
=== Pipeline Execution Prerequisites ===

  [OK] Nextflow (/usr/local/bin/nextflow)
  [OK] Java (/usr/bin/java)
  [OK]   docker (/usr/bin/docker)
  [--]   singularity (not found)
  [--]   apptainer (not found)
  [OK] Rscript (/usr/bin/Rscript)

  R Packages:
    [OK]   DESeq2
    [OK]   tximport
    [OK]   Seurat
    [OK]   ggplot2
    [OK]   pheatmap
    [OK]   optparse
    [OK]   jsonlite

  Python Packages (optional):
    [--]   scanpy (not installed)
    [--]   anndata (not installed)
    [OK]   matplotlib

  [OK] Disk Space (156.3 GB free)
```

### 6. 기타 명령

```bash
# LLM 백엔드 상태
bioauto backends

# 시퀀싱 감지 플러그인
bioauto plugins

# 이전 실행 결과 확인
bioauto status
bioauto status --format json

# 버전 확인
bioauto --version
```

---

## 설정

### config.json

주요 설정 항목:

```jsonc
{
  // LLM 서버
  "pipeline_config": {
    "llm_server": {
      "url": "http://localhost:11434",
      "model": "deepseek-coder:33b"
    }
  },

  // Nextflow 파이프라인 실행 (--execute-pipeline 사용 시)
  "nextflow_execution": {
    "enabled": false,
    "genome": "GRCh38",
    "container_runtime": "docker",
    "max_memory": "16.GB",
    "max_cpus": 4,
    "pipeline_params": {
      "nf-core/rnaseq": { "pseudo_aligner": "salmon" },
      "nf-core/scrnaseq": { "protocol": "10XV3" }
    }
  },

  // R/Python 다운스트림 분석
  "analysis": {
    "r_executable": "Rscript",
    "scanpy_enabled": false,
    "deseq2": { "fc_threshold": "1.5", "padj_threshold": "0.05" },
    "seurat": { "min_features": "200", "resolution": "0.8" }
  },

  // 토론 설정
  "debate": {
    "num_rounds": 3,
    "consensus_threshold": 0.7,
    "agent_weights": {
      "phd_expert": 0.5,
      "undergraduate": 0.3,
      "layperson": 0.2
    }
  },

  // Brave Search (웹 검색 보완)
  "brave_search": {
    "enabled": false  // BRAVE_API_KEY 환경변수 필요
  },

  // RAG 벡터 DB
  "rag": {
    "enabled": true,
    "persist_dir": "./results/rag_db"
  }
}
```

### 환경 변수

| 변수 | 용도 | 필수 |
|------|------|------|
| `OPENAI_API_KEY` | OpenAI 백엔드 | 선택 |
| `ANTHROPIC_API_KEY` | Anthropic 백엔드 | 선택 |
| `BRAVE_API_KEY` | Brave Search 웹 검색 | 선택 |
| `NCBI_EMAIL` | PubMed API (Biopython) | 권장 |

---

## 출력 구조

```
results/
├── execution_summary.json          # 전체 실행 요약
├── progress.json                   # 진행 상태 (재시작용)
├── rag_db/                         # RAG 벡터 DB (ChromaDB)
│
├── 40315330/                       # PMID별 결과
│   ├── pubmed_metadata.json        # PubMed 메타데이터
│   ├── sra_metadata.json           # SRA 메타데이터
│   ├── sequencing_detection.json   # 시퀀싱 타입 감지 결과
│   ├── aggregated_data.json        # 외부 데이터 통합
│   ├── enrichment_results.json     # GSEA 분석 결과
│   ├── llm_analysis.json           # LLM 합의 분석
│   ├── debate_report.json          # 토론 보고서
│   ├── final_report.json           # 최종 보고서
│   │
│   ├── fetchngs/                   # [--execute-pipeline] SRA 다운로드
│   │   ├── fastq/                  # FASTQ 파일
│   │   └── samplesheet/            # fetchngs 생성 samplesheet
│   │
│   ├── pipeline/                   # [--execute-pipeline] nf-core 결과
│   │   ├── star_salmon/            # (rnaseq) 정량화 결과
│   │   ├── cellranger/             # (scrnaseq) Cell Ranger 결과
│   │   ├── bwa/                    # (atacseq/chipseq) 정렬 결과
│   │   └── multiqc/                # QC 보고서
│   │
│   └── analysis/                   # [--execute-pipeline] 다운스트림
│       ├── deseq2_results.csv      # (rnaseq) DEG 결과
│       ├── significant_degs.csv    # (rnaseq) 유의미한 DEG
│       ├── volcano_plot.pdf        # (rnaseq) Volcano plot
│       ├── cluster_markers.csv     # (scrnaseq) 클러스터 마커
│       ├── umap_clusters.pdf       # (scrnaseq) UMAP
│       ├── diff_peaks.csv          # (atac/chip) 차등 피크
│       └── summary.json            # 분석 요약
```

---

## 빠른 시작 예제

### 예제 1: 논문 메타데이터 분석만

```bash
pip install -e .
bioauto run 40315330 --no-debate --no-enrichment
```

### 예제 2: 전체 분석 (토론 포함)

```bash
pip install -e ".[all]"
export OPENAI_API_KEY=sk-...
bioauto run 40315330 32416070 --debate-rounds 3
```

### 예제 3: 실제 파이프라인 실행 (서버)

```bash
# 환경 확인
bioauto prereqs

# 실행 (Docker)
bioauto run 40315330 --execute-pipeline --max-cpus 16 --max-memory 64.GB

# 실행 (Singularity, HPC)
bioauto run 40315330 --execute-pipeline --container-runtime singularity --genome GRCh38
```

### 예제 4: 논문 검색 → 분석

```bash
bioauto search "pancreatic cancer single cell RNA-seq"
# 결과에서 번호 선택 → 파이프라인 실행
```

---

## 테스트

```bash
pip install -e ".[dev]"

# 전체 테스트
pytest tests/ -v

# 특정 모듈
pytest tests/test_samplesheet.py -v
pytest tests/test_nextflow.py -v
pytest tests/test_analysis.py -v

# 커버리지
pytest tests/ --cov=. --cov-report=html
```

현재 테스트: **204 passed**, 10 skipped (chromadb 미설치)

---

## 프로젝트 구조

```
bioauto/
├── main.nf                 # Nextflow DSL2 워크플로우
├── nextflow.config         # Nextflow 설정
├── config.json             # 전역 설정
├── pyproject.toml          # 프로젝트 메타데이터 + 의존성
├── README.md
│
├── core/                   # 핵심 오케스트레이션
│   ├── cli.py              #   Click CLI 진입점 (bioauto 명령)
│   ├── pipeline.py         #   비동기 파이프라인 오케스트레이터
│   ├── pubmed_client.py    #   PubMed API 클라이언트
│   ├── sra_explorer.py     #   SRA 메타데이터 탐색
│   └── progress_manager.py #   체크포인트/재시작
│
├── backends/               # LLM 백엔드 (Ollama, OpenAI, Anthropic)
├── clients/                # 외부 API 클라이언트 (SS, EPMC, TCGA)
├── plugins/                # 시퀀싱 타입 감지 플러그인
├── agents/                 # 멀티 에이전트 토론 (PhD, 학부생, 일반인)
├── enrichment/             # GSEA 경로 분석
├── search/                 # 논문 검색 (4소스 팬아웃)
├── mcp/                    # Brave Search 통합
├── rag/                    # RAG 벡터 DB (ChromaDB)
├── nextflow/               # Nextflow 실행 레이어 (fetchngs, executor)
├── analysis/               # R/Python 다운스트림 분석
│   ├── r_scripts/          #   DESeq2, Seurat, peak analysis
│   └── python_scripts/     #   scanpy
│
├── scripts/                # 유틸리티 스크립트
├── tests/                  # 테스트 (204개)
└── docs/                   # 개발 문서 (아키텍처, 개발 이력)
```

---

## 아키텍처

```
CLI (Click)
  │
  ├── bioauto run ─────────── AsyncPipeline (8+ stages)
  │                              ├── Stage 1: PubMed 메타데이터
  │                              ├── Stage 2: SRA 메타데이터
  │                              ├── Stage 3: 시퀀싱 타입 감지 (Plugin System)
  │                              ├── Stage 3.5: [NEW] nf-core/fetchngs (SRA → FASTQ)
  │                              ├── Stage 3.6: [NEW] nf-core 파이프라인 실행
  │                              ├── Stage 3.7: [NEW] R/Python 다운스트림 분석
  │                              ├── Stage 4: 외부 데이터 통합 (SS + EPMC + TCGA)
  │                              ├── Stage 5: GSEA 경로 분석
  │                              ├── Stage 6: LLM 다중 합의 분석
  │                              ├── Stage 7: 멀티 에이전트 토론
  │                              └── Stage 8: 보고서 + RAG 인덱싱
  │
  ├── bioauto search ─────── TopicSearcher (4소스 팬아웃) → ResultRanker
  │
  ├── bioauto consult ────── LLM 대화 → 쿼리 생성 → search → pipeline
  │
  └── bioauto prereqs ────── 환경 검증 (Nextflow/Docker/R/디스크)
```

---

## License

MIT
