# Bioauto 실행 백로그

> 마지막 업데이트: 2026-08-20 · 우선순위 순 · 완료 항목은 `../DEVELOPMENT_HISTORY.md`로 이동 후 여기서 제거
> 상태: `ready`(구현 가능) / `blocked`(선행 조건 대기) / `in-review`

## PH-0 Platform Hardening (사용자 편의성·설치·보안·Melchizedek Gateway 우선 구현)

| ID | 우선 | 작업 | 의존성 | Definition of Done | 상태 |
|---|---:|---|---|---|---|
| UX-001 | P0 | installer 복구 및 install profile (`core`, `web`, `analysis`, `full`) | 없음 | repo URL 정상화; 실패 은폐 금지; clean venv 설치 성공; 멱등성 보장 | **ready** |
| UX-002 | P0 | `bioauto doctor` 및 `--json` 진단 CLI | UX-001 | Java 17+/Nextflow 25.10+/Container/Python/R/API key 상태 진단; 비밀값 redaction | **ready** |
| CFG-001 | P0 | versioned config schema & precedence | 없음 | `CLI > env > project > user > default` 강제; redaction 마스킹 검증 | **ready** |
| SEC-001 | P0 | web 기본 바인딩 127.0.0.1 제한 및 보안 가드 | 없음 | 기본 127.0.0.1 바인딩; `0.0.0.0` 설정 시 명시적 opt-in 및 경고 출력; 파괴적 endpoint 보안 | **ready** |
| LLM-001 | P0 | `MelchizedekBackend` 및 `X-Melchizedek-Client` 헤더 추가 | G1/G2 | `https://REDACTED-GATEWAY` 게이트웨이 연동; `/v1/chat/completions` 지원 | **ready** |
| LLM-002 | P0 | Gateway-first 라우터 및 단계별 프로필 | LLM-001 | gateway 라우팅 우선 사용; 이중 failover/ensemble 방지; degraded 상태 명시 | **ready** |
| LLM-003 | P0 | Route provenance & 에러 분류/retry 수정 | LLM-001 | 응답 provenance(`route.provider/model/reason`) 아티팩트 보존; 429/503 retryable 분리 | **ready** |
| LLM-004 | P0 | Gateway 테스트 스위트 및 opt-in live smoke | LLM-001 | mock 전체 검증 + live 1회 최소 chat 검증 (G6) | **ready** |
| WEB-001 | P1 | Onboarding/Settings/Provider 진단 화면 | SEC-001, LLM-001 | 서버 사이드 설정 저장 및 진단; 비밀값 마스킹; gateway health/model 노출 | **ready** |
| WEB-002 | P1 | 논문 키워드 검색/상담 UI 및 Run Preview | SEC-001 | PMID 단일 입력 외 검색/선택 지원; 예상 다운로드/disk 예산 실행 전 표시 | **ready** |
| MOD-001 | P1 | 호환성 매트릭스 자동 검증 | UX-002 | Java 17+, Nextflow 25.10 LTS / 26.04 strict syntax v2 준비 검증 | **ready** |
| MOD-002 | P1 | `nf-core/rnaseq` 우선 승격 (3.26.0) | MOD-001 | 파이프라인 입력/출력 fixture 회귀 검증; `scrna`는 대형 migration으로 분리 | **ready** |
| DOC-001 | P1 | 사용자 설치·운영·gateway 문서화 | UX-001~002 | fresh-user 튜토리얼 및 CLI help drift 방지 검증 | **ready** |

## Completed / Approved Foundation Tasks

