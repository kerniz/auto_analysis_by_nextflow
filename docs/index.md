# BioAuto 문서 색인

> 마지막 업데이트: 2026-08-20 · 바이오인포매틱스 연구 자동화 플랫폼 문서 허브
> 링크는 모두 **레포 상대경로**다 — GitHub·다른 머신·다른 사용자 환경에서 동일하게 동작해야 한다.

## 빠른 시작

```bash
BIOAUTO_PROFILE=core bash install.sh   # 프로필: core | web | analysis | full
python3 -m core.cli doctor             # 런타임 진단 (Java/Nextflow/Python/API key)
python3 -m core.cli web                # 대시보드 (기본 127.0.0.1)
```

`[analysis]`·`[full]` 프로필은 **Python 3.12+** 가 필요하다(scanpy 1.12 제약). core 전용은 3.10에서도 동작한다.

## 문서 지도

| 축 | 문서 | 내용 |
|---|---|---|
| 현재(구조) | [ARCHITECTURE.md](ARCHITECTURE.md) | 시스템 구조·데이터 흐름·기술 스택 |
| 미래 | [planning/ROADMAP.md](planning/ROADMAP.md) | 북극성, 릴리스 순서(PH-0 → 5.0 Spatial → 5.1 VE), 결정 기록 |
| 실행 | [planning/BACKLOG.md](planning/BACKLOG.md) | 실행 백로그(PH-0, AUTO-*, DOC-IA-*, BL-*), 기술부채(TD-*) |
| 과거 | [DEVELOPMENT_HISTORY.md](DEVELOPMENT_HISTORY.md) | 버전별 개발 이력 |
| 설계 결정 | [rfcs/0001-spatial-mvp.md](rfcs/0001-spatial-mvp.md) | Spatial MVP 계약(manifest·WorkflowPlan·claim schema) |
| 재현 데이터 | [planning/spatial-fixtures.md](planning/spatial-fixtures.md) | gold fixture URL·크기·SHA256·라이선스 |
| 비전(별도 제품) | [CITIZEN_SCIENCE_PLATFORM_VISION.md](CITIZEN_SCIENCE_PLATFORM_VISION.md) | AutoIdeaLab — **본 로드맵과 버전 체계 독립** |
| 사용법 | [../README.md](../README.md) · [README.ko.md](README.ko.md) | 설치·실행·CLI |

## LLM 게이트웨이 (Melchizedek)

- 기본 라우팅은 **게이트웨이 우선**이다: `config.json`의 `priority_order[0] = melchizedek`, `enable_auto_failover = false`.
- 게이트웨이 장애를 다른 provider가 조용히 대체하지 않는다(G1). direct Ollama는 opt-in fallback이다(G8).
- 모든 요청에 `X-Melchizedek-Client` 라벨이 붙는다(G9): `bioauto/pipeline` · `debate` · `report` · `rag` · `search`.
- `model`은 `ollama/<이름>` 또는 ready provider id(`agy`·`claude`·`grok`·`codex`)여야 한다. 잘못된 값은 `model_not_allowed`(404)로 즉시 실패한다.
- 오류는 `{request_id, code, message}` 계약을 따르며, **재시도 가능한 것은 `provider_busy`·`queue_full`·`timeout`뿐**이다. `rate_limited`는 `Retry-After`를 준수한다(`backends/base.py::classify_error`).

## 웹 대시보드 보안

- 기본 바인딩은 `127.0.0.1`이다. 외부 바인딩은 `--allow-remote`를 명시해야 하며, 이때 서버 토큰이 자동 생성된다.
- 원격 모드에서는 상태 변경 API와 읽기 엔드포인트(`/api/results/`, `/pipeline-files/`)가 모두 토큰을 요구한다. 토큰 비교는 상수 시간이다.

## 문서 규칙

- 링크는 상대경로만 쓴다(절대 `file://` 금지 — 다른 환경에서 깨진다).
- 완료 항목은 BACKLOG에서 제거하고 `DEVELOPMENT_HISTORY.md`로 옮긴다.
- "구현됨"은 코드·테스트 근거가 있을 때만 쓴다. 미확인은 `목표/부분/미구현`으로 표기한다.
