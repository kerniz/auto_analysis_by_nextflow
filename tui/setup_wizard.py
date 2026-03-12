"""BioAuto Setup Wizard — Textual TUI 초기 설정 마법사"""

from __future__ import annotations

import json
import os
import shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from textual import work
from textual.app import App, ComposeResult
from textual.containers import Horizontal, ScrollableContainer, Vertical
from textual.screen import Screen
from textual.widgets import (
    Button,
    Footer,
    Header,
    Input,
    Label,
    RadioButton,
    RadioSet,
    Rule,
    Static,
    Switch,
)

# ── Data Classes ──


@dataclass
class CheckResult:
    """환경 체크 결과"""

    name: str
    ok: bool
    detail: str = ""
    category: str = "general"


@dataclass
class WizardState:
    """마법사 전체 상태 (모든 Screen 간 공유)"""

    # Environment
    env_checks: list[CheckResult] = field(default_factory=list)

    # Step 2: LLM Backend
    llm_backend_type: str = "ollama"
    ollama_url: str = "http://localhost:11434"
    ollama_model: str = "auto"
    ollama_timeout: int = 120
    openai_api_key_env: str = "OPENAI_API_KEY"
    openai_model: str = ""
    anthropic_api_key_env: str = "ANTHROPIC_API_KEY"
    anthropic_model: str = ""

    # Step 3: Execution
    container_runtime: str = "docker"
    results_dir: str = "./results"
    enable_nextflow: bool = False
    genome: str = "GRCh38"
    max_memory: str = "16.GB"
    max_cpus: int = 4

    # Step 4: Advanced
    debate_rounds: int = 3
    enable_debate: bool = True
    enable_enrichment: bool = True
    enable_data_aggregation: bool = True
    enable_rag: bool = True

    # Language
    primary_lang: str = "en"
    secondary_lang: str = "ko"
    translate_debate: bool = True

    def to_config_dict(self) -> dict[str, Any]:
        """config.json 호환 딕셔너리 생성"""
        ollama_on = self.llm_backend_type == "ollama"
        openai_on = self.llm_backend_type == "openai"
        anthropic_on = self.llm_backend_type == "anthropic"

        rounds = max(1, min(10, self.debate_rounds))

        return {
            "locale": self.secondary_lang,
            "language": {
                "primary": self.primary_lang,
                "secondary": self.secondary_lang,
                "translate_debate": self.translate_debate,
                "translation_model": "auto",
            },
            "pipeline_config": {
                "llm_server": {
                    "url": self.ollama_url,
                    "model": self.ollama_model,
                    "timeout": self.ollama_timeout,
                    "max_retries": 3,
                },
                "container_runtime": {
                    "preferred": self.container_runtime,
                    "fallback": (
                        "singularity"
                        if self.container_runtime != "singularity"
                        else "docker"
                    ),
                },
                "sra_download": {
                    "max_parallel": 4,
                    "timeout_minutes": 30,
                    "max_samples": 50,
                },
            },
            "llm_providers": {
                "backends": {
                    "ollama": {
                        "enabled": ollama_on,
                        "url": self.ollama_url,
                        "model": self.ollama_model,
                        "timeout": self.ollama_timeout,
                        "max_retries": 3,
                        "max_tokens": 4096,
                        "temperature": 0.1,
                        "top_p": 0.9,
                    },
                    "openai": {
                        "enabled": openai_on,
                        "api_key_env": self.openai_api_key_env,
                        "base_url": None,
                        "model": self.openai_model,
                        "timeout": 120,
                        "max_retries": 3,
                        "max_tokens": 4096,
                        "temperature": 0.1,
                        "top_p": 0.9,
                    },
                    "anthropic": {
                        "enabled": anthropic_on,
                        "api_key_env": self.anthropic_api_key_env,
                        "model": self.anthropic_model,
                        "timeout": 120,
                        "max_retries": 3,
                        "max_tokens": 4096,
                        "temperature": 0.1,
                        "top_p": 0.9,
                    },
                },
                "router": {
                    "strategy": "priority",
                    "priority_order": ["ollama", "openai", "anthropic"],
                    "enable_auto_failover": True,
                    "health_check_interval": 60,
                    "max_concurrent_requests": 10,
                },
            },
            "debate": {
                "num_rounds": rounds,
                "consensus_threshold": 0.7,
                "enable_cross_examination": True,
                "timeout_per_agent": self.ollama_timeout,
                "parallel_assessment": False,
                "specialist_max_rounds": 1,
                "agent_weights": {
                    "phd_expert": 0.20,
                    "undergraduate": 0.12,
                    "layperson": 0.08,
                    "statistical_skeptic": 0.18,
                    "biological_realist": 0.15,
                    "experimental_critic": 0.13,
                    "translation_evaluator": 0.14,
                },
            },
            "enrichment": {
                "gsea_gene_set_db": "KEGG_2021_Human",
                "organism": "human",
                "deg_fc_threshold": 1.5,
                "deg_padj_threshold": 0.05,
                "top_pathways_count": 10,
                "top_genes_count": 50,
            },
            "directories": {
                "raw_data": f"{self.results_dir}/raw_data",
                "processed_data": f"{self.results_dir}/processed_data",
                "nextflow_work": f"{self.results_dir}/nextflow_work",
                "containers": f"{self.results_dir}/containers",
                "results": self.results_dir,
                "logs": f"{self.results_dir}/logs",
                "charts": f"{self.results_dir}/charts",
            },
            "rag": {
                "enabled": self.enable_rag,
                "persist_dir": f"{self.results_dir}/rag_db",
                "embedding_model": "all-MiniLM-L6-v2",
                "max_context_tokens": 1500,
            },
            "search": {
                "limit_per_source": 20,
                "pubmed_enabled": True,
                "semantic_scholar_enabled": True,
                "europe_pmc_enabled": True,
                "brave_enabled": False,
            },
            "nextflow_execution": {
                "enabled": self.enable_nextflow,
                "container_runtime": self.container_runtime,
                "profile": self.container_runtime,
                "genome": self.genome,
                "max_memory": self.max_memory,
                "max_cpus": self.max_cpus,
                "max_time": "24.h",
                "resume": True,
            },
            "analysis": {
                "r_executable": "Rscript",
                "r_scripts_dir": None,
                "scanpy_enabled": False,
                "deseq2": {"fc_threshold": "1.5", "padj_threshold": "0.05"},
                "seurat": {
                    "min_features": "200",
                    "max_features": "5000",
                    "max_mt_percent": "20",
                    "resolution": "0.8",
                },
            },
            "execution": {
                "resume_enabled": True,
                "progress_file": f"{self.results_dir}/progress.json",
                "log_level": "ERROR",
                "max_concurrent": 5,
                "enable_debate": self.enable_debate,
                "enable_enrichment": self.enable_enrichment,
                "enable_data_aggregation": self.enable_data_aggregation,
            },
            "data_sources": {
                "semantic_scholar": {
                    "base_url": "https://api.semanticscholar.org",
                    "timeout": 30,
                    "rate_limit_delay": 1.0,
                },
                "europe_pmc": {
                    "base_url": "https://www.ebi.ac.uk/europepmc/webservices/rest",
                    "timeout": 30,
                    "rate_limit_delay": 0.5,
                },
            },
        }

    def save_config(self, config_path: Path) -> None:
        """config.json으로 저장 (기존 파일 있으면 deep merge)"""
        new_config = self.to_config_dict()

        if config_path.exists():
            with open(config_path) as f:
                existing = json.load(f)
            merged = _deep_merge(existing, new_config)
        else:
            merged = new_config

        config_path.parent.mkdir(parents=True, exist_ok=True)
        with open(config_path, "w") as f:
            json.dump(merged, f, indent=2, ensure_ascii=False)


