# Bioauto 실행 백로그

> 마지막 업데이트: 2026-08-27 · 우선순위 순 · 완료 항목은 `../DEVELOPMENT_HISTORY.md`로 이동 후 여기서 제거
> 상태: `ready`(구현 가능) / `blocked`(선행 조건 대기) / `in-review`

## GPU — 클러스터 가속 & Heterogeneous Worker Pool (NVIDIA Parabricks & BioNeMo)

> 대상 노드: `REDACTED-HOST-ARM64` (DGX Spark / ARM64 GB10 - Parabricks 우선), `REDACTED-HOST-X86` (x86 GPU - BioNeMo/Ollama)

| ID | 우선 | 작업 | 의존성 | Definition of Done | 상태 |
|---|---:|---|---|---|---|
| GPU-001A | P0 | kerniz3 (x86 GPU) secure inventory access | SSH key/bootstrap | x86 arch·GPU·driver·CUDA·Docker·RAM·Ollama 점유 수집 | **blocked-access** |
| GPU-001B | P0 | kerniz5 (DGX Spark ARM64) secure inventory access | SSH key/bootstrap | ARM64 arch·GB10 capability·Docker GPU 수집 | **blocked-access** |
| GPU-004 | P0 | ExecutionTarget & WorkerCapability 추상화 (RFC 0003) | 없음 | `ExecutionTargetResolver` 안전 가드 모듈 수록 및 fail-closed 회귀 테스트 | **in-review** (`core/execution_target.py` scaffold 수록) |
| GPU-006 | P1 | CapabilityProbe & Target Registry | GPU-004 | unavailable 노드 자동 탐지 및 사전 차단 | **ready** |
| PB-001 | P1 | Parabricks prerequisite smoke | GPU-001B | `docker --gpus all` official sample, image digest/version provenance | **blocked GPU-001B** |
| PB-002 | P1 | fq2bam adapter & Nextflow integration | PB-001 | typed manifest/params, reference bundle validation, dry-run resource | **blocked PB-001** |
| PB-003 | P1 | Germline caller adapter (HaplotypeCaller/DeepVariant) | PB-002 | VCF QC, failure artifact 및 provenance 보존 | **blocked PB-002** |
| BN-001A | P2 | BioNeMo x86 probe on kerniz3 | GPU-001A | official supported GPU/driver 확인, minimal import/inference | **blocked GPU-001A** |
| BN-001B | P2 | BioNeMo ARM64 probe on kerniz5 | GPU-001B | x86-only 공식 상태를 유지하며 experimental container probe | **blocked GPU-001B** |

## PH-0 Platform Hardening (사용자 편의성·설치·보안·Melchizedek Gateway 구현)

