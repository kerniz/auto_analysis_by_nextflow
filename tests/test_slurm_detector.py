"""
Tests for SlurmDetector
Slurm HPC 환경 자동 감지 테스트
"""

import json
from unittest.mock import MagicMock, patch

from core.slurm_detector import SlurmDetector


class TestIsAvailable:

    @patch("shutil.which", return_value=None)
    def test_not_available(self, mock_which):
        assert SlurmDetector.is_available() is False

    @patch("shutil.which")
    def test_is_available(self, mock_which):
        def side_effect(cmd):
            if cmd in ("sbatch", "squeue"):
                return f"/usr/bin/{cmd}"
            return None
        mock_which.side_effect = side_effect
        assert SlurmDetector.is_available() is True

    @patch("shutil.which")
    def test_partial_tools(self, mock_which):
        """sbatch found but squeue not found -> not available."""
        def side_effect(cmd):
            if cmd == "sbatch":
                return "/usr/bin/sbatch"
            return None
        mock_which.side_effect = side_effect
        assert SlurmDetector.is_available() is False


class TestDetectPartitions:

    @patch("shutil.which", return_value="/usr/bin/sinfo")
    @patch("subprocess.run")
    def test_detect_partitions(self, mock_run, mock_which):
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout=(
                "normal*|32|128000|1-00:00:00|up|10\n"
                "gpu|64|256000|2-00:00:00|up|4\n"
                "debug|8|32000|01:00:00|up|2\n"
            ),
        )
        partitions = SlurmDetector._get_partitions()
        assert len(partitions) == 3
        assert partitions[0]["name"] == "normal"
        assert partitions[0]["is_default"] is True
        assert partitions[0]["cpus"] == "32"
        assert partitions[0]["memory_mb"] == "128000"
        assert partitions[1]["name"] == "gpu"
        assert partitions[1]["is_default"] is False

    @patch("shutil.which", return_value="/usr/bin/sinfo")
    @patch("subprocess.run")
    def test_detect_partitions_filters_down(self, mock_run, mock_which):
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout=(
                "normal*|32|128000|1-00:00:00|up|10\n"
                "maint|8|32000|01:00:00|down|2\n"
            ),
        )
        partitions = SlurmDetector._get_partitions()
        assert len(partitions) == 1
        assert partitions[0]["name"] == "normal"

    @patch("shutil.which", return_value=None)
    def test_detect_partitions_no_sinfo(self, mock_which):
        partitions = SlurmDetector._get_partitions()
        assert partitions == []


class TestDetectAccounts:

    @patch("shutil.which", return_value="/usr/bin/sacctmgr")
    @patch("subprocess.run")
    @patch.dict("os.environ", {"USER": "testuser"})
    def test_detect_accounts(self, mock_run, mock_which):
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout="myaccount\nsharedaccount\n",
        )
        accounts = SlurmDetector._get_accounts()
        assert accounts == ["myaccount", "sharedaccount"]

    @patch("shutil.which", return_value=None)
    def test_detect_accounts_no_sacctmgr(self, mock_which):
        accounts = SlurmDetector._get_accounts()
        assert accounts == []


class TestDetectQos:

    @patch("shutil.which", return_value="/usr/bin/sacctmgr")
    @patch("subprocess.run")
    def test_detect_qos(self, mock_run, mock_which):
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout="normal\nhigh\nlow\n",
        )
        qos_list = SlurmDetector._get_qos()
        assert qos_list == ["normal", "high", "low"]

    @patch("shutil.which", return_value=None)
    def test_detect_qos_no_sacctmgr(self, mock_which):
        qos_list = SlurmDetector._get_qos()
        assert qos_list == []


class TestBuildSuggestedConfig:

    def test_build_suggested_config(self):
        detection = {
            "default_partition": "normal",
            "default_account": "myaccount",
            "partitions": [
                {
                    "name": "normal",
                    "is_default": True,
                    "cpus": "32",
                    "memory_mb": "128000",
                    "time_limit": "1-00:00:00",
                    "state": "up",
                    "nodes": "10",
                }
            ],
            "qos_list": ["normal", "high"],
        }
        config = SlurmDetector._build_suggested_config(detection)
        assert config["enabled"] is True
        assert config["queue"] == "normal"
        assert config["account"] == "myaccount"
        assert config["qos"] == "normal"
        assert config["cpus_per_task"] == 8  # capped at 8
        assert config["time_limit"] == "24:00:00"

    def test_build_suggested_config_no_partitions(self):
        detection = {
            "default_partition": None,
            "default_account": None,
            "partitions": [],
            "qos_list": [],
        }
        config = SlurmDetector._build_suggested_config(detection)
        assert config["enabled"] is True
        assert config["queue"] is None
        assert config["time_limit"] == "24:00:00"


class TestNormalizeTime:

    def test_normalize_time_days(self):
        assert SlurmDetector._normalize_time("1-00:00:00") == "24:00:00"

    def test_normalize_time_infinite(self):
        assert SlurmDetector._normalize_time("infinite") == "72:00:00"

    def test_normalize_time_passthrough(self):
        assert SlurmDetector._normalize_time("12:00:00") == "12:00:00"

    def test_normalize_time_multi_days(self):
        result = SlurmDetector._normalize_time("3-12:00:00")
        assert result == "84:00:00"


class TestApplyToConfig:

    def test_apply_to_config(self, tmp_path):
        config_path = tmp_path / "config.json"
        config_path.write_text(json.dumps({
            "nextflow_execution": {
                "profile": "docker",
                "slurm": {},
            }
        }))

        detection = {
            "available": True,
            "suggested_config": {
                "enabled": True,
                "queue": "normal",
                "account": "myaccount",
                "qos": "normal",
                "time_limit": "24:00:00",
                "memory": "16G",
                "cpus_per_task": 4,
                "nodes": 1,
                "extra_args": "",
                "submit_rate_limit": "50/2min",
                "queue_size": 100,
                "cluster_options": "",
            },
        }

        result = SlurmDetector.apply_to_config(str(config_path), detection)
        assert result["available"] is True

        with open(config_path) as f:
            saved = json.load(f)
        assert saved["nextflow_execution"]["profile"] == "slurm"
        assert saved["nextflow_execution"]["slurm"]["enabled"] is True
        assert saved["nextflow_execution"]["slurm"]["queue"] == "normal"

    def test_apply_to_config_not_available(self, tmp_path):
        config_path = tmp_path / "config.json"
        config_path.write_text("{}")

        detection = {"available": False, "suggested_config": {}}
        result = SlurmDetector.apply_to_config(str(config_path), detection)
        assert result["available"] is False

        # Config file should not be modified (still empty JSON)
        with open(config_path) as f:
            saved = json.load(f)
        assert saved == {}

    def test_apply_to_config_missing_file(self, tmp_path):
        config_path = tmp_path / "nonexistent.json"

        detection = {
            "available": True,
            "suggested_config": {
                "enabled": True,
                "queue": "normal",
                "account": "",
                "qos": "",
                "time_limit": "24:00:00",
                "memory": "16G",
                "cpus_per_task": 4,
                "nodes": 1,
                "extra_args": "",
                "submit_rate_limit": "50/2min",
                "queue_size": 100,
                "cluster_options": "",
            },
        }

        result = SlurmDetector.apply_to_config(str(config_path), detection)
        assert result["available"] is True
        assert config_path.exists()

        with open(config_path) as f:
            saved = json.load(f)
        assert saved["nextflow_execution"]["slurm"]["enabled"] is True
