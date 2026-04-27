# bioauto

**하나의 주제를 넣으면 관련 논문·유전체 데이터 수집 → 모델링 → 어노테이션 → 토론 → 아이디어 검증까지 자동으로 해주는 올인원 바이오인포매틱스 연구 자동화 시스템.**

연구 주제나 PMID를 입력하면, 논문 메타데이터 수집부터 시퀀싱 데이터 분석, 다중 LLM 합의, 멀티 에이전트 토론까지 전 과정을 자동 수행하고 HTML 보고서를 생성합니다.

---

## 핵심 기능

| 명령 | 설명 |
|------|------|
| `bioauto run <PMIDs>` | 논문 메타데이터 + LLM 분석 + 토론 → 보고서 생성 |
| `bioauto run <PMIDs> --execute-pipeline` | + 실제 시퀀싱 데이터 다운로드 → nf-core 분석 → R/Python 다운스트림 |
| `bioauto search "키워드"` | 4개 소스 동시 검색 → 선택 → 파이프라인 실행 |
| `bioauto consult` | LLM 상담 → 주제 정제 → 검색 → 파이프라인 |
| `bioauto report --all` | 기존 결과에서 HTML 보고서 재생성 |
| `bioauto web` | 웹 대시보드 서버 시작 (SSE 실시간 모니터링) |
| `bioauto stop` | 실행 중인 모든 서비스 종료 |
| `bioauto stop web` | 웹 서버만 종료 |
| `bioauto stop pipeline` | 파이프라인만 종료 |
| `bioauto prereqs` | 실행 환경 검증 |
| `bioauto backends` | LLM 백엔드 상태 확인 |
| `bioauto setup-slurm` | Slurm HPC 자동 감지 및 설정 |
| `bioauto uninstall` | bioauto 완전 제거 (소스/결과 보존) |

---

## 파이프라인 흐름

```
입력: PMID / 키워드 / 연구 주제
  │
  ├─ Stage 1: PubMed 메타데이터 수집
  ├─ Stage 2: SRA/GEO 메타데이터 수집
  ├─ Stage 3: 시퀀싱 타입 자동 감지 (scRNA-seq / Bulk RNA / ATAC / ChIP)
  │
  │  ┌─ --execute-pipeline 활성화 시 ─────────────────────────┐
  │  │ Stage 3.5: nf-core/fetchngs → SRA 데이터 다운로드       │
  │  │ Stage 3.6: nf-core 파이프라인 실행 (rnaseq/scrnaseq/...) │
  │  │ Stage 3.7: R/Python 다운스트림 분석 (DESeq2/Seurat/...)  │
  │  └──────────────────────────────────────────────────────────┘
  │
  ├─ Stage 4: 외부 데이터 통합 (Semantic Scholar + Europe PMC + TCGA)
  ├─ Stage 5: 유전자 경로 분석 (GSEA/Enrichr)
  ├─ Stage 6: LLM 다중 합의 분석 (모든 백엔드 동시 쿼리)
  ├─ Stage 7: 멀티 에이전트 토론 (PhD · 학부생 · 일반인 3인 패널)
  └─ Stage 8: 보고서 생성 + RAG 인덱싱

출력: results/{PMID}/ 폴더에 JSON + HTML 보고서
      2개 이상 PMID → 종합보고서 (project_report.html) 자동 생성
```

---

## 설치

```bash
# 기본 설치
git clone git@github.com:kerniz/auto_analysis_by_nextflow.git
cd auto_analysis_by_nextflow
pip install -e .

# 개발 환경
pip install -e ".[dev]"

# 전체 기능 (RAG + 분석)
pip install -e ".[all,analysis]"
```

### 선택적 설치

```bash
pip install -e ".[openai]"       # OpenAI 백엔드
pip install -e ".[anthropic]"    # Anthropic 백엔드
pip install -e ".[enrichment]"   # GSEA/경로 분석
pip install -e ".[rag]"          # ChromaDB RAG
pip install -e ".[analysis]"     # scanpy (Python scRNA-seq)
pip install -e ".[web]"          # 웹 대시보드 (FastAPI)
pip install -e ".[tui]"          # TUI 대시보드 (Textual)
```

