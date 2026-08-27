"""
Execution Target Abstraction & Capability Resolver for Heterogeneous Cluster Nodes
DGX Spark (kerniz5), x86 GPU Worker (kerniz3), Slurm HPC, and Local CPU Targets.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class TargetType(str, Enum):
    CPU_LOCAL = "cpu-local"
    SLURM_HPC = "slurm-hpc"
    KERNIZ3_X86_GPU = "kerniz3-x86-gpu"
    KERNIZ5_ARM64_SPARK = "kerniz5-arm64-spark"


@dataclass
class WorkerCapability:
    """Worker 노드 성능 및 하드웨어 사양 정보 구조"""

    host: str
    target_type: TargetType
    arch: str = "x86_64"  # x86_64 또는 arm64 (aarch64)
    cpu_cores: int = 4
    memory_gb: float = 16.0
    gpu_count: int = 0
    gpu_model: str = ""
    cuda_version: str = ""
    has_parabricks: bool = False
    has_bionemo: bool = False
    ollama_active: bool = False
    status: str = "online"  # online, offline, blocked-access
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "host": self.host,
            "target_type": self.target_type.value,
            "arch": self.arch,
            "cpu_cores": self.cpu_cores,
            "memory_gb": self.memory_gb,
            "gpu_count": self.gpu_count,
            "gpu_model": self.gpu_model,
            "cuda_version": self.cuda_version,
            "has_parabricks": self.has_parabricks,
            "has_bionemo": self.has_bionemo,
            "ollama_active": self.ollama_active,
            "status": self.status,
            "metadata": self.metadata,
        }


@dataclass
class TargetAssignment:
    """워크로드별 노드 할당 결과"""

    workload: str
    target_type: TargetType
    assigned_host: str
    reason: str
    capabilities: WorkerCapability | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "workload": self.workload,
            "target_type": self.target_type.value,
            "assigned_host": self.assigned_host,
            "reason": self.reason,
            "capabilities": self.capabilities.to_dict() if self.capabilities else None,
        }


class ExecutionTargetResolver:
    """워크로드 특성에 따라 최적의 ExecutionTarget을 결정하는 리졸버"""

    def __init__(self):
        self._targets: dict[TargetType, WorkerCapability] = {}
        self._register_default_targets()

    def _register_default_targets(self):
        # 1. Local CPU Controller
        self._targets[TargetType.CPU_LOCAL] = WorkerCapability(
            host="localhost",
            target_type=TargetType.CPU_LOCAL,
            arch="x86_64",
            cpu_cores=4,
            memory_gb=16.0,
            status="online",
        )

        # 2. kerniz3 x86 GPU Worker (BioNeMo / Ollama LLM 후보)
        self._targets[TargetType.KERNIZ3_X86_GPU] = WorkerCapability(
            host="REDACTED-HOST-X86",
            target_type=TargetType.KERNIZ3_X86_GPU,
            arch="x86_64",
            gpu_count=1,
            gpu_model="NVIDIA RTX GPU (x86)",
            cuda_version="12.2",
            has_bionemo=True,
            ollama_active=True,
            status="blocked-access",  # SSH key 등록 전
        )

        # 3. kerniz5 DGX Spark ARM64 Worker (Parabricks / Spark Cluster)
        self._targets[TargetType.KERNIZ5_ARM64_SPARK] = WorkerCapability(
            host="REDACTED-HOST-ARM64",
            target_type=TargetType.KERNIZ5_ARM64_SPARK,
            arch="arm64",
            gpu_count=1,
            gpu_model="NVIDIA Blackwell GB10",
            cuda_version="12.4",
            has_parabricks=True,
            status="blocked-access",  # SSH key 등록 전
        )

    def register_target(self, capability: WorkerCapability):
        """커스텀 타겟 등록 또는 갱신"""
        self._targets[capability.target_type] = capability

    def resolve(self, workload: str) -> TargetAssignment:
        """
        워크로드 이름(parabricks, bionemo, llm, general_cpu 등)에 따라 타겟을 라우팅합니다.
        """
        workload_lower = workload.lower()

        # Parabricks 워크로드 -> kerniz5 (DGX Spark ARM64)
        if "parabricks" in workload_lower or "fq2bam" in workload_lower or "variant_call" in workload_lower:
            spark_target = self._targets.get(TargetType.KERNIZ5_ARM64_SPARK)
            if spark_target and spark_target.status == "online":
                return TargetAssignment(
                    workload=workload,
                    target_type=TargetType.KERNIZ5_ARM64_SPARK,
                    assigned_host=spark_target.host,
                    reason="Assigned to DGX Spark (kerniz5) for Parabricks GPU acceleration",
                    capabilities=spark_target,
                )
            return TargetAssignment(
                workload=workload,
                target_type=TargetType.KERNIZ5_ARM64_SPARK,
                assigned_host=spark_target.host if spark_target else "REDACTED-HOST-ARM64",
                reason="Targeted to kerniz5 (Parabricks preferred); waiting for SSH access/online status",
                capabilities=spark_target,
            )

        # BioNeMo 워크로드 -> kerniz3 (x86 GPU)
        if "bionemo" in workload_lower or "geneformer" in workload_lower or "esm" in workload_lower or "evo" in workload_lower:
            x86_target = self._targets.get(TargetType.KERNIZ3_X86_GPU)
            if x86_target and x86_target.status == "online":
                return TargetAssignment(
                    workload=workload,
                    target_type=TargetType.KERNIZ3_X86_GPU,
                    assigned_host=x86_target.host,
                    reason="Assigned to x86 GPU Worker (kerniz3) for BioNeMo container/model execution",
                    capabilities=x86_target,
                )
            return TargetAssignment(
                workload=workload,
                target_type=TargetType.KERNIZ3_X86_GPU,
                assigned_host=x86_target.host if x86_target else "REDACTED-HOST-X86",
                reason="Targeted to kerniz3 (BioNeMo x86 preferred); waiting for SSH access/online status",
                capabilities=x86_target,
            )

        # 기본 CPU 워크로드 -> CPU Local
        local_target = self._targets.get(TargetType.CPU_LOCAL)
        return TargetAssignment(
            workload=workload,
            target_type=TargetType.CPU_LOCAL,
            assigned_host="localhost",
            reason="Assigned to CPU Local target for standard pipeline processing",
            capabilities=local_target,
        )
