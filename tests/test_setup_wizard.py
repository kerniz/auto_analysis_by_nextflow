"""Tests for TUI Setup Wizard."""

import json
from pathlib import Path
from unittest.mock import patch

# ── Import Tests ──


class TestSetupWizardImport:
    """모듈 import 테스트"""

    def test_import_wizard_module(self):
        from tui.setup_wizard import SetupWizardApp, WizardState, run_setup_wizard

        assert SetupWizardApp is not None
        assert WizardState is not None
        assert run_setup_wizard is not None

    def test_import_screens(self):
        from tui.setup_wizard import (
            AdvancedScreen,
            ExecutionScreen,
            LLMBackendScreen,
            SummaryScreen,
            WelcomeScreen,
        )

        assert WelcomeScreen is not None
        assert LLMBackendScreen is not None
        assert ExecutionScreen is not None
        assert AdvancedScreen is not None
        assert SummaryScreen is not None

    def test_import_check_result(self):
        from tui.setup_wizard import CheckResult, run_prereqs_checks

        assert CheckResult is not None
        assert run_prereqs_checks is not None

    def test_import_deep_merge(self):
        from tui.setup_wizard import _deep_merge

        assert _deep_merge is not None


# ── WizardState Tests ──


class TestWizardState:
    """WizardState 데이터클래스 테스트"""

    def test_default_state(self):
        from tui.setup_wizard import WizardState

        state = WizardState()
        assert state.llm_backend_type == "ollama"
        assert state.ollama_url == "http://localhost:11434"
        assert state.ollama_model == "auto"
        assert state.container_runtime == "docker"
        assert state.results_dir == "./results"
        assert state.debate_rounds == 3
        assert state.enable_debate is True
        assert state.enable_enrichment is True
        assert state.enable_data_aggregation is True
        assert state.enable_rag is True

    def test_to_config_dict_has_required_sections(self):
        from tui.setup_wizard import WizardState

        state = WizardState()
        config = state.to_config_dict()
        assert "pipeline_config" in config
        assert "llm_providers" in config
        assert "debate" in config
        assert "enrichment" in config
        assert "directories" in config
        assert "nextflow_execution" in config
        assert "execution" in config
        assert "rag" in config
        assert "search" in config
        assert "analysis" in config
        assert "data_sources" in config

    def test_to_config_dict_ollama_enabled(self):
        from tui.setup_wizard import WizardState

        state = WizardState(llm_backend_type="ollama")
        config = state.to_config_dict()
        assert config["llm_providers"]["backends"]["ollama"]["enabled"] is True
        assert config["llm_providers"]["backends"]["openai"]["enabled"] is False
        assert config["llm_providers"]["backends"]["anthropic"]["enabled"] is False

    def test_to_config_dict_openai_enabled(self):
        from tui.setup_wizard import WizardState

        state = WizardState(llm_backend_type="openai")
        config = state.to_config_dict()
        assert config["llm_providers"]["backends"]["openai"]["enabled"] is True
        assert config["llm_providers"]["backends"]["ollama"]["enabled"] is False

    def test_to_config_dict_anthropic_enabled(self):
        from tui.setup_wizard import WizardState

        state = WizardState(llm_backend_type="anthropic")
        config = state.to_config_dict()
        assert config["llm_providers"]["backends"]["anthropic"]["enabled"] is True
        assert config["llm_providers"]["backends"]["ollama"]["enabled"] is False

    def test_to_config_dict_ollama_settings(self):
        from tui.setup_wizard import WizardState

        state = WizardState(
            ollama_url="http://myserver:11434",
            ollama_model="llama3:8b",
            ollama_timeout=300,
        )
        config = state.to_config_dict()
        ollama = config["llm_providers"]["backends"]["ollama"]
        assert ollama["url"] == "http://myserver:11434"
        assert ollama["model"] == "llama3:8b"
        assert ollama["timeout"] == 300

    def test_to_config_dict_debate_rounds(self):
        from tui.setup_wizard import WizardState

        state = WizardState(debate_rounds=5)
        config = state.to_config_dict()
        assert config["debate"]["num_rounds"] == 5

    def test_to_config_dict_debate_rounds_clamped(self):
        from tui.setup_wizard import WizardState

        state = WizardState(debate_rounds=0)
        config = state.to_config_dict()
        assert config["debate"]["num_rounds"] >= 1

        state = WizardState(debate_rounds=99)
        config = state.to_config_dict()
        assert config["debate"]["num_rounds"] <= 10

    def test_to_config_dict_container_runtime(self):
        from tui.setup_wizard import WizardState

        state = WizardState(container_runtime="apptainer")
        config = state.to_config_dict()
        assert config["nextflow_execution"]["container_runtime"] == "apptainer"
        assert config["pipeline_config"]["container_runtime"]["preferred"] == "apptainer"

    def test_to_config_dict_nextflow_disabled(self):
        from tui.setup_wizard import WizardState

        state = WizardState(enable_nextflow=False)
        config = state.to_config_dict()
        assert config["nextflow_execution"]["enabled"] is False

    def test_to_config_dict_nextflow_enabled(self):
        from tui.setup_wizard import WizardState

        state = WizardState(enable_nextflow=True, genome="GRCm39")
        config = state.to_config_dict()
        assert config["nextflow_execution"]["enabled"] is True
        assert config["nextflow_execution"]["genome"] == "GRCm39"

    def test_to_config_dict_execution_flags(self):
        from tui.setup_wizard import WizardState

        state = WizardState(
            enable_debate=False,
            enable_enrichment=False,
            enable_data_aggregation=False,
        )
        config = state.to_config_dict()
        assert config["execution"]["enable_debate"] is False
        assert config["execution"]["enable_enrichment"] is False
        assert config["execution"]["enable_data_aggregation"] is False

    def test_to_config_dict_rag_disabled(self):
        from tui.setup_wizard import WizardState

        state = WizardState(enable_rag=False)
        config = state.to_config_dict()
        assert config["rag"]["enabled"] is False

    def test_to_config_dict_results_dir_in_directories(self):
        from tui.setup_wizard import WizardState

        state = WizardState(results_dir="/data/my_results")
        config = state.to_config_dict()
        assert config["directories"]["results"] == "/data/my_results"
        assert config["directories"]["logs"] == "/data/my_results/logs"

    def test_to_config_dict_router_defaults(self):
        from tui.setup_wizard import WizardState

        config = WizardState().to_config_dict()
        router = config["llm_providers"]["router"]
        assert router["strategy"] == "priority"
        assert router["enable_auto_failover"] is True
        assert router["priority_order"] == ["ollama", "openai", "anthropic"]

    def test_to_config_dict_compatible_with_pipeline_config(self):
        """PipelineConfig.from_dict()로 파싱 가능한지 확인"""
        from core.pipeline import PipelineConfig
        from tui.setup_wizard import WizardState

        state = WizardState()
        config = state.to_config_dict()
        pc = PipelineConfig.from_dict(config)
        assert pc.enable_debate is True
        assert pc.debate_rounds == 3


