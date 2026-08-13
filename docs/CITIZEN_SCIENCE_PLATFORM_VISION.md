# bioauto 확장 비전: 전분야 자율 연구 & 시민 과학 오픈 게재 커뮤니티 (Universal Platform Vision)

> **문서 버전**: v1.2.0  
> **작성일**: 2026-08-13  
> **상태**: 로드맵 및 비전 제안서 (Strategic Vision Proposal)

---

## 1. 개요 (Executive Summary)

본 문서는 현재 구축 완료된 **`bioauto` 파이프라인 엔진**(Nextflow + Multi-LLM 합의 + 멀티 에이전트 토론 + 자동 리포팅)을 기반으로, 바이오 분야를 넘어 **전 학문 분야의 아이디어를 자율 검증하고 논문으로 게재하는 "오픈 사이언스 & 시민 과학 자율 연구 커뮤니티"**로 확장하기 위한 플랫폼 아키텍처 및 전략적 로드맵을 정의합니다.

```
[사용자 입력: 아이디어 + 논리 (Idea & Logic)]
                       │
                       ▼
    ┌──────────────────────────────────────────────┐
    │  1. 오픈 데이터 RAG 연합 레거시 (Open APIs) │
    │  - OpenAlex (2.5억개 논문 지식 그래프)        │
    │  - Semantic Scholar (2억개 논문 API)         │
    │  - arXiv, PubMed, FRED, GitHub API           │
    └──────────────────┬───────────────────────────┘
                       ▼
    ┌──────────────────────────────────────────────┐
    │  2. Multi-Agent 파이프라인 & 실행 샌드박스   │
    │  - 가설 정밀화 ──► 데이터 분석 코드 자동 실행│
    │  - Red Team 교차 검증 ──► 논문 자동 집필     │
    └──────────────────┬───────────────────────────┘
                       ▼
    ┌──────────────────────────────────────────────┐
    │  3. 오픈 게재 & 스타(Star) 평가 커뮤니티    │
    │  - ⭐ Upvote / Star 추천 알고리즘             │
    │  - 💬 AI + 인간 오픈 피어 리뷰 (OpenReview)  │
    │  - 🏆 Kaggle 스타일 리더보드 & 연구자 티어    │
    └──────────────────────────────────────────────┘
```

---

## 2. Kaggle 플랫폼 개요 및 벤치마킹 요소

### ❓ Kaggle(캐글)이란 어떤 사이트인가?
**Kaggle**은 구글(Google)이 소유한 **세계 최대의 데이터 사이언스 & 머신러닝 커뮤니티 플랫폼**입니다.

1. **Competitions (경쟁 대격돌)**: 기업/기관이 데이터셋과 상금을 걸면 전 세계 사용자가 AI 모델을 제출해 실시간 리더보드(Leaderboard)로 경쟁.
2. **Datasets & Notebooks (오픈 코드/데이터)**: 무료 브라우저 Jupyter Notebook(GPU 지원) 환경에서 코드와 분석 리포트를 공유.
3. **Upvote & Tier 게이피케이션**: 커뮤니티의 Upvote(추천)를 모아 **Novice ➔ Contributor ➔ Expert ➔ Master ➔ Grandmaster** 티어를 획득 (글로벌 AI 채용의 핵심 포트폴리오).

> **💡 본 서비스와의 결합 포인트**: Kaggle은 **"머신러닝 경진대회"**에 집중되어 있으므로, 본 플랫폼은 **"Kaggle의 스타/티어 재미요소 + 전 학문 논문 자동 집필 RAG + 오픈 피어 리뷰 게재"**를 결합하여 **"Kaggle for Open Science & Research Papers"**로 진화시킵니다.

---

## 3. 전 세계 문헌 RAG 인덱싱 현황: "우리가 직접 RAG를 구축해야 하는가?"

### ❓ "이미 전 세계 논문/데이터를 RAG화 해둔 곳이 있는가?"
**답변: 네! 전 세계 2억 5천만 편 이상의 모든 논문과 인용 그래프는 이미 글로벌 기관에서 오픈 API로 완벽하게 RAG화되어 제공되고 있습니다.**

따라서 플랫폼이 직접 2억 개의 PDF를 다운로드받아 Vector DB를 거대하게 구축할 필요가 없으며, **이미 완성된 오픈 RAG API를 연합(Federation) 호출**하기만 하면 됩니다.

