"""
Slurm HPC 환경 자동 감지 및 설정 생성
설치 시 Slurm 클러스터가 감지되면 자동으로 config.json에 반영
"""

import shutil
import subprocess


class SlurmDetector:
    """Detect Slurm HPC environment and generate optimal configuration."""

    @staticmethod
    def is_available() -> bool:
        """Check if Slurm tools are installed."""
        return shutil.which("sbatch") is not None and shutil.which("squeue") is not None

    @staticmethod
    def detect() -> dict:
        """
        Detect Slurm environment and return configuration suggestion.

        Returns dict with:
          - available: bool
          - tools: dict[str, str|None] (tool paths)
          - partitions: list[dict] (available queues)
          - default_partition: str|None
          - accounts: list[str]
          - default_account: str|None
          - qos_list: list[str]
          - suggested_config: dict (ready for SlurmConfig)
        """
        result = {
            "available": False,
            "tools": {},
            "partitions": [],
            "default_partition": None,
            "accounts": [],
            "default_account": None,
            "qos_list": [],
            "suggested_config": {},
        }

        # Check tools
        tools = ["sbatch", "squeue", "sinfo", "sacct", "sacctmgr", "scontrol"]
        for tool in tools:
            result["tools"][tool] = shutil.which(tool)

        if not result["tools"]["sbatch"] or not result["tools"]["squeue"]:
            return result

        result["available"] = True

        # Detect partitions
        result["partitions"] = SlurmDetector._get_partitions()
        result["default_partition"] = SlurmDetector._get_default_partition(
            result["partitions"]
        )

        # Detect accounts
        result["accounts"] = SlurmDetector._get_accounts()
        if result["accounts"]:
            result["default_account"] = result["accounts"][0]

        # Detect QoS
        result["qos_list"] = SlurmDetector._get_qos()

        # Generate suggested config
        result["suggested_config"] = SlurmDetector._build_suggested_config(result)

        return result

    @staticmethod
    def _get_partitions() -> list[dict]:
        """Query sinfo for available partitions with resource limits."""
        if not shutil.which("sinfo"):
            return []
        try:
            out = subprocess.run(
                [
                    "sinfo", "--noheader", "--format=%P|%c|%m|%l|%a|%D",
                ],
                capture_output=True, text=True, timeout=10,
            )
            if out.returncode != 0:
                return []

            partitions = []
            for line in out.stdout.strip().split("\n"):
                if not line.strip():
                    continue
                parts = line.strip().split("|")
                if len(parts) < 6:
                    continue
                name = parts[0].rstrip("*")
                is_default = parts[0].endswith("*")
                partitions.append({
                    "name": name,
                    "is_default": is_default,
                    "cpus": parts[1].strip(),
                    "memory_mb": parts[2].strip(),
                    "time_limit": parts[3].strip(),
                    "state": parts[4].strip(),
                    "nodes": parts[5].strip(),
                })
            return [p for p in partitions if p["state"] == "up"]
        except Exception:
            return []

    @staticmethod
    def _get_default_partition(partitions: list[dict]) -> str | None:
        """Find the default partition from detected partitions."""
        for p in partitions:
            if p.get("is_default"):
                return p["name"]
        # Fallback: first available partition
        if partitions:
            return partitions[0]["name"]
        return None

    @staticmethod
    def _get_accounts() -> list[str]:
        """Query sacctmgr for user's Slurm accounts."""
        if not shutil.which("sacctmgr"):
            return []
        try:
            import os
            user = os.environ.get("USER", "")
            if not user:
                return []
            out = subprocess.run(
                [
                    "sacctmgr", "show", "user", user,
                    "format=Account%30", "--noheader", "--parsable2",
                ],
                capture_output=True, text=True, timeout=10,
            )
            if out.returncode != 0:
                return []
            accounts = [
                line.strip() for line in out.stdout.strip().split("\n")
                if line.strip()
            ]
            return accounts
        except Exception:
            return []

    @staticmethod
    def _get_qos() -> list[str]:
        """Query sacctmgr for available QoS levels."""
        if not shutil.which("sacctmgr"):
            return []
        try:
            out = subprocess.run(
                [
                    "sacctmgr", "show", "qos",
                    "format=Name%30", "--noheader", "--parsable2",
                ],
                capture_output=True, text=True, timeout=10,
            )
            if out.returncode != 0:
                return []
            return [
                line.strip() for line in out.stdout.strip().split("\n")
                if line.strip()
            ]
        except Exception:
            return []

    @staticmethod
    def _build_suggested_config(detection: dict) -> dict:
        """Build a suggested SlurmConfig dict from detection results."""
        config = {
            "enabled": True,
            "queue": detection.get("default_partition", ""),
            "account": detection.get("default_account", ""),
            "qos": "",
            "time_limit": "24:00:00",
            "memory": "16G",
            "cpus_per_task": 4,
            "nodes": 1,
            "extra_args": "",
            "submit_rate_limit": "50/2min",
            "queue_size": 100,
            "cluster_options": "",
        }

        # Infer resource limits from default partition
        partitions = detection.get("partitions", [])
        default_name = detection.get("default_partition")
        default_part = None
        for p in partitions:
            if p["name"] == default_name:
                default_part = p
                break

        if default_part:
            # Time limit from partition
            time_str = default_part.get("time_limit", "")
            if time_str and time_str != "infinite":
                config["time_limit"] = SlurmDetector._normalize_time(time_str)

            # CPUs: use partition max, capped at 8 for safety
            try:
                max_cpus = int(default_part.get("cpus", "4"))
                config["cpus_per_task"] = min(max_cpus, 8)
            except (ValueError, TypeError):
                pass

            # Memory: use partition max in MB, convert to G, capped at 64G
            try:
                mem_mb = int(default_part.get("memory_mb", "16000").rstrip("+"))
                mem_gb = mem_mb // 1024
                config["memory"] = f"{min(mem_gb, 64)}G"
            except (ValueError, TypeError):
                pass

        # QoS: use "normal" if available
        qos_list = detection.get("qos_list", [])
        if "normal" in qos_list:
            config["qos"] = "normal"
        elif qos_list:
            config["qos"] = qos_list[0]

        return config

    @staticmethod
    def _normalize_time(time_str: str) -> str:
        """Normalize Slurm time format to HH:MM:SS."""
        # Slurm formats: "1-00:00:00" (days), "24:00:00", "infinite"
        if time_str == "infinite":
            return "72:00:00"
        if "-" in time_str:
            parts = time_str.split("-", 1)
            try:
                days = int(parts[0])
                rest = parts[1] if len(parts) > 1 else "00:00:00"
                h, m, s = (rest.split(":") + ["00", "00"])[:3]
                total_hours = days * 24 + int(h)
                return f"{total_hours}:{m}:{s}"
            except (ValueError, IndexError):
                return "24:00:00"
        return time_str

    @staticmethod
    def apply_to_config(config_path: str, detection: dict | None = None) -> dict:
        """
        Detect Slurm and apply suggested config to config.json.

        Returns the detection result dict.
        """
        import json

        if detection is None:
            detection = SlurmDetector.detect()

        if not detection["available"]:
            return detection

        suggested = detection["suggested_config"]

        try:
            with open(config_path) as f:
                config = json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            config = {}

        # Update config.json
        nf = config.setdefault("nextflow_execution", {})
        slurm = nf.setdefault("slurm", {})

        # Only update fields that are empty/default
        for key, value in suggested.items():
            if key == "enabled":
                slurm[key] = True
            elif not slurm.get(key):
                slurm[key] = value

        # Set profile to slurm if not already set
        if nf.get("profile", "docker") == "docker":
            nf["profile"] = "slurm"

        with open(config_path, "w") as f:
            json.dump(config, f, indent=2, ensure_ascii=False)

        return detection