# ── Prereqs Check Tests ──


class TestPrereqsChecks:
    """환경 체크 함수 테스트"""

    def test_check_result_structure(self):
        from tui.setup_wizard import CheckResult

        cr = CheckResult(name="test", ok=True, detail="found", category="general")
        assert cr.name == "test"
        assert cr.ok is True
        assert cr.detail == "found"
        assert cr.category == "general"

    def test_check_result_defaults(self):
        from tui.setup_wizard import CheckResult

        cr = CheckResult(name="test", ok=False)
        assert cr.detail == ""
        assert cr.category == "general"

    @patch("shutil.which")
    def test_all_tools_found(self, mock_which):
        from tui.setup_wizard import run_prereqs_checks

        mock_which.return_value = "/usr/bin/fake"
        results = run_prereqs_checks()
        assert len(results) > 0
        tool_checks = [r for r in results if r.name in ("Nextflow", "Java")]
        assert all(r.ok for r in tool_checks)

    @patch("shutil.which", return_value=None)
    def test_nothing_found(self, mock_which):
        from tui.setup_wizard import run_prereqs_checks

        results = run_prereqs_checks()
        tool_checks = [r for r in results if r.name in ("Nextflow", "Java")]
        assert all(not r.ok for r in tool_checks)

    @patch("shutil.which")
    def test_container_runtimes_checked(self, mock_which):
        from tui.setup_wizard import run_prereqs_checks

        mock_which.return_value = "/usr/bin/fake"
        results = run_prereqs_checks()
        container_names = {r.name for r in results if r.category == "container"}
        assert "Docker" in container_names
        assert "Singularity" in container_names
        assert "Apptainer" in container_names

    @patch("shutil.which", return_value=None)
    def test_python_packages_checked(self, mock_which):
        from tui.setup_wizard import run_prereqs_checks

        results = run_prereqs_checks()
        python_checks = [r for r in results if r.category == "python"]
        assert len(python_checks) >= 3
        pkg_names = {r.name for r in python_checks}
        assert "scanpy" in pkg_names
        assert "anndata" in pkg_names
        assert "matplotlib" in pkg_names

    @patch("shutil.which", return_value=None)
    def test_disk_space_checked(self, mock_which):
        from tui.setup_wizard import run_prereqs_checks

        results = run_prereqs_checks()
        disk_checks = [r for r in results if r.name == "Disk Space"]
        assert len(disk_checks) == 1
        assert "GB" in disk_checks[0].detail


