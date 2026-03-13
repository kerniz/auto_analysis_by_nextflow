# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 개발 명령어

```bash
# 테스트 (전체)
python3 -m pytest tests/ -v

# 테스트 (단일 파일)
python3 -m pytest tests/test_backends.py -v

# 테스트 (단일 함수)
python3 -m pytest tests/test_backends.py::TestOllamaBackend::test_generate -v

# 커버리지 (전 모듈)
python3 -m pytest tests/ --cov=backends --cov=plugins --cov=clients --cov=agents --cov=enrichment --cov=search --cov=mcp --cov=rag --cov=nextflow --cov=analysis --cov=core --cov=tui --cov=web -v

# 린트
python3 -m ruff check .

# 린트 자동 수정
python3 -m ruff check . --fix

# 타입 체크
python3 -m mypy core/ backends/ plugins/ --ignore-missing-imports

# CLI 실행
python3 -m core.cli run <PMIDs>
```

## 필수 규칙

1. **ABC 패턴**: 새 백엔드/플러그인/클라이언트는 반드시 추상 클래스 상속
2. **async/await**: 모든 I/O 작업은 비동기 (httpx 사용)
3. **Graceful degradation**: optional 기능 미설치 시 skip (try/except ImportError)
4. **Pydantic v2**: 데이터 모델은 Pydantic 2.0+ 문법
5. **환경변수**: API 키는 절대 하드코딩 금지 (OPENAI_API_KEY, ANTHROPIC_API_KEY, BRAVE_API_KEY)
6. **테스트 격리**: 외부 API/프로세스 호출은 반드시 mock
7. **ruff lint**: `python3 -m ruff check .` 0 warning 유지 (line-length=100, ignore E501)
8. **결과 폴더**: 모든 결과는 `results/{PMID}/` 서브폴더에 저장

## 테스트 현황

- **1468 수집 / 1405 passed, 10 skipped** (chromadb 미설치 시 skip)
- **커버리지 ~90%**
- asyncio_mode = "auto" (pyproject.toml)

## 팀 에이전트 (7인)

| 에이전트 | 파일 | 담당 |
|----------|------|------|
| orchestrator | `.claude/agents/orchestrator.md` | 아키텍처 설계, 태스크 분배 |
| pipeline-dev | `.claude/agents/pipeline-dev.md` | core/ plugins/ nextflow/ analysis/ |
| backend-dev | `.claude/agents/backend-dev.md` | backends/ clients/ agents/ search/ mcp/ rag/ enrichment/ |
| tester | `.claude/agents/tester.md` | tests/ 커버리지, 회귀 테스트 |
| reviewer-docs | `.claude/agents/reviewer-docs.md` | 코드 리뷰 + 문서화 |
| infra-dev | `.claude/agents/infra-dev.md` | Docker/Singularity/Slurm/HPC/nextflow.config |
| bio-researcher | `.claude/agents/bio-researcher.md` | nf-core 파라미터 자문, 분석 전략 |

## 문서 관리

### 문서 구조 (전역 `REDACTED-NFS-PATH/.claude.md` 지침 준수)

| 문서 | 역할 | 전역 지침 매핑 |
|------|------|----------------|
| `docs/ARCHITECTURE.md` | 설계 철학, 시스템 구조, 데이터 흐름, 기술 스택 | 안정적, 자주 안 바뀌는 것 |
| `docs/DEVELOPMENT_HISTORY.md` | 버전별 개발 이력, Phase별 변경사항 | `개발히스토리.md` 역할 |
| `README.md` | 설치/실행/사용법 (간결) | 사용법 기본 문서 |

### 문서 관리 원칙

1. **코드 변경 시 설계 문서 동기화** — ARCHITECTURE.md는 항상 현재 코드와 일치
2. **버그 수정 패턴** → `REDACTED-NFS-PATH/.changehistory.md`에 기록 (프로젝트 공통)
3. **모든 설계 문서에 마지막 업데이트 날짜 명시**
4. **중복 문서 발생 시 즉시 하나로 합침**
5. **커밋/푸시 후 관련 문서(README, ARCHITECTURE, DEVELOPMENT_HISTORY) 최신화**
6. **500줄 초과 시** `docs/architecture/` 폴더로 주제별 분할
