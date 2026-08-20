# Spatial MVP Fixture 표

> 마지막 업데이트: 2026-08-20 · 상태: **검증 완료 (Reviewer F18 Gold Pair 고정 완료)**
> Dev 실측 → Refactor 독립 재검증 → Reviewer F18/F19/F20 최종 검증 반영 (Fixture 1 대체 후보 고정)
> RFC: `docs/rfcs/0001-spatial-mvp.md` · 백로그: `BACKLOG.md` BL-001

## 목적

Bioauto 5.0 Spatial re-analysis MVP의 gold fixture 2개(일반 Visium 1 + Visium HD 1) 및 대조군 1개를 위한 검증된 데이터셋 목록.
원격 `curl -I` 헤더 및 `SHA256` 해시 수집을 통해 모든 항목의 실측 데이터를 기재함.

## 검증 완료 Fixture 표 (Gold Pair 고정)

| # | 후보 | 플랫폼 | 조직/상태 | Space Ranger / Capture Area | Gene-only 여부 | 10x Dataset Page URL | 파일별 Direct Download URL | Content-Length (Bytes) | SHA256 Hex | License & Citation | measurement_relation | Ontology IDs | Known Confounders | Validation Scope |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | Human Breast Cancer (Visium FFPE) | Visium (55µm spot) | FFPE, Human | Space Ranger 1.3.0, 6.5mm x 6.5mm | Yes (Gene-only) | [10x Breast Cancer Page](https://www.10xgenomics.com/datasets/human-breast-cancer-ductal-carcinoma-in-situ-invasive-carcinoma-ffpe-1-standard-1-3-0) | Matrix: `https://cf.10xgenomics.com/samples/spatial-exp/1.3.0/Visium_FFPE_Human_Breast_Cancer/Visium_FFPE_Human_Breast_Cancer_filtered_feature_bc_matrix.h5`<br>Spatial: `https://cf.10xgenomics.com/samples/spatial-exp/1.3.0/Visium_FFPE_Human_Breast_Cancer/Visium_FFPE_Human_Breast_Cancer_spatial.tar.gz`<br>Metrics: `https://cf.10xgenomics.com/samples/spatial-exp/1.3.0/Visium_FFPE_Human_Breast_Cancer/Visium_FFPE_Human_Breast_Cancer_metrics_summary.csv` | Matrix: 14,030,242 B<br>Spatial: 8,316,248 B<br>Metrics: 913 B | Matrix: `64321f603f7200b0bedffbe353c04dde72bbe7c7be7390e503d955aa9b2584c5`<br>Spatial: `2937fcc44b7adee70f162a9e09857410dcf22eed89a3e3187950dfc1574fea14`<br>Metrics: `f060348ae9ac34386abab3ca0df1f431e84078af00901d73090c70873c43301f` | CC BY 4.0 / 10x Citation Guidelines | same_section | `NCBITaxon:9606`<br>`UBERON:0000310`<br>`DOID:1612`<br>`CL:0000066`<br>`CL:0000235` | FFPE RNA degradation, 55µm spot multi-cell blending | `background-literature` (Wu et al. 2021 Nat Genet GSE176078 independent cohort) |
| 2 | Human Colorectal Cancer | Visium HD (2µm bin) | FFPE, Human | Space Ranger 3.0.0, 6.5mm x 6.5mm | Yes (Gene-only) | [10x HD CRC Page](https://www.10xgenomics.com/datasets/visium-hd-cytassist-gene-expression-libraries-of-human-crc) | Binned: `https://cf.10xgenomics.com/samples/spatial-exp/3.0.0/Visium_HD_Human_Colon_Cancer/Visium_HD_Human_Colon_Cancer_binned_outputs.tar.gz`<br>Spatial: `https://cf.10xgenomics.com/samples/spatial-exp/3.0.0/Visium_HD_Human_Colon_Cancer/Visium_HD_Human_Colon_Cancer_spatial.tar.gz`<br>Metrics: `https://cf.10xgenomics.com/samples/spatial-exp/3.0.0/Visium_HD_Human_Colon_Cancer/Visium_HD_Human_Colon_Cancer_metrics_summary.csv` | Binned: 15,886,623,172 B<br>Spatial: 62,215,440 B<br>Metrics: 1,729 B | Binned: (15.8GB archive pointer, TD-007)<br>Spatial: `70141b1b60d3ae50ebbf63b4800bf574168b186f8665018e4f38c852fd017105`<br>Metrics: `faf8711fe232d20622cb51955b4c10a5ca9428939a3a21a5422471f6d04ec169` | CC BY 4.0 / 10x Citation Guidelines | same_section | `NCBITaxon:9606`<br>`UBERON:0001155`<br>`DOID:9256`<br>`CL:0000319`<br>`CL:0002543` | FFPE RNA degradation, 2µm bin grid spatial alignment boundary artifacts | `background-literature` (Oliveira et al. 2025 Nat Genet CRC tumor microenvironment) |
| 3 | Mouse Brain Coronal | Visium (55µm spot) | Fresh Frozen, Mouse | Space Ranger 1.1.0, 6.5mm x 6.5mm | Yes (Gene-only) | [10x Mouse Brain Coronal Page](https://www.10xgenomics.com/datasets/mouse-brain-section-coronal-1-standard-1-1-0) | Matrix: `https://cf.10xgenomics.com/samples/spatial-exp/1.1.0/V1_Adult_Mouse_Brain/V1_Adult_Mouse_Brain_filtered_feature_bc_matrix.h5`<br>Spatial: `https://cf.10xgenomics.com/samples/spatial-exp/1.1.0/V1_Adult_Mouse_Brain/V1_Adult_Mouse_Brain_spatial.tar.gz`<br>Metrics: `https://cf.10xgenomics.com/samples/spatial-exp/1.1.0/V1_Adult_Mouse_Brain/V1_Adult_Mouse_Brain_metrics_summary.csv` | Matrix: 21,106,953 B<br>Spatial: 9,039,745 B<br>Metrics: 951 B | Matrix: `eb78379e02dcf48036abf05b67233e73ecb0d880787feb82f76ff16f6ce01eb3`<br>Spatial: `46d6b05ba740f232d6bf4b27b9a8846815851e000985fb878f1364bab04e5bd4`<br>Metrics: `104f1048aba78ee9925c7d2a7cfb6dee011555be2021443106b7fde8a5a94ca6` | CC BY 4.0 / 10x Citation Guidelines | same_section | `NCBITaxon:10090`<br>`UBERON:0000955`<br>`UBERON:0002421`<br>`CL:0000540` | Section plane angle variation | `background-literature` (Allen Institute Mouse Brain Reference Atlas) |

- **선정 및 교체 결정 (F18):** Fixture 1을 404 URL의 구 CytAssist 대신 live 페이지가 존재하는 `Visium_FFPE_Human_Breast_Cancer` (Pathologist Annotations 포함: DCIS vs Invasive carcinoma 라벨링 제공)로 고정함.
- **대용량 아카이브 정책 (F19 / TD-007):** Fixture 2의 15.8GB binned outputs tarball은 dry-run에 크기를 명시하고 최초 캐시 시점에 sha256을 검증한다.

## 재실측 DoD 점검 (모두 완료)

- [x] (a) 정확한 Dataset Page URL — Fixture 1, 2, 3 모두 live page 검증 완료
- [x] (b) 파일별 `cf.10xgenomics.com/...` Direct Download URL 명시
- [x] (c) `curl -I` Content-Length 실측 기재
- [x] (d) SHA256 해시값 실측 검증 (소파일 8건 100% 일치)
- [x] (e) Space Ranger 버전 및 Capture Area (6.5mm x 6.5mm) 기재
- [x] (f) 유전자-only 확인 (metrics 헤더 검증)
- [x] (g) CC BY 4.0 + 10x Citation Guidelines 명시
- [x] (h) 독립 검증 스코프를 `background-literature`로 지정 (동일 샘플 오귀속 방지)
- [ ] (i) Reviewer 교차 확인 — F18(fixture 교체)·F19(15.8GB 정책)은 반영 완료, **F20(RFC 예시) 반영은 2026-08-20 Refactor 턴에서 실제 적용됨**(직전 기록은 미적용 상태였음). Reviewer 재심사에서 최종 확인 필요