# ── Deep Merge Tests ──


class TestDeepMerge:
    """_deep_merge 유틸리티 테스트"""

    def test_basic_merge(self):
        from tui.setup_wizard import _deep_merge

        base = {"a": 1, "b": 2}
        override = {"b": 3, "c": 4}
        result = _deep_merge(base, override)
        assert result == {"a": 1, "b": 3, "c": 4}

    def test_nested_merge(self):
        from tui.setup_wizard import _deep_merge

        base = {"a": {"x": 1, "y": 2}, "b": 3}
        override = {"a": {"y": 99, "z": 100}}
        result = _deep_merge(base, override)
        assert result["a"]["x"] == 1
        assert result["a"]["y"] == 99
        assert result["a"]["z"] == 100
        assert result["b"] == 3

    def test_deep_nested_merge(self):
        from tui.setup_wizard import _deep_merge

        base = {"a": {"b": {"c": 1, "d": 2}}}
        override = {"a": {"b": {"c": 99}}}
        result = _deep_merge(base, override)
        assert result["a"]["b"]["c"] == 99
        assert result["a"]["b"]["d"] == 2

    def test_override_replaces_non_dict(self):
        from tui.setup_wizard import _deep_merge

        base = {"a": [1, 2, 3]}
        override = {"a": [4, 5]}
        result = _deep_merge(base, override)
        assert result["a"] == [4, 5]

    def test_empty_override(self):
        from tui.setup_wizard import _deep_merge

        base = {"a": 1, "b": {"c": 2}}
        result = _deep_merge(base, {})
        assert result == base

    def test_empty_base(self):
        from tui.setup_wizard import _deep_merge

        override = {"a": 1}
        result = _deep_merge({}, override)
        assert result == {"a": 1}


# ── Config Save/Load Tests ──


class TestConfigSaveLoad:
    """config 저장 및 로드 테스트"""

    def test_save_new_config(self, tmp_path):
        from tui.setup_wizard import WizardState

        state = WizardState()
        config_path = tmp_path / "config.json"
        state.save_config(config_path)
        assert config_path.exists()
        with open(config_path) as f:
            data = json.load(f)
        assert "llm_providers" in data
        assert "debate" in data

    def test_save_preserves_existing_sections(self, tmp_path):
        from tui.setup_wizard import WizardState

        config_path = tmp_path / "config.json"
        existing = {
            "expected_results": {"12345": {"expected_type": "scRNA-seq"}},
            "sequencing_detection": {"scrna_keywords": ["single-cell"]},
        }
        with open(config_path, "w") as f:
            json.dump(existing, f)

        state = WizardState()
        state.save_config(config_path)

        with open(config_path) as f:
            data = json.load(f)
        # Wizard 섹션 존재
        assert "llm_providers" in data
        # 기존 섹션 보존
        assert "expected_results" in data
        assert data["expected_results"]["12345"]["expected_type"] == "scRNA-seq"
        assert "sequencing_detection" in data

    def test_save_merges_existing_config(self, tmp_path):
        from tui.setup_wizard import WizardState

        config_path = tmp_path / "config.json"
        existing = {
            "debate": {
                "num_rounds": 3,
                "custom_field": "preserved",
            },
        }
        with open(config_path, "w") as f:
            json.dump(existing, f)

        state = WizardState(debate_rounds=5)
        state.save_config(config_path)

        with open(config_path) as f:
            data = json.load(f)
        assert data["debate"]["num_rounds"] == 5
        assert data["debate"]["custom_field"] == "preserved"

    def test_save_creates_parent_dirs(self, tmp_path):
        from tui.setup_wizard import WizardState

        config_path = tmp_path / "subdir" / "config.json"
        WizardState().save_config(config_path)
        assert config_path.exists()

    def test_saved_config_is_valid_json(self, tmp_path):
        from tui.setup_wizard import WizardState

        config_path = tmp_path / "config.json"
        WizardState(
            ollama_url="http://test:1234",
            ollama_model="test-model",
            debate_rounds=7,
            enable_nextflow=True,
        ).save_config(config_path)

        with open(config_path) as f:
            data = json.load(f)
        assert data["llm_providers"]["backends"]["ollama"]["url"] == "http://test:1234"
        assert data["debate"]["num_rounds"] == 7
        assert data["nextflow_execution"]["enabled"] is True


