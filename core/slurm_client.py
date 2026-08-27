"""
Slurm Client — REST API (slurmrestd) 기반 작업 제출 및 모니터링.

SSH 불필요. slurmrestd:6820 + JWT 인증으로 직접 통신.
"""

from __future__ import annotations

import logging
import os
import time
from dataclasses import dataclass, field
from typing import Any

import httpx

logger = logging.getLogger(__name__)

DEFAULT_API_URL = os.environ.get("SLURM_API_URL", "http://localhost:6820")
API_VERSION = "v0.0.40"


def _get_auth_headers() -> dict[str, str]:
    """환경변수에서 Slurm 인증 정보 로드."""
    user = os.environ.get("SLURM_USER", os.environ.get("USER", "slurm-user"))
    jwt = os.environ.get("SLURM_JWT", "")
    if not jwt:
        # NFS 공유 토큰 파일 시도
        nfs_token = os.path.expanduser(
            os.environ.get("SLURM_JWT_TOKEN_PATH", "~/.slurm/jwt_token.txt")
        )
        try:
            jwt = open(nfs_token).read().strip()
        except Exception:
            pass
    if not jwt:
        # slurm-token helper 시도
        try:
            import subprocess
            result = subprocess.run(
                [os.path.expanduser("~/bin/slurm-token"), "--raw"],
                capture_output=True, text=True, timeout=10,
            )
            jwt = result.stdout.strip()
        except Exception:
            pass
    return {
        "X-SLURM-USER-NAME": user,
        "X-SLURM-USER-TOKEN": jwt,
        "Content-Type": "application/json",
    }


@dataclass
class SlurmJobSpec:
    """Slurm 작업 스펙"""
    name: str
    script: str
    partition: str = ""
    account: str = ""
    time_limit: str = "24:00:00"
    memory: str = "16G"
    cpus: int = 4
    nodes: int = 1
    gpu: str = ""
    work_dir: str = ""
    environment: list[str] = field(default_factory=lambda: [
        "PATH=/usr/local/bin:/usr/bin:/bin",
    ])


