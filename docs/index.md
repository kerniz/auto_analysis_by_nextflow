# BioAuto Platform Documentation Hub

> 바이오인포매틱스 연구 자동화 플랫폼 문서 색인 및 시스템 가이드

## Quick Start (5분 빠른 시작)

- **설치 가이드**: [`install.sh`](file://REDACTED-NFS-PATH/10.yolo/nextflow_automation/install.sh) 또는 `BIOAUTO_PROFILE=standard bash install.sh`
- **초기 진단**: `bioauto doctor`
- **빠른 실행 테스트**: `bioauto run --pmid 34567890 --dry-run`

---

## 문서 구구조 & 네비게이션

### 1. 설치 & 설정 (`getting-started/`)
- **[Installation Guide](file://REDACTED-NFS-PATH/10.yolo/nextflow_automation/README.md#installation)**: 프로필 기반 (`core`, `standard`, `analysis`, `full`) 자동 설치
- **[Configuration & Secrets](file://REDACTED-NFS-PATH/10.yolo/nextflow_automation/config.json)**: `config.json` 계층 구조, 환경 변수 우선순위 및 보안 토큰 관리

### 2. 게이트웨이 & 백엔드 연동 (`integrations/`)
- **Melchizedek Gateway**: `https://REDACTED-GATEWAY` 게이트웨이 라우팅 (`provider=auto, effort=medium, strategy=solo`) 및 Client Labeling (`X-Melchizedek-Client`)
- **Local Fallback**: Direct Ollama / OpenAI / Anthropic 연동 및 명시적 장애 전이 (Strict Fallback)

### 3. 기능 및 파이프라인 가이드 (`guides/`)
- **Spatial Transcriptomics MVP**: [RFC 0001 Specification](file://REDACTED-NFS-PATH/10.yolo/nextflow_automation/docs/rfcs/0001-spatial-mvp.md) 및 [Fixtures Reference](file://REDACTED-NFS-PATH/10.yolo/nextflow_automation/docs/planning/spatial-fixtures.md)
- **Web Dashboard**: `bioauto web` (기본 바인딩 `127.0.0.1`, `--allow-remote` 보안 미들웨어)

### 4. 아키텍처 & 승인 계획 (`planning/` & `rfcs/`)
- **[ROADMAP.md](file://REDACTED-NFS-PATH/10.yolo/nextflow_automation/docs/planning/ROADMAP.md)**: PH-0 Platform Hardening 및 Spatial MVP 로드맵
- **[BACKLOG.md](file://REDACTED-NFS-PATH/10.yolo/nextflow_automation/docs/planning/BACKLOG.md)**: 실행 백로그 (AUTO-CFG, AUTO-INST, AUTO-SETUP, AUTO-CHK, DOC-IA 포함)
- **[RFC 0001](file://REDACTED-NFS-PATH/10.yolo/nextflow_automation/docs/rfcs/0001-spatial-mvp.md)**: Spatial MVP 계약 및 데이터 다이어그램
