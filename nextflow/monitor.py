"""
Pipeline Monitor
Nextflow 파이프라인 실행 모니터링
"""

import logging
import re
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger(__name__)


@dataclass
class PipelineProgress:
    """Current progress of a Nextflow pipeline execution."""

    pipeline: str = ""
    status: str = "unknown"  # "running", "completed", "failed"
    processes_completed: int = 0
    processes_total: int = 0
    percent_complete: float = 0.0
    current_process: str = ""
    elapsed_time: str = ""
    error_message: str = ""

    def to_dict(self) -> dict:
        return {
            "pipeline": self.pipeline,
            "status": self.status,
            "processes_completed": self.processes_completed,
            "processes_total": self.processes_total,
            "percent_complete": self.percent_complete,
            "current_process": self.current_process,
            "elapsed_time": self.elapsed_time,
        }


class PipelineMonitor:
    """Monitors Nextflow pipeline execution by parsing logs."""

    def __init__(self, work_dir: Path):
        self.work_dir = work_dir

    def parse_log_progress(self, log_file: Path) -> PipelineProgress:
        """Parse the Nextflow log file for progress information."""
        progress = PipelineProgress()

        if not log_file.exists():
            progress.status = "not_started"
            return progress

        try:
            content = log_file.read_text(errors="replace")
        except Exception:
            return progress

        # Parse process execution lines
        # Format: [xx/yyyyyy] process > PROCESS_NAME (N) [100%] N of M ✔
        process_pattern = re.compile(
            r'\[([0-9a-f]{2}/[0-9a-f]+)\]\s+process\s+>\s+(\S+)'
            r'(?:\s+\((\d+)\))?\s+\[(\d+)%\]\s+(\d+)\s+of\s+(\d+)'
        )

        completed = set()
        total_processes = 0
        current = ""

        for match in process_pattern.finditer(content):
            process_name = match.group(2)
            pct = int(match.group(4))
            _ = int(match.group(5))
            total = int(match.group(6))

            current = process_name
            total_processes = max(total_processes, total)

            if pct == 100:
                completed.add(process_name)

        progress.processes_completed = len(completed)
        progress.processes_total = total_processes
        progress.current_process = current

        if total_processes > 0:
            progress.percent_complete = (
                len(completed) / total_processes * 100
            )

        # Check final status
        if "Execution complete" in content or "COMPLETED" in content:
            progress.status = "completed"
            progress.percent_complete = 100.0
        elif "ERROR" in content or "Error executing process" in content:
            progress.status = "failed"
            error_match = re.search(r'Error executing process.*?(?:\n.*?){0,3}', content)
            if error_match:
                progress.error_message = error_match.group(0).strip()
        elif completed:
            progress.status = "running"
        else:
            progress.status = "starting"

        # Parse elapsed time
        time_match = re.search(r'Duration\s*:\s*(.+)', content)
        if time_match:
            progress.elapsed_time = time_match.group(1).strip()

        return progress

    def parse_trace_file(self, trace_file: Path) -> dict:
        """
        Parse Nextflow trace.txt for per-process execution metrics.

        Returns dict with process-level stats:
            {process_name: {realtime, cpu_pct, peak_rss, status}}
        """
        if not trace_file.exists():
            return {}

        results: dict[str, dict] = {}

        try:
            lines = trace_file.read_text().strip().split("\n")
            if len(lines) < 2:
                return {}

            headers = lines[0].split("\t")

            for line in lines[1:]:
                fields = line.split("\t")
                if len(fields) < len(headers):
                    continue

                row = dict(zip(headers, fields))
                name = row.get("name", row.get("process", "unknown"))
                results[name] = {
                    "status": row.get("status", ""),
                    "realtime": row.get("realtime", ""),
                    "cpu_pct": row.get("%cpu", ""),
                    "peak_rss": row.get("peak_rss", ""),
                    "read_bytes": row.get("read_bytes", ""),
                    "write_bytes": row.get("write_bytes", ""),
                }
        except Exception as e:
            logger.warning(f"Failed to parse trace file: {e}")

        return results