| ID | 우선 | 작업 | 의존성 | Definition of Done | 상태 |
|---|---:|---|---|---|---|
| UX-001 | P0 | installer 복구 및 install profile (`core`, `web`, `analysis`, `full`) | 없음 | repo URL 정상화; install profile(`BIOAUTO_PROFILE`) 설치 검증 | **done 2026-08-20** |
| UX-002 | P0 | `bioauto doctor` 및 `--json` 진단 CLI | UX-001 | Java 17+/Nextflow/Container/Python/API key 마스킹 진단; 단위 테스트 통과 | **done 2026-08-20** |
| CFG-001 | P0 | versioned config schema & precedence | 없음 | `CLI > env > project > user > default` 강제; redaction 마스킹 검증 | **ready** |
| SEC-001 | P0 | web 기본 바인딩 127.0.0.1 제한 및 보안 가드 | 없음 | 기본 127.0.0.1 바인딩; `--allow-remote` 설정 시 토큰 자동생성; 상수시간 토큰 미들웨어 | **done 2026-08-20** |
| LLM-001 | P0 | `OpenAIBackend` gateway 라우팅 및 `X-Melchizedek-Client` 헤더 | G1/G2 | `https://REDACTED-GATEWAY` 게이트웨이 파라미터화; dummy key 게이트웨이 분리 | **done 2026-08-20** |
| LLM-002 | P0 | Gateway-first 라우터 및 단계별 프로필 | LLM-001 | gateway 라우팅 우선 사용; 이중 failover/ensemble 방지; degraded 상태 명시 | **done 2026-08-20** (config.json 및 pipeline.py / setup_wizard.py `priority_order[0]=melchizedek`, `enable_auto_failover=false` 고정) |
| LLM-003 | P0 | Route provenance & 에러 분류/retry | LLM-001 | `LLMResponse.to_dict()`에 route provenance 보존; 429/503 retryable 분리 | **done 2026-08-20** (`backends/base.py::classify_error` — gateway code 우선, `Retry-After` 준수, fatal 즉시 실패. 계약 테스트 6건) |
| LLM-004 | P0 | Gateway 테스트 스위트 및 live smoke | LLM-001 | mock 전체 검증 + live 1회 최소 chat 검증 (G6) | **done 2026-08-20** (G6 live chat 1회 실행: HTTP 200, 6.15s, `route.provider=claude`, `reason=explicit_provider_model`. 응답 전문 미저장) |
| LLM-005 | P1 | 진짜 auto 라우팅 (`model` 생략 + `routing`) | LLM-002 | 게이트웨이 계약상 `model` 생략 시 `routing`이 결정한다. 현 백엔드는 `model`을 항상 보내 G2의 `provider=auto`가 무력화됨. `model` 생략 경로 + `routing:{provider:auto,effort:medium,strategy:solo}` extra_body 전달 | **ready** |
| WEB-001 | P1 | Onboarding/Settings/Provider 진단 화면 | SEC-001, LLM-001 | 서버 사이드 설정 저장 및 진단; 비밀값 마스킹; gateway health/model 노출 | **ready** |
| WEB-002 | P1 | 논문 키워드 검색/상담 UI 및 Run Preview | SEC-001 | PMID 단일 입력 외 검색/선택 지원; 예상 다운로드/disk 예산 실행 전 표시 | **ready** |
| MOD-001 | P1 | 호환성 매트릭스 자동 검증 | UX-002 | Java 17+, Nextflow 25.10 LTS / 26.04 strict syntax v2 준비 검증 | **ready** |
| MOD-002 | P1 | `nf-core/rnaseq` 우선 승격 (3.26.0) | MOD-001 | 파이프라인 입력/출력 fixture 회귀 검증; `scrna`는 대형 migration으로 분리 | **ready** |
| DOC-001 | P1 | 사용자 설치·운영·gateway 문서화 | UX-001~002 | fresh-user 튜토리얼 및 CLI help drift 방지 검증 | **done 2026-08-20** |
| VM-001 | P1 | `config.json` 부재 시 gateway 정책 미적용 | AUTO-CFG-002 | config 없이 `PipelineConfig()` 생성 시 `llm_providers=None`이라 G1/G2/G8이 적용되지 않고 legacy 백엔드로 폴백. 현재는 CLI 경고만 있음 — loader가 gateway-first 기본값을 항상 구성하도록 | **ready** (2026-08-27 VM 실사용 확인) |
| VM-002 | P2 | `bioauto doctor`에 gateway/LLM 진단 없음 | UX-002 | doctor가 Java/Nextflow/Python/API key만 보고 gateway health·router 정책을 진단하지 않음. `backends`와 동일 정보를 doctor에 통합 | **ready** (2026-08-27 VM 실사용 확인) |
| VM-003 | P2 | `python -m core.cli` 실행 시 RuntimeWarning | 없음 | `'core.cli' found in sys.modules...` 경고가 매 실행 출력됨. `core/__init__.py`가 `core.cli`를 import해 발생 — 콘솔 스크립트 진입점 사용 또는 lazy import로 해소 | **ready** (2026-08-27 VM 실사용 확인) |
| VM-004 | P2 | 이 VM에 Java/Nextflow 미설치 | AUTO-INST-004 | `doctor` 결과 Java/Nextflow MISSING — 파이프라인 실행 불가. user-space runtime bootstrap으로 해소 예정 | **ready** (환경 이슈, 코드 결함 아님) |
| GPU-002 | P0 | kerniz5/kerniz3 노드 사양 실측 | 없음 | SSH 접근 확보 후 `uname -m`·`nvidia-smi`·CUDA·컨테이너 런타임·Parabricks/BioNeMo 설치 여부 실측. `register_target(verified=True)`로 등록. **실측 전 GPU 워크로드 dispatch 금지** | **ready** (2026-08-27: SSH `Permission denied (publickey)` — 접근 차단 상태) |
| GPU-003 | P1 | Parabricks/BioNeMo arm64 매니페스트 확정 | GPU-002 | NGC 라벨상 `clara-parabricks`·`bionemo-framework` 모두 `containers:multiarch`. 단 multiarch가 arm64를 포함하는지는 매니페스트로 확정 필요. 부속 컨테이너(`clara-parabricks-umi-fgbio`, `-deepsap`)에는 multiarch 라벨 **없음** → arm64 미지원 가능 | **ready** |
| GPU-004 | P1 | Slurm 통합 경로 결정 (신규 SSH vs 기존 slurmctld) | GPU-002 | kerniz5의 6817/6818(slurm) 포트가 **열려 있음**(2026-08-27 실측). 기존 `_run_nfcore_via_slurm` 경로로 흡수할지, `ExecutionTargetResolver` 별도 SSH 경로로 갈지 결정. 두 경로 병존은 F8류 사고 재발 위험 | **ready** |
| GPU-005 | P2 | nf-core GPU 프로세스 라벨 매핑 | GPU-003 | Parabricks/BioNeMo를 Nextflow에서 쓰려면 process label·`accelerator` 지시자·컨테이너 pull 정책(NGC 인증 포함)이 필요. TD-001(rnaseq 전용 param 템플릿)과 함께 WorkflowPlan에서 설계 | **ready** |

