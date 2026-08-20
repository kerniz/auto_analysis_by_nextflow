# RFC 0001 — Bioauto 5.0 Spatial Transcriptomics Re-analysis MVP

> 마지막 업데이트: 2026-08-20 · 상태: **Approved for BL-005 Implementation (Reviewer 승인 2026-08-20)**
> 출처: shared board 토의 (codex 확정안 + grok F1–F21 + claude 대조 + 운영자 승인 2026-08-20)

## 1. 범위

**입력:** 공개 Visium/Visium HD의 processed expression matrix + tissue image + spatial positions/scalefactors + metadata manifest.
**출력:** input/QC/artifact provenance, spot/cell annotation, spatial domain, neighborhood summary, 관측·문헌 근거·가설을 분리한 report.
**명시 제외 (5.0):** raw FASTQ/Space Ranger 재처리, Xenium/Stereo-seq native ingest, Multiome/scATAC/CITE, Perturb-seq, long-read, pathology 임상 데이터, foundation model 예측.

**버전:** 기존 릴리스(4.x)와 충돌하지 않도록 **5.0**부터 (1.x 리셋 금지 — grok F5).

## 2. 데이터 계약 및 명세

- **결과 항등원**: `experiment_id` / `dataset_accession`. `PMID`는 optional provenance로 강등 (grok F2). 결과 폴더는 `results/{experiment_id}/`.
- **Legacy 호환**: `PipelineDefinition.nf_core_name`은 deprecate하지 않고 `WorkflowPlan.steps[]`의 adapter step 하나로 wrap (grok F4). `PluginRegistry.detect_all()` 결과를 보존하고 CLI에는 기존 winner-take-all만 노출.
- **분석 라우트**: 새 `analysis_type="spatial"` 추가. 기존 seurat/scanpy 라우트에 좌표/이미지를 넣지 않는다 (grok F6).
- **Visium HD 해상도 정책 (TD-006 / F17)**: 2µm raw matrix는 파이프라인 입력 pointer로 온전히 보존하되, 기본 spatial domain/niche 분석은 **8µm bin**을 표준 단위로 사용한다.

### 2.1 Manifest v0 JSON 명세 (예시)

```json
{
  "schema_version": "0.1",
  "experiment_id": "exp-visium-hd-crc-001",
  "dataset_accession": "10x-visium-hd-crc",
  "pmid": null,
  "license": "CC-BY-4.0",
  "source_url": "https://www.10xgenomics.com/datasets/visium-hd-cytassist-gene-expression-libraries-of-human-crc",
  "reference": {
    "species": "NCBITaxon:9606",
    "genome": "GRCh38",
    "ensembl_version": "110"
  },
  "modality": "spatial_transcriptomics",
  "platform": "10x Visium HD",
  "preservation": "FFPE",
  "spatial_resolution": {
    "raw_bin_um": 2,
    "analysis_bin_um": 8
  },
  "components": {
    "matrix": {
      "format": "h5",
      "path": "binned_outputs/square_008um/filtered_feature_bc_matrix.h5",
      "checksum_sha256": "<64-hex-sha256>",
      "checksum_status": "pending-first-cache",
      "content_length": 15886623172,
      "source_archive": "Visium_HD_Human_Colon_Cancer_binned_outputs.tar.gz"
    },
    "image": {
      "hires": "spatial/tissue_hires_image.png",
      "lowres": "spatial/tissue_lowres_image.png"
    },
    "spatial_positions": {
      "format": "parquet",
      "path": "spatial/tissue_positions.parquet"
    },
    "scalefactors": {
      "format": "json",
      "path": "spatial/scalefactors_json.json"
    }
  }
}
```

### 2.2 WorkflowPlan JSON 명세 (예시)

```json
{
  "plan_id": "plan-spatial-5.0-001",
  "experiment_id": "exp-visium-hd-crc-001",
  "created_at": "2026-08-20T17:00:00Z",
  "recommended_pipeline": null,
  "steps": [
    {
      "step_id": "qc_and_ingest",
      "adapter": "spatial_manifest_validator",
      "parameters": {"min_gene_count": 200, "max_mitochondrial_pct": 20.0}
    },
    {
      "step_id": "spatial_preprocessing",
      "adapter": "spatial_binned_reader",
      "parameters": {"bin_size_um": 8, "normalize": "<tool-neutral: B2 미결정>"}
    },
    {
      "step_id": "domain_and_niche",
      "adapter": "spatial_domain_annotator",
      "parameters": {"n_top_genes": 2000, "spatial_neighbors_k": 6}
    },
    {
      "step_id": "report_generation",
      "adapter": "evidence_separated_reporter",
      "parameters": {"output_format": "markdown+jsonl"}
    }
  ]
}
```

### 2.3 Legacy Signature Mapping

