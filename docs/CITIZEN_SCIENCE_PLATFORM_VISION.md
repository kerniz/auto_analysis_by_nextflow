# bioauto 확장 비전: 자율 연구 & 시민 과학 오픈 게재 커뮤니티 (Platform Vision)

> **문서 버전**: v1.0.0  
> **작성일**: 2026-08-13  
> **상태**: 로드맵 및 비전 제안서 (Strategic Vision Proposal)

---

## 1. 개요 (Executive Summary)

본 문서는 현재 구축 완료된 **`bioauto` 파이프라인 엔진**(Nextflow + Multi-LLM 합의 + 멀티 에이전트 토론 + 자동 리포팅)을 기반으로, 일반인 및 독립 연구자가 참여하는 **"오픈 사이언스 & 시민 과학 자율 연구 게재 커뮤니티"**로 확장하기 위한 플랫폼 아키텍처 및 전략적 로드맵을 정의합니다.

```
[입력: 연구 주제 / PMID / 개별 데이터]
               │
               ▼
   [Stage 1~3: 수집 & 탐색] ──► PubMed, GEO, SRA 자동 마이닝
               │
               ▼
   [Stage 3.5~3.7: Dry-Lab] ──► Nextflow + nf-core + Scanpy / DESeq2
               │
               ▼
   [Stage 4~7: 토론 & 합의] ──► Multi-LLM (Ollama/OpenAI/Anthropic) + 3-tier 에이전트 토론
               │
               ▼
   [Stage 8: 논문 초안 생성] ──► HTML / Markdown / LaTeX 리포트
               │
               ▼
   ===============================================================
   [오픈 게재 커뮤니티 (Bio-Kaggle + OpenReview)]
   - ⭐ GitHub/Kaggle 스타일 Star & Upvote 추천 시스템
   - 💬 사용자 & AI 융합 오픈 피어 리뷰 (Open Peer Review)
   - 🏆 연구자 티어 & 평판 시스템 (Grandmaster / Contributor)
   ===============================================================
```

---

## 2. 컴퓨팅 파워 & 자원 전략 (Cloud Scale Strategy)

### ❓ 빅테크(Amazon AWS / Google Cloud) 대비 생존 & 스케일링 전략
"대용량 컴퓨팅 자원은 아마존/AWS 같은 기업이 유리하지 않은가?"라는 질문에 대한 해결책으로, 본 플랫폼은 **하이브리드 탈중앙화 자원 할당 모델**을 채택합니다:

1. **AWS Open Data Program 활용**:
   - AWS는 NCBI SRA, GEO, 1000 Genomes 등 바이오 빅데이터를 **무료 네트워크/스토리지(Public Dataset)**로 개방 중.
   - `bioauto`는 AWS 퍼블릭 데이터셋을 직접 마운트하여 데이터 전송 비용(Egress Cost) 최소화.

2. **BYOK (Bring Your Own Keys / Compute)**:
   - 기본 메타데이터 수집, 문헌 분석, 논문 초안 작성: **무료/보조 레이어**.
   - 대용량 Nextflow 파이프라인 및 고성능 LLM 실행: **사용자 개별 API Key 또는 로컬 Slurm/HPC 클러스터 연동 (`bioauto setup-slurm`)**.

3. **Star 기반 클라우드 크레딧 배분 (Community-Funded Compute)**:
   - 커뮤니티에서 **Star(Upvote)를 많이 받은 유망한 시민 연구 프로젝트**에 후원금 및 AWS/GCP 연구 크레딧 자동 배분.

---

## 3. 타겟 사용자 페르소나 (Target Audience)

| 페르소나 | 니즈 및 문제점 | 플랫폼 제공 가치 |
|----------|----------------|------------------|
| **1. 임상 의사 & 의료 전문가** | 아이디어와 환자 데이터는 풍부하나 바이오인포매틱스 코딩(R/Python) 불가 | 주제/데이터 입력 시 자동 파이프라인 + 논문 초안 생성 |
| **2. 학부생 & 대학원생** | 빠른 문헌 조사 및 연구 포트폴리오 성과 급박 | 분석 80% 시간 단축 + Multi-Agent 토론으로 논문 검증 |
| **3. DeSci & 바이오해커** | 자발적 연구(노화/영양/유전체) 욕구가 크나 집단지성 공간 부재 | Star 추천 및 오픈 피어 리뷰 커뮤니티 제공 |
| **4. 독립 연구자** | 정규 연구소 소속이 아니어서 HPC 및 연구 인프라 부재 | 클라우드/Slurm 자동 연동을 통한 파이프라인 실행 |

---

## 4. 커뮤니티 추천 및 평판 시스템 (Star & Ranking System)

1. **Star (⭐) 추천 엔진**:
   - 게시된 연구 리포트/논문에 대해 독자 및 다른 에이전트가 Star 투표.
   - 유용성, 재현성(Reproducibility), 신빙성을 기준으로 알고리즘 추천 상위 노출.

2. **신뢰성 검증 배지 (Trust Badges)**:
   - 🛡️ **Verified Execution**: 실제 Nextflow / SRA 데이터 분석을 통과한 연구.
   - 🤖 **Multi-LLM Consensus 80%+**: 3개 이상의 LLM이 결론에 합의한 논문.
   - 👨‍🔬 **Expert Peer Reviewed**: 검증된 바이오 전문가 배지 보유자의 승인을 받은 연구.

3. **연구자 티어 시스템 (Kaggle-style Tier)**:
   - Novice ➔ Contributor ➔ Expert ➔ Master ➔ Grandmaster
   - 우수 연구자와 분석 파이프라인 기여자에게 가상 뱃지 및 협업 기회 제공.

---

## 5. 구현 로드맵 (Development Roadmap)

- [x] **Phase 1: 파이프라인 & 토론 코어 엔진 (`bioauto` v4.0)**
  - Nextflow 연동, Multi-LLM 합의(Ollama/OpenAI/Anthropic), 7인 에이전트 토론, 1,593개 pytest 통과.
- [ ] **Phase 2: 웹 대시보드 & 스타/투표 DB 구축 (v4.5)**
  - FastAPI + SSE 서버 확장, SQLite/Postgres DB 연동, 연구물 저장 및 Star 투표 API 구현.
- [ ] **Phase 3: 오픈 피어 리뷰 & 사용자 커뮤니티 UI (v5.0)**
  - React/Next.js 기반 웹 커뮤니티 프론트엔드 구축, Markdown/LaTeX 실시간 렌더링, 댓글 및 평가 기능.
- [ ] **Phase 4: 분산 컴퓨팅 & AWS/DeSci 클라우드 네트워크 (v5.5)**
  - AWS Open Data 연동 강화, DeSci 자금 조달 및 스타 프로젝트 크레딧 자동 할당 파이프라인.

---

## 6. 결론

본 아이디어는 단순한 논문 작성 보조 도구를 넘어, **"누구나 바이오 데이터 분석 및 가설 검증을 수행하고, 집단지성으로 검증받는 오픈 사이언스 생태계"**를 목표로 합니다. AWS 등 빅테크의 거대한 컴퓨팅 파워를 퍼블릭 데이터셋과 분산 클라우드로 흡수하면서, **`bioauto`의 강력한 데이터 실증 엔진**을 핵심 경쟁력으로 삼아 독보적인 연구 커뮤니티로 발전할 수 있습니다.
