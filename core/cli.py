#!/usr/bin/env python3
"""
CLI Entry Point - Bioinformatics Research Automation Platform
바이오인포매틱스 연구 자동화 플랫폼 CLI
"""

import asyncio
import json
import os
import sys
from pathlib import Path

try:
    import click
except ImportError:
    print("click 패키지가 필요합니다: pip install click")
    sys.exit(1)

from core.pipeline import AsyncPipeline, PipelineConfig, PipelineStatus


def _load_config() -> dict:
    """config.json에서 설정을 로드합니다."""
    config_paths = [
        Path(__file__).parent.parent / "config.json",
        Path.cwd() / "config.json",
    ]
    for p in config_paths:
        if p.exists():
            with open(p) as f:
                return json.load(f)
    return {}


def _get_llm_server_config() -> tuple[str, str, int, str | None]:
    """config.json에서 LLM 서버 설정을 반환합니다. (url, model, timeout, failover_url)"""
    cfg = _load_config()
    llm = cfg.get("pipeline_config", {}).get("llm_server", {})
    url = llm.get("url", "http://localhost:11434")
    model = llm.get("model", "qwen3:30b")
    timeout = llm.get("timeout", 60)
    failover_url = llm.get("failover_url")
    return url, model, timeout, failover_url


def _create_backends_from_config():
    """config.json에서 LLM 백엔드 목록과 RouterConfig를 생성합니다."""
    import os

    from backends import LLMConfig, OllamaBackend, OpenAIBackend
    from backends.router import RouterConfig

    cfg = _load_config()
    llm_providers = cfg.get("llm_providers")

    if llm_providers:
        backends_data = llm_providers.get("backends", {})
        router_data = llm_providers.get("router", {})
        priority_order = router_data.get(
            "priority_order", ["ollama", "openai", "anthropic"]
        )
        backends_list = []
        for name in priority_order:
            bcfg = backends_data.get(name, {})
            if not bcfg.get("enabled", False):
                continue
            llm_config = LLMConfig(
                model=bcfg.get("model", ""),
                temperature=bcfg.get("temperature", 0.1),
                top_p=bcfg.get("top_p", 0.9),
                max_tokens=bcfg.get("max_tokens", 4096),
                timeout=bcfg.get("timeout", 120),
                max_retries=bcfg.get("max_retries", 3),
            )
            if name == "ollama":
                backends_list.append(OllamaBackend(
                    base_url=bcfg.get("url", "http://localhost:11434"),
                    config=llm_config,
                    failover_url=bcfg.get("failover_url"),
                ))
            elif name == "openai":
                api_key_env = bcfg.get("api_key_env", "OPENAI_API_KEY")
                api_key = os.environ.get(api_key_env)
                if api_key:
                    backends_list.append(OpenAIBackend(
                        config=llm_config,
                        api_key=api_key,
                        base_url=bcfg.get("base_url"),
                    ))
            elif name == "anthropic":
                try:
                    from backends import AnthropicBackend
                    api_key_env = bcfg.get(
                        "api_key_env", "ANTHROPIC_API_KEY"
                    )
                    api_key = os.environ.get(api_key_env)
                    if api_key:
                        backends_list.append(AnthropicBackend(
                            config=llm_config, api_key=api_key,
                        ))
                except ImportError:
                    pass
        router_config = RouterConfig(
            strategy=router_data.get("strategy", "priority"),
            health_check_interval=router_data.get(
                "health_check_interval", 60
            ),
            enable_auto_failover=router_data.get(
                "enable_auto_failover", True
            ),
            max_concurrent_requests=router_data.get(
                "max_concurrent_requests", 10
            ),
        )
        return backends_list, router_config

    # Legacy fallback
    url, model, timeout, failover_url = _get_llm_server_config()
    backends_list = [
        OllamaBackend(
            base_url=url, config=LLMConfig(model=model, timeout=timeout),
            failover_url=failover_url,
        )
    ]
    if os.environ.get("OPENAI_API_KEY"):
        backends_list.append(
            OpenAIBackend(config=LLMConfig(model="gpt-4o", timeout=timeout))
        )
    try:
        from backends import AnthropicBackend
        if os.environ.get("ANTHROPIC_API_KEY"):
            backends_list.append(AnthropicBackend(
                config=LLMConfig(
                    model="claude-sonnet-4-20250514", timeout=timeout,
                )
            ))
    except ImportError:
        pass
    router_config = RouterConfig(
        strategy="priority", enable_auto_failover=True
    )
    return backends_list, router_config


@click.group()
@click.version_option(version="4.0.0", prog_name="bioauto")
def cli():
    """Bioinformatics Research Automation Platform

    논문 수집 -> 데이터 통합 -> 시퀀싱 분석 -> LLM 합의 -> 멀티 에이전트 토론
    """
    pass


@cli.command()
@click.argument("pmids", nargs=-1, required=True)
@click.option("--results-dir", "-o", type=click.Path(), default="./results",
              help="결과 저장 디렉토리")
@click.option("--max-concurrent", "-j", type=int, default=5,
              help="최대 동시 처리 PMID 수")
@click.option("--config", "-c", type=click.Path(exists=True), default=None,
              help="설정 파일 경로 (config.json)")
@click.option("--debate/--no-debate", default=True,
              help="멀티 에이전트 토론 활성화")
@click.option("--enrichment/--no-enrichment", default=True,
              help="농축 분석 활성화")
@click.option("--aggregate/--no-aggregate", default=True,
              help="데이터 소스 통합 활성화")
@click.option("--resume/--no-resume", default=True,
              help="체크포인트 기반 재시작")
@click.option("--debate-rounds", type=int, default=3,
              help="토론 라운드 수")
@click.option("--execute-pipeline/--no-execute-pipeline", default=False,
              help="실제 nf-core 파이프라인 실행 (Nextflow + 컨테이너 필요)")
@click.option("--genome", type=str, default="GRCh38",
              help="Reference genome for nf-core pipelines")
@click.option("--container-runtime",
              type=click.Choice(["docker", "singularity", "apptainer"]),
              default="docker", help="Container runtime for Nextflow")
@click.option("--max-memory", type=str, default="16.GB",
              help="Max memory for Nextflow processes")
@click.option("--max-cpus", type=int, default=4,
              help="Max CPUs for Nextflow processes")
@click.option("--project", "-p", type=str, default=None,
              help="프로젝트명 (종합보고서 제목에 사용)")
def run(pmids, results_dir, max_concurrent, config, debate, enrichment,
        aggregate, resume, debate_rounds, execute_pipeline, genome,
        container_runtime, max_memory, max_cpus, project):
    """주어진 PMID에 대해 전체 파이프라인을 실행합니다.

    결과 구조:
      results/{PMID}/          ← PMID별 개별 보고서
      results/project_report.html  ← 종합보고서 (2+ PMID)

    예시: bioauto run 40315330 32416070
    예시: bioauto run 40315330 32416070 -p "RA_bee_venom"
    """
    # config.json 로드 (--config 지정 시 해당 파일, 아니면 자동 탐색)
    config_path = config or None
    if config_path:
        pipeline_config = PipelineConfig.from_json(config_path)
        pipeline_config.pmids = list(pmids) or pipeline_config.pmids
    else:
        # config.json 자동 탐색하여 설정 로드
        cfg_data = _load_config()
        if cfg_data:
            pipeline_config = PipelineConfig.from_dict(cfg_data)
            pipeline_config.pmids = list(pmids)
        else:
            pipeline_config = PipelineConfig(pmids=list(pmids))

    # CLI 옵션으로 오버라이드
    pipeline_config.results_dir = Path(results_dir)
    pipeline_config.max_concurrent = max_concurrent
    pipeline_config.enable_resume = resume
    pipeline_config.enable_data_aggregation = aggregate
    pipeline_config.enable_enrichment = enrichment
    pipeline_config.enable_debate = debate
    pipeline_config.debate_rounds = debate_rounds
    pipeline_config.project_slug = project

    # Pipeline execution config
    if execute_pipeline:
        try:
            from nextflow.config import ContainerRuntime, NextflowExecutionConfig
            nf_config = NextflowExecutionConfig(
                enabled=True,
                genome=genome,
                container_runtime=ContainerRuntime(container_runtime),
                profile=container_runtime,
                max_memory=max_memory,
                max_cpus=max_cpus,
            )
            pipeline_config.enable_pipeline_execution = True
            pipeline_config.nextflow_config = nf_config
        except ImportError:
            click.echo(click.style(
                "[WARN] nextflow package not available, --execute-pipeline disabled",
                fg="yellow"
            ))

    from core.terminal_fx import (
        AnimatedWait,
        print_completion_summary,
        print_run_banner,
        print_status_bar,
    )

    print_run_banner(list(pmids), project)

    # 설정 요약
    opts = []
    if debate:
        opts.append(f"토론 {debate_rounds}R")
    if enrichment:
        opts.append("농축분석")
    if aggregate:
        opts.append("데이터통합")
    if execute_pipeline:
        opts.append(f"파이프라인({genome})")
    if resume:
        opts.append("이어하기")
    if opts:
        print_status_bar(" · ".join(opts), "info")
        print()

    pipeline = AsyncPipeline(pipeline_config)

    import time as _time

    t0 = _time.monotonic()

    async def _run_with_animation():
        async with AnimatedWait(
            f"파이프라인 실행 중 — {len(pmids)} PMID(s)",
            category="pipeline",
            style="dna",
        ):
            return await pipeline.run()

    results = asyncio.run(_run_with_animation())
    elapsed = _time.monotonic() - t0

    # 결과 출력
    print_status_bar("분석 결과", "magic")

    completed_count = 0
    failed_count = 0

    for pmid, result in results.items():
        status_color = {
            PipelineStatus.COMPLETED: "green",
            PipelineStatus.FAILED: "red",
            PipelineStatus.PARTIAL: "yellow",
        }.get(result.status, "white")

        if result.status == PipelineStatus.COMPLETED:
            completed_count += 1
        elif result.status == PipelineStatus.FAILED:
            failed_count += 1

        click.echo(click.style(
            f"\n  PMID {pmid}: {result.status.value} ({result.duration_seconds:.1f}s)",
            fg=status_color, bold=True
        ))

        if result.sequencing_result:
            click.echo(f"    Sequencing: {result.sequencing_result.get('sequencing_type', '?')} "
                       f"(confidence: {result.sequencing_result.get('confidence', 0):.2f})")

        if result.llm_analysis:
            click.echo(f"    LLM Rating: {result.llm_analysis.get('consistency_rating', '?')}")
            consensus = result.llm_analysis.get("consensus", {})
            if consensus:
                click.echo(f"    Consensus: {consensus.get('num_backends', 0)} backends")

        if result.debate_report and result.debate_report.get("overall_verdict"):
            verdict = result.debate_report["overall_verdict"]
            verdict_color = {"PASS": "green", "WARN": "yellow", "FAIL": "red"}.get(verdict, "white")
            click.echo(click.style(
                f"    Debate Verdict: {verdict} "
                f"(score: {result.debate_report.get('overall_score', 0):.2f})",
                fg=verdict_color
            ))

        if result.pipeline_execution and result.pipeline_execution.get("status"):
            pe_status = result.pipeline_execution["status"]
            pe_color = {"completed": "green", "failed": "red"}.get(pe_status, "yellow")
            click.echo(click.style(
                f"    Pipeline: "
                f"{result.pipeline_execution.get('pipeline_name', '?')} ({pe_status})",
                fg=pe_color
            ))

        if result.downstream_analysis and result.downstream_analysis.get("success"):
            da = result.downstream_analysis.get("summary", {})
            da_type = result.downstream_analysis.get("analysis_type", "?")
            click.echo(f"    Analysis: {da_type}")
            if "significant_degs" in da:
                click.echo(
                    f"      DEGs: {da['significant_degs']} "
                    f"(up: {da.get('upregulated', 0)}, down: {da.get('downregulated', 0)})"
                )
            if "n_clusters" in da:
                click.echo(
                    f"      Clusters: {da['n_clusters']}, "
                    f"Cells: {da.get('filtered_cells', '?')}"
                )

        if result.error:
            click.echo(click.style(f"    Error: {result.error}", fg="red"))

    print_completion_summary(len(results), completed_count, failed_count, elapsed)