class SlurmClient:
    """Slurm REST API 클라이언트."""

    def __init__(self, api_url: str | None = None):
        self.api_url = (
            api_url
            or os.environ.get("SLURM_API_URL", DEFAULT_API_URL)
        ).rstrip("/")
        self.base = f"{self.api_url}/slurm/{API_VERSION}"

    def _headers(self) -> dict[str, str]:
        return _get_auth_headers()

    def _get(self, endpoint: str) -> dict[str, Any]:
        r = httpx.get(
            f"{self.base}/{endpoint}",
            headers=self._headers(), timeout=30,
        )
        r.raise_for_status()
        return r.json()

    def _post(self, endpoint: str, data: dict) -> dict[str, Any]:
        r = httpx.post(
            f"{self.base}/{endpoint}",
            headers=self._headers(), json=data, timeout=30,
        )
        r.raise_for_status()
        return r.json()

    def _delete(self, endpoint: str) -> dict[str, Any]:
        r = httpx.delete(
            f"{self.base}/{endpoint}",
            headers=self._headers(), timeout=30,
        )
        r.raise_for_status()
        return r.json()

    # ── 클러스터 정보 ──

    def nodes(self) -> list[dict[str, Any]]:
        return self._get("nodes").get("nodes", [])

    def partitions(self) -> list[dict[str, Any]]:
        return self._get("partitions").get("partitions", [])

    def jobs(self) -> list[dict[str, Any]]:
        return self._get("jobs").get("jobs", [])

    def job_info(self, job_id: int) -> dict[str, Any]:
        return self._get(f"job/{job_id}")

    # ── 작업 제출 ──

    def submit_job(self, spec: SlurmJobSpec) -> int:
        """작업 제출. 반환: Slurm job ID."""
        job_desc: dict[str, Any] = {
            "name": spec.name,
            "current_working_directory": spec.work_dir or os.path.expanduser("~"),
            "environment": spec.environment,
        }
        if spec.partition:
            job_desc["partition"] = spec.partition
        if spec.account:
            job_desc["account"] = spec.account
        if spec.time_limit:
            # "HH:MM:SS" → minutes
            parts = spec.time_limit.split(":")
            if len(parts) == 3:
                minutes = int(parts[0]) * 60 + int(parts[1])
                job_desc["time_limit"] = {"number": minutes, "set": True}
        if spec.memory:
            mem_mb = spec.memory.replace("G", "000").replace("M", "")
            job_desc["memory_per_node"] = {
                "number": int(mem_mb), "set": True,
            }
        if spec.cpus > 0:
            job_desc["cpus_per_task"] = {
                "number": spec.cpus, "set": True,
            }
        if spec.gpu:
            job_desc["tres_per_job"] = spec.gpu

        data = {"script": spec.script, "job": job_desc}
        result = self._post("job/submit", data)

        errors = result.get("errors", [])
        if errors:
            err_msg = "; ".join(e.get("description", "") for e in errors)
            raise RuntimeError(f"Slurm submit failed: {err_msg}")

        # job_id는 top-level 또는 result 내부에 있을 수 있음
        job_id = (
            result.get("job_id")
            or result.get("result", {}).get("job_id", 0)
        )
        logger.info("Slurm job submitted: %d (%s)", job_id, spec.name)
        return job_id

    def submit_script(self, script_content: str, name: str = "bioauto") -> int:
        """간단한 스크립트 제출 (최소 파라미터)."""
        headers = self._headers()
        data = {
            "script": script_content,
            "job": {
                "name": name,
                "current_working_directory": os.path.expanduser("~"),
                "environment": ["PATH=/usr/local/bin:/usr/bin:/bin"],
            },
        }
        r = httpx.post(
            f"{self.base}/job/submit",
            headers=headers, json=data, timeout=30,
        )
        r.raise_for_status()
        result = r.json()
        return result.get("job_id") or result.get("result", {}).get("job_id", 0)

    def cancel_job(self, job_id: int) -> dict[str, Any]:
        """작업 취소."""
        return self._delete(f"job/{job_id}")

    # ── nf-core 파이프라인 ──

    def submit_nfcore_pipeline(
        self,
        pipeline: str,
        samplesheet: str,
        outdir: str,
        genome: str = "GRCh38",
        profile: str = "singularity",
        extra_params: dict[str, str] | None = None,
        partition: str = "cpu",
        memory: str = "32G",
        cpus: int = 8,
        time_limit: str = "48:00:00",
    ) -> int:
        """nf-core 파이프라인 Slurm 작업 제출."""
        params = extra_params or {}
        params_str = " ".join(f"--{k} {v}" for k, v in params.items())

        script = f"""#!/bin/bash
set -euo pipefail
echo "=== nf-core {pipeline} ==="
echo "Host: $(hostname) | Start: $(date)"

export NXF_HOME=$HOME/.nextflow
export NXF_SINGULARITY_CACHEDIR=$HOME/containers

nextflow run {pipeline} \\
    -profile {profile} \\
    --input {samplesheet} \\
    --outdir {outdir} \\
    --genome {genome} \\
    {params_str} \\
    -resume

echo "Finished: $(date) | Exit: $?"
"""
        spec = SlurmJobSpec(
            name=f"nfcore_{pipeline.replace('/', '_')}",
            script=script,
            partition=partition,
            memory=memory,
            cpus=cpus,
            time_limit=time_limit,
            work_dir=os.path.dirname(outdir),
        )
        return self.submit_job(spec)

    # ── 작업 대기 ──

    def wait_for_job(
        self, job_id: int, poll_interval: int = 30, timeout: int = 86400,
    ) -> dict[str, Any]:
        """작업 완료 대기."""
        start = time.time()
        while time.time() - start < timeout:
            try:
                info = self.job_info(job_id)
                jobs = info.get("jobs", [])
                if jobs:
                    state = jobs[0].get("job_state", [])
                    if isinstance(state, list):
                        state = state[0] if state else "UNKNOWN"
                    if state in ("COMPLETED", "FAILED", "CANCELLED", "TIMEOUT"):
                        return {"job_id": job_id, "state": state, "info": jobs[0]}
            except Exception as e:
                logger.warning("Job %d 상태 확인 실패: %s", job_id, e)
            time.sleep(poll_interval)
        return {"job_id": job_id, "state": "TIMEOUT"}
