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
    # 위 하드웨어/도구 필드가 실제 노드에서 확인된 값인지.
    # SSH·nvidia-smi로 검증하기 전까지는 False — 검증되지 않은 사양으로
    # 실제 작업을 라우팅하면 실행 시점에야 실패한다 (GPU-002).
    verified: bool = False
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def dispatchable(self) -> bool:
        """실제로 작업을 보낼 수 있는 상태인지."""
        return self.status == "online" and self.verified

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
    # 라우팅 대상은 정해졌지만 아직 실행하면 안 되는 상태(미검증/오프라인).
    # 호출자가 이 값을 보고 차단해야 한다 — 낙관적 assignment를 그대로
    # 실행하면 F8(미지원 타입을 rnaseq로 제출)과 같은 사고가 반복된다.
    blocked: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "workload": self.workload,
            "target_type": self.target_type.value,
            "assigned_host": self.assigned_host,
            "reason": self.reason,
            "blocked": self.blocked,
            "capabilities": self.capabilities.to_dict() if self.capabilities else None,
        }


# (workload 키워드, 대상, fallback host, 성공 시 reason)
_ROUTING_RULES: list[tuple[tuple[str, ...], TargetType, str, str]] = [
    (
        ("parabricks", "fq2bam", "variant_call"),
        TargetType.KERNIZ5_ARM64_SPARK,
        "REDACTED-HOST-ARM64",
        "Assigned to DGX Spark (kerniz5) for Parabricks GPU acceleration",
    ),
    (
        ("bionemo", "geneformer", "esm", "evo"),
        TargetType.KERNIZ3_X86_GPU,
        "REDACTED-HOST-X86",
        "Assigned to x86 GPU Worker (kerniz3) for BioNeMo container/model execution",
    ),
]


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

        # 2·3번 노드의 사양은 **아직 실측되지 않았다**. SSH 접근이 막혀 있어
        # arch/GPU/CUDA/설치 도구를 확인할 수 없으므로, 추정값을 사실처럼
        # 기록하지 않고 metadata의 `assumed`에만 둔다 (GPU-002).
        # 실측 후 register_target()으로 verified=True와 함께 덮어쓴다.

        # 2. kerniz3 x86 GPU Worker (BioNeMo / Ollama LLM 후보)
        self._targets[TargetType.KERNIZ3_X86_GPU] = WorkerCapability(
            host="REDACTED-HOST-X86",
            target_type=TargetType.KERNIZ3_X86_GPU,
            arch="x86_64",
            ollama_active=True,  # 11434 응답 확인됨 (2026-08-27)
            status="blocked-access",  # SSH key 등록 전
            verified=False,
            metadata={"assumed": {"gpu_model": "NVIDIA RTX GPU (x86)", "has_bionemo": True}},
        )

        # 3. kerniz5 DGX Spark ARM64 Worker (Parabricks 후보)
        self._targets[TargetType.KERNIZ5_ARM64_SPARK] = WorkerCapability(
            host="REDACTED-HOST-ARM64",
            target_type=TargetType.KERNIZ5_ARM64_SPARK,
            status="blocked-access",  # SSH key 등록 전
            verified=False,
            metadata={"assumed": {
                "arch": "arm64",
                "gpu_model": "NVIDIA Blackwell GB10",
                "cuda_version": "12.4",
                "has_parabricks": True,
            }},
        )

    def register_target(self, capability: WorkerCapability):
        """커스텀 타겟 등록 또는 갱신"""
        self._targets[capability.target_type] = capability

    def resolve(self, workload: str) -> TargetAssignment:
        """
        워크로드 이름(parabricks, bionemo, llm, general_cpu 등)에 따라 타겟을 라우팅합니다.

        대상 노드가 미검증이거나 오프라인이면 `blocked=True`로 표시한다.
        호출자는 blocked assignment로 실제 작업을 제출하면 안 된다.
        """
        workload_lower = workload.lower()

        for keywords, target_type, fallback_host, ok_reason in _ROUTING_RULES:
            if not any(k in workload_lower for k in keywords):
                continue
            target = self._targets.get(target_type)
            if target and target.dispatchable:
                return TargetAssignment(
                    workload=workload,
                    target_type=target_type,
                    assigned_host=target.host,
                    reason=ok_reason,
                    capabilities=target,
                )
            status = target.status if target else "unregistered"
            verified = target.verified if target else False
            return TargetAssignment(
                workload=workload,
                target_type=target_type,
                assigned_host=target.host if target else fallback_host,
                reason=(
                    f"{ok_reason} — 실행 차단: status={status}, "
                    f"verified={verified}. 노드 사양·도구를 실측한 뒤 해제할 것"
                ),
                capabilities=target,
                blocked=True,
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