| ID | 작업 | 의존성 | Definition of Done | 상태 |
|---|---|---|---|---|
| BL-001 | Spatial fixture 2개 실측 (URL/file list/size/checksum/license/endpoint) | public-only 정책(D4) | `spatial-fixtures.md` §재실측 DoD (a)~(i) 전부 충족 | **done 2026-08-20** (F18 DoD 실측 완료 — Fixture 1 live URL 교체 및 (a)~(i) 전 항목 수집) |
| BL-002 | F13/F14 안전 수정 + caller-level 회귀 테스트 | 없음 | blocked가 `nfcore_done`으로 기록되지 않음, 미검증 Slurm adapter submit 0건 | **done 2026-08-18** (Reviewer 검증 완료 — 커밋 후 히스토리 이동) |
| BL-003 | RFC 0001 보완 (JSON 예시, CLI error UX, legacy signature mapping — fixture 실측 불필요 항목) | BL-002 | Reviewer가 승인 판단 가능한 수준의 계약 명세 | **done 2026-08-20** (Dev RFC 0001 보완 완료 — Manifest/WorkflowPlan/Legacy Mapping/F17/F20 예시 반영) |
| BL-004 | RFC 0001 승인 | BL-001, BL-003, D1–D5 결정 | Reviewer 승인 + 운영자 결정 기록 | **done 2026-08-20** (Reviewer 최종 승인 완료 — Approved for BL-005 Implementation) |
| BL-005 | manifest/`WorkflowPlan` foundation 구현 | BL-004 | legacy tests/CLI 호환, deterministic plan/dry-run, TD-008 기계검증 테스트 포함 | **done 2026-08-20** (Foundation 모듈 `core/manifest.py`, `core/workflow_plan.py`, `core/artifact.py` 및 TD-008 테스트 1629 passed 완료) |

## Spatial & Verification Engine Roadmap Tasks (PH-0 완료 후 재개)

| ID | 작업 | 의존성 | Definition of Done | 상태 |
|---|---|---|---|---|
| BL-006 | Spatial processed reader + 분석 (`analysis_type=spatial`) | BL-005, PH-0 | fixture 2개 gold endpoint + warning artifact 통과 | **blocked (PH-0 진행 완료 후 착수)** |
| BL-007 | Spatial report + release 검증 | BL-006 | 관측/문헌/가설 분리, full regression/lint, 5.0 release checklist | **blocked** |
| BL-008 | RFC 0002 Verification Engine 초안 | BL-004와 병행 가능 | JSONL schema/state machine/validation policy 승인 | **blocked** |
| BL-009 | Verification Engine v0 구현 | BL-007, BL-008 | independent vs internal 상태를 과장 없이 출력 | **blocked** |

## 기술부채·미해결 (릴리스 비종속)

| ID | 항목 | 출처 | 비고 |
|---|---|---|---|
| TD-001 | Slurm script 템플릿이 rnaseq 전용 플래그 고정 — scrnaseq/atacseq 제출도 param 실패 가능 | F12/B6 | 5.0 WorkflowPlan에서 파이프라인별 param 템플릿으로 해소 |
| TD-002 | Stage 3.5가 `enable_pipeline_execution` 설정과 무관하게 `public_sra_ids`만으로 실행됨 | F13(b) | 게이트 추가 여부는 기존 사용자 흐름 확인 후 결정 (보류) |
| TD-003 | scRNA+spatial 병행 논문 과차단 (`unknown`) | R12 | 5.0 `AssayDetection[]` 다중 감지로 해소 — 그 전까지 의도 동작 |
| TD-004 | `ResearchEvaluationScorer` 총점이 idea quality와 evidence strength 혼합 — 검증 판정에 재사용 금지 | grok 실측 | 5.1 VE에서 축 분리 (a~f), 기존 점수는 idea 단계 전용으로 격하 |
| TD-005 | `DocumentStore` 단일 collection — claim ID/span/evidence type 없음 | grok 실측 | 5.1 VE ledger 신설로 해소 (기존 store는 검색 전용 유지) |
| TD-006 | Visium HD 분석 bin 크기 미결정 (2µm 저장 vs 8µm 분석) | F17 | BL-003에서 RFC 0001에 분석 bin 명시 — 도구 선택(D5)과 별개 · **RFC §2 반영 완료(8µm)** |
| TD-007 | Visium HD 입력이 15.8 GB 단일 tarball — `square_008um/` 분석 입력이 그 안에만 존재 | Refactor 실측(D-d1) | **RFC §2.5로 계약화 완료** (dry-run 바이트 표시 · `tar` 부분추출 · `checksum_status` 승격 · content_length 불일치 시 차단). BL-006 구현 시 이행 |
| TD-008 | 보드↔파일 drift 방지용 기계 검증 테스트 추가 | Refactor/Reviewer | **done 2026-08-20** (`tests/test_rfcs_and_fixtures.py` 5종 검증 수록 완료) |