@cli.command()
@click.option("--results-dir", "-o", type=click.Path(exists=True), default="./results")
@click.option("--format", "-f", "fmt", type=click.Choice(["table", "json"]), default="table")
def status(results_dir, fmt):
    """파이프라인 실행 상태를 확인합니다."""
    results_path = Path(results_dir)
    summary_file = results_path / "execution_summary.json"
    progress_file = results_path / "progress.json"

    if summary_file.exists():
        with open(summary_file) as f:
            summary = json.load(f)

        if fmt == "json":
            click.echo(json.dumps(summary, indent=2, ensure_ascii=False))
        else:
            exec_summary = summary.get("execution_summary", {})
            click.echo(f"Total PMIDs: {exec_summary.get('total_pmids', 0)}")
            click.echo(f"Completed: {exec_summary.get('completed', 0)}")
            click.echo(f"Failed: {exec_summary.get('failed', 0)}")
            click.echo(f"Debate: {'ON' if exec_summary.get('debate_enabled') else 'OFF'}")
            click.echo(f"Timestamp: {summary.get('timestamp', '?')}")

            pmid_results = summary.get("pmid_results", {})
            for pmid, result in pmid_results.items():
                click.echo(f"\n  PMID {pmid}: {result.get('status', '?')}")
                click.echo(f"    Type: {result.get('sequencing_type', '?')}")
                click.echo(f"    LLM: {result.get('llm_rating', '?')}")
                click.echo(f"    Debate: {result.get('debate_verdict', '?')}")
    elif progress_file.exists():
        with open(progress_file) as f:
            progress = json.load(f)
        click.echo(f"Execution ID: {progress.get('execution_id', '?')}")
        click.echo(f"Current Phase: {progress.get('current_phase', '?')}")
        click.echo(f"Current PMID: {progress.get('current_pmid', '?')}")
        click.echo(f"Completed Phases: {len(progress.get('completed_phases', []))}")
    else:
        click.echo("실행 기록이 없습니다.")


@cli.command()
def backends():
    """LLM 백엔드 상태를 확인합니다."""
    import os

    cfg = _load_config()
    llm_providers = cfg.get("llm_providers")
    click.echo("=== LLM Backend Status ===\n")

    if llm_providers:
        # Config-driven multi-provider display
        backends_data = llm_providers.get("backends", {})
        router_data = llm_providers.get("router", {})
        priority_order = router_data.get(
            "priority_order", list(backends_data.keys())
        )
        for i, name in enumerate(priority_order, 1):
            bcfg = backends_data.get(name, {})
            enabled = bcfg.get("enabled", False)
            model = bcfg.get("model", "unknown")
            click.echo(f"{i}. {name.capitalize()} ({model})")
            if not enabled:
                click.echo(
                    click.style("   Status: DISABLED", fg="yellow")
                )
                click.echo()
                continue
            if name == "ollama":
                url = bcfg.get("url", "http://localhost:11434")
                try:
                    import httpx
                    resp = httpx.get(f"{url}/api/tags", timeout=10)
                    if resp.status_code == 200:
                        models = resp.json().get("models", [])
                        model_names = [m.get("name", "") for m in models]
                        is_auto = model in ("auto", "")
                        if is_auto:
                            model_found = len(model_names) > 0
                        else:
                            model_found = any(
                                model in mn
                                or mn.startswith(model.split(":")[0])
                                for mn in model_names
                            )
                        if model_found:
                            status = "HEALTHY"
                            if is_auto:
                                status += f" (auto — {len(model_names)}개 모델)"
                            click.echo(click.style(
                                f"   Status: {status}", fg="green"
                            ))
                        else:
                            click.echo(click.style(
                                f"   Status: Model '{model}' not found",
                                fg="yellow",
                            ))
                        click.echo(f"   Server: {url}")
                        click.echo(
                            f"   Models: {', '.join(model_names[:5])}"
                        )
                        if len(model_names) > 5:
                            click.echo(
                                f"   ... +{len(model_names) - 5} more"
                            )
                    else:
                        click.echo(click.style(
                            "   Status: UNHEALTHY", fg="red"
                        ))
                except Exception:
                    click.echo(click.style(
                        "   Status: UNREACHABLE", fg="red"
                    ))
            else:
                api_key_env = bcfg.get("api_key_env", "")
                if api_key_env and os.environ.get(api_key_env):
                    click.echo(click.style(
                        "   Status: API key configured", fg="green"
                    ))
                else:
                    click.echo(click.style(
                        f"   Status: No API key ({api_key_env})",
                        fg="yellow",
                    ))
            click.echo()
        strategy = router_data.get("strategy", "priority")
        failover = router_data.get("enable_auto_failover", True)
        click.echo(
            f"Router: strategy={strategy}, "
            f"failover={'ON' if failover else 'OFF'}"
        )
    else:
        # Legacy display
        ollama_url, ollama_model, _, _ = _get_llm_server_config()
        click.echo(f"1. Ollama ({ollama_model})")
        try:
            import httpx
            resp = httpx.get(f"{ollama_url}/api/tags", timeout=10)
            if resp.status_code == 200:
                models = resp.json().get("models", [])
                model_names = [m.get("name", "") for m in models]
                model_found = any(
                    ollama_model in name
                    or name.startswith(ollama_model.split(":")[0])
                    for name in model_names
                )
                if model_found:
                    click.echo(click.style(
                        "   Status: HEALTHY", fg="green"
                    ))
                else:
                    click.echo(click.style(
                        f"   Status: Model '{ollama_model}' not found",
                        fg="yellow",
                    ))
                click.echo(f"   Server: {ollama_url}")
                click.echo(
                    f"   Models: {', '.join(model_names[:5])}"
                )
            else:
                click.echo(click.style(
                    "   Status: UNHEALTHY", fg="red"
                ))
        except Exception:
            click.echo(click.style(
                "   Status: UNREACHABLE", fg="red"
            ))
        click.echo("\n2. OpenAI (GPT-4)")
        if os.environ.get("OPENAI_API_KEY"):
            click.echo(click.style(
                "   Status: API key configured", fg="green"
            ))
        else:
            click.echo(click.style(
                "   Status: No API key (OPENAI_API_KEY)", fg="yellow"
            ))
        click.echo("\n3. Anthropic (Claude)")
        if os.environ.get("ANTHROPIC_API_KEY"):
            click.echo(click.style(
                "   Status: API key configured", fg="green"
            ))
        else:
            click.echo(click.style(
                "   Status: No API key (ANTHROPIC_API_KEY)", fg="yellow"
            ))


@cli.command()
def plugins():
    """등록된 시퀀싱 탐지 플러그인 목록을 확인합니다."""
    from plugins import register_default_plugins

    registry = register_default_plugins()
    click.echo("=== Sequencing Detection Plugins ===\n")

    for name in sorted(registry.list_plugins()):
        plugin = registry.get(name)
        if plugin is None:
            continue
        click.echo(f"  {plugin.display_name}")
        click.echo(f"    Name: {name}")
        click.echo(f"    Priority: {plugin.priority}")
        click.echo(f"    Pipeline: {plugin.pipeline.nf_core_name}")
        click.echo(f"    Keywords: {', '.join(plugin.keywords[:5])}...")
        click.echo()


@cli.command()
def prereqs():
    """파이프라인 실행을 위한 사전 요구사항을 확인합니다."""
    import shutil

    click.echo("=== Pipeline Execution Prerequisites ===\n")

    # Nextflow
    nf = shutil.which("nextflow")
    _show_check("Nextflow", nf is not None, nf or "not found")

    # Java
    java = shutil.which("java")
    _show_check("Java", java is not None, java or "not found")

    # Container runtimes
    for rt in ["docker", "singularity", "apptainer"]:
        found = shutil.which(rt)
        _show_check(f"  {rt}", found is not None, found or "not found")

    # R
    r = shutil.which("Rscript")
    _show_check("Rscript", r is not None, r or "not found")

    if r:
        click.echo("\n  R Packages:")
        r_packages = [
            "DESeq2", "tximport", "Seurat", "ggplot2",
            "pheatmap", "optparse", "jsonlite",
        ]
        for pkg in r_packages:
            try:
                import subprocess
                result = subprocess.run(
                    [r, "-e", f'cat(requireNamespace("{pkg}", quietly=TRUE))'],
                    capture_output=True, text=True, timeout=10,
                )
                installed = result.stdout.strip() == "TRUE"
                _show_check(f"    {pkg}", installed)
            except Exception:
                _show_check(f"    {pkg}", False, "check failed")

    # Python packages
    click.echo("\n  Python Packages (optional):")
    for pkg in ["scanpy", "anndata", "matplotlib"]:
        try:
            __import__(pkg)
            _show_check(f"    {pkg}", True)
        except ImportError:
            _show_check(f"    {pkg}", False, "not installed")

    # Slurm HPC
    click.echo("\n  Slurm HPC:")
    try:
        from core.slurm_detector import SlurmDetector
        if SlurmDetector.is_available():
            _show_check("    Slurm", True, "클러스터 감지됨")
            detection = SlurmDetector.detect()
            for tool, path in detection["tools"].items():
                if path:
                    _show_check(f"      {tool}", True, path)
            if detection["partitions"]:
                parts = [p["name"] for p in detection["partitions"]]
                click.echo(f"    Partitions: {', '.join(parts)}")
                if detection["default_partition"]:
                    click.echo(f"    Default: {detection['default_partition']}")
            if detection["accounts"]:
                click.echo(f"    Accounts: {', '.join(detection['accounts'])}")
            if detection["qos_list"]:
                click.echo(f"    QoS: {', '.join(detection['qos_list'])}")
            click.echo("    → `bioauto setup-slurm` 으로 자동 설정 가능")
        else:
            _show_check("    Slurm", False, "not found (선택사항)")
    except Exception:
        _show_check("    Slurm", False, "감지 실패")

    # Disk space
    try:
        stat = os.statvfs(".")
        free_gb = (stat.f_bavail * stat.f_frsize) / (1024**3)
        _show_check("\nDisk Space", free_gb > 10, f"{free_gb:.1f} GB free")
    except Exception:
        pass

    click.echo()


def _show_check(name: str, ok: bool, detail: str = ""):
    """Display a prerequisite check result."""
    symbol = click.style("[OK]", fg="green") if ok else click.style("[--]", fg="red")
    msg = f"  {symbol} {name}"
    if detail:
        msg += f" ({detail})"
    click.echo(msg)