## AUTO — 설치·설정 완전 자동화 (Installation & Setup Automation)

| ID | 우선 | 작업 | 의존성 | Definition of Done | 상태 |
|---|---:|---|---|---|---|
| AUTO-CFG-001 | P0 | Pydantic 기반 versioned `BioAutoConfig` SSOT | 없음 | CLI/pipeline/TUI/Web가 동일 loader 사용; unknown/invalid field 오류 | **ready** |
| AUTO-CFG-002 | P0 | Config 위치와 precedence | AUTO-CFG-001 | `--config > env > project > XDG user > defaults`; `bioauto config show --effective` | **done 2026-08-27** |
| AUTO-CFG-003 | P0 | Atomic migration & backup | AUTO-CFG-001 | 구 config dry-run diff, backup, temp+rename 저장, 실패 시 원본 보존 | **ready** |
| AUTO-INST-001 | P0 | `install.sh` option parser & profiles | UX-001 | `--profile`, `--yes`, `--dry-run`, `--non-interactive`, `--no-modify-path` 지원 | **done 2026-08-27** (`install.sh` CLI 파서 및 dry-run 구현 완료) |
| AUTO-INST-004 | P0 | User-space runtime bootstrap | UX-001 | pinned Nextflow/Java archive checksum 검증, cache, 재사용, sudo 없음 | **ready** |
| AUTO-SETUP-001 | P0 | Headless setup engine | CFG-001 | UI 독립 service가 profile/gateway/results/runtime config 생성 | **ready** |
| AUTO-SETUP-003 | P0 | Gateway auto-discovery | LLM-001 | 승인 URL→health/providers/models 확인; G1–G9 defaults 생성 | **ready** |
| AUTO-CHK-001 | P0 | Version-aware doctor | UX-002 | Java 17+ major parsing, Nextflow, Python profile, Scanpy/AnnData 검사 | **done 2026-08-20** |
| AUTO-CHK-003 | P0 | Offline synthetic smoke test | UX-002 | synthetic metadata→plan→mock LLM→report; network/download/LLM quota 0 | **ready** |

