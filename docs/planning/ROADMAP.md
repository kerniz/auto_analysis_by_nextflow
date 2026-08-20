# Bioauto 제품 로드맵 (멀티모달 및 플랫폼 고도화)

> 마지막 업데이트: 2026-08-20 · SSOT: 이 문서 (계획의 미래 축)
> 관련: 백로그 `BACKLOG.md` · 설계 `../rfcs/0001-spatial-mvp.md`(Approved) · fixture `spatial-fixtures.md`(검증 완료)
> 주의: `CITIZEN_SCIENCE_PLATFORM_VISION.md`(AutoIdeaLab)는 **별도 제품 비전**으로 버전 체계 독립 — 본 로드맵과 릴리스 번호를 공유하지 않는다.

## 북극성 (운영자 승인 완료 — D1)

**bioauto = reproducible claim lifecycle platform.**
단발 분석 자동화가 아니라, 가설(claim)을 증거·독립 재현·반증 기준으로 관리하는 플랫폼. 분석 modality(spatial/perturb/long-read)는 이 위의 생산자다.

## §결정 사항 (운영자 승인 완료 — 2026-08-20)

| ID | 결정 | 상태 |
|---|---|---|
| D1 | 북극성 = claim lifecycle platform 승인 (AutoIdeaLab은 별도 제품 유지) | **승인 완료 (2026-08-20)** |
| D2 | 5.0 범위 = public Visium/Visium HD **processed matrix+image 재분석만** (raw FASTQ·Xenium·Multiome 제외) | **승인 완료 (2026-08-20)** |
| D3 | 검증 규칙: external replication = 독립 study만 / donor·batch split = `internal robustness only` / 둘 다 없으면 `not-testable`·`inconclusive` 종료 | **승인 완료 (2026-08-20)** |
| D4 | 데이터·운영 정책: public-only, license 확인 전 다운로드 금지, 자동화는 protocol 초안+비용 추정까지 (lab 주문·실행 제외) | **승인 완료 (2026-08-20)** |
| D5 | 설계 선택(B1–B6): ledger=append-only versioned JSONL, 이미지=pointer-only는 승인 / spatial 도구·experiment ID 체계·다음 slice는 보류 유지 | **분할 승인 완료 (2026-08-20)** |

## §플랫폼 고도화 (PH-0) 및 LLM 게이트웨이 정책 결정안 (G1~G6)

| ID | 항목 | 팀 권고안 | 목적 / 효과 |
|---|---|---|---|
| G1 | Gateway 장애 시 동작 | **명시 실패가 기본**, opt-in 설정 시에만 direct backend fallback | gateway 장애 및 모델 이탈을 조용히 숨기지 않음 |
| G2 | Gateway 기본 라우팅 | **`provider=auto, effort=medium, strategy=solo`** | 비용·지연 과도 증가 방지, high/max 중첩 호출 제한 |
| G3 | Web 원격 바인딩 보안 | **`127.0.0.1` 기본 바인딩**, Tailnet/인증 proxy 문서화 | 파괴적 API(중단/삭제)의 무인증 외부 노출 차단 |
| G4 | Python 분석 환경 | **Core Python 3.10 유지 + Analysis 컨테이너/venv Python 3.12+ 격리** | 설치 호환성 보존 및 최신 Scanpy 1.12+ 지원 |
| G5 | 파이프라인 현행화 | **Java 17+, Nextflow 25.10 LTS / 26.04 strict syntax v2 준비, `rnaseq` 우선 승격** | 대규모 파이프라인 회귀 리스크 분리 |
| G6 | Live Gateway 시험 | **다음 라운드 최소 chat 1회 허용**, 검색은 mock 우선 | 불필요한 external LLM quota 소비 방지 |

## 릴리스 순서와 Exit Gate

| 우선 | 릴리스 | 내용 | Exit gate (완료 기준) |
|---|---|---|---|
| P0 | (릴리스 전) 안전·계약 정리 | 오분류·오실행 차단(F1~F14), fixture 실측, RFC 보완 | unknown/unsupported가 **어떤 실행 경로에서도** 제출되지 않음 + fixture 2개 license·endpoint 검증 |
| P0 | **5.0-Foundation** | Manifest v0, WorkflowPlan, Claim schema, TD-008 기계 검증 | **완료 (2026-08-20)** — Foundation 모듈 및 1629 passed 검증 |
| P0 | **PH-0 Platform Hardening** | UX/설치기, `bioauto doctor`, 보안(127.0.0.1), Melchizedek LLM Gateway, 현행화(Java17/Nextflow25.10) | 설치기 venv 산출물 작동, gateway router 헤더/provenance 보존, web 보안 100% 검증 |
| P1 | **5.0 Spatial MVP** | Spatial processed reader + 분석 (`analysis_type=spatial`), domain/niche, report | fixture 2개에서 사전 지정 endpoint 재현 + 전 artifact provenance 보존 |
| P1 | **5.1** Verification Engine v0 | JSONL claim/evidence/validation ledger, schema validator, 상태 분리 | 기존 DEG/pathway + 5.0 spatial artifact를 같은 contract로 소비, 종료 상태는 `supported/contradicted/inconclusive/not-testable`만 |
| P2 | **5.2** Perturb-seq processed re-analysis | guide/control/replicate QC, effect/uncertainty (spatial perturbation 제외) | NTC·guide coverage 검증 + 독립-study validation contract |
| P2 | **5.3** bulk long-read | isoform/fusion candidate, benchmark/short-read 교차검증 | caller/reference/protocol provenance + candidate-only 표기 |
| P3 | **5.4–5.5** Multiome/CITE/scATAC, pathology image | `measurement_relation`·ontology·privacy policy 갖춘 adapter | paired/adjacent/reference-transfer 구분 + uncertainty 보고 |
| P3 | **6.x** | Spatial Perturb-seq, single-cell long-read, ModelProvider, virtual experiment | 각 modality external benchmark + baseline 비교 선행 |

- 버전은 현행 4.x 다음인 **5.0부터** (1.x 리셋 금지). `pyproject.toml` bump는 각 release gate 통과 시에만.
- Foundation model은 항상 **plugin** (ModelProvider) — 프로젝트 중심에 두지 않는다 (SCMBench/VCBench 근거: task별 순위 변동, baseline 동등/우세 사례).

## 문서 책임 분리

| 문서 | 역할 |
|---|---|
| 본 문서 | 미래: 북극성·릴리스 순서·결정 대기 및 G1~G6 정책 |
| `BACKLOG.md` | 실행 가능 작업(BL-xxx, UX-xxx, LLM-xxx)·의존성·DoD·상태 |
| `../rfcs/` | 설계 계약 (0001 Spatial MVP Approved, 0002 Verification Engine 예정) |
| `spatial-fixtures.md` | 재현 fixture 실측 데이터 (검증 완료) |
| `../ARCHITECTURE.md`·README | **구현된 현행** 계약만 — release gate 후 갱신 |
| `../DEVELOPMENT_HISTORY.md` | 과거: 완료 항목 이동 (append-only) |
