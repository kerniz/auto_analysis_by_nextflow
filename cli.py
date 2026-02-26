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
    click.echo(f"=== Topic Search: '{query}' ===\n")

    results = asyncio.run(_run_search(query, limit, no_brave))

    if not results:
        click.echo("검색 결과가 없습니다.")
        return

    # 결과 표시
    click.echo(f"  {'#':>3}  {'PMID':>10}  {'Year':>5}  {'Cited':>6}  {'Sources':20}  Title")
    click.echo(f"  {'─'*3}  {'─'*10}  {'─'*5}  {'─'*6}  {'─'*20}  {'─'*40}")
    for i, r in enumerate(results, 1):
        pmid_str = r.pmid or "N/A"
        year_str = str(r.year) if r.year else "?"
        sources_str = ",".join(r.sources)
        title_str = r.title[:55] + "..." if len(r.title) > 55 else r.title
        score_bar = "█" * int(r.relevance_score * 10)
        click.echo(
            f"  {i:3d}  {pmid_str:>10}  {year_str:>5}  {r.citation_count:6d}  "
            f"{sources_str:20}  {title_str}"
        )

    click.echo(f"\n총 {len(results)}건")

    # 사용자 선택
    selection = click.prompt(
        "\n파이프라인 실행할 논문 번호 선택 (쉼표 구분, 예: 1,3,5, 'q'=종료)",
        default="q",
    )

    if selection.strip().lower() == "q":
        click.echo("종료합니다.")
        return

    try:
        indices = [int(s.strip()) - 1 for s in selection.split(",")]
        selected = [results[i] for i in indices if 0 <= i < len(results)]
    except (ValueError, IndexError):
        click.echo("잘못된 입력입니다.")
        return

    pmids = [r.pmid for r in selected if r.pmid]
    if not pmids:
        click.echo("PMID가 있는 논문이 없습니다.")
        return

    click.echo(f"\n선택된 PMID: {', '.join(pmids)}")

    if auto_run or click.confirm("파이프라인을 실행할까요?"):
        pipeline_config = PipelineConfig(
            pmids=pmids,
            results_dir=Path(results_dir),
            enable_debate=debate,
            rag_dir=Path(results_dir) / "rag_db",
        )
        pipeline = AsyncPipeline(pipeline_config)
        asyncio.run(pipeline.run())
        click.echo("파이프라인 실행 완료!")


async def _run_search(query: str, limit: int, no_brave: bool):
    """검색 실행 헬퍼"""
    from search import TopicSearcher, ResultRanker
    from clients.semantic_scholar_client import SemanticScholarClient
    from clients.europe_pmc_client import EuropePMCClient
    from pubmed_client import PubMedClient

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
    click.echo("=== 바이오인포매틱스 연구 상담 모드 ===\n")
    asyncio.run(_run_consult(results_dir, debate))