## DOC-IA — 문서 정보구조 재구조화 (Documentation Information Architecture)

| ID | 우선 | 작업 | 의존성 | Definition of Done | 상태 |
|---|---:|---|---|---|---|
| DOC-IA-001 | P0 | 문서 inventory/ownership/SSOT 표 | 없음 | 문서별 audience·현행/계획/역사·owner 명시; 중복 section 목록 생성 | **ready** |
| DOC-IA-002 | P0 | Docs Index & Hub 신설 (`docs/index.md`) | DOC-IA-001 | README→install→setup→smoke를 5분 내 찾을 수 있는 네비게이션 구축 | **done 2026-08-20** |
| DOC-IA-003 | P0 | 설치/설정/gateway/security 문서 분리 | DOC-IA-002 | 코드 option과 예제가 테스트되며 G1–G9/remote auth/secret 정책 반영 | **ready** |
| DOC-IA-004 | P0 | Planning status 정합화 | DOC-IA-002 | 완료/부분/ready/blocked 상태를 코드와 일치; 폐기된 문구 제거 | **done 2026-08-20** |
| DOC-IA-007 | P1 | 문서 링크/명령 자동 검증 CI | DOC-IA-003 | markdown links, CLI snippets, README 요구 version을 CI에서 검사 | **ready** |
| DOC-IA-008 | P1 | 문서 링크 상대경로 규약 및 검증 | DOC-IA-002 | `docs/` 내 모든 링크가 상대경로(절대 `file://` 금지); 링크 유효성 자동 검증 | **done 2026-08-20** |

## Completed / Approved Foundation Tasks

| ID | 작업 | 의존성 | Definition of Done | 상태 |
|---|---|---|---|---|
| BL-001 | Spatial fixture 2개 실측 (URL/file list/size/checksum/license/endpoint) | public-only 정책(D4) | `spatial-fixtures.md` §재실측 DoD (a)~(i) 전부 충족 | **done 2026-08-20** (F18 DoD 실측 완료 — Fixture 1 live URL 교체 및 (a)~(i) 전 항목 수집) |
| BL-002 | F13/F14 안전 수정 + caller-level 회귀 테스트 | 없음 | blocked가 `nfcore_done`으로 기록되지 않음, 미검증 Slurm adapter submit 0건 | **done 2026-08-18** (Reviewer 검증 완료 — 커밋 후 히스토리 이동) |
| BL-003 | RFC 0001 보완 (JSON 예시, CLI error UX, legacy signature mapping — fixture 실측 불필요 항목) | BL-002 | Reviewer가 승인 판단 가능한 수준의 계약 명세 | **done 2026-08-20** (Dev RFC 0001 보완 완료 — Manifest/WorkflowPlan/Legacy Mapping/F17/F20 예시 반영) |
| BL-004 | RFC 0001 승인 | BL-001, BL-003, D1–D5 결정 | Reviewer 승인 + 운영자 결정 기록 | **done 2026-08-20** (Reviewer 최종 승인 완료 — Approved for BL-005 Implementation) |
| BL-005 | manifest/`WorkflowPlan` foundation 구현 | BL-004 | legacy tests/CLI 호환, deterministic plan/dry-run, TD-008 기계검증 테스트 포함 | **done 2026-08-20** (Foundation 모듈 `core/manifest.py`, `core/workflow_plan.py`, `core/artifact.py` 및 F22/F23/TD-008 검증 통과) |

## Spatial & Verification Engine Roadmap Tasks

| ID | 작업 | 의존성 | Definition of Done | 상태 |
|---|---|---|---|---|
| BL-006 | Spatial processed reader + 분석 (`analysis_type=spatial`) | BL-005, PH-0 | fixture 2개 gold endpoint + warning artifact 통과 | **blocked** |
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
| TD-008 | 보드↔파일 drift 방지용 기계 검증 테스트 추가 | Refactor/Reviewer | **done 2026-08-20** (`tests/test_rfcs_and_fixtures.py` 12종 검증 수록 완료) |
