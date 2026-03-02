# bioauto Development History

## Project Overview

**bioauto** - 바이오인포매틱스 연구 자동화 플랫폼

PMID 기반 논문 분석, 시퀀싱 타입 감지, LLM 다중 에이전트 토론, 유전자 경로 분석을 통합하는 올인원 CLI 도구.

---

## v3.0.0 — 올인원 바이오인포매틱스 연구 자동화 플랫폼

**릴리스일**: 2026-02-26
**커밋**: `df312fc`

### 배경

기존 프로젝트는 Nextflow 기반의 단순 RNA-seq 파이프라인이었다. v3.0.0에서 전면 재설계하여 Python 기반의 모듈화된 연구 자동화 플랫폼으로 전환했다.

### 구현 (6 Phase)

#### Phase 1: 프로젝트 정리
- 기존 Nextflow/R/Bash 스크립트 정리
- Python 프로젝트 구조 확립 (`pyproject.toml`, `requirements.txt`)
- Click CLI 프레임워크 도입

#### Phase 2: 외부 API 클라이언트 (`clients/`)
| 파일 | 설명 |
|------|------|
| `clients/base.py` | `ClientResponse` 공통 응답 모델 |
| `clients/semantic_scholar.py` | Semantic Scholar API (논문 검색, 메타데이터) |
| `clients/europe_pmc.py` | Europe PMC API (전문 텍스트, 텍스트 마이닝) |
| `clients/tcga_gdc.py` | TCGA/GDC API (암 데이터) |
| `clients/data_aggregator.py` | 다중 소스 데이터 집계 |

