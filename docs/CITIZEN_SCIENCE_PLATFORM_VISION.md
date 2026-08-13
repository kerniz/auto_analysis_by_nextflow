# AutoIdeaLab (오토아이디어랩) 마스터 비전 & 아키텍처 청사진 (Master Product Blueprint)

> **플랫폼 공식명**: **AutoIdeaLab** (오토아이디어랩)  
> **문서 버전**: v3.0.0 (공식 마스터 청사진)  
> **작성일**: 2026-08-13  
> **상태**: 확정 마스터 비전 제안서 (Official Master Blueprint)

---

## 1. 개요 (Executive Summary)

**AutoIdeaLab(오토아이디어랩)**은 `bioauto` 코어 분석 엔진을 기점으로, 모든 학문 분야의 아이디어를 **"자국어 편한 작성 ➔ AI 품질 선별 ➔ 사전 찬반 방어 포인트 ➔ 1클릭 Star vs 사유명시 Anti-Star(-10스타/동일사유 1회) ➔ 최초 게재일 인증 ➔ 정식 논문화 졸업 축하"**까지 완전 자동 연결하는 **전세계 최초의 자율 연구 & 캐주얼 논문 게재 커뮤니티**입니다.

```
[1. 자국어로 편하게 아이디어 작성 (하루 최대 5편 제한)]
                       │
                       ▼
[2. AI 사전 품질 선별 (High-Signal Pre-Curation)]
- 똥글/스팸 100% 사전에 컷팅 ➔ 오직 검증된 "보석급 아이디어"만 게재
- bioauto 7인 에이전트 사전 찬반 방어 포인트 제시
                       │
                       ▼
[3. 글로벌 다국어 자동 번역 (Native to Multi-Lingual)]
- 한국어/일어/스페인어 등 편한 자국어 입력 ➔ 영어 및 전세계 언어로 1초 자동 번역
                       │
                       ▼
[4. 타임스탬프 최초 게재일 인증 (Priority Protection)]
- 해시(SHA-256) 기반 최초 가설 창안 일시 영구 증명 (아이디어 도용 방지)
                       │
                       ▼
[5. Star(⭐) vs Anti-Star(⚡) 게임이론 메커니즘]
- Star (⭐): 1클릭 즉시 추천 (+1 Star)
- Anti-Star (⚡): 이유 명시 필수 + AI 스크리닝 검증 ➔ 승인 시 "-10 Star 페널티" (동일 사유 중복합산 1회 제한)
- 맹목적 비난 억제 & 지적 정직성 기반 "뜨거운 화제성 지수" 산출
                       │
                       ▼
[6. 집단지성 피드백 ➔ 정식 논문화 졸업(Graduation) 축하]
- 1클릭 AI 인용 (BibTeX/APA) & 글로벌 커뮤니티 피드백
- 정식 학술지/학회 채택 시 "명예의 전당 (Graduated Paper)" 배지 및 축하 이행
```

---

## 2. AutoIdeaLab 공식 정체성 (Brand Identity)

- **플랫폼명**: **AutoIdeaLab** (오토아이디어랩)
- **슬로건**: *"Where Every Idea Becomes a Proven Paper." (모든 아이디어가 검증된 논문이 되는 연구소)*
- **핵심 가치**:
  1. **High-Signal Pre-Curation**: 똥글 노이즈 없이 오직 검증된 보석급 아이디어만 서비스.
  2. **Zero Barrier**: 자국어로 편하게 써도 실시간 글로벌 다국어 논문으로 변환.
  3. **Priority Protection**: 최초 작성 일시 암호화 타임스탬프 영구 증명.
  4. **Fair Game Theory**: 1클릭 Star와 사유명시 Anti-Star(-10스타 중량 / 동일사유 중복 금지)의 완벽한 밸런스.

---

## 3. 투표 메커니즘 및 게임이론 설계 (Star & Anti-Star Game Theory)

### 🌟 Star (⭐) 투표 메커니즘
- **방식**: **1클릭 방식 (Click-and-Go)** (`+1 Star`).
- **기능**: 공감, 지지, 훌륭한 아이디어에 대해 저항 없이 즉시 추천.

### ⚡ Anti-Star (⚡) 투표 메커니즘 (동일 사유 중복 금지 룰)
- **방식**: **구체적 사유 명시 필수 + AI 스크리닝 검증**.
- **규칙 세부사항**:
  1. **사유 입력 의무화**: 단순 해이트/비방 클릭 불가.
  2. **AI 스크리닝 필터**: 반론 사유 실시간 검증.
  3. **-10 Star 페널티 효과**: 정식 승인 시 마이너스 10개의 Star 중량.
  4. **🚫 동일 사유 중복합산 금지 (Deduplication Rule)**:
     - 이미 지적된 동일 사유는 단 1회만 -10 Star 페널티 적용, 후속 사용자는 지지/동의만 가능.

---

## 4. 종합 개발 로드맵 (Development Roadmap)

- [x] **Phase 1: 코어 분석 & 토론 엔진 (`bioauto` v4.0)** (Nextflow + Multi-LLM 토론 + 1,593개 pytest)
- [ ] **Phase 2: AI 품질 선별 & 자국어 작성-다국어 번역 엔진 (v4.5)** (High-Signal Filter + Multi-Lingual Translator)
- [ ] **Phase 3: Anti-Star 사유명시/AI스크리닝(-10스타/동일사유1회) & 최초 게재일 인증 (v5.0)** (Deduplicated Anti-Star + SHA-256 Priority)
- [ ] **Phase 4: AutoIdeaLab 웹 갤러리 UI & 1클릭 인용/졸업 축하 커뮤니티 (v5.5)** (DC/Reddit 스타일 갤러리 + 명예의 전당)
