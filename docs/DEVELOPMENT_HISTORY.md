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

## 프로젝트 구조

```
nextflow_automation/
├── cli.py                    # Click CLI 진입점
├── async_pipeline.py         # 비동기 파이프라인 (9 stages)
├── pubmed_client.py          # PubMed API (Biopython Entrez)
├── sra_client.py             # SRA metadata 조회
├── config.json               # 전역 설정
├── pyproject.toml            # 프로젝트 메타데이터
├── requirements.txt          # 의존성
│
├── backends/                 # LLM 백엔드
│   ├── base.py               # LLMResponse, LLMRouter
│   ├── ollama_backend.py     # Ollama (로컬)
│   ├── openai_backend.py     # OpenAI API
│   └── anthropic_backend.py  # Anthropic API
│
├── clients/                  # 외부 API 클라이언트
│   ├── base.py               # ClientResponse 모델
│   ├── semantic_scholar.py   # Semantic Scholar
│   ├── europe_pmc.py         # Europe PMC
│   ├── tcga_gdc.py           # TCGA/GDC
│   └── data_aggregator.py    # 다중 소스 집계
│
├── agents/                   # 다중 에이전트 토론
│   ├── base.py               # AgentRole, AgentResponse, DebateRound
│   ├── debate_agents.py      # 5개 역할 에이전트
│   └── debate_manager.py     # 토론 진행 관리
│
├── enrichment/               # 유전자 경로 분석
│   ├── gsea_analyzer.py      # Enrichr GSEA
│   └── pathway_visualizer.py # 시각화
│
├── search/                   # 주제어 검색 (v3.1.0)
│   ├── topic_searcher.py     # 4소스 팬아웃 검색
│   └── result_ranker.py      # 점수/중복제거/정렬
│
├── mcp/                      # MCP 통합 (v3.1.0)
│   └── brave_client.py       # Brave Search REST 클라이언트
│
├── rag/                      # RAG 벡터 DB (v3.1.0)
│   ├── document_store.py     # ChromaDB 저장소
│   └── rag_context.py        # 컨텍스트 빌더
│
├── sequencing/               # 시퀀싱 타입 감지
│   ├── detector.py           # 메인 감지기
│   ├── registry.py           # 플러그인 레지스트리
│   └── plugins/              # 감지 플러그인
│
├── tests/                    # 테스트
│   ├── conftest.py           # 공통 fixture
│   ├── test_cli.py           # CLI 테스트
│   ├── test_clients.py       # API 클라이언트 테스트
│   ├── test_agents.py        # 에이전트 테스트
│   ├── test_enrichment.py    # 경로 분석 테스트
│   ├── test_search.py        # 검색 테스트 (v3.1.0)
│   ├── test_mcp.py           # MCP 테스트 (v3.1.0)
│   ├── test_rag.py           # RAG 테스트 (v3.1.0)
│   └── ...
│
├── docs/                     # 문서
│   └── DEVELOPMENT_HISTORY.md
│
└── .github/workflows/ci.yml  # CI/CD
```

---

## 의존성

### 필수
```
biopython>=1.80
httpx>=0.24.0
click>=8.0
pydantic>=2.0
rich>=13.0
```

### 선택 (RAG)
```
chromadb>=0.4.0
sentence-transformers>=2.2.0
```

### LLM 백엔드 (하나 이상 필요)
- Ollama (로컬, 무료)
- OpenAI API (`OPENAI_API_KEY`)
- Anthropic API (`ANTHROPIC_API_KEY`)

### 검색 (선택)
- Brave Search API (`BRAVE_API_KEY`)

---

## Git History

| 커밋 | 설명 |
|------|------|
| `a30ab78` | refactor: SRA 모듈 분리 |
| `8b93376` | feat: RNA-seq 분석 파이프라인 |
| `7a2ba8b` | 기존 파일 삭제 |
| `5939291` | Update README.md |
| `df312fc` | feat: bioauto v3.0.0 — 올인원 플랫폼 |
| *(next)* | feat: bioauto v3.1.0 — 검색/상담/Brave/RAG |