@cli.command(name="setup-slurm")
@click.option("--dry-run", is_flag=True, default=False, help="변경 없이 감지 결과만 표시")
def setup_slurm(dry_run):
    """Slurm HPC 환경을 자동 감지하고 config.json에 적용합니다."""
    from core.slurm_detector import SlurmDetector

    click.echo("=== Slurm HPC 자동 감지 ===\n")

    detection = SlurmDetector.detect()

    if not detection["available"]:
        click.echo(click.style("Slurm이 설치되어 있지 않습니다.", fg="red"))
        click.echo("sbatch, squeue 등 Slurm 도구가 PATH에 있는지 확인하세요.")
        return

    click.echo(click.style("Slurm 클러스터 감지됨!", fg="green"))

    # Show tools
    click.echo("\n도구:")
    for tool, path in detection["tools"].items():
        if path:
            click.echo(f"  {click.style('[OK]', fg='green')} {tool}: {path}")

    # Show partitions
    if detection["partitions"]:
        click.echo(f"\n파티션 ({len(detection['partitions'])}개):")
        for p in detection["partitions"]:
            default_tag = " (default)" if p.get("is_default") else ""
            click.echo(
                f"  {p['name']}{default_tag}"
                f" — CPUs: {p['cpus']}, Mem: {p['memory_mb']}MB,"
                f" Time: {p['time_limit']}, Nodes: {p['nodes']}"
            )

    # Show accounts
    if detection["accounts"]:
        click.echo(f"\n계정: {', '.join(detection['accounts'])}")

    # Show QoS
    if detection["qos_list"]:
        click.echo(f"QoS: {', '.join(detection['qos_list'])}")

    # Show suggested config
    suggested = detection["suggested_config"]
    click.echo("\n--- 권장 설정 ---")
    click.echo(f"  partition: {suggested.get('queue', 'N/A')}")
    click.echo(f"  account:   {suggested.get('account', 'N/A')}")
    click.echo(f"  qos:       {suggested.get('qos', 'N/A')}")
    click.echo(f"  cpus:      {suggested.get('cpus_per_task', 4)}")
    click.echo(f"  memory:    {suggested.get('memory', '16G')}")
    click.echo(f"  time:      {suggested.get('time_limit', '24:00:00')}")

    if dry_run:
        click.echo("\n(--dry-run: config.json 변경 없음)")
        return

    # ── 공유 스토리지 확인 ──
    click.echo("\n=== 결과 파일 접근 확인 ===")
    click.echo("Slurm 노드에서 생성된 결과 파일을 이 PC에서 볼 수 있어야 합니다.")
    click.echo("(NFS, Lustre, GPFS 등 공유 파일시스템이 필요합니다)\n")

    # 현재 프로젝트의 results 경로로 기본 체크
    default_results = str(Path(__file__).parent.parent / "results")
    results_path = click.prompt(
        "결과 저장 경로",
        default=default_results,
    )
    results_path = os.path.expanduser(results_path)

    fs_check = SlurmDetector.check_shared_filesystem(results_path)

    if fs_check["is_shared"]:
        # 공유 파일시스템 확인됨
        click.echo(
            click.style("\n[OK] 공유 파일시스템 감지됨", fg="green")
            + f" (타입: {fs_check['fs_type']})"
        )
        if fs_check["mount_point"]:
            click.echo(f"  마운트: {fs_check['mount_point']}")
    else:
        # 자동 판단 불가 → 사용자에게 질문
        click.echo(click.style("\n[?] 공유 파일시스템 자동 감지 실패", fg="yellow"))
        if fs_check["fs_type"]:
            click.echo(f"  감지된 파일시스템: {fs_check['fs_type']}")
        if fs_check["mount_point"]:
            click.echo(f"  마운트 포인트: {fs_check['mount_point']}")
        if fs_check["method"] == "path_pattern":
            click.echo("  (경로 패턴상 공유 스토리지일 가능성 있음)")

        click.echo(
            "\n이 경로가 Slurm 컴퓨트 노드에서도 동일하게 접근 가능한가요?"
        )
        click.echo("예: NFS 마운트, Lustre, GPFS 등으로 모든 노드에 공유된 경로")
        user_confirms = click.confirm("현재 경로를 컴퓨트 노드에서 접근 가능합니까?")

        if not user_confirms:
            # 다른 경로 안내
            click.echo(
                "\n컴퓨트 노드와 공유되는 경로가 있다면 입력해주세요."
            )
            click.echo("예: /home/user/shared, /scratch/user, REDACTED-NFS-PATH/...")
            alt_path = click.prompt(
                "공유 경로 (없으면 빈칸)",
                default="",
            )

            if alt_path:
                alt_path = os.path.expanduser(alt_path)
                alt_check = SlurmDetector.check_shared_filesystem(alt_path)
                if alt_check["is_shared"]:
                    click.echo(
                        click.style("\n[OK] 공유 파일시스템 확인됨", fg="green")
                        + f" (타입: {alt_check['fs_type']})"
                    )
                    results_path = alt_path
                else:
                    click.echo(click.style(
                        "\n[?] 해당 경로도 공유 파일시스템으로 확인되지 않았습니다.",
                        fg="yellow",
                    ))
                    force = click.confirm("그래도 이 경로로 설정하시겠습니까?")
                    if force:
                        results_path = alt_path
                    else:
                        click.echo(click.style(
                            "\nSlurm 자동 설정을 중단합니다.", fg="red",
                        ))
                        click.echo(
                            "공유 스토리지 구성 후 다시 실행하세요: bioauto setup-slurm"
                        )
                        return
            else:
                # 공유 경로 없음 → 노드 직접 연결 가능 여부 확인
                click.echo("\n공유 스토리지 없이도 사용 가능한 경우:")
                click.echo("  - 이 PC가 Slurm 클러스터의 헤드 노드인 경우")
                click.echo("  - 컴퓨트 노드와 동일한 로컬 디스크 구성인 경우")
                is_head = click.confirm("이 PC가 클러스터 헤드 노드입니까?")

                if not is_head:
                    click.echo(click.style(
                        "\nSlurm 자동 설정을 중단합니다.", fg="red",
                    ))
                    click.echo(
                        "컴퓨트 노드의 결과 파일에 접근할 수 없으면 "
                        "Slurm 설정을 해도 결과를 확인할 수 없습니다."
                    )
                    click.echo("해결 방법:")
                    click.echo("  1. NFS/Lustre 등 공유 스토리지를 마운트")
                    click.echo("  2. 클러스터 헤드 노드에서 bioauto를 실행")
                    click.echo(
                        "  3. 수동 설정: config.json의 "
                        "nextflow_execution.slurm 섹션 직접 편집"
                    )
                    return

    # 쓰기 권한 확인
    if not fs_check["writable"]:
        alt_check = SlurmDetector.check_shared_filesystem(results_path)
        if not alt_check["writable"]:
            click.echo(click.style(
                f"\n[!] {results_path} 에 쓰기 권한이 없습니다.", fg="yellow"
            ))
            if not click.confirm("그래도 계속하시겠습니까?"):
                return

    # ── config.json 적용 ──
    config_path = Path(__file__).parent.parent / "config.json"
    if not config_path.exists():
        click.echo(click.style(
            f"\nconfig.json을 찾을 수 없습니다: {config_path}", fg="red"
        ))
        return

    SlurmDetector.apply_to_config(str(config_path), detection)

    # results 경로가 기본값과 다르면 config에도 반영
    if results_path != default_results:
        import json
        with open(config_path) as f:
            cfg = json.load(f)
        cfg.setdefault("directories", {})["results"] = results_path
        nf = cfg.setdefault("nextflow_execution", {})
        nf["outdir"] = str(Path(results_path) / "nfcore")
        nf["work_dir"] = str(Path(results_path) / "nextflow_work")
        with open(config_path, "w") as f:
            json.dump(cfg, f, indent=2, ensure_ascii=False)

    click.echo(click.style("\n✓ config.json에 Slurm 설정 적용 완료", fg="green"))
    click.echo(f"  파일: {config_path}")
    click.echo(f"  결과 경로: {results_path}")
    click.echo("  nextflow_execution.slurm.enabled = true")
    click.echo("  nextflow_execution.profile = slurm")
    click.echo("\n수동 조정이 필요하면 config.json을 직접 편집하세요.")


@cli.command()
@click.argument("query")
@click.option("--limit", "-n", type=int, default=20, help="소스별 최대 검색 결과 수")
@click.option("--results-dir", "-o", type=click.Path(), default="./results",
              help="결과 저장 디렉토리")
@click.option("--no-brave", is_flag=True, default=False, help="Brave 웹 검색 비활성화")
@click.option("--auto-run", is_flag=True, default=False, help="선택 후 파이프라인 자동 실행")
@click.option("--debate/--no-debate", default=True, help="토론 활성화")
def search(query, limit, results_dir, no_brave, auto_run, debate):
    """주제 기반 논문 검색 후 파이프라인 실행.

    예시: bioauto search "spatial transcriptomics cancer"
    """
    asyncio.run(_run_search_cmd(query, limit, results_dir, no_brave, auto_run, debate))


async def _run_search_cmd(query, limit, results_dir, no_brave, auto_run, debate):
    """search 명령 비동기 실행 — 애니메이션 포함."""
    from core.terminal_fx import (
        AnimatedWait,
        print_results_table,
        print_search_banner,
        print_status_bar,
    )

    print_search_banner(query)

    # 한국어 검색어 → 영어 번역
    query = await _translate_query_if_korean(query)

    # RAG 자동 수집기 (조용히 초기화, 실패해도 무시)
    collector = _get_collector(results_dir)

    async with AnimatedWait("논문 검색 중", category="search", style="molecule"):
        results = await _run_search(query, limit, no_brave)

    if not results:
        print_status_bar("검색 결과가 없습니다", "error")
        return

    # 자동 RAG 수집: 검색 결과 논문 인덱싱
    if collector:
        collector.collect_search(query, results)
        collector.collect_papers_from_search(results)

    # 화려한 결과 테이블
    print_results_table(results)

    # 사용자 선택 (오타 시 재입력)
    pmids = _select_papers(results)
    if not pmids:
        click.echo("  종료합니다.")
        return

    # 자동 RAG 수집: 선택한 PMID 기록
    if collector:
        collector.collect_search(query, results, selected_pmids=pmids)

    print_status_bar(f"선택: {', '.join(pmids)}", "success")

    if auto_run or click.confirm(
        click.style("\n  파이프라인을 실행할까요?", fg="cyan", bold=True)
    ):
        cfg_data = _load_config() or {}
        pipeline_config = PipelineConfig.from_dict(cfg_data)
        pipeline_config.pmids = pmids
        pipeline_config.results_dir = Path(results_dir)
        pipeline_config.enable_debate = debate
        pipeline_config.rag_dir = Path(results_dir) / "rag_db"

        pipeline = AsyncPipeline(pipeline_config)
        print()
        print_status_bar("파이프라인 실행 시작", "magic")
        results = await pipeline.run()

        # LLM 실패 감지
        failed = [
            (p, r) for p, r in results.items()
            if r.status == PipelineStatus.FAILED
        ]
        if failed and len(failed) == len(results):
            print_status_bar(
                "파이프라인 실패 — LLM 백엔드 연결 불가", "error"
            )
            for pmid, r in failed:
                click.echo(click.style(
                    f"  ✗ {pmid}: {r.error}", fg="red",
                ))
        elif failed:
            print_status_bar(
                f"파이프라인 부분 완료 — {len(failed)}개 실패", "warn"
            )
            for pmid, r in failed:
                click.echo(click.style(
                    f"  ✗ {pmid}: {r.error}", fg="red",
                ))
        else:
            print_status_bar("파이프라인 실행 완료!", "success")


def _has_korean(text: str) -> bool:
    """텍스트에 한국어가 포함되어 있는지 확인."""
    return any('\uac00' <= c <= '\ud7a3' for c in text)


async def _translate_query_if_korean(query: str) -> str:
    """한국어 검색어를 영어 PubMed 검색어로 변환.

    PubMed/Semantic Scholar는 영어만 지원하므로
    한국어가 포함된 쿼리를 LLM으로 번역합니다.
    """
    if not _has_korean(query):
        return query

    try:
        backends_list, router_config = _create_backends_from_config()
        from backends import LLMRouter
        router = LLMRouter(backends=backends_list, config=router_config)
        await router.start()
        resp = await router.generate(
            f"Translate the following Korean biomedical search query "
            f"to English for PubMed search. "
            f"Output ONLY the English query, nothing else.\n\n"
            f"Korean: {query}",
        )
        await router.stop()
        if resp.success and resp.content.strip():
            translated = resp.content.strip().strip('"').strip("'")
            import click as _click
            _click.echo(
                _click.style(f"  🌐 번역: {query} → {translated}", dim=True)
            )
            return translated
    except Exception:
        pass
    return query


def _save_consult_log(
    conversation: list[dict],
    search_queries: list[str],
    results_dir: str = "./results",
):
    """상담 대화 로그를 JSON 파일로 저장합니다."""
    if not conversation:
        return
    import json
    from datetime import datetime
    log_dir = Path(results_dir) / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_file = log_dir / f"consult_{ts}.json"
    log_data = {
        "timestamp": datetime.now().isoformat(),
        "turns": len(conversation),
        "search_queries": search_queries,
        "conversation": conversation,
    }
    try:
        with open(log_file, "w", encoding="utf-8") as f:
            json.dump(log_data, f, ensure_ascii=False, indent=2)
        import click as _click
        _click.echo(
            _click.style(f"  💬 대화 로그: {log_file}", dim=True)
        )
    except OSError:
        pass


