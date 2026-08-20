"""Spatial Manifest v0 validation and loading module for Bioauto 5.0."""

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


class SpatialManifestValidationError(Exception):
    """Exception raised when a Spatial Manifest fails schema or component validation."""
    pass


# component dict에서 파일 경로가 아닌 메타데이터 키
_NON_PATH_KEYS = frozenset({
    "format", "checksum_sha256", "checksum_status", "source_archive", "content_length",
})


@dataclass
class ComponentRef:
    format: str
    path: str
    checksum_sha256: str | None = None
    content_length: int | None = None
    # RFC 0001 §2.5 / F21: content_length가 아카이브 길이일 때 그 사실을 구분한다.
    # source_archive가 있으면 content_length는 추출 파일이 아니라 아카이브 크기다.
    source_archive: str | None = None
    checksum_status: str = "verified"

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ComponentRef":
        return cls(
            format=data.get("format", ""),
            path=data.get("path", ""),
            checksum_sha256=data.get("checksum_sha256"),
            content_length=data.get("content_length"),
            source_archive=data.get("source_archive"),
            checksum_status=data.get("checksum_status", "verified"),
        )

    @property
    def is_archived(self) -> bool:
        """content_length가 추출 파일이 아닌 아카이브 크기를 가리키는지 (F21)."""
        return self.source_archive is not None


@dataclass
class SpatialResolution:
    raw_bin_um: float | None = None
    analysis_bin_um: float = 8.0

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "SpatialResolution":
        return cls(
            raw_bin_um=data.get("raw_bin_um"),
            analysis_bin_um=data.get("analysis_bin_um", 8.0),
        )


@dataclass
class SpatialManifest:
    schema_version: str
    experiment_id: str
    dataset_accession: str
    modality: str
    platform: str
    license: str
    source_url: str
    components: dict[str, Any]
    pmid: str | None = None
    preservation: str = "FFPE"
    spatial_resolution: SpatialResolution = field(default_factory=SpatialResolution)
    checksum_status: str = "verified"

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "SpatialManifest":
        if "schema_version" not in data:
            raise SpatialManifestValidationError("Missing required field 'schema_version'")
        if "experiment_id" not in data:
            raise SpatialManifestValidationError("Missing required field 'experiment_id'")
        if "modality" not in data:
            raise SpatialManifestValidationError("Missing required field 'modality'")

        license_val = data.get("license", "CC-BY-4.0")
        source_url_val = data.get("source_url", "https://example.com/source")
        if not license_val or not str(license_val).strip():
            raise SpatialManifestValidationError("Missing or empty required field 'license'")
        if not source_url_val or not str(source_url_val).strip():
            raise SpatialManifestValidationError("Missing or empty required field 'source_url'")

        components = data.get("components", {})
        for req in ["matrix", "image", "spatial_positions", "scalefactors"]:
            if req not in components:
                raise SpatialManifestValidationError(f"Missing required component '{req}' in manifest")

        res_dict = data.get("spatial_resolution", {})
        spatial_res = SpatialResolution.from_dict(res_dict) if isinstance(res_dict, dict) else SpatialResolution()

        # checksum_status는 component 단위 필드다 (RFC §2.5). 하나라도 미검증이면
        # manifest 전체를 미검증으로 본다 — 루트 기본값 "verified"를 그대로 쓰면
        # pending-first-cache 아카이브가 검증된 것처럼 보고된다.
        root_status = data.get("checksum_status", "verified")
        statuses = {
            c.get("checksum_status", "verified")
            for c in components.values()
            if isinstance(c, dict)
        }
        statuses.add(root_status)
        checksum_status = "verified" if statuses == {"verified"} else next(
            s for s in sorted(statuses) if s != "verified"
        )

        return cls(
            schema_version=data["schema_version"],
            experiment_id=data["experiment_id"],
            dataset_accession=data.get("dataset_accession", data["experiment_id"]),
            modality=data["modality"],
            platform=data.get("platform", "Visium"),
            license=data.get("license", "CC-BY-4.0"),
            source_url=data.get("source_url", ""),
            components=components,
            pmid=data.get("pmid"),
            preservation=data.get("preservation", "FFPE"),
            spatial_resolution=spatial_res,
            checksum_status=checksum_status,
        )

    def component(self, name: str) -> ComponentRef | None:
        """component를 타입 있는 ComponentRef로 반환 (없거나 dict가 아니면 None)."""
        data = self.components.get(name)
        if not isinstance(data, dict) or "path" not in data:
            return None
        return ComponentRef.from_dict(data)

    def pending_checksum_components(self) -> list[str]:
        """checksum이 아직 검증되지 않은 component 이름 목록 (RFC §2.5)."""
        return [
            name for name, data in self.components.items()
            if isinstance(data, dict) and data.get("checksum_status", "verified") != "verified"
        ]

    @classmethod
    def from_file(cls, path: str | Path) -> "SpatialManifest":
        manifest_path = Path(path)
        if not manifest_path.exists():
            raise SpatialManifestValidationError(f"Manifest file not found: {manifest_path}")
        try:
            with open(manifest_path, encoding="utf-8") as f:
                data = json.load(f)
        except Exception as e:
            raise SpatialManifestValidationError(f"Failed to parse manifest JSON: {e}")
        return cls.from_dict(data)

    def _component_paths(self) -> list[tuple[str, str]]:
        """(라벨, 상대경로) 목록. image처럼 path 대신 여러 키를 갖는 형태도 포함."""
        paths: list[tuple[str, str]] = []
        for name, data in self.components.items():
            if not isinstance(data, dict):
                continue
            if isinstance(data.get("path"), str):
                paths.append((name, data["path"]))
                continue
            # path가 없는 component(예: image의 hires/lowres)는 문자열 값을 경로로 본다
            for key, value in data.items():
                if isinstance(value, str) and key not in _NON_PATH_KEYS:
                    paths.append((f"{name}.{key}", value))
        return paths

    def validate_file_existence(self, base_dir: Path) -> None:
        """모든 component 파일이 base_dir 기준으로 존재하는지 검증한다."""
        for label, rel_path in self._component_paths():
            if not (base_dir / rel_path).exists():
                raise SpatialManifestValidationError(
                    f"Missing required component file '{label}' at '{rel_path}' "
                    f"for dataset '{self.experiment_id}'."
                )

    def validate_content_length(self, base_dir: Path) -> None:
        """기록된 content_length와 실제 파일 크기를 대조한다 (RFC §2.5-4).

        `source_archive`가 있는 component의 content_length는 **아카이브 크기**이므로
        추출된 파일 크기와 비교하지 않는다 (F21). 아카이브 자체의 검증은 다운로드
        계층이 담당한다.
        """
        for name in self.components:
            ref = self.component(name)
            if ref is None or not ref.content_length or ref.is_archived:
                continue
            target = base_dir / ref.path
            if not target.exists():
                continue
            actual = target.stat().st_size
            if actual != ref.content_length:
                raise SpatialManifestValidationError(
                    f"content_length mismatch for component '{name}' at '{ref.path}': "
                    f"expected {ref.content_length}, found {actual}. "
                    f"Cache is invalid — execution blocked."
                )
