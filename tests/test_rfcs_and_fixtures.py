"""Mechanical verification tests for RFCs, Fixture table formats, and Foundation models (TD-008)."""

import json
import re
from pathlib import Path

import pytest

from core.artifact import ClaimRecord
from core.manifest import SpatialManifest, SpatialManifestValidationError
from core.workflow_plan import WorkflowPlan


def test_rfc0001_json_examples_parse_cleanly():
    """Verify that all JSON code blocks in docs/rfcs/0001-spatial-mvp.md parse cleanly with json.loads."""
    rfc_path = Path("docs/rfcs/0001-spatial-mvp.md")
    assert rfc_path.exists(), "RFC 0001 file must exist"

    content = rfc_path.read_text(encoding="utf-8")
    json_blocks = re.findall(r"```json\s*(\{.*?\})\s*```", content, re.DOTALL)
    assert len(json_blocks) >= 3, f"Expected at least 3 JSON blocks in RFC 0001, found {len(json_blocks)}"

    for idx, block in enumerate(json_blocks, start=1):
        try:
            parsed = json.loads(block)
            assert isinstance(parsed, dict), f"JSON block {idx} must parse into a dict"
        except Exception as e:
            pytest.fail(f"JSON block {idx} in RFC 0001 failed to parse: {e}\nBlock content:\n{block}")


def test_rfc0001_claim_schema_obeys_d3_rules():
    """Verify that the Claim schema example in RFC 0001 complies with D3 rules."""
    rfc_path = Path("docs/rfcs/0001-spatial-mvp.md")
    content = rfc_path.read_text(encoding="utf-8")
    json_blocks = re.findall(r"```json\s*(\{.*?\})\s*```", content, re.DOTALL)

    claim_block = None
    for block in json_blocks:
        data = json.loads(block)
        if "claim_id" in data:
            claim_block = data
            break

    assert claim_block is not None, "Claim record JSON block not found in RFC 0001"
    claim = ClaimRecord.from_dict(claim_block)
    assert claim.validation_scope == "none"
    assert claim.validation_status in ["not-testable", "inconclusive"]
    assert claim.validation_status != "supported"


def test_spatial_fixtures_table_formatting_and_urls():
    """Verify that docs/planning/spatial-fixtures.md contains valid HTTP/HTTPS URLs and SHA256 hex hashes."""
    fixtures_path = Path("docs/planning/spatial-fixtures.md")
    assert fixtures_path.exists(), "spatial-fixtures.md must exist"

    content = fixtures_path.read_text(encoding="utf-8")
    urls = re.findall(r"https?://cf\.10xgenomics\.com/[^\s\"'<>|`]+", content)
    assert len(urls) >= 6, f"Expected direct download URLs in spatial-fixtures.md, found {len(urls)}"

    # sha256 hex strings (64 hex characters)
    sha256_hashes = re.findall(r"`([a-f0-9]{64})`", content)
    assert len(sha256_hashes) >= 5, f"Expected 64-hex SHA256 hashes in spatial-fixtures.md, found {len(sha256_hashes)}"


def test_rfc0001_pins_reviewer_conditions():
    """보드↔파일 drift 재발 방지 (TD-008).

    과거 F19/F20이 '수정 완료'로 기록됐으나 파일에는 반영되지 않은 사고가 있었다.
    Reviewer가 명시한 조건을 파일 내용으로 직접 고정한다.
    """
    content = Path("docs/rfcs/0001-spatial-mvp.md").read_text(encoding="utf-8")

    # F20: 도구(B2) 조기 확정 금지
    assert "SCTransform" not in content, "F20 위반: B2 미결정인데 특정 도구가 RFC에 확정됨"
    # F19: 대용량 아카이브 checksum 승격 계약
    assert "pending-first-cache" in content, "F19 위반: checksum 승격 계약이 RFC에 없음"
    # F19: dry-run이 표시해야 하는 정확한 아카이브 바이트
    assert "15,886,623,172" in content or "15886623172" in content, \
        "F19 위반: HD 아카이브 바이트 수가 RFC에 없음"


def test_rfc0001_hd_manifest_reports_pending_checksum():
    """RFC의 HD manifest 예시가 checksum 미검증으로 보고되는지 (F19/§2.5-3).

    component 단위 checksum_status를 읽지 않으면 15.8GB 미검증 아카이브가
    'verified'로 보고되는 회귀가 발생한다.
    """
    content = Path("docs/rfcs/0001-spatial-mvp.md").read_text(encoding="utf-8")
    blocks = re.findall(r"```json\s*(\{.*?\})\s*```", content, re.DOTALL)
    manifest_data = next(
        json.loads(b) for b in blocks if "components" in json.loads(b)
    )

    manifest = SpatialManifest.from_dict(manifest_data)
    assert manifest.checksum_status == "pending-first-cache"
    assert "matrix" in manifest.pending_checksum_components()


