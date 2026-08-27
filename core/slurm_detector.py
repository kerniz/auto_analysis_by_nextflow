"""
Slurm HPC 환경 자동 감지 및 설정 생성
설치 시 Slurm 클러스터가 감지되면 자동으로 config.json에 반영
"""

import os
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
    def check_shared_filesystem(path: str) -> dict:
        """
        Check if a path is on a shared/network filesystem accessible from compute nodes.

        Returns dict with:
          - is_shared: bool (confirmed shared filesystem)
          - fs_type: str|None (detected filesystem type)
          - mount_point: str|None
          - method: str (how it was detected)
          - writable: bool
        """
        result = {
            "is_shared": False,
            "fs_type": None,
            "mount_point": None,
            "method": "none",
            "writable": False,
        }

        abs_path = os.path.abspath(os.path.expanduser(path))

        # Check if path exists and is writable
        if os.path.exists(abs_path):
            result["writable"] = os.access(abs_path, os.W_OK)
        else:
            # Check parent
            parent = os.path.dirname(abs_path)
            if os.path.exists(parent):
                result["writable"] = os.access(parent, os.W_OK)

        # Method 1: df -T (Linux) to get filesystem type
        fs_type = SlurmDetector._get_fs_type_df(abs_path)
        if fs_type:
            result["fs_type"] = fs_type
            shared_types = {
                "nfs", "nfs4", "cifs", "smb", "smbfs", "lustre", "gpfs",
                "beegfs", "pvfs2", "orangefs", "glusterfs", "ceph", "fuse.sshfs",
                "afs", "panfs", "fuse.nfs",
            }
            if fs_type.lower() in shared_types:
                result["is_shared"] = True
                result["method"] = "fs_type"

        # Method 2: mount point check
        mount = SlurmDetector._get_mount_point(abs_path)
        if mount:
            result["mount_point"] = mount

        # Method 3: Check if path matches common shared patterns
        if not result["is_shared"]:
            shared_patterns = [
                "/home/", "/Users/",  # Often NFS-mounted home dirs on HPC
                "/shared/", "/scratch/", "/data/",
                "/mnt/nfs", "/mnt/shared", "/mnt/lustre",
                "/gpfs/", "/lustre/", "/beegfs/",
                "site-nfs",  # NFS mount pattern (site-specific)
            ]
            for pattern in shared_patterns:
                if pattern in abs_path:
                    result["method"] = "path_pattern"
                    # Don't confirm as shared, just hint
                    break

        return result

    @staticmethod
    def _get_fs_type_df(path: str) -> str | None:
        """Get filesystem type using df command."""
        try:
            # Linux: df -T, macOS: df -T doesn't exist, use mount
            out = subprocess.run(
                ["df", "-T", path],
                capture_output=True, text=True, timeout=5,
            )
            if out.returncode == 0:
                lines = out.stdout.strip().split("\n")
                if len(lines) >= 2:
                    # Linux df -T: Filesystem Type 1K-blocks Used Available Use% Mounted
                    parts = lines[1].split()
                    if len(parts) >= 2:
                        return parts[1]
        except Exception:
            pass

        # macOS fallback: parse mount output
        try:
            out = subprocess.run(
                ["mount"],
                capture_output=True, text=True, timeout=5,
            )
            if out.returncode == 0:
                for line in out.stdout.split("\n"):
                    # Format: device on /mount/point (type, options)
                    if " on " in line and "(" in line:
                        mount_point = line.split(" on ")[1].split(" (")[0]
                        if path.startswith(mount_point) and len(mount_point) > 1:
                            paren = line.split("(")[1].split(")")[0]
                            fs_type = paren.split(",")[0].strip()
                            return fs_type
        except Exception:
            pass

        return None

    @staticmethod
    def _get_mount_point(path: str) -> str | None:
        """Get the mount point for a path."""
        try:
            out = subprocess.run(
                ["df", path],
                capture_output=True, text=True, timeout=5,
            )
            if out.returncode == 0:
                lines = out.stdout.strip().split("\n")
                if len(lines) >= 2:
                    parts = lines[1].split()
                    return parts[-1] if parts else None
        except Exception:
            pass
        return None

    @staticmethod
    def verify_node_access(path: str, node: str | None = None) -> dict:
        """
        Verify a compute node can access the given path.

        If node is None, tries to find an idle node from sinfo.

        Returns dict with:
          - accessible: bool
          - node: str|None (tested node)
          - method: str
          - error: str|None
        """
        result = {
            "accessible": False,
            "node": node,
            "method": "none",
            "error": None,
        }

        if not shutil.which("srun"):
            result["error"] = "srun not found"
            return result

        # Find a node to test
        if not node:
            node = SlurmDetector._get_idle_node()
            result["node"] = node

        if not node:
            result["error"] = "idle 노드를 찾을 수 없습니다"
            return result

        # Test with srun: check if path exists on the compute node
        try:
            out = subprocess.run(
                [
                    "srun", "--nodelist", node, "--time=0:01:00",
                    "--quiet", "--overlap",
                    "test", "-d", path, "&&", "echo", "OK",
                ],
                capture_output=True, text=True, timeout=30,
            )
            if "OK" in out.stdout:
                result["accessible"] = True
                result["method"] = "srun_test"
            else:
                result["error"] = f"노드 {node}에서 {path} 접근 불가"
        except subprocess.TimeoutExpired:
            result["error"] = "srun 타임아웃 (노드 할당 대기 중)"
        except Exception as e:
            result["error"] = str(e)

        return result

    @staticmethod
    def _get_idle_node() -> str | None:
        """Find an idle compute node for testing."""
        if not shutil.which("sinfo"):
            return None
        try:
            out = subprocess.run(
                [
                    "sinfo", "--noheader", "--states=idle",
                    "--format=%n", "--responding",
                ],
                capture_output=True, text=True, timeout=5,
            )
            if out.returncode == 0:
                nodes = [
                    n.strip() for n in out.stdout.strip().split("\n")
                    if n.strip()
                ]
                return nodes[0] if nodes else None
        except Exception:
            pass
        return None

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