### 🌐 이미 RAG화/지식그래프가 구축된 주요 오픈 API

| 글로벌 오픈 RAG/API 플랫폼 | 인덱싱 규모 | 제공 서비스 및 연동 방식 |
|----------------------------|-------------|-------------------------|
| **1. OpenAlex (openalex.org)** | **2억 5,000만+ 편** | 인류 역사상 모든 학술 논문, 저자, 기관, 인용 관계를 100% 무료 REST API로 제공하는 지식 그래프 |
| **2. Semantic Scholar API** | **2억+ 편** | 앨런 AI 연구소(AI2) 제공. 논문 요약(TLDR), 시맨틱 유사도, 인용 영향력 API 제공 |
| **3. Europe PMC / PubMed API** | **3,500만+ 편** | 바이오/의학 전 분야 전문(Full-text) XML 및 메타데이터 RAG API |
| **4. arXiv API** | **200만+ 편** | CS, AI, 물리학, 수학 분야 최신 논문 & LaTeX 소스 코드 API |
| **5. FRED / SEC EDGAR API** | **80만+ 경제지표** | 미 연준(FRED) 경제 지표 및 미국 상장기업 재무제표 API |

---

## 4. 본 플랫폼이 실제로 구축해야 하는 핵심 핵심 요소 (Secret Sauce)

우리가 만들어야 하는 핵심 가치는 **"데이터 보관"**이 아니라 **"RAG 연합 + Multi-Agent 검증 + 실증 실행 + 오픈 게재/평가"**입니다:

1. **RAG 연합 엔진 (Federated RAG Engine)**:
   - 사용자가 "아이디어 + 논리"를 입력하면 OpenAlex / Semantic Scholar / FRED API를 조합해 관련 문헌과 퍼블릭 데이터셋을 즉시 RAG로 끌어옴.
2. **가설 검증 코드 샌드박스 (Code Execution Sandbox)**:
   - RAG로 끌어온 데이터를 실제로 검증하는 Python / R / Nextflow 코드 샌드박스를 자동 생성 및 실행.
3. **Multi-Agent Red Team 리뷰 (AI Peer Reviewer)**:
   - 가설의 허점, 통계적 오류(p-value 체킹), 할루시네이션을 반박(Debunk)하는 에이전트 패널.
4. **오픈 게재 & Star/Tier 평가 커뮤니티 (Open Publishing Community)**:
   - 검증을 통과한 인터랙티브 논문(HTML/LaTeX)이 커뮤니티에 공개되고, 동료 연구자들의 Star(Upvote)와 댓글 평가로 가치가 입증됨.

---

## 5. 구현 로드맵 (Development Roadmap)

- [x] **Phase 1: 파이프라인 & 토론 코어 엔진 (`bioauto` v4.0)**
  - Nextflow 연동, Multi-LLM 합의, 7인 에이전트 토론, 1,593개 pytest 통과.
- [ ] **Phase 2: OpenAlex & Semantic Scholar 연합 RAG 어댑터 구현 (v4.5)**
  - 2억 5천만 편 오픈 논문 API 연동 및 온디맨드 코드 샌드박스 템플릿 제작.
- [ ] **Phase 3: 웹 커뮤니티 & Star / Upvote 리더보드 구축 (v5.0)**
  - Kaggle 스타일 연구자 티어(Master/Grandmaster), Star 투표 DB 및 OpenReview 게시판 구축.
- [ ] **Phase 4: 글로벌 오픈 사이언스 게재 네트워크 (v5.5)**
  - 인터랙티브 논문 출판(실행 가능한 코드/데이터 셀 포함) 및 글로벌 DeSci 연동.

---

## 6. 결론

사용자는 오직 **"아이디어 + 논리"**만 제공하고, 플랫폼은 **OpenAlex/Semantic Scholar 등 이미 구축된 2.5억 편의 오픈 RAG API**를 연동하여 **가설 검증 ➔ 코드 실행 ➔ 논문 집필 ➔ 커뮤니티 게재/평가**를 완전 자동화합니다. 이것이 바로 **"Kaggle의 재미 + OpenReview의 검증"**이 결합된 전세계 최초의 **보편적 자율 연구 생태계**입니다.