def _get_collector(results_dir: str = "./results"):
    """RAG 자동 수집기를 조용히 초기화합니다. 실패 시 None 반환."""
    try:
        from rag.auto_collector import AutoRAGCollector
        return AutoRAGCollector(rag_dir=Path(results_dir) / "rag_db")
    except Exception:
        return None


async def _run_search(query: str, limit: int, no_brave: bool):
    """검색 실행 헬퍼"""
    from clients.europe_pmc_client import EuropePMCClient
    from clients.semantic_scholar_client import SemanticScholarClient
    from core.pubmed_client import PubMedClient
    from search import ResultRanker, TopicSearcher

    pubmed = PubMedClient()
    ss = SemanticScholarClient()
    epmc = EuropePMCClient()

    brave = None
    if not no_brave:
        try:
            from mcp import BraveSearchClient
            brave = BraveSearchClient()
        except ImportError:
            pass

    searcher = TopicSearcher(
        pubmed_client=pubmed,
        ss_client=ss,
        epmc_client=epmc,
        brave_client=brave,
        limit_per_source=limit,
    )

    raw_results = await searcher.search(query)

    # 클라이언트 정리
    await ss.close()
    await epmc.close()
    if brave:
        await brave.close()

    ranker = ResultRanker()
    return ranker.rank(raw_results)


@cli.command()
@click.option("--results-dir", "-o", type=click.Path(), default="./results",
              help="결과 저장 디렉토리")
@click.option("--debate/--no-debate", default=True, help="토론 활성화")
def consult(results_dir, debate):
    """대화형 연구 주제 상담 후 검색 및 파이프라인 실행.

    예시: bioauto consult
    """
    asyncio.run(_run_consult(results_dir, debate))


def _read_input(prompt_str: str) -> str:
    """readline 기반 입력 (백스페이스/방향키 정상 동작)."""
    try:
        import readline  # noqa: F401 — import activates readline editing
    except ImportError:
        pass
    try:
        return input(prompt_str)
    except (EOFError, KeyboardInterrupt):
        print()
        return "q"


def _select_papers(results: list, max_retries: int = 5) -> list[str]:
    """논문 선택 — 번호, 범위, 조건, 전체 선택 지원.

    입력 방식:
      번호:    1,3,5        개별 선택
      범위:    1-10         범위 선택
      전체:    all / a      PMID 있는 전부
      조건:    >2023        2023년 이후
               cited>50     인용 50 이상
               "키워드"      제목에 키워드 포함
      종료:    q            취소
    """
    click.echo()
    click.echo(click.style("  선택 방법:", dim=True))
    click.echo(click.style(
        "    번호: 1,3,5  |  범위: 1-10  |  전체: a  |  "
        "조건: >2023  cited>50  \"키워드\"  |  종료: q",
        dim=True,
    ))
    click.echo()

    for attempt in range(max_retries):
        selection = _read_input(
            f"  {click.style('선택', fg='cyan')}: "
        )

        sel = selection.strip()
        if sel.lower() == "q":
            return []

        if not sel:
            # 빈 Enter → 커서를 한 줄 위로 올려서 프롬프트 덮어쓰기
            sys.stdout.write("\033[A\033[2K")
            sys.stdout.flush()
            continue

        # 전체 선택
        if sel.lower() in ("all", "a"):
            pmids = [r.pmid for r in results if r.pmid]
            if pmids:
                click.echo(click.style(f"  전체 {len(pmids)}건 선택됨", fg="green"))
                return pmids
            click.echo(click.style("  PMID가 있는 논문이 없습니다.", fg="yellow"))
            continue

        # 조건 기반 필터
        filtered = _filter_by_condition(results, sel)
        if filtered is not None:
            pmids = [r.pmid for r in filtered if r.pmid]
            if pmids:
                click.echo(click.style(
                    f"  조건 매칭 {len(pmids)}건: {', '.join(pmids[:10])}"
                    + ("..." if len(pmids) > 10 else ""),
                    fg="green",
                ))
                return pmids
            click.echo(click.style("  조건에 맞는 PMID 논문이 없습니다.", fg="yellow"))
            continue

        # 번호/범위 파싱
        indices = _parse_selection_indices(sel, len(results))
        if indices is None:
            remaining = max_retries - attempt - 1
            if remaining > 0:
                click.echo(click.style(
                    f"  숫자만 입력하세요 (예: 1,3,5 또는 1-10). "
                    f"재시도 {remaining}회 남음",
                    fg="yellow",
                ))
            else:
                click.echo(click.style("  잘못된 입력입니다.", fg="red"))
            continue

        valid = [i for i in indices if 0 <= i < len(results)]
        invalid = [i + 1 for i in indices if i < 0 or i >= len(results)]

        if invalid:
            click.echo(click.style(
                f"  범위 밖 번호 무시됨: {invalid} "
                f"(1~{len(results)} 사이만 가능)",
                fg="yellow",
            ))

        if not valid:
            remaining = max_retries - attempt - 1
            if remaining > 0:
                click.echo(click.style(
                    f"  유효한 번호가 없습니다. 재시도 {remaining}회 남음",
                    fg="yellow",
                ))
            else:
                click.echo(click.style("  유효한 선택이 없습니다.", fg="red"))
            continue

        selected = [results[i] for i in valid]
        pmids = [r.pmid for r in selected if r.pmid]

        if not pmids:
            click.echo(click.style(
                "  선택한 논문에 PMID가 없습니다. 다른 번호를 선택하세요.",
                fg="yellow",
            ))
            continue

        return pmids

    return []


def _parse_selection_indices(sel: str, total: int) -> list[int] | None:
    """번호/범위 문자열을 인덱스 리스트로 파싱. 실패 시 None."""
    import re
    indices = []
    parts = re.split(r'[,\s]+', sel.strip())
    for part in parts:
        part = part.strip()
        if not part:
            continue
        # 범위 (1-10)
        range_match = re.match(r'^(\d+)\s*-\s*(\d+)$', part)
        if range_match:
            start = int(range_match.group(1))
            end = int(range_match.group(2))
            indices.extend(range(start - 1, end))  # 1-based → 0-based
            continue
        # 단일 숫자
        try:
            indices.append(int(part) - 1)
        except ValueError:
            return None
    return indices if indices else None


def _filter_by_condition(results: list, condition: str) -> list | None:
    """조건 문자열로 논문 필터링. 조건이 아니면 None 반환."""
    import re
    condition = condition.strip()

    # 연도 조건: >2023 / >=2020 / <2022
    year_match = re.match(r'^([><=]+)\s*(\d{4})$', condition)
    if year_match:
        op, year = year_match.group(1), int(year_match.group(2))
        filtered = []
        for r in results:
            ry = r.year if not isinstance(r, dict) else r.get("year")
            if ry is None:
                continue
            if op == ">" and ry > year:
                filtered.append(r)
            elif op == ">=" and ry >= year:
                filtered.append(r)
            elif op == "<" and ry < year:
                filtered.append(r)
            elif op == "<=" and ry <= year:
                filtered.append(r)
            elif op == "=" and ry == year:
                filtered.append(r)
        return filtered

    # 인용수 조건: cited>50 / cite>=100
    cite_match = re.match(r'^cite[ds]?\s*([><=]+)\s*(\d+)$', condition, re.IGNORECASE)
    if cite_match:
        op, count = cite_match.group(1), int(cite_match.group(2))
        filtered = []
        for r in results:
            cc = r.citation_count if not isinstance(r, dict) else r.get("citation_count", 0)
            if op == ">" and cc > count:
                filtered.append(r)
            elif op == ">=" and cc >= count:
                filtered.append(r)
            elif op == "<" and cc < count:
                filtered.append(r)
            elif op == "<=" and cc <= count:
                filtered.append(r)
        return filtered

    # 키워드 조건: "키워드" 또는 '키워드'
    keyword_match = re.match(r'^["\'](.+)["\']$', condition)
    if keyword_match:
        keyword = keyword_match.group(1).lower()
        filtered = []
        for r in results:
            title = (r.title if not isinstance(r, dict) else r.get("title", "")).lower()
            abstract = (r.abstract if not isinstance(r, dict) else r.get("abstract", "")).lower()
            if keyword in title or keyword in abstract:
                filtered.append(r)
        return filtered

    # 조건이 아님
    return None


