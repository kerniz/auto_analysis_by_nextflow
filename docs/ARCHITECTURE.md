# bioauto 아키텍처

## 시스템 개요

```
사용자 입력 (PMID / 키워드 / 상담)
         │
    ┌────▼────┐
    │  CLI    │  core/cli.py (Click)
    └────┬────┘
         │
    ┌────▼──────────────────────────────────────────────────┐
    │  AsyncPipeline (core/pipeline.py)                     │
    │                                                       │
    │  Stage 1: PubMed 메타데이터 ──── core/pubmed_client   │
    │  Stage 2: SRA 메타데이터 ──────── core/sra_explorer    │
    │  Stage 3: 시퀀싱 타입 감지 ────── plugins/             │
    │                                                       │
    │  ┌─ --execute-pipeline 활성화 시 ──────────────────┐  │
    │  │ Stage 3.5: SRA 다운로드 ──── nextflow/fetchngs  │  │
    │  │ Stage 3.6: nf-core 실행 ──── nextflow/executor  │  │
    │  │ Stage 3.7: 다운스트림 분석 ── analysis/          │  │
    │  └─────────────────────────────────────────────────┘  │
    │                                                       │
    │  Stage 4: 외부 데이터 통합 ────── clients/             │
    │  Stage 5: GSEA 경로 분석 ──────── enrichment/         │
    │  Stage 6: LLM 다중 합의 ──────── backends/            │
    │  Stage 7: 멀티 에이전트 토론 ──── agents/              │
    │  Stage 8: 보고서 + RAG ────────── rag/                │
    └───────────────────────────────────────────────────────┘
```

---

## 패키지별 역할

### core/ — 핵심 오케스트레이션

| 파일 | 역할 |
|------|------|
| `cli.py` | Click CLI 진입점. `run`, `search`, `consult`, `prereqs`, `backends`, `plugins`, `status` 명령 |
| `pipeline.py` | `AsyncPipeline` 메인 오케스트레이터. PMID별 8+ 스테이지 비동기 실행 |
| `pubmed_client.py` | Biopython Entrez 기반 PubMed 메타데이터 + 주제 검색 |
| `sra_explorer.py` | SRA/GEO 데이터셋 탐색, SRR accession 추출 |
| `progress_manager.py` | JSON 기반 체크포인트/재시작 관리 |

### backends/ — LLM 백엔드

| 파일 | 역할 |
|------|------|
| `base.py` | `LLMBackend` ABC, `LLMResponse`, `LLMConfig`, `BackendStatus` |
| `ollama_backend.py` | Ollama REST API (로컬 LLM) |
| `openai_backend.py` | OpenAI API (GPT-4 등) |
| `anthropic_backend.py` | Anthropic API (Claude 등) |
| `router.py` | `LLMRouter` — 멀티 백엔드 라우팅, 자동 failover, health check |

### plugins/ — 시퀀싱 타입 감지

| 파일 | 역할 |
|------|------|
| `base.py` | `SequencingPlugin` ABC, `PipelineDefinition`, `PluginRegistry` |
| `scrna_plugin.py` | scRNA-seq 감지 (10x Genomics, Drop-seq, ...) |
| `bulk_rna_plugin.py` | Bulk RNA-seq 감지 |
| `atac_plugin.py` | ATAC-seq 감지 |
| `chipseq_plugin.py` | ChIP-seq 감지 |

### clients/ — 외부 API 클라이언트

| 파일 | 역할 |
|------|------|
| `base.py` | `ClientResponse` 공통 모델 |
| `semantic_scholar_client.py` | Semantic Scholar API (논문 메타데이터, 인용) |
| `europe_pmc_client.py` | Europe PMC API (전문 텍스트, 텍스트 마이닝) |
| `annotation_client.py` | GO, KEGG, Ensembl 어노테이션 |
| `tcga_gdc.py` | TCGA/GDC 암 데이터 |
| `data_aggregator.py` | 다중 소스 데이터 집계 |

### agents/ — 멀티 에이전트 토론

| 파일 | 역할 |
|------|------|
| `base.py` | `AgentRole`, `AgentResponse`, `DebateRound` 모델 |
| `debate_agents.py` | PhD, Undergraduate, Layperson 3인 에이전트 |
| `debate_manager.py` | 토론 진행, 라운드 관리, 가중 점수 합의 도출 |

### search/ — 논문 검색

| 파일 | 역할 |
|------|------|
| `topic_searcher.py` | 4소스 팬아웃 (PubMed + SS + EPMC + Brave) |
| `result_ranker.py` | 가중 점수 + 중복 제거 + 정렬 |

### nextflow/ — Nextflow 실행 레이어

| 파일 | 역할 |
|------|------|
| `config.py` | `NextflowExecutionConfig`, `ContainerRuntime` |
| `samplesheet.py` | nf-core 파이프라인별 samplesheet CSV 생성 |
| `fetchngs.py` | `FetchNGSRunner` — nf-core/fetchngs로 SRA 다운로드 |
| `executor.py` | `NextflowExecutor` — nf-core 파이프라인 실행 |
| `monitor.py` | `PipelineMonitor` — 로그/trace 파싱 |
| `output_parser.py` | `OutputParser` — 파이프라인 출력 파일 탐색 |

### analysis/ — R/Python 다운스트림 분석

| 파일 | 역할 |
|------|------|
| `orchestrator.py` | `AnalysisOrchestrator` — 분석 타입 라우팅 + 인자 매핑 |
| `script_runner.py` | `RScriptRunner`, `PythonScriptRunner` — 비동기 실행 |
| `r_scripts/deseq2_analysis.R` | Bulk RNA-seq DESeq2 차등발현 분석 |
| `r_scripts/seurat_analysis.R` | scRNA-seq Seurat 클러스터링 |
| `r_scripts/peak_analysis.R` | ATAC/ChIP-seq 피크 차등 분석 |
| `python_scripts/scanpy_analysis.py` | scRNA-seq scanpy 대안 (R 없이) |