def test_dry_run_separates_archive_from_extracted_file():
    """F21: source_archive가 있으면 content_length는 아카이브 크기다.

    추출 파일 크기로 오인해 임의 배수로 disk를 추정하면 안 된다.
    """
    manifest = SpatialManifest.from_dict({
        "schema_version": "0.1",
        "experiment_id": "exp-hd-001",
        "modality": "spatial_transcriptomics",
        "license": "CC-BY-4.0",
        "source_url": "https://www.10xgenomics.com/datasets/test",
        "components": {
            "matrix": {
                "format": "h5",
                "path": "binned_outputs/square_008um/filtered_feature_bc_matrix.h5",
                "content_length": 15886623172,
                "source_archive": "Visium_HD_Human_Colon_Cancer_binned_outputs.tar.gz",
                "checksum_status": "pending-first-cache",
            },
            "image": {"hires": "spatial/tissue_hires_image.png"},
            "spatial_positions": {"format": "parquet", "path": "spatial/tissue_positions.parquet"},
            "scalefactors": {"format": "json", "path": "spatial/scalefactors_json.json"},
        },
    })

    ref = manifest.component("matrix")
    assert ref is not None and ref.is_archived

    dry_run = WorkflowPlan.create_spatial_plan(manifest).dry_run_summary(manifest)
    assert dry_run["estimated_download_bytes"] == 15886623172
    # 추출 후 크기를 모르므로 총 disk를 단정하지 않는다
    assert dry_run["estimated_disk_bytes"] is None
    assert dry_run["requires_extraction"] is True
    archived = dry_run["archived_components"]
    assert len(archived) == 1
    assert archived[0]["archive_bytes"] == 15886623172
    assert archived[0]["extracted_bytes"] is None


def test_content_length_mismatch_blocks_execution(tmp_path):
    """RFC §2.5-4: content_length 불일치 시 실행 차단 (silent 재다운로드 금지)."""
    (tmp_path / "matrix.h5").write_bytes(b"x" * 10)
    manifest = SpatialManifest.from_dict({
        "schema_version": "0.1",
        "experiment_id": "exp-001",
        "modality": "spatial_transcriptomics",
        "license": "CC-BY-4.0",
        "source_url": "https://www.10xgenomics.com/datasets/test",
        "components": {
            "matrix": {"format": "h5", "path": "matrix.h5", "content_length": 999},
            "image": {"hires": "hires.png"},
            "spatial_positions": {"format": "parquet", "path": "positions.parquet"},
            "scalefactors": {"format": "json", "path": "scalefactors.json"},
        },
    })

    with pytest.raises(SpatialManifestValidationError, match="content_length mismatch"):
        manifest.validate_content_length(tmp_path)

    # 아카이브 component는 추출 파일 크기와 비교하지 않는다 (F21)
    archived = SpatialManifest.from_dict({
        "schema_version": "0.1",
        "experiment_id": "exp-002",
        "modality": "spatial_transcriptomics",
        "license": "CC-BY-4.0",
        "source_url": "https://www.10xgenomics.com/datasets/test",
        "components": {
            "matrix": {
                "format": "h5", "path": "matrix.h5",
                "content_length": 999, "source_archive": "bundle.tar.gz",
            },
            "image": {"hires": "hires.png"},
            "spatial_positions": {"format": "parquet", "path": "positions.parquet"},
            "scalefactors": {"format": "json", "path": "scalefactors.json"},
        },
    })
    archived.validate_content_length(tmp_path)  # 예외 없이 통과해야 함


def test_missing_image_file_is_detected(tmp_path):
    """path 키가 없는 image component도 존재 검증 대상에 포함된다."""
    for name in ("matrix.h5", "positions.parquet", "scalefactors.json"):
        (tmp_path / name).write_bytes(b"")
    manifest = SpatialManifest.from_dict({
        "schema_version": "0.1",
        "experiment_id": "exp-003",
        "modality": "spatial_transcriptomics",
        "license": "CC-BY-4.0",
        "source_url": "https://www.10xgenomics.com/datasets/test",
        "components": {
            "matrix": {"format": "h5", "path": "matrix.h5"},
            "image": {"hires": "missing_hires.png"},
            "spatial_positions": {"format": "parquet", "path": "positions.parquet"},
            "scalefactors": {"format": "json", "path": "scalefactors.json"},
        },
    })

    with pytest.raises(SpatialManifestValidationError, match="image.hires"):
        manifest.validate_file_existence(tmp_path)