async def _run_consult(results_dir: str, debate: bool):
    """상담 모드 실행 — 화려한 터미널 이펙트 포함"""
    import re

    import httpx

    from backends import LLMRouter
    from core.terminal_fx import (
        AnimatedWait,
        fancy_prompt,
        print_consult_banner,
        print_goodbye,
        print_results_table,
        print_status_bar,
        reveal_response,
    )

    # RAG 자동 수집기
    collector = _get_collector(results_dir)

    # 배너
    print_consult_banner()

    # 과거 관심사 표시 (축적된 데이터가 있는 경우)
    if collector:
        interests = collector.get_interests()
        if interests:
            print_status_bar("이전 연구 관심사 감지", "magic")
            recent_queries = [
                i["query"] for i in interests[:5] if i.get("query")
            ]
            if recent_queries:
                click.echo(click.style("  최근 관심사: ", dim=True)
                           + click.style(", ".join(recent_queries), fg="cyan"))
                print()

    # LLM 연결 테스트 + 라우터 초기화 (1단계로 통합)
    print_status_bar("LLM 백엔드 연결 중", "info")
    cfg = _load_config()
    llm_providers = cfg.get("llm_providers", {})
    backends_data = llm_providers.get("backends", {})
    ollama_cfg = backends_data.get("ollama", {})
    ollama_url = ollama_cfg.get("url", "http://localhost:11434")

    if not ollama_url:
        legacy = cfg.get("pipeline_config", {}).get("llm_server", {})
        ollama_url = legacy.get("url", "http://localhost:11434")

    # API 연결 테스트 (1회, 빠른 실패)
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(f"{ollama_url}/api/tags")
        if resp.status_code != 200:
            print_status_bar(
                f"Ollama 응답 오류 (HTTP {resp.status_code})", "error"
            )
            click.echo("  Ollama가 정상 실행 중인지 확인하세요: ollama serve\n")
            return
    except (httpx.ConnectError, httpx.ConnectTimeout) as e:
        print_status_bar("Ollama 연결 실패", "error")
        click.echo(f"\n  Ollama 서버({ollama_url})에 연결할 수 없습니다.")
        click.echo(f"  오류: {e}")
        click.echo(f"  확인: {click.style('ollama serve', fg='cyan')}\n")
        return

    print_status_bar("Ollama 연결 OK", "success")

    # 라우터 초기화 (연결 확인됨 — health_check에서 재연결 불필요)
    backends_list, router_config = _create_backends_from_config()
    router = LLMRouter(backends=backends_list, config=router_config)
    await router.start()

    # 선택된 모델 표시
    for b in backends_list:
        if hasattr(b, 'config') and b.config.model:
            model_name = b.config.model
            if model_name not in ("auto", ""):
                print_status_bar(f"모델: {model_name}", "success")
                break
    print_status_bar("상담 준비 완료", "success")
    print()

    # 이전 검색 이력을 가져와서 중복 방지
    past_queries_text = ""
    if collector:
        try:
            interests = collector.get_interests(n_recent=10)
            past_qs = [
                i.get("query", "") or i.get("topic", "")
                for i in interests if i.get("query") or i.get("topic")
            ]
            if past_qs:
                past_queries_text = (
                    "\n\nThe user has previously searched for:\n"
                    + "\n".join(f"- {q}" for q in past_qs[:8])
                    + "\nAvoid suggesting identical queries. Build on their history "
                    "or explore new angles."
                )
        except Exception:
            pass

    system_prompt = f"""You are a bioinformatics research assistant helping a researcher \
define and refine their research question. Guide the conversation:
1. First, understand their broad topic of interest
2. Ask 1-2 clarifying questions (organism, disease, methodology, data type, etc.)
3. When you have enough context, propose exactly 3 SPECIFIC and DISTINCT search queries \
tailored to the user's exact needs. Each query should target a different angle:
   - Query 1: Core topic with specific biological terms (genes, pathways, diseases)
   - Query 2: Methodological focus (sequencing type, analysis method, model organism)
   - Query 3: Translational or novel angle (clinical application, recent advances, \
cross-domain connection)
   Format:
   SEARCH_QUERY_1: "query here"
   SEARCH_QUERY_2: "query here"
   SEARCH_QUERY_3: "query here"

IMPORTANT: Each query must be meaningfully different. Include specific gene names, \
pathway names, disease names, or method names the user mentioned. \
Do NOT generate generic queries like "single cell RNA-seq cancer" — be precise.
{past_queries_text}
Keep responses concise. Respond in the same language the user uses (Korean or English)."""

    conversation_history = []
    search_queries = []

    def _extract_queries(text: str) -> list[str]:
        """응답에서 SEARCH_QUERY 패턴 추출."""
        return re.findall(r'SEARCH_QUERY_\d+:\s*"([^"]+)"', text)

    def _truncate_repetition(text: str, max_repeat: int = 3) -> str:
        """LLM 반복 루프 감지 및 잘라내기.

        같은 구절이 max_repeat회 이상 반복되면 첫 등장까지만 유지.
        """
        # 8~80자 구절이 3회+ 연속 반복되는 패턴 탐지
        match = re.search(
            r'(.{8,80}?)\1{' + str(max_repeat - 1) + r',}',
            text, re.DOTALL,
        )
        if match:
            end = match.start() + len(match.group(1))
            return text[:end].rstrip()
        return text

    # 초기 인사 — 고정 문구로 즉시 표시 (LLM 대기 없음)
    greeting_text = (
        "안녕하세요! 바이오인포매틱스 연구 상담을 시작합니다.\n"
        "    연구하고 싶은 주제를 알려주세요. "
        "예: 질환명, 유전자, 생물학적 경로, 분석 방법 등"
    )
    await reveal_response("🧬 상담사", greeting_text)
    conversation_history.append({
        "role": "assistant", "content": greeting_text,
    })

    click.echo(
        click.style("  종료: ", dim=True)
        + click.style("q", fg="yellow")
        + click.style(" 입력 후 Enter", dim=True)
    )
    print()

    # 이미 쿼리가 추출된 경우 대화 루프 스킵
    if not search_queries:
        # 대화 루프 (최대 10턴)
        max_turns = 10
        for turn in range(max_turns):
            # 빈 입력 시 줄바꿈 없이 프롬프트 유지
            while True:
                user_input = _read_input(fancy_prompt(turn))
                if user_input.strip():
                    break
                # 빈 Enter → 커서를 한 줄 위로 올려서 프롬프트 덮어쓰기
                sys.stdout.write("\033[A\033[2K")
                sys.stdout.flush()
            if user_input.strip().lower() == "q":
                _save_consult_log(
                    conversation_history, search_queries, results_dir,
                )
                print_goodbye()
                await router.stop()
                return

            # 사용자가 숫자만 입력 → 이전 SEARCH_QUERY 선택 시도
            if (
                user_input.strip().isdigit()
                and search_queries
                and 1 <= int(user_input.strip()) <= len(search_queries)
            ):
                break

            conversation_history.append({
                "role": "user", "content": user_input,
            })

            # 3턴 이상 대화했으면 검색 쿼리를 강제 요청
            force_query = ""
            if turn >= 3:
                force_query = (
                    "\n\nIMPORTANT: You have asked enough questions. "
                    "NOW propose exactly 3 search queries using the "
                    "SEARCH_QUERY_1/2/3 format. Do not ask more questions."
                )

            # 대화 이력 포함 프롬프트 구성
            history_text = "\n".join(
                f"{'User' if m['role'] == 'user' else 'Assistant'}: "
                f"{m['content']}"
                for m in conversation_history[-6:]
            )
            prompt = (
                f"Conversation so far:\n{history_text}\n\n"
                f"Respond to the user's latest message.{force_query}"
            )

            try:
                async with AnimatedWait("🧬 상담사 응답 대기 중", category="llm"):
                    response = await router.generate(
                        prompt, system_prompt=system_prompt
                    )
                if response.success:
                    clean = _truncate_repetition(response.content)
                    await reveal_response("🧬 상담사", clean)
                    conversation_history.append({
                        "role": "assistant",
                        "content": clean,
                    })

                    # 자동 RAG 수집: 상담 대화 저장
                    if collector:
                        collector.collect_consult(
                            user_query=user_input,
                            assistant_response=clean,
                        )

                    # SEARCH_QUERY 패턴 감지
                    queries = _extract_queries(response.content)
                    if queries:
                        search_queries = queries
                        break
                else:
                    click.echo(click.style(
                        "  [!] 응답 생성에 실패했습니다.\n", fg="red"
                    ))
            except Exception as e:
                click.echo(click.style(f"  [!] 오류: {e}\n", fg="red"))

    await router.stop()

    # 대화 로그 저장
    _save_consult_log(conversation_history, search_queries, results_dir)

    # 검색 쿼리 선택
    if not search_queries:
        print_status_bar("검색 쿼리가 제안되지 않았습니다", "warn")
        manual = _read_input(
            f"  {click.style('직접 검색어 입력', fg='yellow')}: "
        )
        if manual.strip():
            search_queries = [manual.strip()]
        else:
            return

    if len(search_queries) > 1:
        print()
        print_status_bar("추천 검색 쿼리", "magic")
        print()
        for i, q in enumerate(search_queries, 1):
            color = [(0, 255, 200), (100, 200, 255), (200, 150, 255)][i - 1]
            r, g, b = color
            click.echo(f"  \033[38;2;{r};{g};{b}m{i}. {q}\033[0m")
        print()

        choice = _read_input(f"  {click.style('선택 (번호)', fg='cyan')}: ")
        try:
            chosen_query = search_queries[int(choice.strip()) - 1]
        except (ValueError, IndexError):
            chosen_query = search_queries[0]
    else:
        chosen_query = search_queries[0]

    # 한국어 검색어 → 영어 번역 (PubMed는 영어만 검색 가능)
    chosen_query = await _translate_query_if_korean(chosen_query)

    print()
    print_status_bar(f"검색: {chosen_query}", "info")

    # 검색 실행
    async with AnimatedWait("논문 검색 중", style="molecule"):
        results = await _run_search(chosen_query, limit=20, no_brave=False)

    if not results:
        print_status_bar("검색 결과가 없습니다", "error")
        return

    # 자동 RAG 수집: 상담 후 검색 결과
    if collector:
        collector.collect_search(chosen_query, results)
        collector.collect_papers_from_search(results)

    # 결과 표시 (화려한 테이블)
    print_results_table(results)

    # 선택 & 실행 (오타 시 재입력)
    pmids = _select_papers(results)
    if not pmids:
        print_goodbye()
        return

    # 자동 RAG 수집: 선택한 PMID 기록
    if collector:
        collector.collect_search(chosen_query, results, selected_pmids=pmids)

    print()
    print_status_bar(f"선택: {', '.join(pmids)}", "success")
    if click.confirm(
        click.style("\n  파이프라인을 실행할까요?", fg="cyan", bold=True)
    ):
        cfg_data = _load_config() or {}
        pipeline_config = PipelineConfig.from_dict(cfg_data)
        pipeline_config.pmids = pmids
        pipeline_config.results_dir = Path(results_dir)
        pipeline_config.enable_debate = debate
        pipeline_config.rag_dir = Path(results_dir) / "rag_db"

        pipeline = AsyncPipeline(pipeline_config)

        print()
        print_status_bar("파이프라인 실행 시작", "magic")
        results = await pipeline.run()

        # LLM 실패 감지
        failed = [
            (p, r) for p, r in results.items()
            if r.status == PipelineStatus.FAILED
        ]
        if failed and len(failed) == len(results):
            print_status_bar(
                "파이프라인 실패 — LLM 백엔드 연결 불가", "error"
            )
            for pmid, r in failed:
                click.echo(click.style(
                    f"  ✗ {pmid}: {r.error}", fg="red",
                ))
        elif failed:
            print_status_bar(
                f"파이프라인 부분 완료 — {len(failed)}개 실패", "warn"
            )
            for pmid, r in failed:
                click.echo(click.style(
                    f"  ✗ {pmid}: {r.error}", fg="red",
                ))
        else:
            print_status_bar("파이프라인 실행 완료!", "success")
    else:
        print_goodbye()



_KNOWLEDGE_TYPE_LABELS = {
    "paper_abstract": ("논문", "green"),
    "analysis_result": ("LLM 분석", "blue"),
    "debate_report": ("토론 보고서", "magenta"),
    "search_record": ("검색 기록", "cyan"),
    "consult_exchange": ("상담 대화", "yellow"),
    "enrichment_result": ("경로 분석", "green"),
    "pipeline_run": ("파이프라인", "blue"),
}


@cli.command()
@click.option("--results-dir", "-o", type=click.Path(), default="./results",
              help="결과 저장 디렉토리")
@click.option("--query", "-q", type=str, default=None,
              help="특정 주제로 검색")
@click.option("--delete-type", type=click.Choice([
    "search_record", "consult_exchange", "paper_abstract",
    "analysis_result", "debate_report", "enrichment_result", "pipeline_run",
]), default=None, help="특정 유형의 데이터 전체 삭제")
@click.option("--delete-pmid", type=str, default=None,
              help="특정 PMID 관련 데이터 삭제")
@click.option("--delete-query", type=str, default=None,
              help="주제로 검색 후 선택 삭제")
@click.option("--list-type", type=click.Choice([
    "search_record", "consult_exchange", "paper_abstract",
    "analysis_result", "debate_report", "enrichment_result", "pipeline_run",
]), default=None, help="특정 유형의 데이터 목록 보기")
@click.option("--reset", is_flag=True, default=False,
              help="지식 DB 전체 초기화")