def _deep_merge(base: dict, override: dict) -> dict:
    """딕셔너리 재귀 병합 (override가 base 위에 덮어씀)"""
    result = base.copy()
    for key, value in override.items():
        if (
            key in result
            and isinstance(result[key], dict)
            and isinstance(value, dict)
        ):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = value
    return result


# ── Prereqs Check ──


def run_prereqs_checks() -> list[CheckResult]:
    """환경 사전 요구사항 체크 (구조화된 결과 반환)"""
    results: list[CheckResult] = []

    # Nextflow
    nf = shutil.which("nextflow")
    results.append(
        CheckResult("Nextflow", nf is not None, nf or "not found")
    )

    # Java
    java = shutil.which("java")
    results.append(
        CheckResult("Java", java is not None, java or "not found")
    )

    # Container runtimes
    for rt in ["docker", "singularity", "apptainer"]:
        found = shutil.which(rt)
        results.append(
            CheckResult(
                rt.capitalize(),
                found is not None,
                found or "not found",
                "container",
            )
        )

    # Rscript
    r = shutil.which("Rscript")
    results.append(
        CheckResult("Rscript", r is not None, r or "not found")
    )

    # Python optional packages
    for pkg in ["scanpy", "anndata", "matplotlib"]:
        try:
            __import__(pkg)
            results.append(CheckResult(pkg, True, "installed", "python"))
        except ImportError:
            results.append(CheckResult(pkg, False, "not installed", "python"))

    # Disk space
    try:
        stat = os.statvfs(".")
        free_gb = (stat.f_bavail * stat.f_frsize) / (1024**3)
        results.append(
            CheckResult(
                "Disk Space",
                free_gb > 10,
                f"{free_gb:.1f} GB free",
            )
        )
    except Exception:
        results.append(CheckResult("Disk Space", False, "check failed"))

    return results