---

## 요구 사항

### 필수

| 항목 | 최소 버전 |
|------|-----------|
| Python | 3.10+ |

### LLM 백엔드 (하나 이상 필요)

| 백엔드 | 설정 |
|--------|------|
| Ollama (로컬, 무료) | `ollama serve` 후 `ollama pull qwen3:30b` |
| OpenAI | `export OPENAI_API_KEY=sk-...` |
| Anthropic | `export ANTHROPIC_API_KEY=sk-ant-...` |

### 파이프라인 실행 시 추가 필요 (`--execute-pipeline`)

| 항목 | 최소 버전 |
|------|-----------|
| Nextflow | 23.04+ |
| Java | 11+ |
| Docker / Singularity / Apptainer / Podman | - |
| 디스크 공간 | 10GB+ (파이프라인에 따라 50-200GB 권장) |

> **참고**: `--genome` 옵션을 지정하지 않으면 논문 메타데이터에서 organism을 자동 감지하여 genome을 매핑합니다 (15종 지원).

### 다운스트림 분석 시 추가 필요

| R 패키지 | 용도 |
|----------|------|
| DESeq2 | Bulk RNA-seq 차등발현 |
| Seurat | scRNA-seq 클러스터링 |
| ggplot2, pheatmap | 시각화 |

```bash
bioauto prereqs   # 전체 환경 검증
```

---

## 사용법

### 1. 단일 PMID 분석

```bash
bioauto run 40315330
```

→ `results/40315330/` 에 보고서 생성

### 2. 다중 PMID 분석

```bash
bioauto run 40315330 32416070 31061532
```

→ PMID별 개별 보고서 + 종합보고서 (`results/project_report.html`) 생성

### 3. 실제 파이프라인 실행 (Nextflow + R)

```bash
# Docker + GRCh38
bioauto run 40315330 --execute-pipeline

# Singularity + 마우스 게놈
bioauto run 40315330 --execute-pipeline --container-runtime singularity --genome mm10

# 리소스 제한
bioauto run 40315330 --execute-pipeline --max-cpus 8 --max-memory 32.GB
```

### 4. 논문 검색 → 분석

```bash
# 4개 소스 동시 검색 (PubMed, Semantic Scholar, Europe PMC, Brave)
bioauto search "spatial transcriptomics cancer"

# 검색 후 자동 파이프라인 실행
bioauto search "CRISPR screen" --auto-run
```

### 5. 연구 상담 모드

```bash
bioauto consult
```

LLM과 대화하며 연구 주제를 정제 → 검색 쿼리 생성 → 자동 검색 → 파이프라인 연결

### 6. 보고서 재생성

```bash
# 특정 PMID
bioauto report 40315330

# 모든 결과
bioauto report --all
```

### 7. 실행 옵션

```bash
# 토론 비활성화 (빠른 실행)
bioauto run 40315330 --no-debate

# 최소 실행 (토론, 농축, 데이터통합 모두 끄기)
bioauto run 40315330 --no-debate --no-enrichment --no-aggregate

# 환경 확인
bioauto prereqs
bioauto backends
```

---

## 출력 구조

```
results/
├── {PMID}/                        # PMID별 결과 서브폴더
│   ├── final_report_{PMID}.json   # 최종 보고서 (JSON)
│   ├── report_{PMID}.html         # HTML 보고서 (한국어 포함)
│   ├── pubmed_{PMID}.json         # PubMed 캐시
│   ├── sra_exploration_{PMID}.json# SRA 캐시
│   │
│   ├── fetchngs/                  # [--execute-pipeline] FASTQ
│   ├── pipeline/                  # [--execute-pipeline] nf-core 결과
│   └── analysis/                  # [--execute-pipeline] 다운스트림 분석
│
├── project_report.html            # 종합보고서 (2+ PMID 시 자동 생성)
├── execution_summary.json         # 실행 요약
└── progress.json                  # 체크포인트 (재시작용)
```