def knowledge(results_dir, query, delete_type, delete_pmid, delete_query,
              list_type, reset):
    """축적된 연구 지식 DB 관리.

    사용할수록 자동으로 쌓이는 개인 맞춤 지식 DB를 확인/검색/삭제합니다.

    \b
    예시:
      bioauto knowledge                              # 전체 통계
      bioauto knowledge -q "암 면역"                  # 관련 지식 검색
      bioauto knowledge --list-type search_record     # 검색 기록 목록
      bioauto knowledge --delete-pmid 12345           # PMID 관련 데이터 삭제
      bioauto knowledge --delete-type search_record   # 검색 기록 전체 삭제
      bioauto knowledge --delete-query "폐암"         # 관련 데이터 검색 후 선택 삭제
      bioauto knowledge --reset                       # 전체 초기화
    """
    collector = _get_collector(results_dir)
    if not collector:
        click.echo(click.style(
            "  RAG 모듈이 설치되지 않았습니다.\n"
            "  설치: pip install chromadb sentence-transformers",
            fg="yellow",
        ))
        return

    # 전체 초기화
    if reset:
        _knowledge_reset(collector, results_dir)
        return

    # 유형별 삭제
    if delete_type:
        _knowledge_delete_type(collector, delete_type)
        return

    # PMID별 삭제
    if delete_pmid:
        _knowledge_delete_pmid(collector, delete_pmid)
        return

    # 검색 후 선택 삭제
    if delete_query:
        _knowledge_delete_by_query(collector, delete_query)
        return

    # 목록 보기
    if list_type:
        _knowledge_list_type(collector, list_type)
        return

    # 기본: 통계 표시
    stats = collector.get_knowledge_stats()
    if not stats or stats.get("count", 0) == 0:
        click.echo()
        click.echo(click.style("  ╭──────────────────────────────────╮", fg="cyan"))
        click.echo(click.style("  │    지식 DB가 비어 있습니다       │", fg="cyan"))
        click.echo(click.style("  ╰──────────────────────────────────╯", fg="cyan"))
        click.echo()
        click.echo("  bioauto를 사용하면 자동으로 지식이 축적됩니다:")
        click.echo(click.style("    bioauto search", fg="cyan") + " \"주제\"  → 논문 검색 기록")
        click.echo(click.style("    bioauto consult", fg="cyan") + "        → 상담 대화 기록")
        click.echo(click.style("    bioauto run", fg="cyan") + " <PMID>    → 분석 결과 축적")
        click.echo()
        return

    # 통계 표시
    click.echo()
    click.echo(click.style("  ╭──────────────────────────────────╮", bold=True))
    click.echo(click.style("  │   ", bold=True)
               + click.style("연구 지식 DB", fg="cyan", bold=True)
               + click.style(f"  ({stats['count']}건)", dim=True)
               + click.style("        │", bold=True))
    click.echo(click.style("  ╰──────────────────────────────────╯", bold=True))
    click.echo()

    for dtype, count in stats.get("doc_types", {}).items():
        if count > 0:
            label, color = _KNOWLEDGE_TYPE_LABELS.get(dtype, (dtype, "white"))
            bar = "█" * min(count, 30)
            click.echo(f"  {click.style(label, fg=color):>20s}  "
                        f"{click.style(bar, fg=color)} {count}")

    click.echo()

    # 관심사 표시
    interests = collector.get_interests()
    if interests:
        click.echo(click.style("  최근 연구 관심사:", bold=True))
        for i in interests[:7]:
            q = i.get("query", "")
            ts = i.get("timestamp", "")[:10]
            click.echo(f"    {click.style(ts, dim=True)}  {q}")
        click.echo()

    # 쿼리 모드
    if query:
        click.echo(click.style(f"  \"{query}\" 관련 지식 검색 중...", fg="cyan"))
        click.echo()
        related = collector.find_related(query, n_results=5)
        if related:
            for doc in related:
                meta = doc.get("metadata", {})
                dtype = meta.get("doc_type", "unknown")
                label, color = _KNOWLEDGE_TYPE_LABELS.get(dtype, (dtype, "white"))
                dist = doc.get("distance", 0.0)
                preview = doc.get("document", "")[:150]
                if len(doc.get("document", "")) > 150:
                    preview += "..."
                click.echo(f"  [{click.style(label, fg=color)}] "
                            f"(유사도: {1 - dist:.2f})")
                click.echo(f"    {preview}")
                click.echo()
        else:
            click.echo("  관련 지식을 찾지 못했습니다.")
        click.echo()

    # 삭제 안내
    click.echo(click.style("  삭제:", dim=True))
    click.echo(click.style(
        "    --delete-query \"키워드\"  검색 후 선택 삭제", dim=True
    ))
    click.echo(click.style(
        "    --delete-pmid PMID      PMID 관련 전체 삭제", dim=True
    ))
    click.echo(click.style(
        "    --delete-type 유형      유형별 전체 삭제", dim=True
    ))
    click.echo()


def _knowledge_reset(collector, results_dir: str) -> None:
    """지식 DB 전체 초기화."""
    import shutil

    stats = collector.get_knowledge_stats()
    count = stats.get("count", 0) if stats else 0

    click.echo()
    click.echo(click.style(
        f"  ⚠ 지식 DB 전체 초기화 ({count}건 삭제)", fg="red", bold=True
    ))
    if not click.confirm(click.style("  정말 삭제하시겠습니까?", fg="red")):
        click.echo("  취소됨.")
        return
    if not click.confirm(click.style("  복구 불가합니다. 확실합니까?", fg="red")):
        click.echo("  취소됨.")
        return

    rag_dir = Path(results_dir) / "rag_db"
    if rag_dir.exists():
        shutil.rmtree(rag_dir)
        click.echo(click.style(f"  ✓ 지식 DB 초기화 완료 ({count}건 삭제됨)", fg="green"))
    else:
        click.echo("  지식 DB 디렉토리가 존재하지 않습니다.")
    click.echo()


def _knowledge_delete_type(collector, doc_type: str) -> None:
    """유형별 전체 삭제."""
    label, color = _KNOWLEDGE_TYPE_LABELS.get(doc_type, (doc_type, "white"))
    click.echo()
    click.echo(click.style(
        f"  '{label}' 유형의 모든 데이터를 삭제합니다.", fg="yellow"
    ))
    if not click.confirm(click.style("  계속하시겠습니까?", fg="yellow")):
        click.echo("  취소됨.")
        return

    deleted = collector.delete_by_type(doc_type)
    click.echo(click.style(f"  ✓ {deleted}건 삭제 완료", fg="green"))
    click.echo()


def _knowledge_delete_pmid(collector, pmid: str) -> None:
    """PMID 관련 데이터 삭제."""
    click.echo()
    click.echo(click.style(
        f"  PMID {pmid} 관련 모든 데이터를 삭제합니다.", fg="yellow"
    ))
    if not click.confirm(click.style("  계속하시겠습니까?", fg="yellow")):
        click.echo("  취소됨.")
        return

    deleted = collector.delete_by_pmid(pmid)
    if deleted > 0:
        click.echo(click.style(f"  ✓ {deleted}건 삭제 완료", fg="green"))
    else:
        click.echo(click.style(f"  PMID {pmid} 관련 데이터가 없습니다.", dim=True))
    click.echo()


def _knowledge_delete_by_query(collector, query: str) -> None:
    """검색 후 선택 삭제."""
    click.echo()
    click.echo(click.style(f"  \"{query}\" 관련 데이터 검색 중...", fg="cyan"))

    related = collector.find_related(query, n_results=10)
    if not related:
        click.echo("  관련 데이터를 찾지 못했습니다.")
        click.echo()
        return

    # 목록 표시
    click.echo()
    for i, doc in enumerate(related, 1):
        meta = doc.get("metadata", {})
        dtype = meta.get("doc_type", "unknown")
        label, color = _KNOWLEDGE_TYPE_LABELS.get(dtype, (dtype, "white"))
        preview = doc.get("document", "")[:100]
        if len(doc.get("document", "")) > 100:
            preview += "..."
        click.echo(f"  {click.style(str(i), fg='cyan', bold=True)}. "
                    f"[{click.style(label, fg=color)}] "
                    f"{click.style(doc['id'], dim=True)}")
        click.echo(f"     {preview}")
    click.echo()

    selection = _read_input(
        f"  {click.style('삭제할 번호', fg='yellow')} "
        f"{click.style('(쉼표 구분, a=전체, q=취소)', dim=True)}: "
    )

    sel = selection.strip().lower()
    if sel == "q" or not sel:
        click.echo("  취소됨.")
        return

    if sel == "a":
        ids_to_delete = [doc["id"] for doc in related]
    else:
        try:
            indices = [int(s.strip()) - 1 for s in sel.split(",")]
            ids_to_delete = [
                related[i]["id"] for i in indices
                if 0 <= i < len(related)
            ]
        except ValueError:
            click.echo(click.style("  잘못된 입력입니다.", fg="red"))
            return

    if not ids_to_delete:
        click.echo("  삭제할 항목이 없습니다.")
        return

    click.echo(click.style(f"  {len(ids_to_delete)}건을 삭제합니다.", fg="yellow"))
    if click.confirm(click.style("  계속하시겠습니까?", fg="yellow")):
        deleted = collector.delete_by_ids(ids_to_delete)
        click.echo(click.style(f"  ✓ {deleted}건 삭제 완료", fg="green"))
    else:
        click.echo("  취소됨.")
    click.echo()


def _knowledge_list_type(collector, doc_type: str) -> None:
    """유형별 데이터 목록 보기."""
    label, color = _KNOWLEDGE_TYPE_LABELS.get(doc_type, (doc_type, "white"))
    docs = collector.list_documents(doc_type=doc_type, limit=30)

    click.echo()
    click.echo(click.style(f"  {label} 목록 ({len(docs)}건)", fg=color, bold=True))
    click.echo()

    if not docs:
        click.echo(click.style("  데이터가 없습니다.", dim=True))
        click.echo()
        return

    for i, doc in enumerate(docs, 1):
        meta = doc.get("metadata", {})
        doc_id = doc.get("id", "")
        preview = doc.get("document", "")[:120]
        if len(doc.get("document", "")) > 120:
            preview += "..."

        # 유형별 핵심 정보 추출
        info_parts = []
        if meta.get("pmid"):
            info_parts.append(f"PMID:{meta['pmid']}")
        if meta.get("query"):
            info_parts.append(f"\"{meta['query']}\"")
        if meta.get("timestamp"):
            info_parts.append(meta["timestamp"][:10])
        if meta.get("rating"):
            info_parts.append(f"Rating:{meta['rating']}")

        info_str = " | ".join(info_parts) if info_parts else doc_id

        click.echo(f"  {click.style(str(i), bold=True):>4s}. "
                    f"{click.style(info_str, fg=color)}")
        click.echo(f"       {click.style(preview, dim=True)}")
    click.echo()


@cli.command()
@click.option("--results-dir", "-o", type=click.Path(), default="./results",
              help="결과 저장 디렉토리")
@click.option("--severity", "-s", type=click.Choice(["CRITICAL", "ERROR", "WARNING", "INFO"]),
              default=None, help="심각도 필터")
@click.option("--stage", type=str, default=None, help="스테이지 필터")
@click.option("--pmid", type=str, default=None, help="PMID 필터")
@click.option("--clear", is_flag=True, default=False, help="에러 기록 전체 삭제")
@click.option("--limit", "-n", type=int, default=20, help="표시할 최대 에러 수")
def errors(results_dir, severity, stage, pmid, clear, limit):
    """에러 기록 조회 및 관리.

    파이프라인 실행 중 발생한 에러를 구조화된 형태로 확인합니다.

    \b
    예시:
      bioauto errors                      # 최근 에러 목록
      bioauto errors -s ERROR             # ERROR 등급만
      bioauto errors --stage debate       # debate 단계만
      bioauto errors --pmid 12345         # 특정 PMID만
      bioauto errors --clear              # 에러 기록 삭제
    """
    from core.error_tracker import get_tracker

    tracker = get_tracker(results_dir)

    if clear:
        if click.confirm(click.style("  에러 기록을 모두 삭제합니까?", fg="yellow")):
            count = tracker.clear()
            click.echo(click.style(f"  ✓ {count}건 삭제 완료", fg="green"))
        else:
            click.echo("  취소됨.")
        return

    # 요약 표시
    summary = tracker.get_summary()
    if summary["total"] == 0:
        click.echo()
        click.echo(click.style("  ✓ 기록된 에러가 없습니다.", fg="green"))
        click.echo()
        return

    click.echo()
    click.echo(click.style(f"  에러 기록 (총 {summary['total']}건)", bold=True))
    click.echo()

    # 심각도별 통계
    severity_colors = {
        "CRITICAL": "red", "ERROR": "red",
        "WARNING": "yellow", "INFO": "cyan",
    }
    for sev, count in sorted(summary["by_severity"].items(),
                              key=lambda x: {"CRITICAL": 0, "ERROR": 1, "WARNING": 2, "INFO": 3}.get(x[0], 9)):
        color = severity_colors.get(sev, "white")
        bar = "█" * min(count, 30)
        click.echo(f"    {click.style(sev, fg=color):>15s}  {click.style(bar, fg=color)} {count}")

    click.echo()

    # 스테이지별 통계
    click.echo(click.style("  스테이지별:", dim=True))
    for stg, count in sorted(summary["by_stage"].items(), key=lambda x: -x[1]):
        click.echo(f"    {stg:>20s}  {count}건")

    click.echo()

    # 필터된 에러 목록
    error_list = tracker.get_errors(
        severity=severity, stage=stage, pmid=pmid, limit=limit
    )

    if not error_list:
        click.echo(click.style("  필터에 맞는 에러가 없습니다.", dim=True))
        return

    click.echo(click.style(f"  최근 에러 ({len(error_list)}건):", bold=True))
    click.echo()

    for i, err in enumerate(reversed(error_list[-limit:]), 1):
        ts = err.get("timestamp", "")[:19]
        sev = err.get("severity", "?")
        stg = err.get("stage", "?")
        msg = err.get("message", "")[:100]
        err_pmid = err.get("pmid", "")
        err_type = err.get("error_type", "")
        color = severity_colors.get(sev, "white")

        click.echo(
            f"  {click.style(str(i), dim=True):>4s}. "
            f"{click.style(ts, dim=True)} "
            f"[{click.style(sev, fg=color)}] "
            f"{click.style(stg, fg='cyan')}"
            + (f" PMID:{err_pmid}" if err_pmid else "")
        )
        click.echo(f"       {click.style(err_type, fg=color)}: {msg}")
        click.echo()