def test_spatial_manifest_validation_and_dry_run(tmp_path):
    """Test SpatialManifest loading, missing component error, and WorkflowPlan dry-run estimation."""
    manifest_data = {
        "schema_version": "0.1",
        "experiment_id": "exp-test-001",
        "dataset_accession": "test-accession",
        "modality": "spatial_transcriptomics",
        "platform": "Visium HD",
        "license": "CC-BY-4.0",
        "source_url": "https://example.com/dataset",
        "spatial_resolution": {"raw_bin_um": 2, "analysis_bin_um": 8},
        "components": {
            "matrix": {"format": "h5", "path": "matrix.h5", "content_length": 14030242},
            "image": {"hires": "hires.png", "lowres": "lowres.png"},
            "spatial_positions": {"format": "parquet", "path": "positions.parquet"},
            "scalefactors": {"format": "json", "path": "scalefactors.json"},
        },
    }

    manifest = SpatialManifest.from_dict(manifest_data)
    assert manifest.experiment_id == "exp-test-001"
    assert manifest.spatial_resolution.analysis_bin_um == 8.0

    plan = WorkflowPlan.create_spatial_plan(manifest)
    assert plan.experiment_id == "exp-test-001"
    assert len(plan.steps) == 4
    assert plan.steps[1].parameters["bin_size_um"] == 8.0
    assert plan.steps[1].parameters["normalize"] == "standard"

    dry_run = plan.dry_run_summary(manifest)
    assert dry_run["estimated_download_bytes"] == 14030242
    assert dry_run["step_count"] == 4

    # File existence validation fails when target files do not exist
    with pytest.raises(SpatialManifestValidationError, match="Missing required component file"):
        manifest.validate_file_existence(tmp_path)


def test_invalid_spatial_manifest_raises_error():
    """Test that missing required fields in manifest raise SpatialManifestValidationError."""
    with pytest.raises(SpatialManifestValidationError, match="Missing required field 'modality'"):
        SpatialManifest.from_dict({"schema_version": "0.1", "experiment_id": "exp-001"})

    with pytest.raises(SpatialManifestValidationError, match="Missing required component 'matrix'"):
        SpatialManifest.from_dict({
            "schema_version": "0.1",
            "experiment_id": "exp-001",
            "modality": "spatial_transcriptomics",
            "license": "CC-BY-4.0",
            "source_url": "https://www.10xgenomics.com/datasets/test",
            "components": {"image": {"hires": "hires.png"}},
        })


def test_f22_direct_claim_record_constructor_enforces_d3():
    """Verify that direct ClaimRecord instantiation enforces D3 rules via __post_init__ (F22)."""
    with pytest.raises(ValueError, match="validation_scope='none' cannot have validation_status='supported'"):
        ClaimRecord(
            statement="Test statement",
            claim_type="observation",
            population_context="context",
            endpoint="endpoint",
            direction="up",
            validation_status="supported",
            validation_scope="none",
        )


def test_f23_empty_license_or_source_url_raises_validation_error():
    """Verify that empty license or source_url fields raise SpatialManifestValidationError (F23)."""
    base_data = {
        "schema_version": "0.1",
        "experiment_id": "exp-001",
        "modality": "spatial_transcriptomics",
        "license": "CC-BY-4.0",
        "source_url": "https://www.10xgenomics.com/datasets/test",
        "components": {
            "matrix": {"format": "h5", "path": "matrix.h5"},
            "image": {"hires": "hires.png"},
            "spatial_positions": {"format": "parquet", "path": "pos.parquet"},
            "scalefactors": {"format": "json", "path": "scale.json"},
        },
    }

    with pytest.raises(SpatialManifestValidationError, match="Missing or empty required field 'license'"):
        SpatialManifest.from_dict({**base_data, "license": "   "})

    with pytest.raises(SpatialManifestValidationError, match="Missing or empty required field 'source_url'"):
        SpatialManifest.from_dict({**base_data, "source_url": ""})



def test_f23_missing_license_or_source_url_raises_validation_error():
    """F23: license·source_url이 '누락'된 경우에도 차단돼야 한다.

    기본값을 먼저 채우고 빈 문자열만 검사하면 누락이 통과한다 — 그 회귀를 고정한다.
    """
    base_data = {
        "schema_version": "0.1",
        "experiment_id": "exp-001",
        "modality": "spatial_transcriptomics",
        "components": {
            "matrix": {"format": "h5", "path": "matrix.h5"},
            "image": {"hires": "hires.png"},
            "spatial_positions": {"format": "parquet", "path": "pos.parquet"},
            "scalefactors": {"format": "json", "path": "scale.json"},
        },
    }

    with pytest.raises(SpatialManifestValidationError, match="required field 'license'"):
        SpatialManifest.from_dict(base_data)

    with pytest.raises(SpatialManifestValidationError, match="required field 'source_url'"):
        SpatialManifest.from_dict({**base_data, "license": "CC-BY-4.0"})


def test_web_token_comparison_is_constant_time():
    """G3: 서버 토큰 비교가 secrets.compare_digest를 쓰는지 (타이밍 누출 방지)."""
    source = Path("web/app.py").read_text(encoding="utf-8")
    assert "secrets.compare_digest" in source, "토큰 비교가 상수 시간이 아님"
    assert "!= server_token" not in source, "단순 문자열 비교가 남아 있음"
