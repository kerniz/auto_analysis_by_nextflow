# bioauto — Bioinformatics Research Automation Platform

## 프로젝트 개요

PMID 기반 논문 분석 → SRA 데이터 탐색 → 시퀀싱 타입 감지 → 다중 LLM 합의 분석 → 멀티 에이전트 토론 → nf-core 파이프라인 실행 → R/Python 다운스트림 분석까지 자동화하는 올인원 바이오인포매틱스 CLI 플랫폼.

## 핵심 아키텍처

```
core/          — CLI + AsyncPipeline 오케스트레이터
backends/      — LLM 라우터 (Ollama/OpenAI/Anthropic) + failover
plugins/       — 시퀀싱 타입 감지 플러그인 (ABC + Registry)
clients/       — 외부 API (Semantic Scholar, Europe PMC, TCGA, Annotation)
agents/        — 멀티 에이전트 토론 (PhD/Undergraduate/Layperson)
enrichment/    — GSEA 경로 분석
search/        — 다중 소스 논문 검색 + 랭킹
mcp/           — Brave Search 통합
rag/           — ChromaDB 벡터 DB + RAG 컨텍스트
nextflow/      — Nextflow 실행, 샘플시트, 모니터링
analysis/      — R/Python 다운스트림 분석
```

## 필수 규칙

1. **ABC 패턴**: 새 백엔드/플러그인/클라이언트는 반드시 추상 클래스 상속
2. **async/await**: 모든 I/O 작업은 비동기 (httpx 사용)
3. **Graceful degradation**: optional 기능 미설치 시 skip (ImportError 핸들링)
4. **Pydantic v2**: 데이터 모델은 Pydantic 2.0+ 문법
5. **환경변수**: API 키는 절대 하드코딩 금지
6. **테스트 격리**: 외부 API 호출은 반드시 mock

## 개발 명령어

```bash
# 테스트 실행
python3 -m pytest tests/ -v

# 커버리지
python3 -m pytest tests/ --cov=backends --cov=plugins --cov=clients --cov=agents --cov=enrichment --cov=search --cov=mcp --cov=rag --cov=nextflow --cov=analysis --cov=core -v

# 린트
python3 -m ruff check .

# 타입 체크
python3 -m mypy core/ backends/ plugins/ --ignore-missing-imports

# CLI 실행
python3 -m core.cli run <PMIDs>
```

## 팀 에이전트 구성 (7인)

| 에이전트 | 파일 | 역할 |
|----------|------|------|
| orchestrator | `.claude/agents/orchestrator.md` | 아키텍처 설계, 태스크 분배, 의존성 관리 |
| pipeline-dev | `.claude/agents/pipeline-dev.md` | core/ plugins/ nextflow/ analysis/ 개발 |
| backend-dev | `.claude/agents/backend-dev.md` | backends/ clients/ agents/ search/ mcp/ rag/ enrichment/ |
| tester | `.claude/agents/tester.md` | tests/ CI/CD, 커버리지, 회귀 테스트 |
| reviewer-docs | `.claude/agents/reviewer-docs.md` | 코드 리뷰 + 문서화 + CLAUDE.md 유지보수 |
| infra-dev | `.claude/agents/infra-dev.md` | Docker/Singularity/Slurm/HPC/nextflow.config |
| bio-researcher | `.claude/agents/bio-researcher.md` | nf-core 파라미터 자문, 분석 전략, 도메인 검증 |

## 설정 파일

- `config.json` — 런타임 설정 (LLM, 파이프라인, 분석, 토론 등)
- `pyproject.toml` — 패키지 메타데이터 + 의존성
- `nextflow.config` — Nextflow 실행 프로파일
- `.claude/settings.local.json` — Claude Code 권한 설정