@cli.command()
@click.argument("pmids", nargs=-1, required=True)
@click.option("--results-dir", "-o", type=click.Path(), default="./results",
              help="결과 저장 디렉토리")
@click.option("--config", "-c", type=click.Path(exists=True), default=None,
              help="설정 파일 경로 (config.json)")
@click.option("--debate/--no-debate", default=True,
              help="멀티 에이전트 토론 활성화")
@click.option("--enrichment/--no-enrichment", default=True,
              help="농축 분석 활성화")
@click.option("--aggregate/--no-aggregate", default=True,
              help="데이터 소스 통합 활성화")
@click.option("--debate-rounds", type=int, default=3,
              help="토론 라운드 수")
@click.option("--project", "-p", type=str, default=None,
              help="프로젝트명")
def tui(pmids, results_dir, config, debate, enrichment, aggregate,
        debate_rounds, project):
    """TUI 대시보드로 파이프라인을 실행합니다.

    실시간 진행 상황을 터미널 UI로 모니터링합니다.

    예시: bioauto tui 33564749 32416070
    """
    try:
        from tui.app import run_tui
    except ImportError:
        click.echo(click.style(
            "textual 패키지가 필요합니다: pip install textual", fg="red"
        ))
        return

    # config.json 로드
    config_path = config or None
    if config_path:
        with open(config_path) as f:
            cfg_data = json.load(f)
    else:
        cfg_data = _load_config()

    # CLI 옵션 오버라이드
    cfg_data["_cli_overrides"] = {
        "pmids": list(pmids),
        "results_dir": results_dir,
        "enable_debate": debate,
        "enable_enrichment": enrichment,
        "enable_data_aggregation": aggregate,
        "debate_rounds": debate_rounds,
        "project_slug": project,
    }

    click.echo("=== BioAuto TUI Dashboard ===")
    click.echo(f"PMIDs: {', '.join(pmids)}")
    click.echo("Starting TUI...\n")

    run_tui(
        pmids=list(pmids),
        results_dir=results_dir,
        config_data=cfg_data,
    )


def _get_pidfile(service: str = "web") -> Path:
    """서비스별 PID 파일 경로 반환"""
    return Path.home() / ".bioauto" / f"{service}.pid"


def _find_service_pids(service: str) -> list[int]:
    """특정 서비스의 실행 중인 PID 목록 반환"""
    import subprocess

    pids = []
    pidfile = _get_pidfile(service)

    # 1) PID 파일에서 읽기
    if pidfile.exists():
        try:
            pid = int(pidfile.read_text().strip())
            os.kill(pid, 0)  # 프로세스 존재 확인
            pids.append(pid)
        except (ValueError, ProcessLookupError, PermissionError):
            pidfile.unlink(missing_ok=True)

    # 2) pgrep으로 추가 탐지 (PID 파일 없이 실행된 경우)
    patterns = {
        "web": ["uvicorn.*web\\.app", "bioauto.*web"],
        "pipeline": ["bioauto.*run"],
    }
    my_pid = os.getpid()
    for pattern in patterns.get(service, [f"bioauto.*{service}"]):
        try:
            result = subprocess.run(
                ["pgrep", "-f", pattern],
                capture_output=True, text=True, timeout=5,
            )
            for line in result.stdout.strip().splitlines():
                if not line.strip():
                    continue
                pid = int(line.strip())
                if pid != my_pid and pid not in pids:
                    try:
                        os.kill(pid, 0)
                        pids.append(pid)
                    except (ProcessLookupError, PermissionError):
                        pass
        except Exception:
            pass

    return pids


def _find_all_pids() -> dict[str, list[int]]:
    """모든 bioauto 서비스의 PID를 반환"""
    result = {}
    for service in ["web", "pipeline"]:
        pids = _find_service_pids(service)
        if pids:
            result[service] = pids
    return result


@cli.command()
@click.option("--json", "json_out", is_flag=True, help="JSON 형식으로 결과 출력")
def doctor(json_out):
    """플랫폼 환경, 런타임, 의존성 및 백엔드 상태를 진단합니다."""
    import shutil
    import subprocess
    import sys

    diagnostics = {}

    # Python
    py_ver = f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"
    diagnostics["python"] = {"version": py_ver, "status": "ok" if sys.version_info >= (3, 10) else "warn"}

    # Java (requires 17+)
    java_bin = shutil.which("java")
    if java_bin:
        try:
            res = subprocess.run([java_bin, "-version"], capture_output=True, text=True, timeout=5)
            out = res.stderr or res.stdout
            first_line = out.splitlines()[0] if out else "java"
            diagnostics["java"] = {"binary": java_bin, "info": first_line, "status": "ok"}
        except Exception as e:
            diagnostics["java"] = {"binary": java_bin, "info": str(e), "status": "warn"}
    else:
        diagnostics["java"] = {"binary": None, "info": "java not found (Nextflow requires Java 17+)", "status": "missing"}

    # Nextflow
    nf_bin = shutil.which("nextflow")
    if nf_bin:
        diagnostics["nextflow"] = {"binary": nf_bin, "status": "ok"}
    else:
        diagnostics["nextflow"] = {"binary": None, "status": "missing"}

    # Container runtime
    containers = [c for c in ["docker", "singularity", "apptainer", "podman"] if shutil.which(c)]
    diagnostics["container_runtimes"] = containers

    # Environment Secrets (Redacted)
    keys_check = {}
    for key_name in ["OPENAI_API_KEY", "ANTHROPIC_API_KEY", "SEMANTIC_SCHOLAR_API_KEY", "NCBI_API_KEY"]:
        val = os.environ.get(key_name)
        if val:
            keys_check[key_name] = f"{val[:4]}...***(redacted)"
        else:
            keys_check[key_name] = "not_set"
    diagnostics["environment_keys"] = keys_check

    if json_out:
        click.echo(json.dumps(diagnostics, indent=2, ensure_ascii=False))
        return

    click.echo("=== BioAuto Platform Diagnostics (Doctor) ===")
    click.echo(f"Python: {diagnostics['python']['version']} ({diagnostics['python']['status'].upper()})")
    click.echo(f"Java: {diagnostics['java']['info']} ({diagnostics['java']['status'].upper()})")
    click.echo(f"Nextflow: {diagnostics['nextflow']['binary'] or 'Not installed'} ({diagnostics['nextflow']['status'].upper()})")
    click.echo(f"Containers: {', '.join(containers) if containers else 'None'}")
    click.echo("\nEnvironment Keys:")
    for k, v in keys_check.items():
        click.echo(f"  {k}: {v}")
    click.echo("=============================================")


@cli.command()
@click.option("--host", default="127.0.0.1", help="서버 호스트 (기본값: 127.0.0.1)")
@click.option("--port", default=8888, type=int, help="서버 포트")
@click.option("--results-dir", "-o", type=click.Path(), multiple=True,
              help="결과 저장 디렉토리 (여러 개 지정 가능)")
@click.option("--allow-remote", is_flag=True, help="외부 네트워크 바인딩(0.0.0.0 등) 허용")
@click.option("--server-token", help="원격 바인딩 시 인증 토큰 (미지정 시 자동 생성)")
def web(host, port, results_dir, allow_remote, server_token):
    """웹 대시보드 서버를 시작합니다.

    브라우저에서 http://host:port 로 접근하여 파이프라인을 모니터링합니다.

    여러 results 디렉토리를 동시에 모니터링:
      bioauto web -o ./proj_A/results -o ./proj_B/results

    예시: bioauto web --port 8080
    종료: bioauto stop
    """
    is_loopback = host in ("127.0.0.1", "localhost", "::1")
    if not is_loopback and not allow_remote:
        click.echo(click.style(
            f"[ERROR] Security Guard: Binding to non-loopback host '{host}' requires explicit '--allow-remote' flag.",
            fg="red",
        ))
        return

    if not is_loopback and allow_remote and not server_token:
        import secrets
        server_token = secrets.token_hex(16)
        click.echo(click.style(
            f"[WARNING] Remote binding enabled on host '{host}'. State-changing APIs require 'X-Server-Token' header.",
            fg="yellow",
        ))
        click.echo(f"Generated Server Token: {server_token}\n")

    try:
        import uvicorn

        from web.app import create_app
    except ImportError as e:
        click.echo(click.style(
            f"웹 UI 패키지가 필요합니다: pip install fastapi uvicorn sse-starlette\n{e}",
            fg="red",
        ))
        return

    # 기본값: -o 미지정 시 ./results
    dirs = list(results_dir) if results_dir else ["./results"]

    # PID 파일 기록
    pidfile = _get_pidfile("web")
    pidfile.parent.mkdir(parents=True, exist_ok=True)
    pidfile.write_text(str(os.getpid()))

    click.echo("=== BioAuto Web Dashboard ===")
    click.echo(f"Server: http://{host}:{port}")
    click.echo(f"Results: {', '.join(dirs)}")
    click.echo("Stop: bioauto stop web  /  bioauto stop  /  Ctrl+C\n")

    try:
        app = create_app(results_dirs=dirs, server_token=server_token)
        uvicorn.run(app, host=host, port=port)
    finally:
        pidfile.unlink(missing_ok=True)


@cli.command()
@click.argument("service", required=False, default=None)
def stop(service):
    """실행 중인 bioauto 서비스를 종료합니다.

    SERVICE를 지정하면 해당 서비스만, 생략하면 모든 서비스를 종료합니다.

    \b
    서비스 목록:
      web       웹 대시보드 서버
      pipeline  실행 중인 파이프라인

    \b
    예시:
      bioauto stop          # 모든 서비스 종료
      bioauto stop web      # 웹 서버만 종료
      bioauto stop pipeline # 파이프라인만 종료
    """
    import signal

    known_services = ["web", "pipeline"]

    if service and service not in known_services:
        click.echo(
            f"  {click.style('!', fg='yellow')}"
            f" 알 수 없는 서비스: {service}"
        )
        click.echo(f"  사용 가능: {', '.join(known_services)}")
        return

    if service:
        # 특정 서비스만 종료
        services = {service: _find_service_pids(service)}
    else:
        # 전체 종료
        services = _find_all_pids()

    if not any(services.values()):
        if service:
            click.echo(f"  실행 중인 {service} 서비스가 없습니다.")
        else:
            click.echo("  실행 중인 bioauto 서비스가 없습니다.")
        return

    for svc_name, pids in services.items():
        for pid in pids:
            try:
                os.kill(pid, signal.SIGTERM)
                click.echo(
                    f"  {click.style('✓', fg='green')}"
                    f" {svc_name} 종료: PID {pid}"
                )
            except ProcessLookupError:
                click.echo(f"  {svc_name} PID {pid} 이미 종료됨")
            except PermissionError:
                click.echo(
                    f"  {click.style('!', fg='yellow')}"
                    f" {svc_name} PID {pid} 종료 권한 없음 (sudo kill {pid})"
                )
        # PID 파일 정리
        _get_pidfile(svc_name).unlink(missing_ok=True)