# ── Screens ──


class WelcomeScreen(Screen):
    """Step 1: 환영 + 환경 체크"""

    def compose(self) -> ComposeResult:
        yield Header()
        with ScrollableContainer(id="wizard-content"):
            yield Static(
                "[bold cyan]BioAuto Setup Wizard[/]\n\n"
                "바이오인포매틱스 연구 자동화 플랫폼 초기 설정을 도와드립니다.\n"
                "5단계로 구성되어 있으며, 각 단계에서 설정을 입력합니다.\n",
                id="welcome-text",
            )
            yield Rule()
            yield Static("[bold]환경 체크[/]", classes="section-title")
            yield Static("", id="check-results")
            yield Button("환경 체크 실행", id="run-checks", variant="default")
        with Horizontal(id="nav-bar"):
            yield Button("Next →", id="next", variant="primary")
        yield Footer()

    def on_mount(self) -> None:
        if self.app.state.env_checks:
            self._display_checks(self.app.state.env_checks)

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "run-checks":
            self._do_checks()
        elif event.button.id == "next":
            self.app.push_screen(LLMBackendScreen())

    @work(thread=True)
    def _do_checks(self) -> None:
        checks = run_prereqs_checks()
        self.app.state.env_checks = checks
        self.app.call_from_thread(self._display_checks, checks)

    def _display_checks(self, checks: list[CheckResult]) -> None:
        lines = []
        for c in checks:
            icon = "[green]✓[/]" if c.ok else "[red]✗[/]"
            detail = f" ({c.detail})" if c.detail else ""
            lines.append(f"  {icon} {c.name}{detail}")
        self.query_one("#check-results", Static).update("\n".join(lines))


