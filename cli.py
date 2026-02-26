#!/usr/bin/env python3
"""
CLI Entry Point - Bioinformatics Research Automation Platform
바이오인포매틱스 연구 자동화 플랫폼 CLI
"""

import asyncio
import json
import sys
from pathlib import Path
from typing import Optional

try:
    import click
except ImportError:
    print("click 패키지가 필요합니다: pip install click")
    sys.exit(1)

from async_pipeline import AsyncPipeline, PipelineConfig, PipelineStatus


@click.group()
@click.version_option(version="3.0.0", prog_name="bioauto")
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
def run(pmids, results_dir, max_concurrent, config, debate, enrichment,
        aggregate, resume, debate_rounds):
    """주어진 PMID에 대해 전체 파이프라인을 실행합니다.

    예시: bioauto run 40315330 32416070
    """
    if config:
        pipeline_config = PipelineConfig.from_json(config)
        pipeline_config.pmids = list(pmids) or pipeline_config.pmids
    else:
        pipeline_config = PipelineConfig(
            pmids=list(pmids),
            results_dir=Path(results_dir),
            max_concurrent=max_concurrent,
            enable_resume=resume,
            enable_data_aggregation=aggregate,
            enable_enrichment=enrichment,
            enable_debate=debate,
            debate_rounds=debate_rounds,
        )

    click.echo(f"=== Bioinformatics Research Automation Platform ===")
    click.echo(f"PMIDs: {', '.join(pipeline_config.pmids)}")
    click.echo(f"Results: {pipeline_config.results_dir}")
    click.echo(f"Debate: {'ON' if debate else 'OFF'} ({debate_rounds} rounds)")
    click.echo(f"Enrichment: {'ON' if enrichment else 'OFF'}")
    click.echo(f"Data Aggregation: {'ON' if aggregate else 'OFF'}")
    click.echo(f"Resume: {'ON' if resume else 'OFF'}")
    click.echo()

    pipeline = AsyncPipeline(pipeline_config)
    results = asyncio.run(pipeline.run())

    # 결과 출력
    click.echo(f"\n{'='*60}")
    click.echo("RESULTS")
    click.echo(f"{'='*60}")

    for pmid, result in results.items():
        status_color = {
            PipelineStatus.COMPLETED: "green",
            PipelineStatus.FAILED: "red",
            PipelineStatus.PARTIAL: "yellow",
        }.get(result.status, "white")

        click.echo(click.style(
            f"\nPMID {pmid}: {result.status.value} ({result.duration_seconds:.1f}s)",
            fg=status_color, bold=True
        ))

        if result.sequencing_result:
            click.echo(f"  Sequencing: {result.sequencing_result.get('sequencing_type', '?')} "
                       f"(confidence: {result.sequencing_result.get('confidence', 0):.2f})")

        if result.llm_analysis:
            click.echo(f"  LLM Rating: {result.llm_analysis.get('consistency_rating', '?')}")
            consensus = result.llm_analysis.get("consensus", {})
            if consensus:
                click.echo(f"  Consensus: {consensus.get('num_backends', 0)} backends")

        if result.debate_report and result.debate_report.get("overall_verdict"):
            verdict = result.debate_report["overall_verdict"]
            verdict_color = {"PASS": "green", "WARN": "yellow", "FAIL": "red"}.get(verdict, "white")
            click.echo(click.style(
                f"  Debate Verdict: {verdict} (score: {result.debate_report.get('overall_score', 0):.2f})",
                fg=verdict_color
            ))

        if result.error:
            click.echo(click.style(f"  Error: {result.error}", fg="red"))


@cli.command()
@click.option("--results-dir", "-o", type=click.Path(exists=True), default="./results")
@click.option("--format", "-f", "fmt", type=click.Choice(["table", "json"]), default="table")
def status(results_dir, fmt):
    """파이프라인 실행 상태를 확인합니다."""
    results_path = Path(results_dir)
    summary_file = results_path / "execution_summary.json"
    progress_file = results_path / "progress.json"

    if summary_file.exists():
        with open(summary_file, "r") as f:
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
        with open(progress_file, "r") as f:
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
    click.echo("=== LLM Backend Status ===\n")

    # Ollama
    click.echo("1. Ollama (DeepSeek-Coder)")
    try:
        import httpx
        resp = httpx.get("http://localhost:11434/api/tags", timeout=5)
        if resp.status_code == 200:
            models = resp.json().get("models", [])
            model_names = [m.get("name", "") for m in models]
            click.echo(click.style("   Status: HEALTHY", fg="green"))
            click.echo(f"   Models: {', '.join(model_names[:5])}")
        else:
            click.echo(click.style("   Status: UNHEALTHY", fg="red"))
    except Exception:
        click.echo(click.style("   Status: UNREACHABLE", fg="red"))

    # OpenAI
    click.echo("\n2. OpenAI (GPT-4)")
    if os.environ.get("OPENAI_API_KEY"):
        click.echo(click.style("   Status: API key configured", fg="green"))
    else:
        click.echo(click.style("   Status: No API key (OPENAI_API_KEY)", fg="yellow"))

    # Anthropic
    click.echo("\n3. Anthropic (Claude)")
    if os.environ.get("ANTHROPIC_API_KEY"):
        click.echo(click.style("   Status: API key configured", fg="green"))
    else:
        click.echo(click.style("   Status: No API key (ANTHROPIC_API_KEY)", fg="yellow"))


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


if __name__ == "__main__":
    cli()
