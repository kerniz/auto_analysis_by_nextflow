"""
HTML Report Generator
파이프라인 결과를 사람이 읽기 편한 HTML 리포트로 변환

final_report_{PMID}.json → report_{PMID}.html
"""

import json
import logging
from datetime import datetime
from html import escape
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


class ReportGenerator:
    """final_report JSON을 자체 포함 HTML 리포트로 변환."""

    def generate(self, report_data: dict[str, Any], output_path: Path) -> Path:
        """
        JSON 리포트 데이터를 HTML 파일로 변환.

        Args:
            report_data: final_report JSON 딕셔너리
            output_path: 출력 HTML 파일 경로

        Returns:
            Path: 생성된 HTML 파일 경로
        """
        html = self._build_html(report_data)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(html, encoding="utf-8")
        logger.info("HTML 리포트 생성: %s", output_path)
        return output_path

    def generate_from_json(self, json_path: Path, output_dir: Path | None = None) -> Path:
        """
        JSON 파일에서 HTML 리포트 생성.

        Args:
            json_path: final_report JSON 파일 경로
            output_dir: 출력 디렉토리 (None이면 JSON과 같은 디렉토리)

        Returns:
            Path: 생성된 HTML 파일 경로
        """
        with open(json_path) as f:
            data = json.load(f)

        if output_dir is None:
            output_dir = json_path.parent

        pmid = data.get("pmid", "unknown")
        output_path = output_dir / f"report_{pmid}.html"
        return self.generate(data, output_path)

    def generate_summary(
        self, reports: list[dict[str, Any]], output_path: Path
    ) -> Path:
        """
        여러 PMID의 요약 리포트 생성.

        Args:
            reports: final_report 딕셔너리 리스트
            output_path: 출력 HTML 파일 경로

        Returns:
            Path: 생성된 HTML 파일 경로
        """
        html = self._build_summary_html(reports)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(html, encoding="utf-8")
        logger.info("요약 리포트 생성: %s", output_path)
        return output_path

    def _build_html(self, data: dict[str, Any]) -> str:
        pmid = data.get("pmid", "N/A")
        meta = data.get("pubmed_metadata", {})

        sections = [
            self._section_header(data),
            self._section_paper_info(meta),
            self._section_sequencing(data),
            self._section_sra(data.get("sra_results", {})),
            self._section_data_sources(data),
            self._section_enrichment(data.get("enrichment_summary", {})),
            self._section_llm_analysis(data),
            self._section_debate(data),
            self._section_pipeline(data),
            self._section_footer(data),
        ]

        return f"""<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>BioAuto Report - PMID {pmid}</title>
{self._css()}
</head>
<body>
<div class="container">
{''.join(sections)}
</div>
</body>
</html>"""

    def _build_summary_html(self, reports: list[dict[str, Any]]) -> str:
        rows = []
        for r in reports:
            pmid = r.get("pmid", "N/A")
            meta = r.get("pubmed_metadata", {})
            title = escape(meta.get("title", "")[:80])
            seq = r.get("sequencing_type", "unknown")
            llm = r.get("llm_rating", "UNKNOWN")
            debate_v = r.get("debate_verdict", "UNDETERMINED")
            debate_s = r.get("debate_score", 0.0)
            dur = r.get("duration_seconds", 0)

            rows.append(f"""<tr>
<td><a href="report_{pmid}.html">{pmid}</a></td>
<td class="title-cell">{title}...</td>
<td>{seq}</td>
<td><span class="badge {self._badge_class(llm)}">{llm}</span></td>
<td><span class="badge {self._badge_class(debate_v)}">{debate_v}</span>
    <small>({debate_s:.2f})</small></td>
<td>{dur:.0f}s</td>
</tr>""")

        return f"""<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>BioAuto Summary Report</title>
{self._css()}
</head>
<body>
<div class="container">
<h1>BioAuto Analysis Summary</h1>
<p class="meta">Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}
 | Total PMIDs: {len(reports)}</p>
<table>
<thead>
<tr>
<th>PMID</th><th>Title</th><th>Sequencing</th>
<th>LLM</th><th>Debate</th><th>Duration</th>
</tr>
</thead>
<tbody>
{''.join(rows)}
</tbody>
</table>
</div>
</body>
</html>"""

    # ── Sections ──

    def _section_header(self, data: dict) -> str:
        pmid = data.get("pmid", "N/A")
        status = data.get("status", "unknown")
        dur = data.get("duration_seconds", 0)
        debate_v = data.get("debate_verdict", "UNDETERMINED")
        debate_s = data.get("debate_score", 0.0)
        llm = data.get("llm_rating", "UNKNOWN")

        return f"""
<header>
  <h1>BioAuto Analysis Report</h1>
  <p class="meta">PMID: <strong>{pmid}</strong> |
    Status: <span class="badge {self._badge_class(status)}">{status}</span> |
    Duration: {dur:.0f}s</p>
  <div class="score-cards">
    <div class="score-card">
      <div class="score-label">LLM Rating</div>
      <div class="score-value {self._badge_class(llm)}">{llm}</div>
    </div>
    <div class="score-card">
      <div class="score-label">Debate Verdict</div>
      <div class="score-value {self._badge_class(debate_v)}">{debate_v}</div>
    </div>
    <div class="score-card">
      <div class="score-label">Debate Score</div>
      <div class="score-value">{debate_s:.2f}</div>
      {self._score_bar(debate_s)}
    </div>
    <div class="score-card">
      <div class="score-label">Sequencing Type</div>
      <div class="score-value seq-type">{data.get('sequencing_type', 'unknown')}</div>
      <small>confidence: {data.get('sequencing_confidence', 0):.0%}</small>
    </div>
  </div>
</header>"""

    def _section_paper_info(self, meta: dict) -> str:
        if not meta:
            return ""

        title = escape(meta.get("title", "N/A"))
        authors = meta.get("authors", [])
        author_str = ", ".join(authors[:5])
        if len(authors) > 5:
            author_str += f" ... (+{len(authors) - 5})"
        journal = escape(meta.get("journal", "N/A"))
        pub_date = escape(meta.get("pub_date", "N/A"))
        doi = meta.get("doi", "")
        abstract = escape(meta.get("abstract", ""))

        doi_link = ""
        if doi:
            doi_clean = doi.replace("doi: ", "").strip()
            doi_link = (
                f'<a href="https://doi.org/{doi_clean}" '
                f'target="_blank">{doi_clean}</a>'
            )

        pmid = meta.get("pmid", "")
        pmid_link = (
            f'<a href="https://pubmed.ncbi.nlm.nih.gov/{pmid}" '
            f'target="_blank">{pmid}</a>'
        ) if pmid else ""

        keywords = meta.get("keywords", [])
        kw_html = " ".join(
            f'<span class="tag">{escape(k)}</span>' for k in keywords
        )

        return f"""
<section>
  <h2>Paper Information</h2>
  <h3 class="paper-title">{title}</h3>
  <p class="authors">{author_str}</p>
  <p><strong>{journal}</strong> | {pub_date}</p>
  <p>PMID: {pmid_link} | DOI: {doi_link}</p>
  {f'<div class="tags">{kw_html}</div>' if kw_html else ''}
  <details>
    <summary>Abstract</summary>
    <p class="abstract">{abstract}</p>
  </details>
</section>"""

    def _section_sequencing(self, data: dict) -> str:
        seq_type = data.get("sequencing_type", "unknown")
        confidence = data.get("sequencing_confidence", 0.0)

        pipeline_map = {
            "scrna_seq": "nf-core/scrnaseq",
            "bulk_rna": "nf-core/rnaseq",
            "atac_seq": "nf-core/atacseq",
            "chipseq": "nf-core/chipseq",
        }
        pipeline = pipeline_map.get(seq_type, "N/A")

        return f"""
<section>
  <h2>Sequencing Detection</h2>
  <div class="info-grid">
    <div class="info-item">
      <span class="info-label">Type</span>
      <span class="info-value">{seq_type}</span>
    </div>
    <div class="info-item">
      <span class="info-label">Confidence</span>
      <span class="info-value">{confidence:.0%}</span>
      {self._score_bar(confidence)}
    </div>
    <div class="info-item">
      <span class="info-label">Recommended Pipeline</span>
      <span class="info-value">{pipeline}</span>
    </div>
  </div>
</section>"""

    def _section_sra(self, sra: dict) -> str:
        if not sra:
            return ""

        downloadable = sra.get("downloadable", False)
        public_ids = sra.get("public_sra_ids", [])
        controlled_ids = sra.get("controlled_sra_ids", [])
        size_gb = sra.get("total_size_gb", 0)

        status_badge = (
            '<span class="badge pass">Downloadable</span>'
            if downloadable
            else '<span class="badge fail">Not Available</span>'
        )

        ids_html = ""
        if public_ids:
            ids_html = "<p>Public IDs: " + ", ".join(
                f"<code>{i}</code>" for i in public_ids[:10]
            ) + "</p>"
        if controlled_ids:
            ids_html += "<p>Controlled IDs: " + ", ".join(
                f"<code>{i}</code>" for i in controlled_ids[:10]
            ) + "</p>"

        return f"""
<section>
  <h2>SRA Data</h2>
  <p>Status: {status_badge}
     | Size: {size_gb:.1f} GB
     | Public: {len(public_ids)} | Controlled: {len(controlled_ids)}</p>
  {ids_html}
</section>"""

    def _section_data_sources(self, data: dict) -> str:
        sources = data.get("aggregated_sources", [])
        if not sources:
            return ""

        source_labels = {
            "ss_citations": "Semantic Scholar Citations",
            "ss_references": "Semantic Scholar References",
            "ss_recommendations": "Semantic Scholar Recommendations",
            "ss_influence": "Semantic Scholar Influence",
            "epmc_article": "EuropePMC Article",
            "epmc_citations": "EuropePMC Citations",
            "epmc_references": "EuropePMC References",
            "tcga_projects": "TCGA Projects",
            "annotation_genes": "Gene Annotations",
        }

        items = " ".join(
            f'<span class="tag source">{source_labels.get(s, s)}</span>'
            for s in sources
        )

        return f"""
<section>
  <h2>Aggregated Data Sources</h2>
  <div class="tags">{items}</div>
</section>"""

    def _section_enrichment(self, enrichment: dict) -> str:
        if not enrichment:
            return ""

        novelty = enrichment.get("novelty_score", 0)
        genes = enrichment.get("top_genes_count", 0)
        pathways = enrichment.get("top_pathways_count", 0)

        return f"""
<section>
  <h2>Enrichment Analysis</h2>
  <div class="info-grid">
    <div class="info-item">
      <span class="info-label">Novelty Score</span>
      <span class="info-value">{novelty:.3f}</span>
      {self._score_bar(novelty)}
    </div>
    <div class="info-item">
      <span class="info-label">Top Genes</span>
      <span class="info-value">{genes}</span>
    </div>
    <div class="info-item">
      <span class="info-label">Top Pathways</span>
      <span class="info-value">{pathways}</span>
    </div>
  </div>
</section>"""

    def _section_llm_analysis(self, data: dict) -> str:
        llm_rating = data.get("llm_rating", "UNKNOWN")
        consensus = data.get("llm_consensus", {})

        if not consensus:
            return f"""
<section>
  <h2>LLM Analysis</h2>
  <p>Rating: <span class="badge {self._badge_class(llm_rating)}">{llm_rating}</span></p>
</section>"""

        rows = ""
        for key, val in consensus.items():
            rows += f"<tr><td>{escape(str(key))}</td><td>{escape(str(val))}</td></tr>"

        return f"""
<section>
  <h2>LLM Analysis</h2>
  <p>Rating: <span class="badge {self._badge_class(llm_rating)}">{llm_rating}</span></p>
  {f'<table><thead><tr><th>Key</th><th>Value</th></tr></thead><tbody>{rows}</tbody></table>' if rows else ''}
</section>"""

    def _section_debate(self, data: dict) -> str:
        verdict = data.get("debate_verdict", "UNDETERMINED")
        score = data.get("debate_score", 0.0)

        # debate_report가 전체 구조에 포함되어 있을 수 있음
        report = data.get("debate_report", {})
        if not report:
            # final_report에는 요약만 있음
            return f"""
<section>
  <h2>Multi-Agent Debate</h2>
  <p>Verdict: <span class="badge {self._badge_class(verdict)}">{verdict}</span>
     | Score: <strong>{score:.2f}</strong></p>
</section>"""

        # 전체 debate report가 있는 경우
        rounds = report.get("rounds", [])
        consensus = report.get("final_consensus", {})
        per_agent = report.get("per_agent_scores", {})
        dissenting = report.get("dissenting_opinions", [])

        rounds_html = ""
        for rnd in rounds:
            rnum = rnd.get("round_number", 0)
            cscore = rnd.get("consensus_score")
            responses = rnd.get("responses", [])

            resp_items = ""
            for resp in responses:
                agent_name = escape(resp.get("agent_name", "Unknown"))
                r_score = resp.get("score", 0.5)
                r_conf = resp.get("confidence", 0.0)
                assessment = escape(resp.get("assessment", "")[:300])
                key_pts = resp.get("key_points", [])
                concerns = resp.get("concerns", [])

                kp_html = "".join(
                    f"<li>{escape(str(p))}</li>" for p in key_pts[:5]
                )
                cc_html = "".join(
                    f"<li>{escape(str(c))}</li>" for c in concerns[:5]
                )

                resp_items += f"""
<div class="agent-response">
  <div class="agent-header">
    <strong>{agent_name}</strong>
    <span>Score: {r_score:.2f} | Confidence: {r_conf:.2f}</span>
  </div>
  <p>{assessment}{'...' if len(resp.get('assessment', '')) > 300 else ''}</p>
  {f'<ul class="key-points">{kp_html}</ul>' if kp_html else ''}
  {f'<ul class="concerns">{cc_html}</ul>' if cc_html else ''}
</div>"""

            cscore_str = f"{cscore:.2f}" if cscore is not None else "N/A"
            rounds_html += f"""
<details{'open' if rnum == len(rounds) else ''}>
  <summary>Round {rnum} (Consensus: {cscore_str})</summary>
  {resp_items}
</details>"""

        # Per-agent scores
        agent_html = ""
        if per_agent:
            agent_rows = "".join(
                f"<tr><td>{escape(name)}</td><td>{s:.2f}</td></tr>"
                for name, s in per_agent.items()
            )
            agent_html = f"""
<h3>Per-Agent Final Scores</h3>
<table><thead><tr><th>Agent</th><th>Score</th></tr></thead>
<tbody>{agent_rows}</tbody></table>"""

        # Dissenting opinions
        dissent_html = ""
        if dissenting:
            items = "".join(f"<li>{escape(str(d))}</li>" for d in dissenting)
            dissent_html = f"<h3>Dissenting Opinions</h3><ul>{items}</ul>"

        # Consensus summary
        consensus_html = ""
        if consensus:
            summary = escape(consensus.get("summary", ""))
            achieved = consensus.get("achieved", False)
            consensus_html = f"""
<div class="consensus-box {'achieved' if achieved else 'not-achieved'}">
  <strong>{'Consensus Achieved' if achieved else 'No Consensus'}</strong>
  <p>{summary}</p>
</div>"""

        return f"""
<section>
  <h2>Multi-Agent Debate</h2>
  <p>Verdict: <span class="badge {self._badge_class(verdict)}">{verdict}</span>
     | Score: <strong>{score:.2f}</strong></p>
  {consensus_html}
  {rounds_html}
  {agent_html}
  {dissent_html}
</section>"""

    def _section_pipeline(self, data: dict) -> str:
        fetchngs = data.get("fetchngs")
        pipeline = data.get("pipeline_execution")
        downstream = data.get("downstream_analysis")

        if not any([fetchngs, pipeline, downstream]):
            return """
<section>
  <h2>Pipeline Execution</h2>
  <p class="muted">Not executed (use --execute-pipeline flag)</p>
</section>"""

        parts = []
        if fetchngs:
            status = fetchngs.get("status", "unknown")
            parts.append(
                f'<p>fetchngs: <span class="badge {self._badge_class(status)}">'
                f"{status}</span></p>"
            )
        if pipeline:
            name = pipeline.get("pipeline_name", "")
            status = pipeline.get("status", "unknown")
            parts.append(
                f'<p>{escape(name)}: '
                f'<span class="badge {self._badge_class(status)}">'
                f"{status}</span></p>"
            )
        if downstream:
            status = downstream.get("status", "unknown")
            parts.append(
                f'<p>Downstream: '
                f'<span class="badge {self._badge_class(status)}">'
                f"{status}</span></p>"
            )

        return f"""
<section>
  <h2>Pipeline Execution</h2>
  {''.join(parts)}
</section>"""

    def _section_footer(self, data: dict) -> str:
        return f"""
<footer>
  <p>Generated by <strong>BioAuto v4.0</strong> |
     {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</p>
</footer>"""

    # ── Helpers ──

    @staticmethod
    def _badge_class(value: str) -> str:
        v = str(value).upper()
        if v in ("PASS", "COMPLETED", "TRUE"):
            return "pass"
        if v in ("WARN", "WARNING"):
            return "warn"
        if v in ("FAIL", "FAILED", "FALSE"):
            return "fail"
        return "neutral"

    @staticmethod
    def _score_bar(value: float) -> str:
        pct = max(0, min(100, value * 100))
        if pct >= 70:
            color = "#2ecc71"
        elif pct >= 50:
            color = "#f39c12"
        else:
            color = "#e74c3c"
        return (
            f'<div class="score-bar">'
            f'<div class="score-fill" style="width:{pct:.0f}%;'
            f'background:{color}"></div></div>'
        )

    @staticmethod
    def _css() -> str:
        return """<style>
* { margin: 0; padding: 0; box-sizing: border-box; }
body {
  font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
  background: #f5f7fa; color: #333; line-height: 1.6;
}
.container { max-width: 960px; margin: 0 auto; padding: 20px; }
header { background: linear-gradient(135deg, #2c3e50 0%, #3498db 100%);
  color: #fff; padding: 30px; border-radius: 12px; margin-bottom: 20px; }
header h1 { font-size: 24px; margin-bottom: 8px; }
header .meta { opacity: 0.9; font-size: 14px; }
.score-cards { display: flex; gap: 16px; margin-top: 20px; flex-wrap: wrap; }
.score-card { background: rgba(255,255,255,0.15); border-radius: 8px;
  padding: 16px; flex: 1; min-width: 140px; text-align: center; }
.score-label { font-size: 12px; text-transform: uppercase; opacity: 0.8;
  margin-bottom: 6px; }
.score-value { font-size: 22px; font-weight: 700; }
.score-value.seq-type { font-size: 16px; }
section { background: #fff; border-radius: 10px; padding: 24px;
  margin-bottom: 16px; box-shadow: 0 1px 3px rgba(0,0,0,0.08); }
h2 { font-size: 18px; color: #2c3e50; margin-bottom: 16px;
  padding-bottom: 8px; border-bottom: 2px solid #ecf0f1; }
h3 { font-size: 15px; color: #34495e; margin: 12px 0 8px; }
.paper-title { font-size: 16px; color: #2c3e50; line-height: 1.4;
  margin-bottom: 8px; }
.authors { color: #7f8c8d; font-size: 13px; margin-bottom: 6px; }
.abstract { color: #555; font-size: 13px; line-height: 1.5;
  margin-top: 8px; text-align: justify; }
.badge { display: inline-block; padding: 2px 10px; border-radius: 12px;
  font-size: 12px; font-weight: 600; text-transform: uppercase; }
.badge.pass { background: #d4edda; color: #155724; }
.badge.warn { background: #fff3cd; color: #856404; }
.badge.fail { background: #f8d7da; color: #721c24; }
.badge.neutral { background: #e2e3e5; color: #383d41; }
.tag { display: inline-block; background: #eef2f7; color: #4a6fa5;
  padding: 2px 8px; border-radius: 4px; font-size: 12px; margin: 2px; }
.tag.source { background: #e8f5e9; color: #2e7d32; }
.tags { margin-top: 8px; }
.info-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
  gap: 16px; }
.info-item { background: #f8f9fa; border-radius: 8px; padding: 14px; }
.info-label { font-size: 11px; text-transform: uppercase; color: #95a5a6;
  display: block; margin-bottom: 4px; }
.info-value { font-size: 18px; font-weight: 600; color: #2c3e50; }
.score-bar { background: #ecf0f1; border-radius: 4px; height: 6px;
  margin-top: 6px; overflow: hidden; }
.score-fill { height: 100%; border-radius: 4px; transition: width 0.5s; }
table { width: 100%; border-collapse: collapse; margin-top: 12px; }
th, td { padding: 8px 12px; text-align: left; border-bottom: 1px solid #ecf0f1;
  font-size: 13px; }
th { background: #f8f9fa; font-weight: 600; color: #2c3e50; }
.title-cell { max-width: 300px; overflow: hidden; text-overflow: ellipsis;
  white-space: nowrap; }
details { margin: 8px 0; }
summary { cursor: pointer; font-weight: 600; padding: 8px;
  background: #f8f9fa; border-radius: 6px; font-size: 14px; }
summary:hover { background: #ecf0f1; }
.agent-response { background: #f8f9fa; border-radius: 8px; padding: 14px;
  margin: 8px 0; border-left: 3px solid #3498db; }
.agent-header { display: flex; justify-content: space-between;
  margin-bottom: 6px; font-size: 13px; }
.agent-response p { font-size: 13px; color: #555; }
.key-points li { color: #27ae60; font-size: 12px; margin-left: 16px; }
.concerns li { color: #e74c3c; font-size: 12px; margin-left: 16px; }
.consensus-box { padding: 14px; border-radius: 8px; margin: 12px 0; }
.consensus-box.achieved { background: #d4edda; border: 1px solid #c3e6cb; }
.consensus-box.not-achieved { background: #fff3cd; border: 1px solid #ffeeba; }
.muted { color: #95a5a6; font-style: italic; }
footer { text-align: center; color: #95a5a6; font-size: 12px;
  padding: 20px; margin-top: 10px; }
a { color: #3498db; text-decoration: none; }
a:hover { text-decoration: underline; }
@media (max-width: 600px) {
  .score-cards { flex-direction: column; }
  .info-grid { grid-template-columns: 1fr; }
}
</style>"""