class LLMBackendScreen(Screen):
    """Step 2: LLM 백엔드 설정"""

    def compose(self) -> ComposeResult:
        yield Header()
        with ScrollableContainer(id="wizard-content"):
            yield Static(
                "[bold cyan]Step 2/5: LLM 백엔드 설정[/]\n",
                classes="section-title",
            )
            yield Static("사용할 LLM 백엔드를 선택하세요:")
            with RadioSet(id="backend-select"):
                yield RadioButton("Ollama (로컬 서버)", id="radio-ollama")
                yield RadioButton("OpenAI (API)", id="radio-openai")
                yield RadioButton("Anthropic (API)", id="radio-anthropic")

            # Ollama panel
            with Vertical(id="ollama-panel"):
                yield Rule()
                yield Label("Ollama Server URL:")
                yield Input(
                    placeholder="http://localhost:11434",
                    id="ollama-url",
                )
                yield Label("Model:")
                yield Input(placeholder="qwen3:30b", id="ollama-model")
                yield Label("Timeout (초):")
                yield Input(placeholder="120", id="ollama-timeout")
                yield Button(
                    "연결 테스트", id="test-connection", variant="default"
                )
                yield Static("", id="connection-status")

            # OpenAI panel
            with Vertical(id="openai-panel"):
                yield Rule()
                yield Label("API Key 환경변수:")
                yield Input(
                    placeholder="OPENAI_API_KEY",
                    id="openai-key-env",
                )
                yield Label("Model:")
                yield Input(placeholder="gpt-4", id="openai-model")
                yield Static("", id="openai-status")

            # Anthropic panel
            with Vertical(id="anthropic-panel"):
                yield Rule()
                yield Label("API Key 환경변수:")
                yield Input(
                    placeholder="ANTHROPIC_API_KEY",
                    id="anthropic-key-env",
                )
                yield Label("Model:")
                yield Input(
                    placeholder="claude-sonnet-4-20250514",
                    id="anthropic-model",
                )
                yield Static("", id="anthropic-status")

        with Horizontal(id="nav-bar"):
            yield Button("← Back", id="back")
            yield Button("Next →", id="next", variant="primary")
        yield Footer()

    def on_mount(self) -> None:
        state = self.app.state
        # Pre-fill
        self.query_one("#ollama-url", Input).value = state.ollama_url
        self.query_one("#ollama-model", Input).value = state.ollama_model
        self.query_one("#ollama-timeout", Input).value = str(
            state.ollama_timeout
        )
        self.query_one("#openai-key-env", Input).value = (
            state.openai_api_key_env
        )
        self.query_one("#openai-model", Input).value = state.openai_model
        self.query_one("#anthropic-key-env", Input).value = (
            state.anthropic_api_key_env
        )
        self.query_one("#anthropic-model", Input).value = (
            state.anthropic_model
        )

        # Set initial radio
        idx = {"ollama": 0, "openai": 1, "anthropic": 2}.get(
            state.llm_backend_type, 0
        )
        radio_set = self.query_one("#backend-select", RadioSet)
        radio_set._selected = idx
        self._update_panels(idx)

    def on_radio_set_changed(self, event: RadioSet.Changed) -> None:
        self._update_panels(event.index)

    def _update_panels(self, index: int) -> None:
        self.query_one("#ollama-panel").display = index == 0
        self.query_one("#openai-panel").display = index == 1
        self.query_one("#anthropic-panel").display = index == 2

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "test-connection":
            self._test_ollama()
        elif event.button.id == "next":
            self._save_to_state()
            self.app.push_screen(ExecutionScreen())
        elif event.button.id == "back":
            self.app.pop_screen()

    def _save_to_state(self) -> None:
        state = self.app.state
        radio_set = self.query_one("#backend-select", RadioSet)
        idx = radio_set._selected if hasattr(radio_set, "_selected") else 0
        state.llm_backend_type = ["ollama", "openai", "anthropic"][
            idx if idx is not None else 0
        ]
        state.ollama_url = self.query_one("#ollama-url", Input).value
        state.ollama_model = self.query_one("#ollama-model", Input).value
        try:
            state.ollama_timeout = int(
                self.query_one("#ollama-timeout", Input).value
            )
        except ValueError:
            state.ollama_timeout = 120
        state.openai_api_key_env = self.query_one(
            "#openai-key-env", Input
        ).value
        state.openai_model = self.query_one("#openai-model", Input).value
        state.anthropic_api_key_env = self.query_one(
            "#anthropic-key-env", Input
        ).value
        state.anthropic_model = self.query_one(
            "#anthropic-model", Input
        ).value

    @work(thread=True)
    def _test_ollama(self) -> None:
        url = self.query_one("#ollama-url", Input).value
        model = self.query_one("#ollama-model", Input).value
        status = self.query_one("#connection-status", Static)
        self.app.call_from_thread(
            status.update, "[yellow]연결 테스트 중...[/]"
        )
        try:
            import httpx

            resp = httpx.get(f"{url}/api/tags", timeout=10)
            if resp.status_code == 200:
                models = resp.json().get("models", [])
                names = [m.get("name", "") for m in models]
                found = any(
                    model in n or n.startswith(model.split(":")[0])
                    for n in names
                )
                if found:
                    msg = f"[green]연결 성공. 모델 '{model}' 확인됨.[/]"
                else:
                    avail = ", ".join(names[:5])
                    msg = (
                        f"[yellow]연결 성공. 모델 '{model}' 없음. "
                        f"사용 가능: {avail}[/]"
                    )
            else:
                msg = f"[red]서버 응답 오류: {resp.status_code}[/]"
        except Exception as e:
            msg = f"[red]연결 실패: {e}[/]"
        self.app.call_from_thread(status.update, msg)