async def _run_consult(results_dir: str, debate: bool):
    """상담 모드 실행"""
    import os
    from backends import LLMRouter, OllamaBackend, LLMConfig
    from backends.router import RouterConfig

    # LLM 라우터 초기화 (경량)
    backends_list = []
    ollama_config = LLMConfig(model="deepseek-coder:33b", timeout=60)
    backends_list.append(OllamaBackend(
        base_url="http://localhost:11434", config=ollama_config
    ))

    if os.environ.get("OPENAI_API_KEY"):
        from backends import OpenAIBackend
        backends_list.append(OpenAIBackend(config=LLMConfig(model="gpt-4", timeout=30)))

    try:
        from backends import AnthropicBackend
        if os.environ.get("ANTHROPIC_API_KEY"):
            backends_list.append(AnthropicBackend(
                config=LLMConfig(model="claude-sonnet-4-20250514", timeout=30)
            ))
    except ImportError:
        pass

    router = LLMRouter(
        backends=backends_list,
        config=RouterConfig(strategy="priority", enable_auto_failover=True),
    )
    await router.start()

    system_prompt = """You are a bioinformatics research assistant helping a researcher
define and refine their research question. Guide the conversation:
1. First, understand their broad topic of interest
2. Ask 1-2 clarifying questions (organism, disease, methodology, etc.)
3. When ready, propose exactly 3 specific search queries in the format:
   SEARCH_QUERY_1: "query here"
   SEARCH_QUERY_2: "query here"
   SEARCH_QUERY_3: "query here"
Keep responses concise. Respond in the same language the user uses (Korean or English)."""

    conversation_history = []
    search_queries = []

    click.echo("연구 주제에 대해 알려주세요. (종료: 'q')\n")

    # 초기 인사
    try:
        greeting = await router.generate(
            "사용자가 바이오인포매틱스 연구 상담을 시작합니다. 인사하고 어떤 연구에 관심이 있는지 물어보세요.",
            system_prompt=system_prompt,
        )
        if greeting.success:
            click.echo(click.style(f"[상담사] {greeting.content}\n", fg="cyan"))
            conversation_history.append({
                "role": "assistant", "content": greeting.content
            })
    except Exception:
        click.echo(click.style("[상담사] 어떤 바이오인포매틱스 연구에 관심이 있으신가요?\n", fg="cyan"))

    # 대화 루프 (최대 10턴)
    for turn in range(10):
        user_input = click.prompt("You", default="q")
        if user_input.strip().lower() == "q":
            click.echo("상담을 종료합니다.")
            await router.stop()
            return

        conversation_history.append({"role": "user", "content": user_input})

        # 대화 이력 포함 프롬프트 구성
        history_text = "\n".join(
            f"{'User' if m['role'] == 'user' else 'Assistant'}: {m['content']}"
            for m in conversation_history[-6:]  # 최근 6턴
        )
        prompt = f"Conversation so far:\n{history_text}\n\nRespond to the user's latest message."

        try:
            response = await router.generate(prompt, system_prompt=system_prompt)
            if response.success:
                click.echo(click.style(f"\n[상담사] {response.content}\n", fg="cyan"))
                conversation_history.append({
                    "role": "assistant", "content": response.content
                })

                # SEARCH_QUERY 패턴 감지
                import re
                queries = re.findall(
                    r'SEARCH_QUERY_\d+:\s*"([^"]+)"', response.content
                )
                if queries:
                    search_queries = queries
                    break
            else:
                click.echo(click.style("[상담사] 응답 생성에 실패했습니다.\n", fg="red"))
        except Exception as e:
            click.echo(click.style(f"[상담사] 오류: {e}\n", fg="red"))

    await router.stop()

    # 검색 쿼리 선택
    if not search_queries:
        click.echo("\n검색 쿼리가 제안되지 않았습니다.")
        manual = click.prompt("직접 검색어를 입력하세요", default="")
        if manual:
            search_queries = [manual]
        else:
            return

    if len(search_queries) > 1:
        click.echo("\n추천 검색 쿼리:")
        for i, q in enumerate(search_queries, 1):
            click.echo(f"  {i}. {q}")

        choice = click.prompt("선택 (번호)", default="1")
        try:
            chosen_query = search_queries[int(choice) - 1]
        except (ValueError, IndexError):
            chosen_query = search_queries[0]
    else:
        chosen_query = search_queries[0]

    click.echo(f"\n검색 실행: '{chosen_query}'")

    # 검색 실행
    results = await _run_search(chosen_query, limit=20, no_brave=False)
    if not results:
        click.echo("검색 결과가 없습니다.")
        return

    # 결과 표시
    click.echo(f"\n  {'#':>3}  {'PMID':>10}  {'Year':>5}  {'Cited':>6}  Title")
    click.echo(f"  {'─'*3}  {'─'*10}  {'─'*5}  {'─'*6}  {'─'*40}")
    for i, r in enumerate(results[:15], 1):
        pmid_str = r.pmid or "N/A"
        year_str = str(r.year) if r.year else "?"
        title_str = r.title[:55] + "..." if len(r.title) > 55 else r.title
        click.echo(f"  {i:3d}  {pmid_str:>10}  {year_str:>5}  {r.citation_count:6d}  {title_str}")

    # 선택 & 실행
    selection = click.prompt(
        "\n파이프라인 실행할 논문 번호 (쉼표 구분, 'q'=종료)", default="q"
    )

    if selection.strip().lower() == "q":
        return

    try:
        indices = [int(s.strip()) - 1 for s in selection.split(",")]
        selected = [results[i] for i in indices if 0 <= i < len(results)]
    except (ValueError, IndexError):
        click.echo("잘못된 입력입니다.")
        return

    pmids = [r.pmid for r in selected if r.pmid]
    if not pmids:
        click.echo("PMID가 있는 논문이 없습니다.")
        return

    if click.confirm(f"PMID {', '.join(pmids)} 파이프라인 실행?"):
        pipeline_config = PipelineConfig(
            pmids=pmids,
            results_dir=Path(results_dir),
            enable_debate=debate,
            rag_dir=Path(results_dir) / "rag_db",
        )
        pipeline = AsyncPipeline(pipeline_config)
        await pipeline.run()
        click.echo("파이프라인 실행 완료!")


if __name__ == "__main__":
    cli()