### 자동 감지 매핑

| 감지된 시퀀싱 | nf-core 파이프라인 | 다운스트림 분석 | 주요 출력 |
|--------------|-------------------|----------------|----------|
| scRNA-seq | nf-core/scrnaseq | Seurat (R) / scanpy (Python) | UMAP, 클러스터 마커 |
| Bulk RNA-seq | nf-core/rnaseq | DESeq2 (R) | DEG 목록, Volcano plot |
| ATAC-seq | nf-core/atacseq | Peak analysis (R) | 차등 피크, 어노테이션 |
| ChIP-seq | nf-core/chipseq | Peak analysis (R) | 차등 피크, 어노테이션 |
| WGS/WES | nf-core/sarek | SnpEff/VEP variant analysis | VCF, variant stats |
| Bisulfite-seq | nf-core/methylseq | Methylation analysis (R) | CpG 통계, DMR |
| CUT&RUN/CUT&Tag | nf-core/cutandrun | Peak analysis (R) | 차등 피크, 어노테이션 |
| RNA-fusion | nf-core/rnafusion | Fusion gene analysis | 융합 유전자 목록 |

---

## 설정

### config.json

```jsonc
{
  // LLM 서버
  "pipeline_config": {
    "llm_server": {
      "url": "http://localhost:11434",
      "model": "qwen3:30b"
    }
  },

  // Nextflow 파이프라인 실행
  "nextflow_execution": {
    "enabled": false,
    "genome": "GRCh38",
    "container_runtime": "docker"
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
  }
}
```

### 환경 변수

| 변수 | 용도 | 필수 |
|------|------|------|
| `OPENAI_API_KEY` | OpenAI 백엔드 | 선택 |
| `ANTHROPIC_API_KEY` | Anthropic 백엔드 | 선택 |
| `BRAVE_API_KEY` | Brave Search 웹 검색 | 선택 |
| `NCBI_EMAIL` | PubMed API | 권장 |

---

## 프로젝트 구조

```
bioauto/
├── core/                   # 핵심 오케스트레이션
│   ├── cli.py              #   Click CLI 진입점
│   ├── pipeline.py         #   비동기 파이프라인 오케스트레이터
│   ├── pubmed_client.py    #   PubMed API 클라이언트
│   ├── sra_explorer.py     #   SRA 메타데이터 탐색
│   ├── report_generator.py #   HTML 보고서 생성기
│   ├── json_utils.py       #   LLM 응답 JSON 파싱
│   └── progress_manager.py #   체크포인트/재시작
│
├── backends/               # LLM 백엔드 (Ollama, OpenAI, Anthropic)
├── plugins/                # 시퀀싱 타입 감지 플러그인
├── agents/                 # 멀티 에이전트 토론 (PhD, 학부생, 일반인)
├── clients/                # 외부 API 클라이언트 (SS, EPMC, TCGA)
├── enrichment/             # GSEA 경로 분석
├── search/                 # 논문 검색 (4소스 팬아웃)
├── mcp/                    # Brave Search 통합
├── rag/                    # RAG 벡터 DB (ChromaDB)
├── nextflow/               # Nextflow 실행 레이어
├── analysis/               # R/Python 다운스트림 분석
│
├── config.json             # 전역 설정
├── pyproject.toml          # 프로젝트 메타데이터 + 의존성
├── nextflow.config         # Nextflow 설정
├── tests/                  # 테스트 (1505개)
└── docs/                   # 아키텍처, 개발 이력
```

---

## 테스트

```bash
pip install -e ".[dev]"

# 전체 테스트
python3 -m pytest tests/ -v

# 특정 모듈
python3 -m pytest tests/test_pipeline.py -v
python3 -m pytest tests/test_report_generator.py -v

# 커버리지
python3 -m pytest tests/ --cov=. --cov-report=html

# 린트
python3 -m ruff check .
```

현재: **1505 passed, 10 skipped** — 커버리지 90%

---

## License

MIT
