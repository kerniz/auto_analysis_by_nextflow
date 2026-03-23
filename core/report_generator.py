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
            self._section_ncbi_links(meta),
            self._section_sequencing(data),
            self._section_sra(data.get("sra_results", {})),
            self._section_data_sources(data),
            self._section_enrichment(data.get("enrichment_summary", {})),
            self._section_llm_analysis(data),
            self._section_debate(data),
            self._section_research_evaluation(data),
            self._section_meta_verdict(data),
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

            # RES + Meta
            debate_report = r.get("debate_report", {})
            res_eval = debate_report.get("research_evaluation", {}) if isinstance(debate_report, dict) else {}
            meta_v = debate_report.get("meta_verdict", {}) if isinstance(debate_report, dict) else {}
            res_score = res_eval.get("total_score", "-") if isinstance(res_eval, dict) else "-"
            res_verdict = res_eval.get("verdict", "-") if isinstance(res_eval, dict) else "-"
            meta_verdict = meta_v.get("verdict", "-") if isinstance(meta_v, dict) else "-"

            res_display = f"{res_score:.1f}" if isinstance(res_score, (int, float)) else "-"
            res_v_class = self._badge_class(res_verdict) if res_verdict != "-" else ""
            meta_v_class = self._badge_class(meta_verdict) if meta_verdict != "-" else ""

            rows.append(f"""<tr>
<td><a href="report_{pmid}.html">{pmid}</a></td>
<td class="title-cell">{title}...</td>
<td>{seq}</td>
<td><span class="badge {self._badge_class(llm)}">{llm}</span></td>
<td><span class="badge {self._badge_class(debate_v)}">{debate_v}</span>
    <small>({debate_s:.2f})</small></td>
<td>{res_display} <span class="badge {res_v_class}">{res_verdict}</span></td>
<td><span class="badge {meta_v_class}">{meta_verdict}</span></td>
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
<th>LLM</th><th>Debate</th><th>RES</th><th>Meta</th><th>Duration</th>
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
  <h2>논문 정보 (Paper Information)</h2>
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

    def _section_ncbi_links(self, meta: dict) -> str:
        """NCBI 연관 데이터베이스 링크 섹션."""
        ncbi = meta.get("ncbi_links", {})
        if not ncbi:
            return ""

        pmid = meta.get("pmid", "")
        db_urls = {
            "sra": ("SRA", f"https://www.ncbi.nlm.nih.gov/sra?linkname=pubmed_sra&from_uid={pmid}"),
            "gds": ("GEO Profiles", f"https://www.ncbi.nlm.nih.gov/geoprofiles?linkname=pubmed_geoprofiles&from_uid={pmid}"),
            "bioproject": ("BioProject", f"https://www.ncbi.nlm.nih.gov/bioproject?linkname=pubmed_bioproject&from_uid={pmid}"),
            "nuccore": ("Nucleotide", f"https://www.ncbi.nlm.nih.gov/nuccore?linkname=pubmed_nuccore&from_uid={pmid}"),
            "protein": ("Protein", f"https://www.ncbi.nlm.nih.gov/protein?linkname=pubmed_protein&from_uid={pmid}"),
            "gene": ("Gene", f"https://www.ncbi.nlm.nih.gov/gene?linkname=pubmed_gene&from_uid={pmid}"),
            "assembly": ("Assembly", f"https://www.ncbi.nlm.nih.gov/assembly?linkname=pubmed_assembly&from_uid={pmid}"),
        }

        badges = []
        for db, ids in ncbi.items():
            if ids and db in db_urls:
                label, url = db_urls[db]
                badges.append(
                    f'<a href="{url}" target="_blank" class="ncbi-badge">'
                    f'{label} <strong>{len(ids)}</strong></a>'
                )

        if not badges:
            return ""

        return f"""
<section>
  <h2>NCBI 연관 데이터 (Linked Databases)</h2>
  <div class="ncbi-links">{"  ".join(badges)}</div>
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
            linked = ", ".join(
                f'<a href="https://www.ncbi.nlm.nih.gov/sra/{i}" '
                f'target="_blank"><code>{i}</code></a>'
                for i in public_ids[:10]
            )
            ids_html = f"<p>Public IDs: {linked}</p>"
        if controlled_ids:
            linked_c = ", ".join(
                f'<a href="https://www.ncbi.nlm.nih.gov/sra/{i}" '
                f'target="_blank"><code>{i}</code></a>'
                for i in controlled_ids[:10]
            )
            ids_html += f"<p>Controlled IDs: {linked_c}</p>"

        # SRA 메타데이터에서 platform/library 정보 추출
        import re as _re
        meta_html = ""
        metadata = sra.get("metadata", {})
        for sra_id, meta in metadata.items():
            expxml = meta.get("expxml", "")
            plat_m = _re.search(r'instrument_model="([^"]+)"', expxml)
            lib_m = _re.search(
                r'<LIBRARY_STRATEGY>([^<]+)</LIBRARY_STRATEGY>', expxml,
            )
            src_m = _re.search(
                r'<LIBRARY_SOURCE>([^<]+)</LIBRARY_SOURCE>', expxml,
            )
            org_m = _re.search(r'ScientificName="([^"]+)"', expxml)
            bp_m = _re.search(r'<Bioproject>([^<]+)</Bioproject>', expxml)

            parts = []
            if plat_m:
                parts.append(f"Platform: <strong>{escape(plat_m.group(1))}</strong>")
            if lib_m:
                parts.append(f"Library: {escape(lib_m.group(1))}")
            if src_m:
                parts.append(f"Source: {escape(src_m.group(1))}")
            if org_m:
                parts.append(f"Organism: <em>{escape(org_m.group(1))}</em>")
            if bp_m:
                bp = bp_m.group(1)
                parts.append(
                    f'BioProject: <a href="https://www.ncbi.nlm.nih.gov/'
                    f'bioproject/{bp}" target="_blank">{bp}</a>'
                )
            if parts:
                meta_html += "<p>" + " | ".join(parts) + "</p>"

        return f"""
<section>
  <h2>SRA Data</h2>
  <p>Status: {status_badge}
     | Size: {size_gb:.1f} GB
     | Public: {len(public_ids)} | Controlled: {len(controlled_ids)}</p>
  {ids_html}
  {meta_html}
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

    def _render_debate_content(
        self, report: dict, verdict: str, score: float, lang: str = "en",
    ) -> str:
        """토론 내용을 지정 언어로 렌더링. lang='en' 원문, 'ko' 한글 번역."""
        if lang == "ko" and report.get("debate_ko"):
            # 한국어 번역 데이터
            ko = report["debate_ko"]
            rounds = ko.get("rounds", report.get("rounds", []))
            consensus = ko.get("final_consensus", report.get("final_consensus", {}))
            per_agent = ko.get("per_agent_scores", report.get("per_agent_scores", {}))
            dissenting = ko.get("dissenting_opinions", report.get("dissenting_opinions", []))
        elif lang == "en" and report.get("debate_en"):
            # 영어 원본 데이터 (명시적으로 debate_en에서 읽기)
            en = report["debate_en"]
            rounds = en.get("rounds", report.get("rounds", []))
            consensus = en.get("final_consensus", report.get("final_consensus", {}))
            per_agent = en.get("per_agent_scores", report.get("per_agent_scores", {}))
            dissenting = en.get("dissenting_opinions", report.get("dissenting_opinions", []))
        else:
            rounds = report.get("rounds", [])
            consensus = report.get("final_consensus", {})
            per_agent = report.get("per_agent_scores", {})
            dissenting = report.get("dissenting_opinions", [])

        # Consensus summary
        consensus_html = ""
        if consensus:
            summary = escape(consensus.get("summary", ""))
            achieved = consensus.get("achieved", False)
            consensus_html = f"""
<div class="consensus-box {'achieved' if achieved else 'not-achieved'}">
  <strong>{'합의 도달' if achieved else '합의 미도달'}</strong>
  <p>{summary}</p>
</div>"""

        # Round details with full agent opinions
        rounds_html = ""
        round_labels = {1: "초기 평가", 2: "교차 검토", 3: "최종 판단"}
        for rnd in rounds:
            rnum = rnd.get("round_number", 0)
            cscore = rnd.get("consensus_score")
            responses = rnd.get("responses", [])
            round_label = round_labels.get(rnum, f"Round {rnum}")

            resp_items = ""
            for resp in responses:
                agent_name = escape(resp.get("agent_name", "Unknown"))
                r_score = resp.get("score", 0.5)
                r_conf = resp.get("confidence", 0.0)
                assessment = escape(resp.get("assessment", ""))
                key_pts = resp.get("key_points", [])
                concerns = resp.get("concerns", [])
                questions = resp.get("questions", [])
                rebuttal = resp.get("rebuttal_to", "")

                kp_html = "".join(
                    f"<li>{escape(str(p))}</li>" for p in key_pts
                )
                cc_html = "".join(
                    f"<li>{escape(str(c))}</li>" for c in concerns
                )
                q_html = "".join(
                    f"<li>{escape(str(q))}</li>" for q in questions
                ) if questions else ""

                rebuttal_html = ""
                if rebuttal:
                    rebuttal_html = (
                        f'<p style="font-size:12px;color:#8e44ad">'
                        f'반론 대상: {escape(str(rebuttal))}</p>'
                    )

                resp_items += f"""
<div class="agent-response">
  <div class="agent-header">
    <strong>{agent_name}</strong>
    <span>평가: {r_score:.2f} | 확신도: {r_conf:.2f}</span>
  </div>
  {rebuttal_html}
  <p>{assessment}</p>
  {f'<h4 style="color:#27ae60;font-size:13px">주요 발견</h4><ul class="key-points">{kp_html}</ul>' if kp_html else ''}
  {f'<h4 style="color:#e74c3c;font-size:13px">우려 사항</h4><ul class="concerns">{cc_html}</ul>' if cc_html else ''}
  {f'<h4 style="color:#2980b9;font-size:13px">추가 질문</h4><ul>{q_html}</ul>' if q_html else ''}
</div>"""

            cscore_str = f"{cscore:.2f}" if cscore is not None else "N/A"
            rounds_html += f"""
<details{'open' if rnum == len(rounds) else ''}>
  <summary>{round_label} — Round {rnum} (합의 점수: {cscore_str})</summary>
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
<h3>에이전트별 최종 점수</h3>
<table><thead><tr><th>에이전트</th><th>점수</th></tr></thead>
<tbody>{agent_rows}</tbody></table>"""

        # Dissenting opinions
        dissent_html = ""
        if dissenting:
            items = "".join(f"<li>{escape(str(d))}</li>" for d in dissenting)
            dissent_html = f"<h3>소수 의견</h3><ul>{items}</ul>"

        return f"""{consensus_html}
  {rounds_html}
  {agent_html}
  {dissent_html}"""

    def _section_debate(self, data: dict) -> str:
        verdict = data.get("debate_verdict", "UNDETERMINED")
        score = data.get("debate_score", 0.0)

        report = data.get("debate_report", {})
        if not report:
            return f"""
<section>
  <h2>멀티 에이전트 토론 (Multi-Agent Debate)</h2>
  <p>판정: <span class="badge {self._badge_class(verdict)}">{verdict}</span>
     | 점수: <strong>{score:.2f}</strong></p>
  <p class="muted">토론 상세 데이터 없음</p>
</section>"""

        rounds = report.get("rounds", [])
        debate_ko = report.get("debate_ko", {})
        has_translation = bool(debate_ko)

        # 번역 언어 감지
        lang_labels = {
            "ko": "한국어", "en": "English", "ja": "日本語",
            "zh": "中文", "de": "Deutsch", "fr": "Français",
            "es": "Español", "pt": "Português", "it": "Italiano",
        }
        translated_to = debate_ko.get("_translated_to", "ko") if debate_ko else "ko"
        primary_label = "English"
        secondary_label = lang_labels.get(translated_to, translated_to)

        # 원문 콘텐츠
        en_content = self._render_debate_content(report, verdict, score, "en")

        # 번역이 있으면 토글 버튼 + 번역 콘텐츠
        if has_translation:
            ko_content = self._render_debate_content(
                report, verdict, score, "ko",
            )
            toggle_btn = f"""
<div class="lang-toggle">
  <button class="lang-btn active" onclick="switchDebateLang('en')"
          id="btn-debate-en">{escape(primary_label)}</button>
  <button class="lang-btn" onclick="switchDebateLang('ko')"
          id="btn-debate-ko">{escape(secondary_label)}</button>
</div>
<script>
function switchDebateLang(lang) {{
  document.getElementById('debate-en').style.display =
    lang === 'en' ? 'block' : 'none';
  document.getElementById('debate-ko').style.display =
    lang === 'ko' ? 'block' : 'none';
  document.getElementById('btn-debate-en').className =
    'lang-btn' + (lang === 'en' ? ' active' : '');
  document.getElementById('btn-debate-ko').className =
    'lang-btn' + (lang === 'ko' ? ' active' : '');
}}
</script>"""
            body = f"""
  {toggle_btn}
  <div id="debate-en">{en_content}</div>
  <div id="debate-ko" style="display:none">{ko_content}</div>"""
        else:
            body = en_content

        return f"""
<section>
  <h2>멀티 에이전트 토론 (Multi-Agent Debate)</h2>
  <p>판정: <span class="badge {self._badge_class(verdict)}">{verdict}</span>
     | 종합 점수: <strong>{score:.2f}</strong>
     | 라운드: {len(rounds)}</p>
  {body}
</section>"""

    def _section_research_evaluation(self, data: dict) -> str:
        report = data.get("debate_report", {})
        res = report.get("research_evaluation") if isinstance(report, dict) else None
        if not res or not isinstance(res, dict) or "error" in res:
            return ""

        total = res.get("total_score", 0)
        verdict = res.get("verdict", "N/A")
        confidence = res.get("confidence", 0)
        dims = res.get("dimensions", [])

        # 차원별 테이블
        # 문헌 중복도는 역방향 지표 (낮을수록 좋음 = 신규성 높음)
        _inverse_dims = {"literature_redundancy"}

        dim_rows = ""
        for d in dims:
            label = escape(d.get("label_ko", d.get("dimension", "")))
            actual = d.get("actual_points", 0)
            mx = d.get("max_points", 0)
            pct = (actual / mx * 100) if mx > 0 else 0
            dim_name = d.get("dimension", "")
            if dim_name in _inverse_dims:
                # 역방향: 점수가 낮을수록 좋음 (녹색)
                bar_color = "#27ae60" if pct <= 40 else "#f39c12" if pct <= 70 else "#e74c3c"
            else:
                bar_color = "#27ae60" if pct >= 70 else "#f39c12" if pct >= 40 else "#e74c3c"
            dim_rows += f"""<tr>
<td>{label}</td>
<td>{d.get('quantitative_score', 0):.2f}</td>
<td>{d.get('qualitative_score', 0):.2f}</td>
<td>{actual:.1f}/{mx}</td>
<td><div style="background:#ecf0f1;border-radius:4px;height:18px;width:100%">
<div style="background:{bar_color};height:18px;width:{pct:.0f}%;border-radius:4px;
font-size:11px;color:#fff;text-align:center;line-height:18px">{pct:.0f}%</div>
</div></td></tr>"""

        verdict_class = (
            "badge-pass" if verdict == "GO"
            else "badge-warn" if verdict == "REVISE"
            else "badge-fail"
        )

        return f"""
<section>
  <h2>연구 평가 점수 (Research Evaluation Score)</h2>
  <p>총점: <strong>{total:.1f}/100</strong>
     | 판정: <span class="badge {verdict_class}">{verdict}</span>
     | 확신도: {confidence:.2f}</p>
  <table>
    <thead><tr>
      <th>차원</th><th>정량</th><th>정성</th><th>점수</th><th>비율</th>
    </tr></thead>
    <tbody>{dim_rows}</tbody>
  </table>
</section>"""

    def _section_meta_verdict(self, data: dict) -> str:
        report = data.get("debate_report", {})
        meta = report.get("meta_verdict") if isinstance(report, dict) else None
        if not meta or not isinstance(meta, dict) or "error" in meta:
            return ""

        verdict = meta.get("verdict", "N/A")
        confidence = meta.get("confidence", 0)
        narrative = escape(meta.get("narrative", ""))
        recs = meta.get("key_recommendations", [])
        risks = meta.get("risk_factors", [])

        verdict_class = (
            "badge-pass" if verdict == "GO"
            else "badge-warn" if verdict == "REVISE"
            else "badge-fail"
        )

        recs_html = "".join(f"<li>{escape(str(r))}</li>" for r in recs)
        risks_html = "".join(f"<li>{escape(str(r))}</li>" for r in risks)

        return f"""
<section>
  <h2>메타 에이전트 종합 판정 (Meta-Agent Verdict)</h2>
  <p>판정: <span class="badge {verdict_class}">{verdict}</span>
     | 확신도: {confidence:.2f}
     | RES: {meta.get('res_score', 0):.1f}/100
     | 토론: {meta.get('debate_score', 0):.2f}</p>
  <div style="background:#f8f9fa;padding:16px;border-radius:8px;margin:12px 0">
    <p>{narrative}</p>
  </div>
  {f'<h3>핵심 권고사항</h3><ul>{recs_html}</ul>' if recs_html else ''}
  {f'<h3>리스크 요인</h3><ul>{risks_html}</ul>' if risks_html else ''}
</section>"""

    def _section_pipeline(self, data: dict) -> str:
        fetchngs = data.get("fetchngs")
        pipeline = data.get("pipeline_execution")
        downstream = data.get("downstream_analysis")
        pmid = data.get("pmid", "")

        # nf-core 산출물 자동 스캔 (results/{PMID}/ 및 results/nfcore/ 하위)
        report_links = self._scan_pipeline_reports(pmid)

        has_reports = any(v for v in report_links.values())
        if not any([fetchngs, pipeline, downstream]) and not has_reports:
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

        # STAR mapping 통계
        if pmid:
            star_summary = self._star_mapping_summary(pmid)
            if star_summary:
                parts.append(star_summary)

        # 카테고리별 링크
        if report_links:
            for cat, items in report_links.items():
                if not items:
                    continue
                link_items = "".join(
                    f'<li><a href="{path}" target="_blank">{name}</a>'
                    f' <span class="muted">({size})</span></li>'
                    for name, path, size in items
                )
                parts.append(
                    f"<h3>{cat}</h3>"
                    f"<ul class='report-list'>{link_items}</ul>"
                )

        return f"""
<section>
  <h2>Pipeline Execution</h2>
  {''.join(parts)}
</section>"""

    def _scan_pipeline_reports(self, pmid: str) -> dict[str, list[tuple[str, str, str]]]:
        """results 폴더에서 nf-core 산출물 자동 탐색, 카테고리별 반환.

        Returns: {category: [(display_name, web_path, file_size), ...]}
        """
        from pathlib import Path as _Path

        cats: dict[str, list[tuple[str, str, str]]] = {
            "QC Reports": [],
            "RNA-seq Data": [],
            "Pipeline Info": [],
        }

        nfcore_dir = _Path(f"results/nfcore/{pmid}") if pmid else None
        if not nfcore_dir or not nfcore_dir.exists():
            return cats

        seen: set[str] = set()

        def _add(cat: str, f: "_Path", display: str | None = None) -> None:
            abs_path = str(f.resolve())
            if abs_path in seen or not f.is_file():
                return
            seen.add(abs_path)
            size_bytes = f.stat().st_size
            size_str = (
                f"{size_bytes / 1_048_576:.1f} MB"
                if size_bytes > 1_048_576
                else f"{size_bytes / 1_024:.0f} KB"
            )
            try:
                rel = f.relative_to(_Path("results"))
                web_path = f"/pipeline-files/{rel}"
            except ValueError:
                web_path = f"/pipeline-files/{f.name}"
            name = display or f.stem.replace("_", " ").replace("-", " ").title()
            cats[cat].append((name, web_path, size_str))

        # ── QC Reports ──
        for f in nfcore_dir.rglob("multiqc_report.html"):
            _add("QC Reports", f, "MultiQC Report")
        for f in sorted(nfcore_dir.rglob("*_fastqc.html")):
            _add("QC Reports", f, f"FastQC — {f.stem.replace('_fastqc','')}")

        # ── RNA-seq Data (TSV / RDS) ──
        rna_targets = [
            ("salmon.merged.gene_counts.tsv", "Gene Counts (merged TSV)"),
            ("salmon.merged.gene_counts_scaled.rds", "Gene Counts Scaled (RDS)"),
            ("salmon.merged.transcript_tpm.tsv", "Transcript TPM (TSV)"),
            ("salmon.merged.transcript_counts.tsv", "Transcript Counts (TSV)"),
            ("salmon.merged.gene_lengths.tsv", "Gene Lengths (TSV)"),
            ("tx2gene.tsv", "Transcript→Gene Map (TSV)"),
            ("quant.sf", "Salmon Quant (quant.sf)"),
            ("quant.genes.sf", "Salmon Gene Quant (quant.genes.sf)"),
            ("deseq2.dds.RData", "DESeq2 Dataset (RData)"),
        ]
        for fname, label in rna_targets:
            for f in nfcore_dir.rglob(fname):
                _add("RNA-seq Data", f, label)

        # STAR alignment log
        for f in nfcore_dir.rglob("*.Log.final.out"):
            _add("RNA-seq Data", f, f"STAR Alignment Log — {f.parent.parent.name}")

        # ── Pipeline Info ──
        for f in nfcore_dir.rglob("execution_report*.html"):
            _add("Pipeline Info", f)
        for f in nfcore_dir.rglob("execution_timeline*.html"):
            _add("Pipeline Info", f)
        for f in nfcore_dir.rglob("pipeline_dag*.html"):
            _add("Pipeline Info", f)

        return cats

    def _star_mapping_summary(self, pmid: str) -> str:
        """STAR alignment 통계 한 줄 요약."""
        from pathlib import Path as _Path
        nfcore_dir = _Path(f"results/nfcore/{pmid}")
        for log_f in nfcore_dir.rglob("*.Log.final.out"):
            try:
                text = log_f.read_text()
                mapped_pct = ""
                total_reads = ""
                for line in text.splitlines():
                    if "Uniquely mapped reads %" in line:
                        mapped_pct = line.split("|")[-1].strip()
                    if "Number of input reads" in line:
                        total_reads = line.split("|")[-1].strip()
                if mapped_pct:
                    warn = " ⚠️" if float(mapped_pct.replace("%", "")) < 5 else ""
                    return (
                        f'<p class="muted" style="font-size:0.9em">'
                        f"STAR mapping: <b>{mapped_pct}</b> uniquely mapped"
                        f" ({total_reads} reads){warn}</p>"
                    )
            except Exception:
                pass
        return ""

    def _section_footer(self, data: dict) -> str:
        return f"""
<footer>
  <p>Generated by <strong>BioAuto v4.0</strong> |
     {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</p>
</footer>"""

    # ── Project Report ──

    def generate_project_report(
        self,
        project: dict[str, Any],
        reports: list[dict[str, Any]],
        output_path: Path,
    ) -> Path:
        """
        프로젝트 종합 보고서 생성.

        Args:
            project: project.json 딕셔너리 (name, description, keywords 등)
            reports: final_report 딕셔너리 리스트
            output_path: 출력 HTML 파일 경로

        Returns:
            Path: 생성된 HTML 파일 경로
        """
        html = self._build_project_html(project, reports)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(html, encoding="utf-8")
        logger.info("프로젝트 종합 리포트 생성: %s", output_path)
        return output_path

    def _build_project_html(
        self, project: dict[str, Any], reports: list[dict[str, Any]]
    ) -> str:
        sections = [
            self._proj_header(project, reports),
            self._proj_dashboard(reports),
            self._proj_pmid_table(reports),
            self._proj_debate_synthesis(reports),
            self._proj_llm_synthesis(reports),
            self._proj_references(reports),
            self._proj_footer(project),
        ]

        name = escape(project.get("name", "Research Project"))
        return f"""<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>BioAuto Project Report - {name}</title>
{self._css()}
</head>
<body>
<div class="container">
{''.join(sections)}
</div>
</body>
</html>"""

    def _proj_header(
        self, project: dict[str, Any], reports: list[dict[str, Any]]
    ) -> str:
        name = escape(project.get("name", "Research Project"))
        desc = escape(project.get("description", ""))
        keywords = project.get("keywords", [])
        kw_html = " ".join(
            f'<span class="tag">{escape(k)}</span>' for k in keywords
        )
        n_pmids = len(reports)
        created = project.get("created_at", "")[:10]

        return f"""
<header>
  <h1>{name}</h1>
  <p class="meta">{desc}</p>
  <p class="meta">PMIDs: {n_pmids} | Created: {created}</p>
  {f'<div class="tags" style="margin-top:10px">{kw_html}</div>' if kw_html else ''}
</header>"""

    def _proj_dashboard(self, reports: list[dict[str, Any]]) -> str:
        n = len(reports)
        if n == 0:
            return '<section><h2>Dashboard</h2><p class="muted">No data</p></section>'

        scores = [r.get("debate_score", 0) for r in reports]
        avg_score = sum(scores) / n
        durations = [r.get("duration_seconds", 0) for r in reports]
        avg_dur = sum(durations) / n

        seq_types: dict[str, int] = {}
        for r in reports:
            st = r.get("sequencing_type", "unknown")
            seq_types[st] = seq_types.get(st, 0) + 1
        seq_str = ", ".join(f"{k} ({v})" for k, v in seq_types.items())

        verdicts: dict[str, int] = {}
        for r in reports:
            v = r.get("debate_verdict", "UNDETERMINED")
            verdicts[v] = verdicts.get(v, 0) + 1
        verdict_str = ", ".join(f"{k} ({v})" for k, v in verdicts.items())

        return f"""
<section>
  <h2>Research Overview</h2>
  <div class="score-cards" style="display:flex;gap:16px;flex-wrap:wrap">
    <div class="score-card" style="background:#f8f9fa;border-radius:8px;
         padding:16px;flex:1;min-width:140px;text-align:center">
      <div class="score-label">Total PMIDs</div>
      <div class="score-value">{n}</div>
    </div>
    <div class="score-card" style="background:#f8f9fa;border-radius:8px;
         padding:16px;flex:1;min-width:140px;text-align:center">
      <div class="score-label">Avg Debate Score</div>
      <div class="score-value">{avg_score:.2f}</div>
      {self._score_bar(avg_score)}
    </div>
    <div class="score-card" style="background:#f8f9fa;border-radius:8px;
         padding:16px;flex:1;min-width:140px;text-align:center">
      <div class="score-label">Avg Duration</div>
      <div class="score-value">{avg_dur:.0f}s</div>
    </div>
    <div class="score-card" style="background:#f8f9fa;border-radius:8px;
         padding:16px;flex:1;min-width:140px;text-align:center">
      <div class="score-label">Verdicts</div>
      <div class="score-value seq-type">{verdict_str}</div>
    </div>
  </div>
  <p style="margin-top:12px;font-size:13px;color:#7f8c8d">
    Sequencing types: {seq_str}</p>
</section>"""

    def _proj_pmid_table(self, reports: list[dict[str, Any]]) -> str:
        if not reports:
            return ""

        rows = []
        for r in reports:
            pmid = r.get("pmid", "N/A")
            meta = r.get("pubmed_metadata", {})
            title = escape(meta.get("title", "")[:80])
            journal = escape(meta.get("journal", "N/A"))
            seq = r.get("sequencing_type", "unknown")
            llm = r.get("llm_rating", "UNKNOWN")
            verdict = r.get("debate_verdict", "UNDETERMINED")
            score = r.get("debate_score", 0.0)
            dur = r.get("duration_seconds", 0)

            rows.append(f"""<tr>
<td><a href="{pmid}/report_{pmid}.html">{pmid}</a></td>
<td class="title-cell">{title}{'...' if len(meta.get('title', '')) > 80 else ''}</td>
<td>{escape(journal)}</td>
<td>{seq}</td>
<td><span class="badge {self._badge_class(llm)}">{llm}</span></td>
<td><span class="badge {self._badge_class(verdict)}">{verdict}</span>
    <small>({score:.2f})</small></td>
<td>{dur:.0f}s</td>
</tr>""")

        return f"""
<section>
  <h2>PMID Analysis Summary</h2>
  <table>
  <thead><tr>
    <th>PMID</th><th>Title</th><th>Journal</th><th>Sequencing</th>
    <th>LLM</th><th>Debate</th><th>Duration</th>
  </tr></thead>
  <tbody>
  {''.join(rows)}
  </tbody>
  </table>
</section>"""

    def _proj_debate_synthesis(self, reports: list[dict[str, Any]]) -> str:
        all_key_points: list[str] = []
        all_concerns: list[str] = []
        # PMID별 에이전트 요약
        pmid_summaries: list[str] = []

        for r in reports:
            pmid = r.get("pmid", "N/A")
            debate = r.get("debate_report", {})
            if not debate:
                continue

            verdict = debate.get("overall_verdict", "UNDETERMINED")
            d_score = debate.get("overall_score", 0.0)

            # 마지막 라운드의 에이전트 의견 요약
            rounds = debate.get("rounds", [])
            agent_opinions = []
            last_round = rounds[-1] if rounds else {}
            for resp in last_round.get("responses", []):
                name = escape(resp.get("agent_name", ""))
                assessment = escape(resp.get("assessment", ""))
                agent_opinions.append(
                    f"<li><strong>{name}</strong>: {assessment}</li>"
                )

            opinions_html = (
                f'<ul style="font-size:13px">{"".join(agent_opinions)}</ul>'
                if agent_opinions else ""
            )

            pmid_summaries.append(f"""
<div class="agent-response">
  <div class="agent-header">
    <strong>PMID {pmid}</strong>
    <span>판정: {verdict} | 점수: {d_score:.2f}</span>
  </div>
  {opinions_html}
</div>""")

            for rnd in rounds:
                for resp in rnd.get("responses", []):
                    for kp in resp.get("key_points", []):
                        s = str(kp).strip()
                        if s and s not in all_key_points:
                            all_key_points.append(s)
                    for c in resp.get("concerns", []):
                        s = str(c).strip()
                        if s and s not in all_concerns:
                            all_concerns.append(s)

        if not pmid_summaries and not all_key_points:
            return ""

        kp_html = "".join(
            f"<li>{escape(p)}</li>" for p in all_key_points[:30]
        )
        cc_html = "".join(
            f"<li>{escape(c)}</li>" for c in all_concerns[:30]
        )

        return f"""
<section>
  <h2>토론 종합 분석 (Cross-PMID Debate Synthesis)</h2>
  {''.join(pmid_summaries)}
  {f'<h3>주요 발견 ({len(all_key_points)}개)</h3><ul class="key-points">{kp_html}</ul>' if kp_html else ''}
  {f'<h3>우려 사항 및 한계 ({len(all_concerns)}개)</h3><ul class="concerns">{cc_html}</ul>' if cc_html else ''}
</section>"""

    def _proj_llm_synthesis(self, reports: list[dict[str, Any]]) -> str:
        consensus_data = []
        for r in reports:
            c = r.get("llm_consensus", {})
            if c:
                consensus_data.append({
                    "pmid": r.get("pmid", "N/A"),
                    "consensus": c,
                })

        if not consensus_data:
            return ""

        rows = ""
        for item in consensus_data:
            pmid = item["pmid"]
            c = item["consensus"]
            details = "; ".join(
                f"{escape(str(k))}: {escape(str(v))}"
                for k, v in c.items()
            )
            rows += f"<tr><td>{pmid}</td><td>{details}</td></tr>"

        return f"""
<section>
  <h2>LLM Consensus Comparison</h2>
  <table>
  <thead><tr><th>PMID</th><th>Consensus Details</th></tr></thead>
  <tbody>{rows}</tbody>
  </table>
</section>"""

    def _proj_references(self, reports: list[dict[str, Any]]) -> str:
        refs = []
        for r in reports:
            meta = r.get("pubmed_metadata", {})
            if not meta:
                continue
            pmid = meta.get("pmid", r.get("pmid", ""))
            title = escape(meta.get("title", "N/A"))
            authors = meta.get("authors", [])
            author_str = ", ".join(authors[:3])
            if len(authors) > 3:
                author_str += " et al."
            journal = escape(meta.get("journal", ""))
            pub_date = escape(meta.get("pub_date", ""))
            doi = meta.get("doi", "")
            doi_clean = doi.replace("doi: ", "").strip() if doi else ""
            doi_link = (
                f' | <a href="https://doi.org/{doi_clean}" '
                f'target="_blank">DOI</a>'
            ) if doi_clean else ""
            pmid_link = (
                f'<a href="https://pubmed.ncbi.nlm.nih.gov/{pmid}" '
                f'target="_blank">PubMed</a>'
            ) if pmid else ""

            refs.append(
                f"<li><strong>{title}</strong><br>"
                f"{author_str}. <em>{journal}</em> ({pub_date}). "
                f"{pmid_link}{doi_link}</li>"
            )

        if not refs:
            return ""

        return f"""
<section>
  <h2>References ({len(refs)})</h2>
  <ol>{''.join(refs)}</ol>
</section>"""

    @staticmethod
    def _proj_footer(project: dict[str, Any]) -> str:
        name = escape(project.get("name", ""))
        return f"""
<footer>
  <p>Project: {name} | Generated by <strong>BioAuto v4.0</strong> |
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
.ncbi-links { display: flex; flex-wrap: wrap; gap: 8px; margin-top: 8px; }
.ncbi-badge { display: inline-block; background: #e3f2fd; color: #1565c0;
  padding: 6px 14px; border-radius: 6px; font-size: 13px; text-decoration: none;
  border: 1px solid #bbdefb; transition: background 0.2s; }
.ncbi-badge:hover { background: #bbdefb; }
.ncbi-badge strong { margin-left: 4px; }
.report-list { list-style: none; padding: 0; }
.report-list li { padding: 6px 0; border-bottom: 1px solid #ecf0f1; }
.report-list li a { color: #2980b9; text-decoration: none; font-weight: 500; }
.report-list li a:hover { text-decoration: underline; }
.report-list .muted { font-size: 12px; color: #95a5a6; margin-left: 8px; }
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
.lang-toggle { display: flex; gap: 4px; margin: 12px 0; }
.lang-btn { padding: 6px 16px; border: 1px solid #bdc3c7; border-radius: 6px;
  background: #f8f9fa; cursor: pointer; font-size: 13px; font-weight: 500;
  color: #555; transition: all 0.2s; }
.lang-btn:hover { border-color: #3498db; color: #3498db; }
.lang-btn.active { background: #3498db; color: #fff; border-color: #3498db; }
footer { text-align: center; color: #95a5a6; font-size: 12px;
  padding: 20px; margin-top: 10px; }
a { color: #3498db; text-decoration: none; }
a:hover { text-decoration: underline; }
@media (max-width: 600px) {
  .score-cards { flex-direction: column; }
  .info-grid { grid-template-columns: 1fr; }
}
</style>"""
