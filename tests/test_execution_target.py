"""Unit tests for core/execution_target.py ExecutionTargetResolver and WorkerCapability."""

from core.execution_target import (
    ExecutionTargetResolver,
    TargetType,
    WorkerCapability,
)


class TestExecutionTargetResolver:
    """ExecutionTargetResolver 동작 검증"""

    def test_default_targets_registration(self):
        resolver = ExecutionTargetResolver()
        assert TargetType.CPU_LOCAL in resolver._targets
        assert TargetType.KERNIZ3_X86_GPU in resolver._targets
        assert TargetType.KERNIZ5_ARM64_SPARK in resolver._targets

    def test_resolve_parabricks_workload(self):
        resolver = ExecutionTargetResolver()
        assignment = resolver.resolve("parabricks_fq2bam")
        assert assignment.target_type == TargetType.KERNIZ5_ARM64_SPARK
        assert assignment.assigned_host == "REDACTED-HOST-ARM64"
        assert "Parabricks" in assignment.reason

    def test_resolve_bionemo_workload(self):
        resolver = ExecutionTargetResolver()
        assignment = resolver.resolve("bionemo_geneformer")
        assert assignment.target_type == TargetType.KERNIZ3_X86_GPU
        assert assignment.assigned_host == "REDACTED-HOST-X86"
        assert "BioNeMo" in assignment.reason

    def test_resolve_general_cpu_workload(self):
        resolver = ExecutionTargetResolver()
        assignment = resolver.resolve("standard_rnaseq")
        assert assignment.target_type == TargetType.CPU_LOCAL
        assert assignment.assigned_host == "localhost"

    def test_custom_target_registration(self):
        resolver = ExecutionTargetResolver()
        custom_cap = WorkerCapability(
            host="REDACTED-HOST-ARM64",
            target_type=TargetType.KERNIZ5_ARM64_SPARK,
            arch="arm64",
            gpu_count=1,
            gpu_model="NVIDIA Blackwell GB10",
            status="online",
        )
        resolver.register_target(custom_cap)
        assignment = resolver.resolve("parabricks")
        assert assignment.target_type == TargetType.KERNIZ5_ARM64_SPARK
        assert assignment.reason.startswith("Assigned to DGX Spark")

    def test_unverified_target_is_blocked(self):
        """사양이 실측되지 않은 노드로는 작업을 보내지 않는다 (GPU-002).

        online이어도 verified=False면 dispatch 불가다 — 추정 사양으로
        실행하면 실행 시점에야 실패한다.
        """
        resolver = ExecutionTargetResolver()
        assignment = resolver.resolve("parabricks_fq2bam")
        assert assignment.blocked is True
        assert "실행 차단" in assignment.reason
        assert assignment.to_dict()["blocked"] is True

        # status만 online으로 바꿔도 verified가 False면 여전히 차단
        resolver.register_target(WorkerCapability(
            host="REDACTED-HOST-ARM64",
            target_type=TargetType.KERNIZ5_ARM64_SPARK,
            status="online",
        ))
        assert resolver.resolve("parabricks").blocked is True

    def test_verified_online_target_is_dispatchable(self):
        resolver = ExecutionTargetResolver()
        resolver.register_target(WorkerCapability(
            host="REDACTED-HOST-ARM64",
            target_type=TargetType.KERNIZ5_ARM64_SPARK,
            arch="arm64",
            gpu_count=1,
            status="online",
            verified=True,
        ))
        assignment = resolver.resolve("parabricks_fq2bam")
        assert assignment.blocked is False
        assert "실행 차단" not in assignment.reason

    def test_no_unverified_specs_presented_as_fact(self):
        """미실측 사양은 필드가 아니라 metadata['assumed']에만 있어야 한다."""
        resolver = ExecutionTargetResolver()
        spark = resolver._targets[TargetType.KERNIZ5_ARM64_SPARK]
        assert spark.verified is False
        assert spark.has_parabricks is False, "미검증인데 도구 보유를 사실로 기록함"
        assert spark.gpu_count == 0, "미검증인데 GPU 개수를 사실로 기록함"
        assert "assumed" in spark.metadata


def test_resolver_is_not_wired_into_execution_paths():
    """GPU-004는 RFC 0003 승인 전까지 격리 스캐폴드여야 한다.

    승인 전에 CLI/pipeline/nextflow 실행 경로에 붙으면, 미실측 노드로
    작업이 나가는 사고(F8류)가 문서 승인 없이 발생할 수 있다.
    """
    from pathlib import Path

    prod_dirs = ["core", "nextflow", "web", "tui", "backends", "plugins", "analysis"]
    offenders = []
    for d in prod_dirs:
        for py in Path(d).rglob("*.py"):
            if py.name == "execution_target.py":
                continue
            if "execution_target" in py.read_text(encoding="utf-8"):
                offenders.append(str(py))

    assert not offenders, (
        f"execution_target이 실행 경로에 부착됨: {offenders}. "
        "RFC 0003 승인 후 이 테스트를 갱신할 것"
    )