class ExecutionScreen(Screen):
    """Step 3: 실행 환경 설정"""

    def compose(self) -> ComposeResult:
        yield Header()
        with ScrollableContainer(id="wizard-content"):
            yield Static(
                "[bold cyan]Step 3/5: 실행 환경 설정[/]\n",
                classes="section-title",
            )
            yield Label("컨테이너 런타임:")
            with RadioSet(id="runtime-select"):
                yield RadioButton("Docker", id="radio-docker")
                yield RadioButton("Singularity", id="radio-singularity")
                yield RadioButton("Apptainer", id="radio-apptainer")

            yield Rule()
            yield Label("결과 저장 디렉토리:")
            yield Input(placeholder="./results", id="results-dir")

            yield Rule()
            yield Static("[bold]Nextflow 파이프라인 실행[/]")
            with Horizontal(classes="switch-row"):
                yield Label("Nextflow 활성화:")
                yield Switch(value=False, id="nf-switch")

            with Vertical(id="nf-panel"):
                yield Label("Reference Genome:")
                yield Input(placeholder="GRCh38", id="genome")
                yield Label("Max Memory:")
                yield Input(placeholder="16.GB", id="max-memory")
                yield Label("Max CPUs:")
                yield Input(placeholder="4", id="max-cpus")

        with Horizontal(id="nav-bar"):
            yield Button("← Back", id="back")
            yield Button("Next →", id="next", variant="primary")
        yield Footer()

    def on_mount(self) -> None:
        state = self.app.state
        self.query_one("#results-dir", Input).value = state.results_dir
        self.query_one("#genome", Input).value = state.genome
        self.query_one("#max-memory", Input).value = state.max_memory
        self.query_one("#max-cpus", Input).value = str(state.max_cpus)

        # Container runtime
        idx = {"docker": 0, "singularity": 1, "apptainer": 2}.get(
            state.container_runtime, 0
        )
        radio_set = self.query_one("#runtime-select", RadioSet)
        radio_set._selected = idx

        # Nextflow switch
        self.query_one("#nf-switch", Switch).value = state.enable_nextflow
        self.query_one("#nf-panel").display = state.enable_nextflow

    def on_switch_changed(self, event: Switch.Changed) -> None:
        if event.switch.id == "nf-switch":
            self.query_one("#nf-panel").display = event.value

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "next":
            self._save_to_state()
            self.app.push_screen(AdvancedScreen())
        elif event.button.id == "back":
            self.app.pop_screen()

    def _save_to_state(self) -> None:
        state = self.app.state
        radio_set = self.query_one("#runtime-select", RadioSet)
        idx = radio_set._selected if hasattr(radio_set, "_selected") else 0
        state.container_runtime = ["docker", "singularity", "apptainer"][
            idx if idx is not None else 0
        ]
        state.results_dir = (
            self.query_one("#results-dir", Input).value or "./results"
        )
        state.enable_nextflow = self.query_one("#nf-switch", Switch).value
        state.genome = self.query_one("#genome", Input).value or "GRCh38"
        state.max_memory = (
            self.query_one("#max-memory", Input).value or "16.GB"
        )
        try:
            state.max_cpus = int(
                self.query_one("#max-cpus", Input).value
            )
        except ValueError:
            state.max_cpus = 4


