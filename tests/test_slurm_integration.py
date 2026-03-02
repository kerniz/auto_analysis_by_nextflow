"""Slurm HPC integration tests — only run on machines with Slurm installed."""
import shutil
import time

import pytest

from core.pipeline import AsyncPipeline, PipelineConfig

pytestmark = pytest.mark.skipif(
    not shutil.which("squeue"),
    reason="Slurm not installed",
)


class TestSlurmIntegration:
    """Live Slurm integration tests."""

    async def test_get_slurm_cpu_alloc_ratio_live(self, tmp_path):
        """_get_slurm_cpu_alloc_ratio returns a valid float from real sinfo."""
        ratio = await AsyncPipeline._get_slurm_cpu_alloc_ratio()
        assert isinstance(ratio, float)
        assert 0.0 <= ratio <= 100.0

    async def test_wait_for_hpc_idle_no_nf_jobs(self, tmp_path):
        """When no nf-core jobs are running, _wait_for_hpc_idle returns immediately."""
        config = PipelineConfig(pmids=["99999"], results_dir=tmp_path)
        pipeline = AsyncPipeline(config)
        start = time.monotonic()
        await pipeline._wait_for_hpc_idle(check_interval=1, max_wait=5)
        elapsed = time.monotonic() - start
        # Should return almost immediately since no nf-core/nextflow jobs
        assert elapsed < 3.0
