# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 프로젝트

**bioauto** — PMID 기반 논문 분석 → SRA 탐색 → 시퀀싱 타입 감지 → 다중 LLM 합의 → 멀티 에이전트 토론 → nf-core 파이프라인 실행 → R/Python 다운스트림 분석까지 자동화하는 올인원 바이오인포매틱스 CLI 플랫폼.

## 개발 명령어

```bash
# 테스트 (전체)
python3 -m pytest tests/ -v

# 테스트 (단일 파일)
python3 -m pytest tests/test_backends.py -v

# 테스트 (단일 함수)
python3 -m pytest tests/test_backends.py::TestOllamaBackend::test_generate -v

# 커버리지 (전 모듈)
python3 -m pytest tests/ --cov=backends --cov=plugins --cov=clients --cov=agents --cov=enrichment --cov=search --cov=mcp --cov=rag --cov=nextflow --cov=analysis --cov=core -v

# 린트
python3 -m ruff check .

# 린트 자동 수정
python3 -m ruff check . --fix

# 타입 체크
python3 -m mypy core/ backends/ plugins/ --ignore-missing-imports

# CLI 실행
python3 -m core.cli run <PMIDs>
```

## 아키텍처

### 파이프라인 흐름 (core/pipeline.py: AsyncPipeline)

```
CLI (core/cli.py — Click)
  └─ AsyncPipeline.process_pmid() — PMID별 8+ 스테이지 비동기 실행
       Stage 1: PubMed 메타데이터      ← core/pubmed_client.py (Biopython Entrez)
       Stage 2: SRA 메타데이터          ← core/sra_explorer.py (pandas)
       Stage 3: 시퀀싱 타입 감지         ← plugins/ (ABC + Registry 패턴)
       Stage 3.5: SRA 다운로드           ← nextflow/fetchngs.py [--execute-pipeline]
       Stage 3.6: nf-core 파이프라인     ← nextflow/executor.py [--execute-pipeline]
       Stage 3.7: R/Python 분석          ← analysis/ [--execute-pipeline]
       Stage 4: 외부 데이터 통합          ← clients/ (SS + EPMC + TCGA + Annotation)
       Stage 5: GSEA 경로 분석           ← enrichment/
       Stage 6: LLM 다중 합의 분석       ← backends/ (Router → Ollama/OpenAI/Anthropic)
       Stage 7: 멀티 에이전트 토론       ← agents/ (PhD/Undergraduate/Layperson 3인)
       Stage 8: 보고서 + RAG 인덱싱      ← rag/ (ChromaDB)
```

### 핵심 디자인 패턴

- **ABC + Plugin Registry**: `backends/base.py`, `plugins/base.py`, `clients/base.py`, `agents/base.py` — 새 구현은 반드시 추상 클래스 상속 후 레지스트리 등록
- **Router + Failover**: `backends/router.py` — 멀티 LLM 백엔드 라우팅, 장애 시 자동 전환
- **Lazy Import + Graceful Degradation**: optional 모듈(`chromadb`, `openai`, `anthropic`, `scanpy`)은 try/except로 지연 로드, 미설치 시 경고 후 스킵
- **Async Subprocess**: `nextflow/`, `analysis/` — `asyncio.create_subprocess_exec`로 Nextflow/R/Python 외부 프로세스 실행

### 설정 연결 (config.json → PipelineConfig)

`core/pipeline.py`의 `PipelineConfig` 클래스가 `config.json`의 9개 섹션을 Pydantic-style dataclass로 파싱:
- `pipeline_config` → `LLMServerConfig` (Ollama URL/모델/타임아웃)
- `debate` → `DebateSettings` (라운드 수, 에이전트 가중치)
- `enrichment` → `EnrichmentSettings` (GSEA 임계값)
- `nextflow_execution` → `NextflowExecutionConfig` (게놈, 컨테이너, Slurm)
- `analysis`, `data_sources`, `search`, `rag`, `directories` → 각각의 설정 클래스

## 필수 규칙

1. **ABC 패턴**: 새 백엔드/플러그인/클라이언트는 반드시 추상 클래스 상속
2. **async/await**: 모든 I/O 작업은 비동기 (httpx 사용)
3. **Graceful degradation**: optional 기능 미설치 시 skip (try/except ImportError)
4. **Pydantic v2**: 데이터 모델은 Pydantic 2.0+ 문법
5. **환경변수**: API 키는 절대 하드코딩 금지 (OPENAI_API_KEY, ANTHROPIC_API_KEY, BRAVE_API_KEY)
6. **테스트 격리**: 외부 API/프로세스 호출은 반드시 mock (`httpx`, `asyncio.create_subprocess_exec`, `shutil.which`)
7. **ruff lint**: `python3 -m ruff check .` 0 warning 유지 (line-length=100, ignore E501)

## 테스트 현황

- **975 passed, 10 skipped** (chromadb 미설치 시 skip)
- **커버리지 87%**
- asyncio_mode = "auto" (pyproject.toml)
- 모든 비동기 테스트는 `@pytest.mark.asyncio` 자동 적용

## 팀 에이전트 (7인)

| 에이전트 | 파일 | 담당 |
|----------|------|------|
| orchestrator | `.claude/agents/orchestrator.md` | 아키텍처 설계, 태스크 분배 |
| pipeline-dev | `.claude/agents/pipeline-dev.md` | core/ plugins/ nextflow/ analysis/ |
| backend-dev | `.claude/agents/backend-dev.md` | backends/ clients/ agents/ search/ mcp/ rag/ enrichment/ |
| tester | `.claude/agents/tester.md` | tests/ 커버리지, 회귀 테스트 |
| reviewer-docs | `.claude/agents/reviewer-docs.md` | 코드 리뷰 + 문서화 + CLAUDE.md 유지 |
| infra-dev | `.claude/agents/infra-dev.md` | Docker/Singularity/Slurm/HPC/nextflow.config |
| bio-researcher | `.claude/agents/bio-researcher.md` | nf-core 파라미터 자문, 분석 전략 |

## 문서 관리

- `docs/ARCHITECTURE.md` — 전체 아키텍처, 패키지별 역할, 데이터 흐름
- `docs/DEVELOPMENT_HISTORY.md` — 버전별 개발 이력 (v3.0 → v4.0 → 현재)
- 코드 변경 시 reviewer-docs 에이전트가 docs/ 동기화 담당

## 설정 파일

- `config.json` — 런타임 설정 (LLM, 파이프라인, 분석, 토론, Slurm 등)
- `pyproject.toml` — 패키지 메타데이터 + 의존성 + 도구 설정
- `nextflow.config` — Nextflow 실행 프로파일
- `.claude/settings.local.json` — Claude Code 권한 설정