@cli.command()
def uninstall():
    """bioauto를 완전히 제거합니다.

    install.sh 설치, pip editable 설치 모두 대응합니다.
    실행 중인 bioauto 프로세스(웹 서버 등)도 종료합니다.
    소스 코드, 결과 데이터(results/), 설정 파일(config.json)은 보존됩니다.

    예시: bioauto uninstall
    """
    import os
    import shutil
    import signal
    import subprocess

    home = Path.home()
    install_dir = Path(os.environ.get("BIOAUTO_HOME", home / ".bioauto"))
    bin_dir = Path(os.environ.get("BIOAUTO_BIN", home / ".local" / "bin"))
    wrapper = bin_dir / "bioauto"

    click.echo("")
    click.echo(click.style("  ┌──────────────────────────────────┐", bold=True))
    click.echo(click.style("  │      ", bold=True) +
               click.style("bioauto", fg="cyan", bold=True) +
               click.style(" uninstaller          │", bold=True))
    click.echo(click.style("  └──────────────────────────────────┘", bold=True))
    click.echo("")

    # ── 실행 중인 bioauto 프로세스 탐지 ──
    all_services = _find_all_pids()
    running_pids = []
    for pids in all_services.values():
        running_pids.extend(p for p in pids if p not in running_pids)

    # ── pip editable 설치 감지 ──
    pip_installed = False
    pip_editable = False
    try:
        result = subprocess.run(
            [sys.executable, "-m", "pip", "show", "bioauto"],
            capture_output=True, text=True, timeout=10,
        )
        if result.returncode == 0:
            pip_installed = True
            output = result.stdout.lower()
            if "editable" in output or "editable" in result.stdout:
                pip_editable = True
            # Location에 site-packages가 아닌 경로면 editable
            for show_line in result.stdout.splitlines():
                if show_line.startswith("Editable project location"):
                    pip_editable = True
                    break
    except Exception:
        pass

    # ── 삭제 대상 표시 ──
    targets = []

    if running_pids:
        targets.append((
            "실행 중인 프로세스",
            f"PID {', '.join(str(p) for p in running_pids)}",
            f"{len(running_pids)}개",
        ))

    if pip_installed:
        label = "pip editable 설치" if pip_editable else "pip 설치"
        targets.append((label, "bioauto 패키지", "pip uninstall"))

    if install_dir.exists():
        try:
            venv_size = sum(
                f.stat().st_size for f in install_dir.rglob("*") if f.is_file()
            )
            size_str = f"{venv_size / (1024 * 1024):.0f} MB"
        except Exception:
            size_str = "? MB"
        targets.append(("가상환경 + 캐시", str(install_dir), size_str))

    if wrapper.exists():
        targets.append(("실행 파일", str(wrapper), "< 1 KB"))

    # egg-info 디렉토리
    egg_info = None
    project_dir = Path(__file__).parent.parent
    for candidate in project_dir.glob("bioauto.egg-info"):
        if candidate.is_dir():
            egg_info = candidate
            break
    if egg_info:
        targets.append(("egg-info", str(egg_info), "메타데이터"))

    # shell rc에 추가된 PATH 라인
    rc_files_with_bioauto = []
    for rc_name in [".bashrc", ".zshrc", ".profile"]:
        rc_path = home / rc_name
        if rc_path.exists():
            try:
                content = rc_path.read_text()
                if "# bioauto" in content or ".bioauto" in content:
                    rc_files_with_bioauto.append(rc_path)
            except Exception:
                pass
    if rc_files_with_bioauto:
        rc_names = ", ".join(f.name for f in rc_files_with_bioauto)
        targets.append(("PATH 설정", rc_names, "shell rc"))

    if not targets:
        click.echo("  bioauto 설치를 찾을 수 없습니다.")
        return

    click.echo(click.style("  삭제 대상:", bold=True))
    for label, path, size in targets:
        click.echo(f"    {click.style('•', fg='red')} {label}: {path} ({size})")

    click.echo("")
    click.echo(click.style("  보존 항목:", bold=True))
    click.echo(f"    {click.style('•', fg='green')} 분석 결과: results/ 폴더 (그대로 유지)")
    click.echo(f"    {click.style('•', fg='green')} 설정 파일: config.json (그대로 유지)")
    click.echo(f"    {click.style('•', fg='green')} 소스 코드: 프로젝트 디렉토리 (그대로 유지)")
    click.echo("")

    # 1차 확인
    if not click.confirm(click.style(
        "  bioauto를 제거하시겠습니까?", fg="yellow", bold=True
    )):
        click.echo("  취소되었습니다.")
        return

    # 2차 확인
    if not click.confirm(click.style(
        "  정말로 제거합니까? 이 작업은 되돌릴 수 없습니다", fg="red", bold=True
    )):
        click.echo("  취소되었습니다.")
        return

    click.echo("")

    # 1) 실행 중인 프로세스 종료
    for svc_name, pids in all_services.items():
        for pid in pids:
            try:
                os.kill(pid, signal.SIGTERM)
                click.echo(
                    f"  {click.style('✓', fg='green')}"
                    f" {svc_name} 종료: PID {pid}"
                )
            except ProcessLookupError:
                pass
            except PermissionError:
                click.echo(
                    f"  {click.style('!', fg='yellow')}"
                    f" {svc_name} PID {pid} 종료 권한 없음 (sudo kill 필요)"
                )
        _get_pidfile(svc_name).unlink(missing_ok=True)

    # 2) pip uninstall (editable 및 일반 설치 모두)
    if pip_installed:
        try:
            pip_cmd = [
                sys.executable, "-m", "pip", "uninstall", "-y", "bioauto",
            ]
            # PEP 668: externally-managed-environment 대응
            test_result = subprocess.run(
                [sys.executable, "-m", "pip", "install", "--dry-run", "pip"],
                capture_output=True, text=True, timeout=10,
            )
            if "externally-managed-environment" in test_result.stderr:
                pip_cmd.insert(4, "--break-system-packages")
            subprocess.run(
                pip_cmd, capture_output=True, text=True, timeout=30,
            )
            click.echo(
                f"  {click.style('✓', fg='green')} pip uninstall bioauto 완료"
            )
        except Exception as e:
            click.echo(
                f"  {click.style('!', fg='yellow')} pip uninstall 실패: {e}"
            )

    # 3) egg-info 제거
    if egg_info and egg_info.exists():
        try:
            shutil.rmtree(egg_info)
            click.echo(
                f"  {click.style('✓', fg='green')} egg-info 제거: {egg_info}"
            )
        except Exception as e:
            click.echo(
                f"  {click.style('!', fg='yellow')} egg-info 제거 실패: {e}"
            )

    # 3.5) site-packages 잔여물 정리 (editable 설치 링크 파일)
    try:
        site_packages = Path(subprocess.run(
            [sys.executable, "-c",
             "import site; print(site.getsitepackages()[0])"],
            capture_output=True, text=True, timeout=5,
        ).stdout.strip())
        if site_packages.is_dir():
            remnants = (
                list(site_packages.glob("bioauto.egg-link"))
                + list(site_packages.glob("__editable__.bioauto-*.pth"))
                + list(site_packages.glob("bioauto-*.dist-info"))
            )
            for remnant in remnants:
                try:
                    if remnant.is_dir():
                        shutil.rmtree(remnant)
                    else:
                        remnant.unlink()
                    click.echo(
                        f"  {click.style('✓', fg='green')}"
                        f" 잔여물 제거: {remnant.name}"
                    )
                except Exception as e:
                    click.echo(
                        f"  {click.style('!', fg='yellow')}"
                        f" {remnant.name} 제거 실패: {e}"
                    )
    except Exception:
        pass

    # 4) shell rc에서 bioauto PATH 라인 제거
    for rc_path in rc_files_with_bioauto:
        try:
            lines = rc_path.read_text().splitlines()
            cleaned = []
            skip_next = False
            for line in lines:
                if skip_next:
                    skip_next = False
                    continue
                if line.strip() == "# bioauto":
                    skip_next = True  # 다음 줄(export PATH=...)도 스킵
                    continue
                cleaned.append(line)
            while cleaned and cleaned[-1] == "":
                cleaned.pop()
            cleaned.append("")  # 파일 끝 개행
            rc_path.write_text("\n".join(cleaned))
            click.echo(
                f"  {click.style('✓', fg='green')} PATH 제거: {rc_path.name}"
            )
        except Exception as e:
            click.echo(
                f"  {click.style('!', fg='yellow')} {rc_path.name} 수정 실패: {e}"
            )

    # 5) 래퍼 스크립트 제거
    if wrapper.exists():
        try:
            wrapper.unlink()
            click.echo(
                f"  {click.style('✓', fg='green')} 실행 파일 제거: {wrapper}"
            )
        except Exception as e:
            click.echo(
                f"  {click.style('!', fg='yellow')} 실행 파일 제거 실패: {e}"
            )

    # 6) 설치 디렉토리 제거 (~/.bioauto)
    if install_dir.exists():
        try:
            shutil.rmtree(install_dir)
            click.echo(
                f"  {click.style('✓', fg='green')} 설치 디렉토리 제거: {install_dir}"
            )
        except Exception as e:
            click.echo(
                f"  {click.style('!', fg='yellow')} 설치 디렉토리 제거 실패: {e}"
            )

    click.echo("")
    click.echo(click.style("  제거 완료!", fg="green", bold=True))
    click.echo("  소스 코드, 분석 결과(results/), 설정(config.json)은 보존되어 있습니다.")
    click.echo("  재설치: pip install -e . 또는 bash install.sh")
    click.echo("")


@cli.command()
@click.option("--config", "-c", type=click.Path(), default=None,
              help="설정 파일 경로 (기본: ./config.json)")
def setup(config):
    """대화형 TUI 설정 마법사를 실행합니다.

    처음 사용자를 위한 초기 설정을 단계별로 안내합니다.

    예시: bioauto setup
    예시: bioauto setup -c /path/to/config.json
    """
    try:
        from tui.setup_wizard import run_setup_wizard
    except ImportError:
        click.echo(click.style(
            "textual 패키지가 필요합니다: pip install textual", fg="red"
        ))
        return

    config_path = Path(config) if config else None
    click.echo("=== BioAuto Setup Wizard ===")
    click.echo("Starting setup wizard...\n")
    run_setup_wizard(config_path=config_path)


@cli.command()
@click.argument("pmids", nargs=-1)
@click.option(
    "--results-dir", default="./results", help="결과 디렉토리 (기본: ./results)"
)
@click.option("--all", "gen_all", is_flag=True, help="모든 final_report에서 생성")
def report(pmids, results_dir, gen_all):
    """기존 분석 결과에서 HTML 리포트 생성.

    결과 구조: results/{PMID}/report_{PMID}.html (개별)
              results/project_report.html (종합, 2+ PMID)

    예시:
      bioauto report 31061532              # 단일 PMID
      bioauto report 31061532 37711782     # 복수 PMID → 개별 + 종합
      bioauto report --all                 # 모든 결과 → 개별 + 종합
    """
    from core.report_generator import ReportGenerator

    results_path = Path(results_dir)
    gen = ReportGenerator()

    # PMID 서브폴더 구조: results/{PMID}/final_report_{PMID}.json
    if gen_all:
        json_files = sorted(results_path.glob("*/final_report_*.json"))
        if not json_files:
            json_files = sorted(results_path.glob("final_report_*.json"))
    elif pmids:
        json_files = []
        for p in pmids:
            # 서브폴더 우선
            sub = results_path / p / f"final_report_{p}.json"
            flat = results_path / f"final_report_{p}.json"
            json_files.append(sub if sub.exists() else flat)
    else:
        click.echo("PMID를 지정하거나 --all 옵션을 사용하세요.")
        return

    reports = []
    for jf in json_files:
        if not jf.exists():
            click.echo(f"  [SKIP] {jf.name} not found")
            continue

        try:
            out_dir = jf.parent
            html_path = gen.generate_from_json(jf, out_dir)
            click.echo(f"  [OK] {html_path}")
            with open(jf) as f:
                reports.append(json.load(f))
        except Exception as e:
            click.echo(f"  [FAIL] {jf.name}: {e}")

    # 2개 이상이면 종합보고서 생성
    if len(reports) >= 2:
        project_meta = {
            "name": "Analysis",
            "description": f"{len(reports)} PMIDs 종합 분석",
            "keywords": [],
            "pmids": [r.get("pmid", "") for r in reports],
            "created_at": "",
        }
        proj_path = results_path / "project_report.html"
        gen.generate_project_report(project_meta, reports, proj_path)
        click.echo(f"  [OK] {proj_path} (종합보고서)")

    click.echo(f"\nTotal: {len(reports)} report(s) generated")


if __name__ == "__main__":
    cli()