| 기존 시스템 (v4.x) | 신규 아키텍처 (v5.0) | 마이그레이션 방안 |
|---|---|---|
| `PMIDResult` (PMID 기반 아이덴티티) | `Experiment` / `Dataset` (Accession 기반) | PMID는 `Experiment.provenance.pmid` 필드로 이동 |
| `PluginRegistry.detect()` (winner-take-all) | `AssayDetection[]` (복수 모달리티 감지) | CLI 호환성을 위해 `detect()`는 winner 1개 반환 shim 유지 |
| `PipelineDefinition.nf_core_name` | `WorkflowPlan.steps[]` (DAG 어댑터) | legacy 단일 파이프라인은 1-step WorkflowPlan으로 wrap |
| `results/{PMID}` | `results/{experiment_id}` | 신규 분석은 experiment_id 사용, 기존 폴더 호환 유지 |

### 2.4 CLI UX 및 오류 보고 계약

1. **Spatial 구성 요소 누락 시:**
   ```text
   [ERROR] Spatial manifest validation failed for dataset 'exp-visium-hd-crc-001':
           Missing required component 'spatial_positions' at 'spatial/tissue_positions.parquet'.
           Execution blocked before pipeline launch.
   ```
2. **미지원 modality 감지 시 (Safe Block):**
   ```text
   [BLOCKED] Detected sequencing modality 'spatial_transcriptomics' in study inputs.
             Legacy single-cell RNA-seq pipeline execution is safely blocked.
             Use '--analysis-type spatial' with a valid spatial manifest.
   ```

### 2.5 대용량 아카이브 및 checksum 정책 (grok F19 / TD-007)

Visium HD CRC fixture의 분석 입력(`square_008um/`)은 **15,886,623,172 B (≈15.8 GB)** 단일 tarball 안에만 존재한다. 8µm만 받는 단독 CDN 경로는 **403**으로 확인되어 "작은 파일만 내려받기"는 불가능하다.

1. **dry-run 의무 표시**: 실행 전 정확한 바이트 수(`15,886,623,172 B`)와 필요 disk를 제시한다. 사용자 확인 없이 다운로드를 시작하지 않는다 (운영자 D4).
2. **부분 추출 우선**: 다운로드가 승인되면 `tar`로 `square_008um/` 경로만 추출해 disk 사용을 줄인다. 원본 2µm는 분석 입력이 아니라 raw pointer로만 기록한다.
3. **checksum 승격 계약**: 공식 SHA256이 없는 대용량 아카이브는 manifest에 `"checksum_status": "pending-first-cache"` + `content_length`로 식별한다. 최초 캐시가 끝나면 실제 SHA256을 계산해 `"checksum_status": "verified"`로 승격하고 그 값을 manifest에 기록한다.
4. **식별 실패 처리**: `content_length`가 기록값과 다르면 캐시를 무효화하고 실행을 차단한다 (silent 재다운로드 금지).

## 3. 수용 기준 (codex 초안 채택)

1. manifest가 matrix/image/coordinate/reference + checksum·license·source URL을 검증한다.
2. QC/annotation/domain/neighborhood 결과가 artifact와 파라미터로 재현된다.
3. gold fixture 2개(`docs/planning/spatial-fixtures.md`)에서 사전 지정 marker/조직구조를 재현하고 warning을 리포트한다.
4. report는 관측/문헌 근거/가설/confidence를 분리하고 causal·clinical claim을 하지 않는다.
5. dry-run이 다운로드량·disk·runtime·도구를 실행 전 제시하고, 기존 CLI/테스트가 유지된다.
6. **Negative detection**: Visium/Xenium/Stereo-seq/Multiome/scATAC 텍스트가 기존 파이프라인(scrnaseq/rnaseq/atacseq)으로 라우팅되지 않는다 (grok F1/F3).

## 4. 구현 차단 조건 (하나라도 미충족 시 분석/LLM 기능 추가 금지)

fixture license 불명확 · 본 RFC 미승인 · negative-detection 테스트 부재 · provenance 없는 결과 · gold endpoint 사전정의 부재.

## 5. 보류 항목 (결정 전 구현 금지 — 운영자/Planner 결정 필요)

| # | 항목 | 이유 | 임시 처리 |
|---|---|---|---|
| B1 | canonical schema 저장 형식 (버전된 JSON manifest + AnnData vs SpatialData/Zarr) | 도구 생태계 대비 유지비 미평가 | manifest는 JSON, artifact 포맷은 fixture 실측 후 결정 |
| B2 | spatial 분석 도구 선택 (squidpy vs Seurat v5 vs 혼합) | 의존성 무게·컨테이너 정책 미결 | RFC 승인 후 fixture로 PoC 비교 |
| B3 | `experiment_id` 체계 (GEO accession 그대로 vs 내부 UUID+alias) | 기존 `results/{PMID}` 마이그레이션 비용 미측정 | 신규 결과만 새 체계, 기존 폴더 무이동 |
| B4 | 다음 slice (Spatial raw ingest vs Multiome) | fixture 결과 확인 전 | 5.0 게이트 통과 후 결정 |
| B5 | 이미지 내 환자식별정보(HE 슬라이드) access policy | 공개 데이터라도 재배포 조건 상이 | 공개 10x 데이터로 한정, 임상 데이터 금지 유지 |
| B6 | Slurm script 파이프라인별 param 템플릿 (F12) | 검증된 param 세트 없이 개별 패치 위험 | 현행 유지, 5.0 WorkflowPlan에서 설계 |

