"""WorkflowPlan module for Bioauto 5.0 DAG-based execution and dry-run resource estimation."""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from core.manifest import SpatialManifest


@dataclass
class WorkflowStep:
    step_id: str
    adapter: str
    parameters: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "step_id": self.step_id,
            "adapter": self.adapter,
            "parameters": self.parameters,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "WorkflowStep":
        return cls(
            step_id=data["step_id"],
            adapter=data["adapter"],
            parameters=data.get("parameters", {}),
        )


@dataclass
class WorkflowPlan:
    plan_id: str
    experiment_id: str
    created_at: str
    steps: list[WorkflowStep]
    recommended_pipeline: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "plan_id": self.plan_id,
            "experiment_id": self.experiment_id,
            "created_at": self.created_at,
            "recommended_pipeline": self.recommended_pipeline,
            "steps": [s.to_dict() for s in self.steps],
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "WorkflowPlan":
        steps = [WorkflowStep.from_dict(s) for s in data.get("steps", [])]
        return cls(
            plan_id=data["plan_id"],
            experiment_id=data["experiment_id"],
            created_at=data.get("created_at", datetime.now(timezone.utc).isoformat()),
            steps=steps,
            recommended_pipeline=data.get("recommended_pipeline"),
        )

    @classmethod
    def create_spatial_plan(cls, manifest: SpatialManifest) -> "WorkflowPlan":
        """Create a deterministic Spatial WorkflowPlan for Bioauto 5.0."""
        analysis_bin = manifest.spatial_resolution.analysis_bin_um
        steps = [
            WorkflowStep(
                step_id="qc_and_ingest",
                adapter="spatial_manifest_validator",
                parameters={"min_gene_count": 200, "max_mitochondrial_pct": 20.0},
            ),
            WorkflowStep(
                step_id="spatial_preprocessing",
                adapter="spatial_binned_reader",
                parameters={"bin_size_um": analysis_bin, "normalize": "standard"},
            ),
            WorkflowStep(
                step_id="domain_and_niche",
                adapter="spatial_domain_annotator",
                parameters={"n_top_genes": 2000, "spatial_neighbors_k": 6},
            ),
            WorkflowStep(
                step_id="report_generation",
                adapter="evidence_separated_reporter",
                parameters={"output_format": "markdown+jsonl"},
            ),
        ]
        plan_id = f"plan-spatial-5.0-{manifest.experiment_id}"
        return cls(
            plan_id=plan_id,
            experiment_id=manifest.experiment_id,
            created_at=datetime.now(timezone.utc).isoformat(),
            steps=steps,
            recommended_pipeline=None,
        )

    def dry_run_summary(self, manifest: SpatialManifest | None = None) -> dict[str, Any]:
        """다운로드 없이 자원 소요를 추정한다 (RFC 0001 §2.5).

        `source_archive`가 있는 component의 `content_length`는 추출 파일이 아니라
        **아카이브 크기**다 (F21). 추출 후 크기는 최초 캐시 전에는 알 수 없으므로
        임의 배수로 추정하지 않고 `null`로 남기고 해당 component를 명시한다.
        """
        download_bytes = 0
        archived: list[dict[str, Any]] = []
        if manifest:
            for name in manifest.components:
                ref = manifest.component(name)
                if ref is None or not ref.content_length:
                    continue
                download_bytes += ref.content_length
                if ref.is_archived:
                    archived.append({
                        "component": name,
                        "source_archive": ref.source_archive,
                        "archive_bytes": ref.content_length,
                        "extract_path": ref.path,
                        "extracted_bytes": None,  # 최초 캐시 전에는 미상
                    })

        return {
            "experiment_id": self.experiment_id,
            "plan_id": self.plan_id,
            "step_count": len(self.steps),
            "estimated_download_bytes": download_bytes,
            # 아카이브가 있으면 추출분을 알 수 없어 총 disk를 단정하지 않는다.
            "estimated_disk_bytes": None if archived else download_bytes,
            "archived_components": archived,
            "requires_extraction": bool(archived),
            "checksum_status": manifest.checksum_status if manifest else "unknown",
            "pending_checksum_components": (
                manifest.pending_checksum_components() if manifest else []
            ),
            "steps": [s.step_id for s in self.steps],
        }