### 기타 패키지

| 패키지 | 역할 |
|--------|------|
| `enrichment/` | GSEA (Enrichr), 경로 분석, 유전자 스코어링 |
| `mcp/` | Brave Search REST 클라이언트 |
| `rag/` | ChromaDB 벡터 DB + 컨텍스트 빌더 |

---

## 데이터 흐름

### 메타데이터 분석 (`bioauto run <PMID>`)

```
PMID
 → PubMedClient.fetch_paper_metadata()     → 논문 제목, 초록, GEO 링크
 → SRAExplorer.explore_sra_datasets()      → SRR accession, 시퀀싱 메타데이터
 → PluginRegistry.detect()                 → scRNA-seq / Bulk RNA / ATAC / ChIP
 → DataAggregator.aggregate()              → SS + EPMC + TCGA 통합 데이터
 → GSEAAnalyzer.analyze()                  → 유전자 경로 농축 결과
 → LLMRouter.generate()                    → 멀티 백엔드 합의 분석
 → DebateManager.run_debate()              → 3인 패널 토론 + 판정
 → DocumentStore.add_*()                   → RAG 인덱싱
 → results/<PMID>/final_report.json        → 최종 보고서
```

### 파이프라인 실행 (`--execute-pipeline`)

```
SRR accessions
 → FetchNGSRunner.run()                    → FASTQ 다운로드
 → SamplesheetGenerator.generate()         → 파이프라인별 CSV
 → NextflowExecutor.execute_pipeline()     → nf-core 파이프라인 실행
 → OutputParser.find_outputs()             → 핵심 출력 파일 탐색
 → AnalysisOrchestrator.run_analysis()     → R/Python 다운스트림 분석
 → summary.json                            → LLM 프롬프트에 주입
```

### 논문 검색 (`bioauto search`)

```
키워드
 → TopicSearcher.search()                  → 4소스 동시 검색
     ├─ PubMedClient.search_by_topic()
     ├─ SemanticScholarClient.search()
     ├─ EuropePMCClient.search()
     └─ BraveSearchClient.search()
 → ResultRanker.rank()                     → 중복 제거 + 가중 점수 정렬
 → 사용자 선택                              → 파이프라인 실행
```

---

## 설정 구조

### config.json 섹션

| 섹션 | 역할 | 사용 위치 |
|------|------|-----------|
| `pipeline_config` | LLM 서버, SRA 다운로드, 타임아웃 | core/pipeline.py |
| `data_sources` | SS, EPMC, TCGA API 설정 | clients/ |
| `debate` | 토론 라운드 수, 에이전트 가중치 | agents/ |
| `enrichment` | GSEA 유전자셋, FC/padj 임계값 | enrichment/ |
| `brave_search` | Brave API 설정 | mcp/ |
| `rag` | ChromaDB 경로, 임베딩 모델 | rag/ |
| `search` | 소스별 활성화, 소스당 결과 수 | search/ |
| `nextflow_execution` | 게놈, 컨테이너, 리소스 제한 | nextflow/ |
| `analysis` | R 실행 경로, DESeq2/Seurat 파라미터 | analysis/ |
| `sequencing_detection` | 키워드 목록 | plugins/ |

### 환경 변수

| 변수 | 용도 |
|------|------|
| `OPENAI_API_KEY` | OpenAI 백엔드 |
| `ANTHROPIC_API_KEY` | Anthropic 백엔드 |
| `BRAVE_API_KEY` | Brave Search |
| `NCBI_EMAIL` | PubMed API |

---

## 디자인 패턴

| 패턴 | 사용 위치 |
|------|-----------|
| **ABC (Abstract Base Class)** | backends/base.py, clients/base.py, agents/base.py, plugins/base.py |
| **Plugin Registry (Singleton)** | plugins/ — 시퀀싱 타입 감지 플러그인 |
| **Router + Failover** | backends/router.py — 멀티 LLM 자동 전환 |
| **Lazy Import** | core/pipeline.py — 선택 모듈 지연 로드 |
| **Async Subprocess** | nextflow/, analysis/ — asyncio.create_subprocess_exec |
| **Graceful Degradation** | 모든 선택 기능 — 미설치 시 경고 후 스킵 |

---

## 테스트 구조

```
tests/
├── conftest.py                # 공통 fixture
├── test_cli.py                # CLI 명령 테스트
├── test_pipeline_integration.py # 파이프라인 통합 테스트
├── test_backends.py           # LLM 백엔드 테스트
├── test_plugins.py            # 시퀀싱 플러그인 테스트
├── test_clients.py            # API 클라이언트 테스트
├── test_agents.py             # 에이전트 토론 테스트
├── test_enrichment.py         # 경로 분석 테스트
├── test_search.py             # 검색 테스트
├── test_mcp.py                # Brave 테스트
├── test_rag.py                # RAG 테스트
├── test_samplesheet.py        # Samplesheet 생성 테스트
├── test_nextflow.py           # Nextflow 실행 테스트
├── test_output_parser.py      # 출력 파서 테스트
└── test_analysis.py           # 분석 오케스트레이터 테스트
```

**모킹 전략**: 외부 API/프로세스는 모두 mock. `asyncio.create_subprocess_exec`, `shutil.which`, `httpx` mock 사용. `tmp_path`로 파일시스템 테스트.

현재: **975 passed, 10 skipped** (chromadb 미설치) — 커버리지 87%