#### Phase 3: 다중 에이전트 토론 시스템 (`agents/`)
| 파일 | 설명 |
|------|------|
| `agents/base.py` | `AgentRole`, `AgentResponse`, `DebateRound` 모델 |
| `agents/debate_agents.py` | 5개 역할 에이전트 (PhD, Industry, Statistician, Devil's Advocate, Layperson) |
| `agents/debate_manager.py` | 토론 진행, 라운드 관리, 점수 집계 |

#### Phase 4: 유전자 경로 분석 (`enrichment/`)
| 파일 | 설명 |
|------|------|
| `enrichment/gsea_analyzer.py` | Enrichr API 기반 GSEA 분석 |
| `enrichment/pathway_visualizer.py` | 경로 시각화 |

#### Phase 5: 파이프라인 통합
| 파일 | 변경 |
|------|------|
| `async_pipeline.py` | 8단계 비동기 파이프라인 (SRA→시퀀싱감지→LLM분석→토론→리포트) |
| `cli.py` | `run`, `status`, `backends`, `plugins` 명령 |
| `config.json` | 전역 설정 (LLM 백엔드, 파이프라인 옵션) |

#### Phase 6: 테스트 & CI
- `tests/` 디렉토리: 102개 테스트 (전체 패스)
- `.github/workflows/ci.yml`: GitHub Actions CI/CD
- `pytest.ini`: 테스트 설정

### 아키텍처

```
CLI (Click) → AsyncPipeline → 8 Stages:
  1. PubMed metadata fetch
  2. SRA metadata fetch
  3. External data aggregation (SS + EPMC + TCGA)
  4. Sequencing type detection (plugin system)
  5. Gene enrichment analysis (GSEA)
  6. LLM consensus analysis
  7. Multi-agent debate
  8. Report generation
```

### 핵심 기술
- **비동기 파이프라인**: `asyncio.gather`로 다중 PMID 동시 처리
- **플러그인 시스템**: 시퀀싱 타입 감지를 플러그인으로 확장 가능
- **LLM 라우팅**: Ollama, OpenAI, Anthropic 백엔드 자동 라우팅
- **다중 에이전트 토론**: 5개 전문가 역할이 2라운드 토론 후 합의 도출

---

## v3.1.0 — 주제어 검색, 상담 모드, Brave Search, RAG 자동 구축

**릴리스일**: 2026-02-26

### 배경

v3.0.0은 PMID를 직접 입력해야만 파이프라인을 실행할 수 있었다. 사용자가 연구 주제만 알고 있을 때 논문을 발견하고 선택하여 분석까지 이어지는 워크플로우가 필요했다.

### 새로운 기능

#### 1. 주제어 검색 (`bioauto search`)
```bash
bioauto search "spatial transcriptomics cancer" --limit 20
```
- 4개 소스 동시 팬아웃 검색: PubMed, Semantic Scholar, Europe PMC, Brave Search
- 가중 점수 기반 순위: 인용수(40%) + 검색순위(35%) + 최신성(15%) + 소스중복도(10%)
- PMID 기반 중복 제거 및 소스 병합
- 대화형 결과 선택 → 파이프라인 즉시 실행

#### 2. 상담 모드 (`bioauto consult`)
```bash
bioauto consult
```
- LLM 기반 연구 상담 대화
- 4단계 상태 머신: GREETING → REFINEMENT → SUGGESTION → HANDOFF
- 연구 주제 정제 → 검색 쿼리 자동 생성 → 검색 → 파이프라인 연결

#### 3. Brave Search 통합 (`mcp/`)
- Brave Search Web API REST 클라이언트
- `BRAVE_API_KEY` 환경변수 기반 (없으면 graceful degradation)
- 학술 검색 보완을 위한 웹 검색 결과 제공

#### 4. RAG 자동 구축 (`rag/`)
- ChromaDB 벡터 DB + `all-MiniLM-L6-v2` 임베딩
- 3가지 문서 타입 자동 인덱싱: 논문 초록, LLM 분석 결과, 토론 보고서
- 파이프라인 실행 시 자동 축적 (Stage 9)
- 후속 분석에서 RAG 컨텍스트 자동 주입

### 구현 (6 Phase)

#### Phase 1: 기반
| 파일 | 변경 |
|------|------|
| `pubmed_client.py` | `search_by_topic()` 추가 — `Entrez.esearch` 기반 주제 검색 |
| `mcp/__init__.py` | MCP 패키지 초기화 |
| `mcp/brave_client.py` | Brave Search REST 클라이언트 (httpx) |
| `config.json` | `brave_search`, `rag`, `search` 섹션 추가 |

#### Phase 2: 검색 레이어 (`search/`)
| 파일 | 설명 |
|------|------|
| `search/__init__.py` | 패키지 초기화, 공개 API |
| `search/topic_searcher.py` | `TopicSearcher` — 4소스 팬아웃, `asyncio.gather` |
| `search/result_ranker.py` | `ResultRanker` — 중복제거, 가중점수, 정렬 |

#### Phase 3: RAG 레이어 (`rag/`)
| 파일 | 설명 |
|------|------|
| `rag/__init__.py` | 패키지 초기화 |
| `rag/document_store.py` | `DocumentStore` — ChromaDB persistent vector DB, lazy init |
| `rag/rag_context.py` | `RAGContext` — LLM 프롬프트용 컨텍스트 빌더 |

#### Phase 4: 파이프라인 통합
| 파일 | 변경 |
|------|------|
| `async_pipeline.py` | `PipelineConfig.rag_dir` 추가, Stage 9 RAG 인덱싱, RAG 컨텍스트 주입 |

#### Phase 5: CLI 통합
| 파일 | 변경 |
|------|------|
| `cli.py` | `search` 명령, `consult` 명령, `_run_search()`, `_run_consult()` 추가 |

#### Phase 6: 테스트
| 파일 | 설명 |
|------|------|
| `tests/test_search.py` | TopicSearcher, ResultRanker 테스트 (13개) |
| `tests/test_mcp.py` | BraveSearchClient 테스트 (6개) |
| `tests/test_rag.py` | DocumentStore, RAGContext 테스트 (12개, chromadb 필요) |
| `tests/conftest.py` | `sample_search_results` fixture 추가 |
| `tests/test_cli.py` | search, consult 명령 테스트 추가 |

### 테스트 결과
```
139 passed, 10 skipped (chromadb not installed), 0 failed
```

### 파이프라인 흐름 (After v3.1.0)
```
사용법 1: bioauto run <PMIDs>         → 기존 8단계 파이프라인 + RAG 인덱싱
사용법 2: bioauto search "키워드"     → 4소스 검색 → 순위 → 선택 → 파이프라인
사용법 3: bioauto consult             → LLM 상담 → 주제 정제 → 검색 → 파이프라인
```

---

## v4.0.0 — Nextflow 파이프라인 실행 + R/Python 다운스트림 분석

**릴리스일**: 2026-02-26

### 배경

v3.1.0까지는 논문 메타데이터 분석만 수행했다. 실제 시퀀싱 데이터를 다운로드하고 nf-core 파이프라인을 실행하여 R/Python으로 다운스트림 분석까지 수행하는 **실행 레이어**가 없었다.

### 새로운 기능

#### 1. SRA 데이터 다운로드 (`nextflow/fetchngs.py`)
- `nf-core/fetchngs` 파이프라인으로 SRR accession → FASTQ 자동 다운로드
- accession 목록 → CSV → `nextflow run nf-core/fetchngs`
- 비동기 실행 (`asyncio.create_subprocess_exec`)

#### 2. nf-core 파이프라인 실행 (`nextflow/executor.py`)
- 4개 nf-core 파이프라인 지원: rnaseq, scrnaseq, atacseq, chipseq
- prerequisite 체크: Nextflow, Java, Docker/Singularity, 디스크 공간
- 자동 samplesheet 생성 (`nextflow/samplesheet.py`)
  - 5개 파이프라인별 CSV 포맷 (rnaseq, scrnaseq, atacseq, chipseq, sarek)
  - FASTQ 경로 자동 해석 (flat + subdirectory)
- 출력 파싱 (`nextflow/output_parser.py`)
  - 파이프라인별 glob 패턴으로 핵심 출력 파일 탐색

#### 3. 실행 모니터링 (`nextflow/monitor.py`)
- `.nextflow.log` 실시간 파싱 → 프로세스 진행률
- `trace.txt` 파싱 → 리소스 사용량

#### 4. R/Python 다운스트림 분석 (`analysis/`)
| 분석 타입 | 스크립트 | 용도 |
|-----------|---------|------|
| `deseq2` | `r_scripts/deseq2_analysis.R` | Bulk RNA-seq 차등발현 |
| `seurat` | `r_scripts/seurat_analysis.R` | scRNA-seq 클러스터링 |
| `peak_diff` | `r_scripts/peak_analysis.R` | ATAC/ChIP-seq 피크 분석 |
| `scanpy` | `python_scripts/scanpy_analysis.py` | scRNA-seq (R 없이) |

- `AnalysisOrchestrator`: nf-core 출력 → 분석 스크립트 인자 자동 매핑
- Seurat → scanpy 자동 폴백 (R 미설치 + scanpy_enabled=True)
- 모든 스크립트 `summary.json` 출력 → Python에서 파싱

#### 5. 파이프라인 통합
- `--execute-pipeline` 플래그 (기본 OFF, 안전)
- 3개 새 스테이지 삽입: Stage 3.5 (fetchngs) → 3.6 (nf-core) → 3.7 (다운스트림 분석)
- LLM 분석 프롬프트에 실제 분석 결과 주입
- `bioauto prereqs` 명령으로 환경 검증

### 구현 (6 Phase)

#### Phase 1: Config + Samplesheet + Plugin
| 파일 | 설명 |
|------|------|
| `nextflow/__init__.py` | 패키지 초기화 |
| `nextflow/config.py` | `NextflowExecutionConfig`, `ContainerRuntime` |
| `nextflow/samplesheet.py` | `SamplesheetGenerator` — 5개 파이프라인 CSV |
| `plugins/base.py` | `PipelineDefinition.analysis_type` 필드 추가 |
| `plugins/*_plugin.py` | analysis_type 설정 (deseq2, seurat, peak_diff) |

#### Phase 2-3: Nextflow 실행 레이어
| 파일 | 설명 |
|------|------|
| `nextflow/fetchngs.py` | `FetchNGSRunner` — SRA 다운로드 |
| `nextflow/executor.py` | `NextflowExecutor` — 파이프라인 실행 |
| `nextflow/monitor.py` | `PipelineMonitor` — 로그/trace 파싱 |
| `nextflow/output_parser.py` | `OutputParser` — 출력 파일 탐색 |

#### Phase 4: R/Python 분석
| 파일 | 설명 |
|------|------|
| `analysis/__init__.py` | 패키지 초기화 |
| `analysis/orchestrator.py` | `AnalysisOrchestrator` — 라우팅 + 인자 매핑 |
| `analysis/script_runner.py` | `RScriptRunner`, `PythonScriptRunner` |
| `analysis/r_scripts/*.R` | DESeq2, Seurat, peak analysis (3개) |
| `analysis/python_scripts/*.py` | scanpy 분석 |

#### Phase 5: 통합
| 파일 | 변경 |
|------|------|
| `async_pipeline.py` | PMIDResult/PipelineConfig 확장, 3개 새 스테이지, LLM 프롬프트 강화 |
| `cli.py` | v4.0.0, `--execute-pipeline`, `--genome`, `--container-runtime`, `prereqs` 명령 |
| `config.json` | `nextflow_execution`, `analysis` 섹션 |
| `pyproject.toml` | v4.0.0, analysis optional deps |

#### Phase 6: 테스트
| 파일 | 테스트 |
|------|--------|
| `tests/test_samplesheet.py` | 16개 — samplesheet 생성 검증 |
| `tests/test_nextflow.py` | 19개 — config, fetchngs, executor, monitor |
| `tests/test_output_parser.py` | 9개 — 출력 파서 패턴 매칭 |
| `tests/test_analysis.py` | 21개 — 오케스트레이터, 스크립트 러너 |

### 테스트 결과
```
204 passed, 10 skipped (chromadb not installed), 0 failed
```

### 파이프라인 흐름 (After v4.0.0)
```
사용법 1: bioauto run <PMIDs>                    → 기존 메타데이터 분석
사용법 2: bioauto run <PMIDs> --execute-pipeline  → 메타데이터 + 실제 파이프라인 실행
           Stage 1-3: PubMed → SRA → 시퀀싱 감지
           Stage 3.5: [NEW] nf-core/fetchngs → FASTQ 다운로드
           Stage 3.6: [NEW] nf-core 파이프라인 실행
           Stage 3.7: [NEW] R/Python 다운스트림 분석
           Stage 4-8: 데이터집계 → LLM분석(+실제 결과) → 토론 → RAG
사용법 3: bioauto prereqs                         → 환경 검증
```

---

## v4.0.1 — 프로젝트 구조 리팩토링

**릴리스일**: 2026-02-27

### 변경 사항

1. **core/ 패키지 생성** — 루트 Python 파일을 `core/`로 이동
   - `cli.py` → `core/cli.py`
   - `async_pipeline.py` → `core/pipeline.py`
   - `pubmed_client.py` → `core/pubmed_client.py`
   - `sra_explorer.py` → `core/sra_explorer.py`
   - `progress_manager.py` → `core/progress_manager.py`

2. **레거시 삭제** — 미사용 파일 제거
   - `deepseek_analyzer.py`, `sequencing_detector.py`, `report_generator.py`, `nextflow_manager.py`
   - `Dockerfile`, `docker-compose.yml` (opencode 전용)
   - `opencode.json`, `pytest.ini`, `requirements.txt`, `requirements-dev.txt`

3. **파일 정리**
   - 개발 문서 → `docs/` (AGENTS.md, DEVELOPMENT_PLAN.md)
   - 유틸리티 스크립트 → `scripts/`
   - 런타임 아티팩트 `.gitignore` 추가 (`results/`, `charts/`, `progress.json`)

4. **docs/ARCHITECTURE.md** 신규 — 전체 아키텍처 문서

---

## 프로젝트 구조 (현재)

> 상세: [docs/ARCHITECTURE.md](ARCHITECTURE.md)

```
bioauto/
├── main.nf                 # Nextflow DSL2 워크플로우
├── nextflow.config         # Nextflow 설정
├── config.json             # 전역 설정
├── pyproject.toml          # 프로젝트 메타데이터 + 의존성
│
├── core/                   # 핵심 오케스트레이션
├── backends/               # LLM 백엔드 (Ollama, OpenAI, Anthropic)
├── clients/                # 외부 API 클라이언트
├── plugins/                # 시퀀싱 감지 플러그인
├── agents/                 # 멀티 에이전트 토론
├── enrichment/             # GSEA 경로 분석
├── search/                 # 논문 검색 (4소스)
├── mcp/                    # Brave Search
├── rag/                    # RAG 벡터 DB
├── nextflow/               # Nextflow 실행 레이어
├── analysis/               # R/Python 다운스트림 분석
├── scripts/                # 유틸리티 스크립트
├── tests/                  # 테스트 (204개)
└── docs/                   # 개발 문서
```

---

## v4.1.0 — Slurm HPC + 입력검증 보안 + 프로젝트 격리 + 7인 에이전트

**릴리스일**: 2026-02-27
**커밋**: `cabdc52`

### 변경 사항

- Slurm HPC executor 지원 (nextflow_execution.slurm 설정)
- 입력 검증 보안 강화 (PMID 형식, 파일 경로 등)
- 프로젝트 격리 구조 (`research_projects/` 디렉토리)
- 7인 팀 에이전트 구성 (`.claude/agents/`)

---

## v4.1.1 — config.json 전체 연결 + lint 전량 수정 + 테스트 커버리지 87%

**릴리스일**: 2026-02-28
**커밋**: `2f81bf0`

### 변경 사항

- PipelineConfig에 9개 설정 클래스 추가 — config.json 전 섹션 파싱
  - `LLMServerConfig`, `DebateSettings`, `EnrichmentSettings`, `DirectoriesConfig` 등
- AsyncPipeline.initialize() 하드코딩 제거, config 값으로 대체
- Ollama 서버 `REDACTED-HOST-X86:11435`, timeout 72시간 설정
- ruff lint **1,365개 → 0개** 전량 수정
- 테스트 **233개 → 975개** (+742), 전체 커버리지 **46% → 87%**
- 89개 파일 변경, +11,267줄 추가
- GSE185440 dry-run 테스트 스크립트 추가

### 커버리지 약점 (개선 필요)

| 모듈 | 커버리지 | 미커버 라인 |
|------|---------|------------|
| `core/cli.py` | 66% | 148줄 |
| `core/pipeline.py` | 68% | 187줄 |
| `search/topic_searcher.py` | 74% | 30줄 |
| `nextflow/executor.py` | 76% | 33줄 |

---

## v4.1.2 — Debate JSON 파싱 강화 + Slurm HPC 부하 체크 (2026-03-02)

**릴리스일**: 2026-03-02
**커밋**: `4e4155c`

### 배경

v4.1.1에서 PMID 31061532 토론 실행 시 debate score가 0.21(FAIL)로 떨어지는 문제가 발생했다. qwen3 모델의 `<think>` 태그가 JSON 응답에 섞이고, 깨진 JSON 응답이 파싱 실패를 유발했다. 또한 Ollama 서버가 동시 요청으로 과부하 상태에 빠지는 문제도 있었다.

### 변경 사항

#### 1. agents/base.py — qwen3 호환성 + JSON 복구
- `_strip_think_tags()` 메서드 추가 — qwen3의 `<think>...</think>` 태그를 LLM 응답에서 자동 제거
- `_repair_json()` 메서드 추가 — 깨진 JSON 복구 (미종결 문자열, trailing comma, 미닫힌 괄호)
- LLM 프롬프트에 `/no_think` 접미사 추가 — qwen3 thinking 모드 비활성화

#### 2. agents/debate_manager.py — 합의 계산 완화
- 파싱 실패 응답도 점수 계산에 포함하도록 confidence 필터 완화
- 기존: 파싱 실패 시 응답 제외 → 유효 응답 부족으로 합의 불가
- 변경: 파싱 실패 응답에 기본 점수 부여 → 합의 도출 가능

#### 3. backends/ollama_backend.py — format kwargs 전달
- `generate()` 메서드에 format kwargs passthrough 지원 추가
- 호출자가 응답 형식(JSON 등)을 명시적으로 지정 가능

#### 4. config.json — 병렬 평가 비활성화
- `parallel_assessment: false` 변경 — Ollama 서버 과부하 방지
- 순차 실행으로 안정성 확보

#### 5. core/pipeline.py — 데이터 매핑 수정 + HPC 부하 체크
- `research_data` 키 매핑 수정: `paper` → `paper_info` (기존 코드와 일관성)
- `_wait_for_hpc_idle()` 메서드 추가 — `squeue`/`sinfo`로 Slurm HPC 노드 부하를 확인하고 유휴 상태가 될 때까지 대기 후 토론 시작

#### 6. 결과
- **Debate score**: 0.21 (FAIL) → 0.70 (WARN) — PMID 31061532 기준
- JSON 파싱 성공률 대폭 향상
- HPC 환경에서 안정적인 토론 실행 보장

---

## v4.1.3 — HTML 리포트 생성기 + 테스트 1000개 (2026-03-02)

### 커밋: `411668c`

### 변경 사항
1. **core/report_generator.py** (신규): 자체 포함 HTML 리포트 생성기
   - 인라인 CSS, 반응형 디자인, XSS 방지 (html.escape)
   - 논문정보, 시퀀싱 감지, SRA, 데이터소스, Enrichment, LLM 분석, 토론 라운드별 상세, 파이프라인 실행 섹션
   - 점수 바, 배지(PASS/WARN/FAIL), 접기(details) 지원
   - generate(), generate_from_json(), generate_summary() 3가지 API

2. **core/cli.py**: `bioauto report` CLI 명령 추가
   - `bioauto report 31061532` — 단일 PMID
   - `bioauto report --all` — 모든 결과에서 생성
   - 2개 이상이면 report_summary.html 자동 생성

3. **core/pipeline.py**: _save_pmid_result() 후 HTML 리포트 자동 생성

4. **tests/test_report_generator.py**: 24개 테스트 추가 (976→1000 passed)

---

## v4.1.4 — Slurm 통합 테스트 + 커버리지 89% + 리팩토링 (2026-03-02)

**릴리스일**: 2026-03-02
**커밋**: `5779e4d`

### 배경

v4.1.3까지 Slurm HPC 연동 코드(`_wait_for_hpc_idle`, `_get_slurm_cpu_alloc_ratio`)가 실제 squeue/sinfo 명령을 직접 호출하는 구조여서 테스트 환경에서 검증이 불가능했다. 또한 `strip_think_tags`, `repair_json` 등 JSON 유틸리티 함수가 `agents/base.py`에 중복 구현되어 있었고, `_fetch_pubmed`/`_explore_sra` 등 블로킹 I/O가 이벤트 루프를 점유하는 문제가 남아 있었다.

### 변경 사항

#### 1. core/json_utils.py (신규) — 공유 JSON 유틸리티
- `strip_think_tags()`: qwen3 `<think>...</think>` 태그 제거
- `repair_json()`: 깨진 JSON 복구 (미종결 문자열, trailing comma, 미닫힌 괄호)
- `extract_json_from_llm()`: LLM 응답에서 JSON 블록 추출 (코드펜스 제거 포함)
- agents/base.py의 중복 구현을 이 모듈로 통합

#### 2. nextflow/executor.py — Slurm 라이브 통합 테스트 대응
- `_wait_for_hpc_idle()`: squeue/sinfo 호출 부분을 내부 메서드로 분리하여 mock 가능하도록 리팩토링
- `_get_slurm_cpu_alloc_ratio()`: CPU 할당률 계산 로직 단위 테스트 10개 추가
- 실제 Slurm 환경 유무에 따라 자동 스킵하는 통합 테스트 추가

#### 3. core/pipeline.py — 블로킹 해소 + 로깅 전환
- `_fetch_pubmed()`: `asyncio.to_thread()` 적용 — Biopython Entrez 블로킹 호출을 스레드 풀로 오프로드
- `_explore_sra()`: `asyncio.to_thread()` 적용 — pandas DataFrame 처리 블로킹 해소
- `print()` 전량 → `logger.info()`/`logger.warning()`/`logger.error()` 전환

#### 4. backends/router.py — 로깅 전환
- `print()` 전량 → `logger` 전환
- 백엔드 선택, 폴백, 오류 등 모든 진단 출력을 로그로 통일

#### 5. 커버리지 개선

| 모듈 | v4.1.3 | v4.1.4 | 개선 |
|------|--------|--------|------|
| `core/pipeline.py` | 64% | 80% | +16%p |
| `core/cli.py` | 65% | 73% | +8%p |
| `nextflow/executor.py` | 76% | 98% | +22%p |
| `search/topic_searcher.py` | 74% | 89% | +15%p |
| 전체 | 86% | 89% | +3%p |

#### 6. 테스트 현황

- 테스트 수: **1000 → 1095 passed** (+95개)
- Slurm 단위 테스트: `_wait_for_hpc_idle`, `_get_slurm_cpu_alloc_ratio` 각 5개 (총 10개)
- json_utils 테스트: `strip_think_tags`, `repair_json`, `extract_json_from_llm` 커버
- pipeline asyncio.to_thread 경로 테스트 추가

---

## v4.1.5 — LLM 안정성 강화 + JSON 파싱 완성 (2026-03-02)

**릴리스일**: 2026-03-02
**커밋**: `94291c8`

### 배경

v4.1.4까지 동시 PMID 처리 시 LLM 요청이 경합하여 qwen3:30b 단일 GPU가 과부하 상태에 빠지는 문제가 있었다. Ollama가 빈 응답을 반환해도 성공으로 처리되어 이후 파이프라인이 빈 데이터로 진행되었다. 또한 `debate_report` 전체 데이터가 `final_report.json`에 저장되지 않는 버그가 있었고, `agents/base.py`에 남아 있던 중복 JSON 파싱 로직도 제거가 필요했다.

### 변경 사항

#### 1. core/pipeline.py — LLM 세마포어 + 버그 수정
- `_llm_semaphore = asyncio.Semaphore(1)` 추가 — Stage 6(LLM 합의 분석)과 Stage 7(토론)을 동일 세마포어로 감싸 동시 PMID 처리 시 LLM 경합 방지
- `_save_pmid_result()` 버그 수정: `debate_report` 전체 데이터가 `final_report.json`에 저장되지 않던 문제 수정
- `max_tokens` 설정값 2000 → 4096으로 상향

#### 2. backends/base.py — generate_with_retry 재시도 로직 강화
- 기존: `success=False` 응답을 성공으로 간주하여 즉시 반환
- 변경: `success=False` 응답도 재시도 대상으로 처리
- 지수 백오프 위치 수정 — 예외 발생과 `success=False` 양쪽 모두 적용

#### 3. backends/ollama_backend.py — 빈 응답 감지
- `response` 필드가 비어 있을 경우 `success=False` 반환하여 재시도 유도
- 비동기(`_async_generate`)와 동기(`_sync_generate`) 양쪽 모두 적용
- 빈 응답 발생 시 model명, prompt_eval_count를 포함하여 `logger.warning` 기록

#### 4. core/json_utils.py — 파싱 견고성 강화
- `strip_think_tags()`: 닫히지 않은 `<think>` 태그 처리 추가 (`<think>` 이후 응답 끝까지 제거)
- `repair_json()`: 문자열 내 이스케이프 처리 개선 — 이스케이프 시퀀스(`\\`)를 올바르게 인식하여 괄호 균형 계산 오류 방지, 제어 문자 제거 추가
- `_find_balanced_json()` 신규 추가 — 중첩 `{}` 를 문자열 컨텍스트를 고려하여 올바르게 매칭, LLM 응답 중간에 삽입된 텍스트에서 JSON 블록 정밀 추출

#### 5. agents/base.py — extract_json_from_llm 공유 유틸 사용
- 기존 중복 JSON 파싱 로직(`_strip_think_tags`, `_repair_json`, `re.search`) 제거
- `core/json_utils.extract_json_from_llm()` 단일 호출로 대체
- 파싱 실패 시 raw 응답 내용을 `logger.debug`로 기록 (진단 지원)
- `import re` 제거 — 불필요 의존성 정리

#### 6. print() → logger 전환 완료
- `core/pipeline.py`: 모든 `print()` → `logger.info/warning/error`
- `backends/ollama_backend.py`: `logging` 모듈 추가, 빈 응답 경고 로깅

### 테스트 현황

- 테스트 수: **1095 → 1109 passed** (+14개)
- `tests/test_json_utils.py`: `_find_balanced_json`, 닫히지 않은 think 태그, 이스케이프 처리 케이스 추가
- `tests/test_pipeline.py`: `_llm_semaphore`, `debate_report` 저장, `max_tokens=4096` 케이스 추가
- 커버리지: **89% → 90%**

---

## Git History

| 커밋 | 설명 |
|------|------|
| `a30ab78` | refactor: SRA 모듈 분리 |
| `8b93376` | feat: RNA-seq 분석 파이프라인 |
| `7a2ba8b` | 기존 파일 삭제 |
| `5939291` | Update README.md |
| `df312fc` | feat: bioauto v3.0.0 — 올인원 플랫폼 |
| `32ac6d1` | feat: bioauto v3.1.0 — 검색/상담/Brave/RAG |
| `117d4f6` | feat: bioauto v4.0.0 — Nextflow 실행 + R/Python 분석 |
| `c992053` | chore: opencode 관련 파일 삭제 |
| `4bb8bb8` | refactor: 프로젝트 구조 정리 |
| `d0b2445` | fix: CI pyproject.toml 전환, coverage 확장 |
| `46466ce` | refactor: core/ 패키지 이동 |
| `cabdc52` | feat: Slurm HPC + 입력검증 + 프로젝트 격리 + 7인 에이전트 |
| `207056b` | feat: 류마티스-봉독 유전체 탐색 + Anthropic 모델 업데이트 |
| `2f81bf0` | refactor: config.json 전체 연결 + lint 전량 수정 + 커버리지 87% |
| `f9679a3` | docs: CLAUDE.md 개선 + 개발 이력 동기화 |
| `297db5b` | fix: /workspace 하드코딩 제거 + config.json 자동 로드 + PubMed JSON 파싱 수정 |
| `4e4155c` | fix: debate JSON 파싱 강화 + Slurm HPC 부하 체크 + 토론 점수 0.21→0.70 |
| `411668c` | feat: HTML 리포트 생성기 + CLI report 명령 + 테스트 1000개 달성 |
| `3633c92` | docs: v4.1.3 HTML 리포트 생성기 개발 이력 추가 |
| `5779e4d` | feat: Slurm 통합 테스트 + 커버리지 89% + 리팩토링 (v4.1.4) |
| `83bc799` | docs: v4.1.4 Slurm 통합 테스트 + 커버리지 89% 개발 이력 추가 |
| `94291c8` | fix: debate JSON 파싱 강화 + LLM 동시 요청 방지 + 빈 응답 재시도 (v4.1.5) |