class AdvancedScreen(Screen):
    """Step 4: 고급 설정"""

    def compose(self) -> ComposeResult:
        yield Header()
        with ScrollableContainer(id="wizard-content"):
            yield Static(
                "[bold cyan]Step 4/5: 고급 설정[/]\n"
                "기본값으로 충분하다면 바로 Next를 누르세요.\n",
                classes="section-title",
            )
            with Horizontal(classes="switch-row"):
                yield Label("멀티 에이전트 토론:")
                yield Switch(value=True, id="debate-switch")
            yield Label("토론 라운드 수:")
            yield Input(placeholder="3", id="debate-rounds")

            yield Rule()
            with Horizontal(classes="switch-row"):
                yield Label("GSEA 농축 분석:")
                yield Switch(value=True, id="enrichment-switch")
            with Horizontal(classes="switch-row"):
                yield Label("데이터 소스 통합:")
                yield Switch(value=True, id="aggregation-switch")
            with Horizontal(classes="switch-row"):
                yield Label("RAG (벡터 DB):")
                yield Switch(value=True, id="rag-switch")

        with Horizontal(id="nav-bar"):
            yield Button("← Back", id="back")
            yield Button("Next →", id="next", variant="primary")
        yield Footer()

    def on_mount(self) -> None:
        state = self.app.state
        self.query_one("#debate-switch", Switch).value = state.enable_debate
        self.query_one("#debate-rounds", Input).value = str(
            state.debate_rounds
        )
        self.query_one("#enrichment-switch", Switch).value = (
            state.enable_enrichment
        )
        self.query_one("#aggregation-switch", Switch).value = (
            state.enable_data_aggregation
        )
        self.query_one("#rag-switch", Switch).value = state.enable_rag

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "next":
            self._save_to_state()
            self.app.push_screen(SummaryScreen())
        elif event.button.id == "back":
            self.app.pop_screen()

    def _save_to_state(self) -> None:
        state = self.app.state
        state.enable_debate = self.query_one(
            "#debate-switch", Switch
        ).value
        try:
            state.debate_rounds = int(
                self.query_one("#debate-rounds", Input).value
            )
        except ValueError:
            state.debate_rounds = 3
        state.enable_enrichment = self.query_one(
            "#enrichment-switch", Switch
        ).value
        state.enable_data_aggregation = self.query_one(
            "#aggregation-switch", Switch
        ).value
        state.enable_rag = self.query_one("#rag-switch", Switch).value


class SummaryScreen(Screen):
    """Step 5: 요약 + 저장"""

    def compose(self) -> ComposeResult:
        yield Header()
        with ScrollableContainer(id="wizard-content"):
            yield Static(
                "[bold cyan]Step 5/5: 설정 요약[/]\n",
                classes="section-title",
            )
            yield Static("", id="summary-text")
            yield Rule()
            yield Static("", id="save-path")
            yield Static("", id="save-status")
        with Horizontal(id="nav-bar"):
            yield Button("← Back", id="back")
            yield Button("Save & Finish", id="save", variant="success")
        yield Footer()

    def on_mount(self) -> None:
        state = self.app.state
        config_path = self.app.config_path

        lines = []
        # LLM
        lines.append("[bold]LLM 백엔드[/]")
        if state.llm_backend_type == "ollama":
            lines.append("  Provider: Ollama")
            lines.append(f"  URL: {state.ollama_url}")
            lines.append(f"  Model: {state.ollama_model}")
            lines.append(f"  Timeout: {state.ollama_timeout}s")
        elif state.llm_backend_type == "openai":
            lines.append("  Provider: OpenAI")
            lines.append(f"  Model: {state.openai_model}")
            lines.append(f"  API Key Env: {state.openai_api_key_env}")
        else:
            lines.append("  Provider: Anthropic")
            lines.append(f"  Model: {state.anthropic_model}")
            lines.append(f"  API Key Env: {state.anthropic_api_key_env}")

        lines.append("")
        lines.append("[bold]실행 환경[/]")
        lines.append(f"  Container: {state.container_runtime}")
        lines.append(f"  Results: {state.results_dir}")
        lines.append(f"  Nextflow: {'ON' if state.enable_nextflow else 'OFF'}")
        if state.enable_nextflow:
            lines.append(f"  Genome: {state.genome}")
            lines.append(f"  Memory: {state.max_memory}, CPUs: {state.max_cpus}")

        lines.append("")
        lines.append("[bold]고급 설정[/]")
        lines.append(
            f"  Debate: {'ON' if state.enable_debate else 'OFF'}"
            f" ({state.debate_rounds} rounds)"
        )
        lines.append(
            f"  Enrichment: {'ON' if state.enable_enrichment else 'OFF'}"
        )
        lines.append(
            f"  Aggregation: {'ON' if state.enable_data_aggregation else 'OFF'}"
        )
        lines.append(f"  RAG: {'ON' if state.enable_rag else 'OFF'}")

        self.query_one("#summary-text", Static).update("\n".join(lines))
        self.query_one("#save-path", Static).update(
            f"[dim]저장 경로: {config_path.resolve()}[/]"
        )

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "save":
            self._save_config()
        elif event.button.id == "back":
            self.app.pop_screen()

    def _save_config(self) -> None:
        try:
            self.app.state.save_config(self.app.config_path)
            self.query_one("#save-status", Static).update(
                "[bold green]설정이 저장되었습니다! "
                "아무 키나 눌러 종료하세요.[/]"
            )
            self.set_timer(1.5, self.app.exit)
        except Exception as e:
            self.query_one("#save-status", Static).update(
                f"[red]저장 실패: {e}[/]"
            )