## 6. 선반영된 안전 수정 (2026-08-18, 본 RFC의 §3-6 항목)

RFC 승인과 무관하게 **현행 오분류가 실사용에서 위험**하므로 P0로 선반영 (전체 목록은 테스트가 진실 — 아래는 요약):
- **감지 계층 (F1/F3/F9)**: `ScRnaSeqPlugin`/`BulkRnaSeqPlugin`에 spatial 배제 키워드(플랫폼명 + "spatial gene expression"/seqfish/starmap 포함), `AtacSeqPlugin`에 scATAC/snATAC/single-nucleus ATAC/multiome 배제 → 미지원 modality는 `unknown`.
- **실행 계층 (F8/F13/F14)**: `_run_nfcore_via_slurm`의 `nf-core/rnaseq` fallback 제거 — 미등록 타입은 Slurm 연결 전에 `blocked_unsupported_type`으로 차단. blocked 결과는 `nfcore_done`이 아닌 `nfcore_blocked` checkpoint로 기록해 타입 지원 추가 시 resume에서 재평가된다 (F13). `chip_seq`는 map 키 오타로 실제 제출된 적이 없고 현행 script 템플릿이 rnaseq 전용이므로 템플릿 검증(F12/B6) 전까지 차단 목록에 유지 (F14).
- **테스트**: `tests/test_plugins.py::TestUnsupportedModalitySafeBlock` (감지) + `tests/test_pipeline.py::TestSlurmUnsupportedTypeBlock` (실행). 이 목록은 고정이 아니며 구멍 발견 시 계속 추가한다.

## 7. Claim/Evidence/Validation 최소 schema (5.1 VE 계약의 씨앗 — 운영자 D3/D5 승인 반영)

5.0 결과물이 5.1 Verification Engine의 생산자가 되도록, spatial report의 각 주장은 아래 최소 필드를 갖는 JSONL 레코드로도 출력한다 (append-only, versioned):

```json
{
  "claim_id": "c-550e8400-e29b-41d4-a716-446655440000",
  "schema_version": "0.1",
  "statement": "EPCAM expression is significantly enriched in Visium HD 8um spatial domain 3 compared to stroma domain 1.",
  "claim_type": "observation",
  "population_context": "NCBITaxon:9606; UBERON:0001155; DOID:9256",
  "endpoint": "EPCAM expression spatial domain differential log2FC",
  "direction": "up",
  "effect": {"value": null, "ci": null, "fdr": null},
  "evidence": [
    {"kind": "artifact", "ref": "results/exp-visium-hd-crc-001/spatial_domain_deg.csv", "span": "L12-L15"}
  ],
  "validation_status": "not-testable",
  "validation_scope": "none",
  "produced_by": {"tool": "spatial_domain_annotator", "version": "5.0.0", "params_ref": "plan-spatial-5.0-001"},
  "created": "2026-08-20T17:00:00Z"
}
```

- `population_context/endpoint/direction` 미기재 claim은 `claim_type=hypothesis` + `validation_status=not-testable`로만 저장 — automated validation을 시작하지 않는다.
- RAG 검색 hit는 `evidence`로 자동 승격하지 않는다. citation evidence는 span(위치) 명시 시에만.
- donor/batch hold-out만 있는 검증은 `validation_scope=internal-robustness-only`로 표기하고 독립 재현이라 부르지 않는다 (운영자 D3 승인).
- 검증 상태는 `supported`, `contradicted`, `inconclusive`, `not-testable` 4가지로 엄격히 통제한다.
- **위 예시는 계약 형태만 보여준다.** 단일 fixture의 관측은 그 자체로 독립 재현이 아니므로 `validation_status=not-testable`, `validation_scope=none`으로 두었고 `effect` 수치는 비웠다. 실제 값 없이 `supported`/`independent-study`를 예시로 쓰면 D3를 스스로 어기는 template이 된다 (grok F20).

## 8. 다음 단계 및 승인 게이트

1. 운영자 결정(D1–D4 승인, D5 분할 승인) 동기화 완료 (2026-08-20)
2. Dev: Fixture 재실측 DoD 충족 (`docs/planning/spatial-fixtures.md` direct download URL, Content-Length, SHA256 hex 기록)
3. Reviewer: 본 RFC 보완본 검토 및 BL-004 RFC 최종 승인 판정
4. 이후 Foundation 구현 (`BL-005` manifest/planner/artifact 모델) 착수