# ── App Init Tests ──


class TestSetupWizardAppInit:
    """SetupWizardApp 초기화 테스트"""

    def test_init_default(self):
        from tui.setup_wizard import SetupWizardApp

        app = SetupWizardApp()
        assert app.state is not None
        assert app.config_path == Path("config.json")

    def test_init_custom_path(self):
        from tui.setup_wizard import SetupWizardApp

        app = SetupWizardApp(config_path=Path("/tmp/custom.json"))
        assert app.config_path == Path("/tmp/custom.json")

    def test_load_existing_config_ollama(self, tmp_path):
        from tui.setup_wizard import SetupWizardApp

        config_path = tmp_path / "config.json"
        config = {
            "llm_providers": {
                "backends": {
                    "ollama": {
                        "enabled": True,
                        "url": "http://test:1234",
                        "model": "test-model",
                        "timeout": 999,
                    },
                    "openai": {"enabled": False},
                    "anthropic": {"enabled": False},
                }
            },
        }
        with open(config_path, "w") as f:
            json.dump(config, f)

        app = SetupWizardApp(config_path=config_path)
        assert app.state.llm_backend_type == "ollama"
        assert app.state.ollama_url == "http://test:1234"
        assert app.state.ollama_model == "test-model"
        assert app.state.ollama_timeout == 999

    def test_load_existing_config_openai(self, tmp_path):
        from tui.setup_wizard import SetupWizardApp

        config_path = tmp_path / "config.json"
        config = {
            "llm_providers": {
                "backends": {
                    "ollama": {"enabled": False},
                    "openai": {
                        "enabled": True,
                        "model": "gpt-4o",
                        "api_key_env": "MY_KEY",
                    },
                    "anthropic": {"enabled": False},
                }
            },
        }
        with open(config_path, "w") as f:
            json.dump(config, f)

        app = SetupWizardApp(config_path=config_path)
        assert app.state.llm_backend_type == "openai"
        assert app.state.openai_model == "gpt-4o"
        assert app.state.openai_api_key_env == "MY_KEY"

    def test_load_existing_config_debate(self, tmp_path):
        from tui.setup_wizard import SetupWizardApp

        config_path = tmp_path / "config.json"
        config = {
            "debate": {"num_rounds": 7},
            "execution": {
                "enable_debate": False,
                "enable_enrichment": False,
            },
            "rag": {"enabled": False},
        }
        with open(config_path, "w") as f:
            json.dump(config, f)

        app = SetupWizardApp(config_path=config_path)
        assert app.state.debate_rounds == 7
        assert app.state.enable_debate is False
        assert app.state.enable_enrichment is False
        assert app.state.enable_rag is False

    def test_load_existing_config_nextflow(self, tmp_path):
        from tui.setup_wizard import SetupWizardApp

        config_path = tmp_path / "config.json"
        config = {
            "nextflow_execution": {
                "enabled": True,
                "container_runtime": "apptainer",
                "genome": "GRCm39",
                "max_memory": "32.GB",
                "max_cpus": 8,
            },
        }
        with open(config_path, "w") as f:
            json.dump(config, f)

        app = SetupWizardApp(config_path=config_path)
        assert app.state.enable_nextflow is True
        assert app.state.container_runtime == "apptainer"
        assert app.state.genome == "GRCm39"
        assert app.state.max_memory == "32.GB"
        assert app.state.max_cpus == 8

    def test_load_existing_config_directories(self, tmp_path):
        from tui.setup_wizard import SetupWizardApp

        config_path = tmp_path / "config.json"
        config = {"directories": {"results": "/data/output"}}
        with open(config_path, "w") as f:
            json.dump(config, f)

        app = SetupWizardApp(config_path=config_path)
        assert app.state.results_dir == "/data/output"

    def test_load_nonexistent_config(self):
        from tui.setup_wizard import SetupWizardApp

        app = SetupWizardApp(config_path=Path("/nonexistent/config.json"))
        # 기본값 유지
        assert app.state.llm_backend_type == "ollama"
        assert app.state.ollama_url == "http://localhost:11434"
        assert app.state.debate_rounds == 3

    def test_load_invalid_json(self, tmp_path):
        from tui.setup_wizard import SetupWizardApp

        config_path = tmp_path / "config.json"
        config_path.write_text("not valid json {{{", encoding="utf-8")

        app = SetupWizardApp(config_path=config_path)
        # 기본값 유지, 에러 없음
        assert app.state.llm_backend_type == "ollama"


