"""
Script Runners
R 및 Python 분석 스크립트 실행기
"""

import asyncio
import logging
import shutil
import sys
from pathlib import Path

logger = logging.getLogger(__name__)


class RScriptRunner:
    """Runs R scripts via Rscript subprocess."""

    def __init__(self, r_executable: str = "Rscript"):
        self.r_executable = r_executable

    async def check_installation(self) -> bool:
        """Verify Rscript is available on the system."""
        return shutil.which(self.r_executable) is not None

    async def check_packages(self, packages: list[str]) -> dict[str, bool]:
        """Check if required R packages are installed."""
        results = {}
        for pkg in packages:
            try:
                proc = await asyncio.create_subprocess_exec(
                    self.r_executable, "-e",
                    f'cat(requireNamespace("{pkg}", quietly=TRUE))',
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                )
                stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=30)
                results[pkg] = stdout.decode().strip() == "TRUE"
            except Exception:
                results[pkg] = False
        return results

    async def run(
        self,
        script_path: Path,
        args: dict[str, str],
        timeout: int = 3600,
    ) -> tuple[bool, str, str]:
        """
        Run an R script with named arguments.

        Args:
            script_path: Path to the .R script
            args: Dict of argument name -> value (e.g., {"input": "data.csv"})
            timeout: Timeout in seconds

        Returns:
            (success, stdout, stderr)
        """
        cmd = [self.r_executable, "--vanilla", str(script_path)]
        for key, val in args.items():
            cmd.extend([f"--{key}", str(val)])

        logger.info(f"Running R script: {' '.join(cmd)}")

        try:
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )

            stdout_bytes, stderr_bytes = await asyncio.wait_for(
                process.communicate(), timeout=timeout
            )

            stdout = stdout_bytes.decode("utf-8", errors="replace")
            stderr = stderr_bytes.decode("utf-8", errors="replace")

            success = process.returncode == 0

            if not success:
                logger.error(f"R script failed: {stderr[:500]}")

            return success, stdout, stderr

        except asyncio.TimeoutError:
            process.kill()
            return False, "", f"R script timed out after {timeout}s"
        except Exception as e:
            return False, "", str(e)


class PythonScriptRunner:
    """Runs Python analysis scripts via subprocess."""

    def __init__(self, python_executable: str | None = None):
        self.python_executable = python_executable or sys.executable

    async def check_installation(self) -> bool:
        """Python is always available."""
        return True

    async def check_packages(self, packages: list[str]) -> dict[str, bool]:
        """Check if required Python packages are installed."""
        results = {}
        for pkg in packages:
            try:
                proc = await asyncio.create_subprocess_exec(
                    self.python_executable, "-c",
                    f"import {pkg}",
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                )
                await asyncio.wait_for(proc.communicate(), timeout=10)
                results[pkg] = proc.returncode == 0
            except Exception:
                results[pkg] = False
        return results

    async def run(
        self,
        script_path: Path,
        args: dict[str, str],
        timeout: int = 3600,
    ) -> tuple[bool, str, str]:
        """
        Run a Python script with named arguments.

        Args:
            script_path: Path to the .py script
            args: Dict of argument name -> value
            timeout: Timeout in seconds

        Returns:
            (success, stdout, stderr)
        """
        cmd = [self.python_executable, str(script_path)]
        for key, val in args.items():
            cmd.extend([f"--{key}", str(val)])

        logger.info(f"Running Python script: {' '.join(cmd)}")

        try:
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )

            stdout_bytes, stderr_bytes = await asyncio.wait_for(
                process.communicate(), timeout=timeout
            )

            stdout = stdout_bytes.decode("utf-8", errors="replace")
            stderr = stderr_bytes.decode("utf-8", errors="replace")

            success = process.returncode == 0

            if not success:
                logger.error(f"Python script failed: {stderr[:500]}")

            return success, stdout, stderr

        except asyncio.TimeoutError:
            process.kill()
            return False, "", f"Python script timed out after {timeout}s"
        except Exception as e:
            return False, "", str(e)
