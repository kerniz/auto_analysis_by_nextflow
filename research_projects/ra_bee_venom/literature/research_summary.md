# 류마티스 관절염(RA) x 봉독(Bee Venom) 유전체 연관 탐색 결과

## 1. 핵심 논문 (PMID)

| PMID | 제목 | 핵심 발견 |
|------|------|-----------|
| 39759520 | Melittin as a therapeutic agent for RA: mechanistic insights | Melittin이 IKKα/IKKβ 억제 → NF-κB 비활성화, TNF-α/IL-6/IL-1β 감소, MMP-1/MMP-8 억제, caspase-3 활성화 |
| 18507870 | JNK pathway in inhibition of NF-κB by melittin | Melittin/BV가 JNK 경로를 통해 NF-κB, iNOS, COX-2 발현 억제 |
| 17067557 | Melittin inhibits inflammatory target gene via IκB kinase | Melittin이 IκB kinase와 직접 상호작용하여 염증 유전자 발현 차단 |
| 25379111 | Immunomodulatory effects of BV in human synovial fibroblast | 봉독의 활액막 섬유모세포에서 면역조절 효과 |
| 31820689 | Melittin induces apoptosis/autophagy in RA FLS | RA 환자 활액막 섬유모세포에서 apoptosis/autophagy 유도 (BAX/BCL-2, caspase-3) |
| 32640244 | Systemic BV anti-arthritic properties in rat model | 봉독 60mg/kg 전신투여로 관절염 래트 모델에서 항관절염 효과 |
| 33339654 | Anti-inflammatory effects of BV in adjuvant arthritis | 실험적 보조제 관절염에서 봉독의 항염 효과 |

## 2. 유전자/경로 교차점 맵

### 봉독 성분별 타겟 유전자
```
Melittin (40-50%)
├── NF-κB pathway: IKKα, IKKβ, IκBα, p50, p65
├── Cytokines: TNF-α, IL-6, IL-1β
├── Enzymes: COX-2, iNOS, PLA2
├── MMPs: MMP-1, MMP-8 (관절 파괴 억제)
├── Apoptosis: caspase-3 ↑, BAX ↑, BCL-2 ↓
└── Signaling: JNK, ERK1/2, p38 MAPK, AKT, PLCγ1

Apamin
└── Ca2+ channel (SK channels)

Adolapin
└── COX inhibition
```

### RA 핵심 유전자와의 교차점
```
RA Genes          Melittin Target    연관성
─────────────────────────────────────────────
TNF-α             ✓ 억제             직접 억제
IL-6              ✓ 억제             직접 억제
IL-1β             ✓ 억제             직접 억제
NF-κB (p50/p65)   ✓ 억제             IKK 차단으로 비활성화
MMP-1/MMP-3       ✓ 억제             관절 연골 파괴 방지
RANKL             간접                NF-κB 하위, 파골세포 분화
JAK-STAT          간접                사이토카인 수용체 하위
COX-2             ✓ 억제             프로스타글란딘 생성 차단
```

## 3. 사용 가능한 GEO/SRA 데이터셋

### RA 활액막 RNA-seq (공개 데이터)
| Accession | 설명 | 타입 | Raw Data | 비고 |
|-----------|------|------|----------|------|
| GSE185440 | RA vs OA 관절 조직 (HOTAIR lncRNA) | bulk RNA-seq + ChIP-seq + scRNA-seq | **SRP340267 공개** | 18 samples |
| GSE109448 | RA synovial fibroblast subsets | RNA-seq | **비공개** (환자 프라이버시) | 25 samples |
| GSE89408 | RA synovial tissue RNA-seq | RNA-seq | 확인 필요 | |
| GSE112656 | RA synovial tissue RNA-seq | RNA-seq | 확인 필요 | |

### 봉독/Melittin 처리 RNA-seq
- 현재까지 봉독/melittin 처리 + RNA-seq 공개 데이터셋은 발견되지 않음
- 대부분 qRT-PCR, Western blot 기반 연구

## 4. 추천 분석 전략

### Phase 1: RA 활액막 전사체 분석
1. **GSE185440** (SRP340267) raw FASTQ 다운로드 → nf-core/fetchngs
2. nf-core/rnaseq (STAR + Salmon) 파이프라인 실행
3. DESeq2로 RA vs OA 차등 발현 분석
4. Melittin 타겟 유전자 (TNF-α, IL-6, NF-κB, MMP-1 등)의 RA에서의 발현 변화 확인

### Phase 2: 경로 분석
1. GSEA: NF-κB, JNK/MAPK, TNF signaling pathway 농축 분석
2. Melittin 타겟 유전자 vs RA DEGs 교차점 분석
3. 봉독이 치료제로 작용할 수 있는 유전체적 근거 도출

### Phase 3 (확장): scRNA-seq
- GSE185440의 scRNA-seq 데이터로 cell-type 특이적 분석
- nf-core/scrnaseq → Seurat 클러스터링
- 활액막 섬유모세포 subtype별 Melittin 타겟 유전자 발현 패턴

## 5. 결론

봉독(특히 Melittin)은 RA의 핵심 병인 경로인 NF-κB, TNF-α, IL-6를 직접 억제하며,
MMP에 의한 관절 파괴를 방지하고, 활액막 섬유모세포의 apoptosis를 유도합니다.
유전체 수준에서 강력한 치료 잠재력이 있으며, 공개 RNA-seq 데이터(GSE185440)를
활용하여 실제 전사체 분석으로 검증할 수 있습니다.