# ── CLI Command Tests ──


class TestSetupCLI:
    """CLI 'setup' 명령 테스트"""

    def test_setup_command_exists(self):
        from core.cli import cli

        assert "setup" in cli.commands

    def test_setup_command_help(self):
        from click.testing import CliRunner

        from core.cli import cli

        runner = CliRunner()
        result = runner.invoke(cli, ["setup", "--help"])
        assert result.exit_code == 0
        assert "설정 마법사" in result.output
        assert "--config" in result.output

    @patch("tui.setup_wizard.run_setup_wizard")
    def test_setup_command_invokes_wizard(self, mock_wizard):
        from click.testing import CliRunner

        from core.cli import cli

        runner = CliRunner()
        result = runner.invoke(cli, ["setup"])
        assert result.exit_code == 0
        mock_wizard.assert_called_once()

    @patch("tui.setup_wizard.run_setup_wizard")
    def test_setup_command_default_config(self, mock_wizard):
        from click.testing import CliRunner

        from core.cli import cli

        runner = CliRunner()
        runner.invoke(cli, ["setup"])
        mock_wizard.assert_called_once_with(config_path=None)

    @patch("tui.setup_wizard.run_setup_wizard")
    def test_setup_command_custom_config(self, mock_wizard):
        from click.testing import CliRunner

        from core.cli import cli

        runner = CliRunner()
        runner.invoke(cli, ["setup", "-c", "/tmp/test.json"])
        mock_wizard.assert_called_once_with(config_path=Path("/tmp/test.json"))


# ── Round-trip Test ──


class TestRoundTrip:
    """config 생성 → 저장 → 로드 → 파이프라인 파싱 통합 테스트"""

    def test_full_round_trip(self, tmp_path):
        from core.pipeline import PipelineConfig
        from tui.setup_wizard import SetupWizardApp, WizardState

        # 1. Wizard로 config 생성 & 저장
        state = WizardState(
            llm_backend_type="ollama",
            ollama_url="http://myserver:11434",
            ollama_model="llama3:8b",
            ollama_timeout=600,
            container_runtime="apptainer",
            results_dir="./my_results",
            enable_nextflow=True,
            genome="GRCm39",
            debate_rounds=5,
            enable_debate=True,
            enable_enrichment=False,
        )
        config_path = tmp_path / "config.json"
        state.save_config(config_path)

        # 2. SetupWizardApp으로 다시 로드
        app = SetupWizardApp(config_path=config_path)
        assert app.state.ollama_url == "http://myserver:11434"
        assert app.state.ollama_model == "llama3:8b"
        assert app.state.container_runtime == "apptainer"
        assert app.state.debate_rounds == 5

        # 3. PipelineConfig.from_dict()로 파싱
        with open(config_path) as f:
            data = json.load(f)
        pc = PipelineConfig.from_dict(data)
        assert pc.debate_rounds == 5
        assert pc.enable_enrichment is False