# ── Main App ──


class SetupWizardApp(App):
    """BioAuto 초기 설정 마법사"""

    TITLE = "BioAuto Setup Wizard"
    CSS = """
    Screen {
        align: center middle;
    }

    #wizard-content {
        width: 80;
        max-height: 90%;
        padding: 1 2;
        border: round $primary;
        background: $surface;
    }

    #nav-bar {
        height: 3;
        dock: bottom;
        padding: 0 1;
        align: right middle;
    }

    .section-title {
        text-style: bold;
        padding: 1 0 0 0;
    }

    .switch-row {
        height: 3;
        align: left middle;
    }

    .switch-row Label {
        width: 24;
        padding: 0 1;
    }

    #ollama-panel, #openai-panel, #anthropic-panel, #nf-panel {
        padding: 0 1;
    }
    """
    BINDINGS = [("q", "quit", "Quit")]

    def __init__(self, config_path: Path | None = None, **kwargs):
        super().__init__(**kwargs)
        self.config_path = config_path or Path("config.json")
        self.state = WizardState()
        self._load_existing_config()

    def _load_existing_config(self) -> None:
        """기존 config.json에서 WizardState 프리필"""
        if not self.config_path.exists():
            return
        try:
            with open(self.config_path) as f:
                data = json.load(f)
        except (json.JSONDecodeError, OSError):
            return

        # LLM providers
        providers = data.get("llm_providers", {})
        backends = providers.get("backends", {})
        for name in ["ollama", "openai", "anthropic"]:
            if backends.get(name, {}).get("enabled"):
                self.state.llm_backend_type = name
                break

        ollama = backends.get("ollama", {})
        if ollama.get("url"):
            self.state.ollama_url = ollama["url"]
        if ollama.get("model"):
            self.state.ollama_model = ollama["model"]
        if ollama.get("timeout"):
            self.state.ollama_timeout = ollama["timeout"]

        openai = backends.get("openai", {})
        if openai.get("api_key_env"):
            self.state.openai_api_key_env = openai["api_key_env"]
        if openai.get("model"):
            self.state.openai_model = openai["model"]

        anthropic = backends.get("anthropic", {})
        if anthropic.get("api_key_env"):
            self.state.anthropic_api_key_env = anthropic["api_key_env"]
        if anthropic.get("model"):
            self.state.anthropic_model = anthropic["model"]

        # Execution
        nf_exec = data.get("nextflow_execution", {})
        if nf_exec.get("container_runtime"):
            self.state.container_runtime = nf_exec["container_runtime"]
        self.state.enable_nextflow = nf_exec.get("enabled", False)
        if nf_exec.get("genome"):
            self.state.genome = nf_exec["genome"]
        if nf_exec.get("max_memory"):
            self.state.max_memory = nf_exec["max_memory"]
        if nf_exec.get("max_cpus"):
            self.state.max_cpus = nf_exec["max_cpus"]

        # Directories
        dirs = data.get("directories", {})
        if dirs.get("results"):
            self.state.results_dir = dirs["results"]

        # Advanced
        debate = data.get("debate", {})
        if debate.get("num_rounds"):
            self.state.debate_rounds = debate["num_rounds"]

        exec_cfg = data.get("execution", {})
        if "enable_debate" in exec_cfg:
            self.state.enable_debate = exec_cfg["enable_debate"]
        if "enable_enrichment" in exec_cfg:
            self.state.enable_enrichment = exec_cfg["enable_enrichment"]
        if "enable_data_aggregation" in exec_cfg:
            self.state.enable_data_aggregation = exec_cfg[
                "enable_data_aggregation"
            ]

        rag = data.get("rag", {})
        if "enabled" in rag:
            self.state.enable_rag = rag["enabled"]

    def on_mount(self) -> None:
        self.push_screen(WelcomeScreen())


def run_setup_wizard(config_path: Path | None = None) -> None:
    """Setup Wizard TUI 실행 헬퍼"""
    app = SetupWizardApp(config_path=config_path)
    app.run()
