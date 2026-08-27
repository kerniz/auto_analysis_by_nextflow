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
