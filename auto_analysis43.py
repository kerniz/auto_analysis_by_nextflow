ut#!/usr/bin/env python3
import subprocess
import sys
import re
import glob
import json
from pathlib import Path

import requests
import pandas as pd
from Bio import Entrez

ENTREZ_EMAIL = "kerniz@nate.com"

########################################
# 1. 논문 평가 및 메타데이터
########################################

def check_paper_reputation(pmid):
    """논문 평가 사이트들 체크"""
    results = {}

    # 1. PubPeer
    try:
        url = f"https://pubpeer.com/v3/publications/{pmid}"
        r = requests.get(url, timeout=10)
        if r.status_code == 200:
            data = r.json()
            results['pubpeer'] = {
                'comments': data.get('total_comments', 0),
                'url': f"https://pubpeer.com/publications/{pmid}"
            }
        else:
            print(f"[INFO] PubPeer API returned status {r.status_code}")
            results['pubpeer'] = None
    except Exception as e:
        print(f"[INFO] PubPeer check failed: {e}")
        results['pubpeer'] = None

    # 2. Altmetric
    try:
        url = f"https://api.altmetric.com/v1/pmid/{pmid}"
        r = requests.get(url, timeout=10)
        if r.status_code == 200:
            data = r.json()
            results['altmetric'] = {
                'score': data.get('score'),
                'news': data.get('cited_by_msm_count', 0),
                'twitter': data.get('cited_by_tweeters_count', 0),
                'url': data.get('details_url')
            }
        else:
            print(f"[INFO] Altmetric API returned status {r.status_code}")
            results['altmetric'] = None
    except Exception as e:
        print(f"[INFO] Altmetric check failed: {e}")
        results['altmetric'] = None

    # 3. Scite
    results['scite_url'] = f"https://scite.ai/reports/{pmid}"

    # 4. Semantic Scholar
    try:
        url = f"https://api.semanticscholar.org/v1/paper/PMID:{pmid}"
        r = requests.get(url, timeout=10)
        if r.status_code == 200:
            data = r.json()
            results['semantic_scholar'] = {
                'citations': data.get('citationCount', 0),
                'influential_citations': data.get('influentialCitationCount', 0),
                'url': f"https://www.semanticscholar.org/paper/{data.get('paperId')}"
            }
        else:
            print(f"[INFO] Semantic Scholar API returned status {r.status_code}")
            results['semantic_scholar'] = None
    except Exception as e:
        print(f"[INFO] Semantic Scholar check failed: {e}")
        results['semantic_scholar'] = None

    return results

def pmid_to_srp(pmid):
    """PubMed ID → SRA Project ID"""
    try:
        handle = Entrez.elink(dbfrom="pubmed", db="sra", id=pmid)
        record = Entrez.read(handle)

        if not record[0].get("LinkSetDb"):
            return None

        uid = record[0]["LinkSetDb"][0]["Link"][0]["Id"]
        handle = Entrez.esummary(db="sra", id=uid)
        summary = Entrez.read(handle)

        # SRP ID 추출
        expxml = summary[0]["ExpXml"]
        srp = re.search(r'<Study acc="(SRP\d+)"', expxml)
        return srp.group(1) if srp else None
    except Exception as e:
        print(f"[WARN] Failed to get SRP from PMID: {e}")
        return None

def download_counts_via_recount3(srp_id):
    """recount3로 count matrix 다운로드"""
    r_script = f"""
    library(recount3)
    library(SummarizedExperiment)

    # 프로젝트 정보 가져오기
    projects <- available_projects()
    proj <- subset(projects, project == "{srp_id}")

    if (nrow(proj) == 0) {{
        stop("Project not found in recount3")
    }}

    # count matrix 다운로드
    rse <- create_rse(proj)

    # CSV로 저장
    counts <- assay(rse, "raw_counts")
    write.csv(counts, "recount3_counts.csv")

    # 메타데이터 저장
    metadata <- colData(rse)
    write.csv(as.data.frame(metadata), "recount3_metadata.csv")
    """

    with open("download_counts.R", "w") as f:
        f.write(r_script)

    result = subprocess.run(["Rscript", "download_counts.R"], check=True, capture_output=True, text=True)

    if result.returncode != 0:
        raise RuntimeError(f"R script failed: {result.stderr}")

    counts = pd.read_csv("recount3_counts.csv", index_col=0)
    metadata = pd.read_csv("recount3_metadata.csv", index_col=0)

    return counts, metadata

########################################
# 2. 환경 검증
########################################

REQUIRED_CMDS = ["nextflow"]

def check_environment():
    print("[CHECK] Environment")

    # Nextflow 필수
    if subprocess.run("which nextflow", shell=True,
                     stdout=subprocess.DEVNULL).returncode != 0:
        raise RuntimeError("nextflow not found")

    # prefetch 확인 (경고만)
    if subprocess.run("which prefetch", shell=True,
                     stdout=subprocess.DEVNULL).returncode != 0:
        print("[WARN] prefetch not found - fallback unavailable")

    print("[OK] Environment ready\n")

########################################
# 3. BioProject → SRR
########################################

def download_sra_runinfo(bioproject_id: str, max_samples=None) -> list:
    """SRA Run Selector에서 RunInfo 다운로드"""
    url = f"https://trace.ncbi.nlm.nih.gov/Traces/sra-db-be/run_selector?acc={bioproject_id}&format=csv"
    df = pd.read_csv(url)
    srr_ids = df['Run'].tolist()

    if max_samples:
        srr_ids = srr_ids[:max_samples]
        print(f"[INFO] Limited to {max_samples} samples")

    return srr_ids

def paper_to_sra(pmid: str, max_ids=10):
    Entrez.email = ENTREZ_EMAIL
    sra_ids = set()

    print(f"[STEP 1] Searching SRA for PMID {pmid}")

    try:
        handle = Entrez.elink(dbfrom="pubmed", db="sra", id=pmid)
        record = Entrez.read(handle)

        links = record[0].get("LinkSetDb", [])
        if not links:
            raise ValueError("No SRA links")

        uids = [l["Id"] for l in links[0]["Link"]]
        handle = Entrez.esummary(db="sra", id=",".join(uids))
        summary = Entrez.read(handle)

        docs = summary["DocumentSummarySet"]["DocumentSummary"]

        for doc in docs:
            expxml = doc.get("ExpXml", "")
            runs = re.findall(r'acc="([SED]R[RX]\d+)"', expxml)
            sra_ids.update(runs)

    except Exception as e:
        print(f"[WARN] Entrez failed: {e}")
        print("[INFO] Falling back to web scraping")

        try:
            url = f"https://www.ncbi.nlm.nih.gov/sra?linkname=pubmed_sra&from_uid={pmid}"
            r = requests.get(url, timeout=10)
            r.raise_for_status()
            sra_ids.update(re.findall(r'([SED]R[RX]\d+)', r.text))
        except Exception as e2:
            print(f"[ERROR] Web scraping failed: {e2}")

    sra_ids = list(sra_ids)[:max_ids]

    if not sra_ids:
        print("[WARN] No direct SRA found")
        return []

    print(f"[OK] Found SRA IDs: {sra_ids}\n")
    return sra_ids

def pmid_to_srr_via_geo(input_id):
    """PubMed ID를 GEO ID로 변환하고, GEO를 통해 SRA ID를 가져옵니다."""
    print(f"[INFO] Getting SRA IDs from GEO via PubMed ID {input_id}...")
    sra_ids = []
    print(f"[INFO] Found {len(sra_ids)} SRA IDs from GEO.")
    return sra_ids

########################################
# 4. 파이프라인 검색
########################################

def detect_pipeline(sra_ids):
    """SRA 메타데이터로 파이프라인 자동 감지"""
    try:
        acc = sra_ids[0]
        if acc.startswith('SRX'):
            url = f"https://trace.ncbi.nlm.nih.gov/Traces/sra-db-be/run_selector?acc={acc}&format=json"
            data = requests.get(url, timeout=10).json()
            acc = data[0]['Run']

        url = f"https://trace.ncbi.nlm.nih.gov/Traces/sra-db-be/run?acc={acc}&format=json"
        data = requests.get(url, timeout=10).json()
        strategy = data[0].get("library_strategy", "RNA-Seq")

        pipeline_map = {
            "RNA-Seq": "rnaseq",
            "ChIP-Seq": "chipseq",
            "ATAC-Seq": "atacseq",
            "WGS": "sarek",
            "WES": "sarek",
            "scRNA-Seq": "scrnaseq",
            "Bisulfite-Seq": "methylseq",
            "AMPLICON": "ampliseq",
            "CUT&RUN": "cutandrun",
        }

        return pipeline_map.get(strategy)
    except Exception as e:
        print(f"[WARN] Pipeline detection failed: {e}")
        return None

########################################
# 5. 다운로드 (recount3 → fetchngs → prefetch)
########################################

def create_nextflow_config():
    """Nextflow DNS 설정 파일 생성"""
    config = """
        apptainer {
            enabled    = true
            autoMounts = true
            runOptions = '-e'
         }
    """
    with open("nextflow.config", "w") as f:
        f.write(config)
    print("[OK] Created nextflow.config\n")

def run_fetchngs(sra_ids, profile="apptainer"):
    """nf-core/fetchngs 다운로드"""
    print("[STEP 2] Running nf-core/fetchngs")

    with open("sra_ids.csv", "w") as f:
        for i in sra_ids:
            f.write(f"{i}\n")

    SUPPORTED = {"rnaseq", "atacseq", "chipseq", "taxprofiler", "viralrecon"}
    pipeline = detect_pipeline(sra_ids)

    cmd = (
        "nextflow run nf-core/fetchngs "
        "-r 1.12.0 "
        "-c nextflow.config "
        "--input sra_ids.csv "
        "--outdir fastq_data "
        f"-profile {profile} "
        "--download_method sratools "
        "-resume "
    )

    if pipeline:
        if pipeline not in SUPPORTED:
            print(f"[WARN] {pipeline} may not be fully supported by fetchngs")
        cmd += f" --nf_core_pipeline {pipeline}"

    create_nextflow_config()
    print(f"[CMD] {cmd}\n")

    result = subprocess.run(cmd, shell=True)

    if result.returncode != 0:
        print(f"\n[ERROR] fetchngs failed with exit code {result.returncode}")
        print("[INFO] Check .nextflow.log for details")
        raise RuntimeError(f"fetchngs failed (exit code {result.returncode})")

    print("[OK] fetchngs finished\n")

def download_from_ncbi(sra_ids):
    """prefetch + fasterq-dump 직접 다운로드"""
    print("[STEP 2-FALLBACK] Downloading from NCBI")

    out_dir = Path("fastq_data/fastq").resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    for sra_id in sra_ids:
        sra_id = sra_id.strip()
        if not sra_id:
            continue

        print(f"--- Processing {sra_id} ---")
        try:
            print(f"  [1/3] Prefetching {sra_id}...")
            subprocess.run(f"prefetch {sra_id} --max-size 100G", shell=True, check=True)

            print(f"  [2/3] Converting {sra_id} to FastQ...")
            subprocess.run(
                f"fasterq-dump {sra_id} --split-files -O {out_dir} -p",
                shell=True, check=True, timeout=3600
            )

            print(f"  [3/3] Compressing {sra_id}...")
            subprocess.run(f"gzip -f {out_dir}/{sra_id}*.fastq", shell=True, check=True)

            print(f"  ✓ {sra_id} completed successfully.")

        except subprocess.CalledProcessError as e:
            print(f"  ✗ {sra_id} failed during command: {e.cmd}")
        except Exception as e:
            print(f"  ✗ {sra_id} unexpected error: {e}")

    print("\n[OK] All SRA processing finished\n")

def download_data(sra_ids, profile="apptainer", pmid=None):
    """recount3 우선 시도 → 실패 시 fetchngs → prefetch"""

    # recount3 시도
    if pmid:
        srp_id = pmid_to_srp(pmid)
        if srp_id:
            try:
                print(f"[INFO] Trying recount3 for SRP {srp_id}...")
                counts, metadata = download_counts_via_recount3(srp_id)

                Path("results/star_salmon").mkdir(parents=True, exist_ok=True)
                counts.to_csv("results/star_salmon/recount3_counts.tsv", sep='\t')
                metadata.to_csv("results/star_salmon/recount3_metadata.tsv", sep='\t')

                print(f"[OK] Downloaded via recount3: {counts.shape[0]} genes x {counts.shape[1]} samples")
                return True

            except Exception as e:
                print(f"[WARN] recount3 failed: {e}")
                print("[INFO] Falling back to nf-core/fetchngs...")

    # 기존 방식
    try:
        run_fetchngs(sra_ids, profile)
    except Exception as e:
        print(f"[WARN] fetchngs failed: {e}")
        print("[INFO] Falling back to prefetch...")
        download_from_ncbi(sra_ids)

    return False

########################################
# 6. samplesheet 자동 생성
########################################

def detect_layout_from_api(srr_id):
    """SRA API로 SE/PE 확인"""
    try:
        url = f"https://trace.ncbi.nlm.nih.gov/Traces/sra-db-be/run?acc={srr_id}&format=json"
        data = requests.get(url, timeout=10).json()
        layout = data[0].get("LibraryLayout", "")
        return layout if layout in ["SINGLE", "PAIRED"] else None
    except:
        return None

def detect_layout_from_files(files):
    """파일 개수로 SE/PE 판단"""
    return "SINGLE" if len(files) == 1 else "PAIRED"

def detect_strandedness_from_api(srr_id):
    """SRA API로 strandedness 자동 판단"""
    try:
        url = f"https://trace.ncbi.nlm.nih.gov/Traces/sra-db-be/run?acc={srr_id}&format=json"
        data = requests.get(url, timeout=10).json()

        lib_selection = data[0].get("library_selection", "").lower()

        # TruSeq/NEBNext/dUTP 기반 → reverse
        if any(x in lib_selection for x in ["stranded", "dutp", "truseq", "nebnext"]):
            return "reverse"

        # SMARTer/SMART-Seq → forward
        if any(x in lib_selection for x in ["smart", "5-methylcytidine"]):
            return "forward"

        return "unstranded"

    except Exception as e:
        print(f"[WARN] Strandedness detection failed for {srr_id}: {e}")
        return "auto"

def create_samplesheet():
    """samplesheet 자동 생성"""
    print("[STEP 3] Creating samplesheet")

    # Option 1: fetchngs samplesheet 확인
    fetchngs_sheet = Path("fastq_data/samplesheet/samplesheet.csv")
    if fetchngs_sheet.exists():
        print("[INFO] Using fetchngs samplesheet")
        df = pd.read_csv(fetchngs_sheet)

        if 'strandedness' not in df.columns or df['strandedness'].isna().any():
            print("[INFO] Detecting strandedness from API...")
            df['strandedness'] = df['sample'].apply(detect_strandedness_from_api)

        df.to_csv("samplesheet.csv", index=False)
        print(f"[OK] Created samplesheet with {len(df)} samples\n")
        return

    # Option 2: FASTQ 파일로 직접 생성
    fastqs = glob.glob("fastq_data/fastq/*fastq.gz")
    if not fastqs:
        raise RuntimeError("No FASTQ files found")

    samples = {}
    for fq in fastqs:
        name = Path(fq).name
        sid = name.split("_")[0]
        samples.setdefault(sid, []).append(fq)

    with open("samplesheet.csv", "w") as f:
        f.write("sample,fastq_1,fastq_2,strandedness\n")

        for sid, files in samples.items():
            files = sorted(files)

            layout = detect_layout_from_api(sid)
            if not layout:
                layout = detect_layout_from_files(files)
                print(f"[INFO] {sid}: API failed, using file count → {layout}")

            strandedness = detect_strandedness_from_api(sid)

            if layout == "SINGLE":
                f.write(f"{sid},{files[0]},,{strandedness}\n")
            else:
                if len(files) < 2:
                    print(f"[WARN] {sid}: Expected PE but only 1 file, using SE")
                    f.write(f"{sid},{files[0]},,{strandedness}\n")
                else:
                    f.write(f"{sid},{files[0]},{files[1]},{strandedness}\n")

    print(f"[OK] Created samplesheet with {len(samples)} samples\n")

########################################
# 7. nf-core/rnaseq 실행
########################################

def run_rnaseq(profile="apptainer"):
    print("[STEP 4] Running nf-core/rnaseq")

    cmd = (
        f"nextflow run nf-core/rnaseq "
        f"-profile {profile} "
        f"--input samplesheet.csv "
        f"--outdir results "
        f"--genome GRCh38 "
        f"-resume"
    )

    print(f"[CMD] {cmd}\n")
    result = subprocess.run(cmd, shell=True)

    if result.returncode != 0:
        raise RuntimeError(f"rnaseq failed (exit code {result.returncode})")

    print("[OK] rnaseq finished\n")

########################################
# 8. 결과 분석
########################################

def fetch_paper_abstract(pmid):
    """PubMed에서 논문 초록 가져오기"""
    try:
        Entrez.email = ENTREZ_EMAIL
        handle = Entrez.efetch(db="pubmed", id=pmid, rettype="abstract", retmode="text")
        abstract = handle.read()
        return abstract
    except Exception as e:
        print(f"[WARN] Failed to fetch abstract: {e}")
        return None

def fetch_pmc_fulltext(pmid):
    """PMC에서 전문 가져오기"""
    try:
        Entrez.email = ENTREZ_EMAIL

        handle = Entrez.elink(dbfrom="pubmed", db="pmc", id=pmid)
        record = Entrez.read(handle)
        pmc_id = record[0]['LinkSetDb'][0]['Link'][0]['Id']

        handle = Entrez.efetch(db="pmc", id=pmc_id, rettype="full", retmode="text")
        fulltext = handle.read()

        if len(fulltext) > 5000:
            fulltext = fulltext[:5000] + "...(truncated)"

        return fulltext
    except Exception as e:
        print(f"[WARN] PMC fulltext not available: {e}")
        return None

def analyze_results_with_llm(pmid=None, results_dir="results"):
    """결과 파일 분석 및 LLM 요약"""
    print("[STEP 5] Analyzing results with LLM")

    results = {}

    # 1. Count 파일 통계
    count_file = f"{results_dir}/star_salmon/salmon.merged.gene_counts.tsv"
    recount3_file = f"{results_dir}/star_salmon/recount3_counts.tsv"

    if Path(recount3_file).exists():
        try:
            df = pd.read_csv(recount3_file, sep='\t', index_col=0)
            sample_cols = list(df.columns)

            results['total_genes'] = len(df)
            results['samples'] = sample_cols
            results['avg_counts'] = float(df.mean().mean())
            results['source'] = 'recount3'
            print(f"[OK] Parsed recount3: {len(df)} genes, {len(sample_cols)} samples")
        except Exception as e:
            print(f"[WARN] recount3 parse error: {e}")
            return {"status": "parse_error"}

    elif Path(count_file).exists():
        try:
            df = pd.read_csv(count_file, sep='\t')
            sample_cols = [c for c in df.columns if c.startswith('SRX') or c.startswith('SRR')]

            if sample_cols:
                results['total_genes'] = len(df)
                results['samples'] = sample_cols
                results['avg_counts'] = float(df[sample_cols].mean().mean())
                results['source'] = 'nf-core'
                print(f"[OK] Parsed {len(df)} genes, {len(sample_cols)} samples")
        except Exception as e:
            print(f"[WARN] Count file parse error: {e}")
            return {"status": "parse_error"}

    else:
        return {"status": "no_results"}

    # 2. MultiQC 데이터 추출
    multiqc_data = f"{results_dir}/multiqc/star_salmon/multiqc_report_data/multiqc_general_stats.txt"

    if Path(multiqc_data).exists():
        try:
            stats = pd.read_csv(multiqc_data, sep='\t')
            print(f"[OK] Found MultiQC stats")

            if 'fastqc_raw-total_sequences' in stats.columns:
                total_millions = stats['fastqc_raw-total_sequences'].sum()
                results['total_reads_millions'] = round(total_millions, 2)
                results['total_reads'] = int(total_millions * 1_000_000)

                results['reads_per_sample_millions'] = {
                    'min': round(stats['fastqc_raw-total_sequences'].min(), 2),
                    'max': round(stats['fastqc_raw-total_sequences'].max(), 2),
                    'mean': round(stats['fastqc_raw-total_sequences'].mean(), 2)
                }

            if 'star-uniquely_mapped_percent' in stats.columns:
                results['mapping_rate'] = float(stats['star-uniquely_mapped_percent'].mean())

        except Exception as e:
            print(f"[WARN] MultiQC parse error: {e}")

    # 3. 논문 가져오기
    paper_context = ""
    if pmid:
        print("[INFO] Fetching paper reputation...")
        reputation = check_paper_reputation(pmid)
        results['reputation'] = reputation

        print(f"\n=== Paper Reputation Report: PMID {pmid} ===\n")

        if reputation['pubpeer']:
            print(f"[PubPeer] {reputation['pubpeer']['comments']} comments")
            print(f"  → {reputation['pubpeer']['url']}\n")

        if reputation['altmetric']:
            print(f"[Altmetric] Score: {reputation['altmetric']['score']}")
            print(f"  News mentions: {reputation['altmetric']['news']}")
            print(f"  Twitter mentions: {reputation['altmetric']['twitter']}")
            print(f"  → {reputation['altmetric']['url']}\n")

        print(f"[Scite] → {reputation['scite_url']}\n")

        if reputation['semantic_scholar']:
            print(f"[Semantic Scholar] {reputation['semantic_scholar']['citations']} citations")
            print(f"  Influential: {reputation['semantic_scholar']['influential_citations']}")
            print(f"  → {reputation['semantic_scholar']['url']}\n")

        print("[INFO] Fetching paper from PMC...")
        fulltext = fetch_pmc_fulltext(pmid)

        if fulltext:
            paper_context = f"\n\n원본 논문 전문:\n{fulltext}\n"
            print("[OK] Using PMC fulltext")
        else:
            print("[INFO] PMC unavailable, using abstract...")
            abstract = fetch_paper_abstract(pmid)
            if abstract:
                paper_context = f"\n\n원본 논문 초록:\n{abstract}\n"
                print("[OK] Using abstract")

    # 4. Ollama로 비교 분석
    mapping_rate_str = f"{results['mapping_rate']:.2f}%" if 'mapping_rate' in results else 'N/A'

    reads_info = ""
    if 'total_reads_millions' in results:
        reads_info = f"- 총 리드 수: {results['total_reads_millions']:.1f}M ({results['total_reads']:,} reads)\n"

        if 'reads_per_sample_millions' in results:
            rps = results['reads_per_sample_millions']
            reads_info += f"- 샘플당 리드 수: 평균 {rps['mean']:.1f}M (범위: {rps['min']:.1f}M ~ {rps['max']:.1f}M)\n"

    prompt = f"""
RNA-seq 재분석 결과:
- 총 유전자 수: {results.get('total_genes', 'N/A'):,}
- 샘플 수: {len(results.get('samples', []))}
{reads_info}- 평균 uniquely mapped rate: {mapping_rate_str}
{paper_context}

다음을 25줄내로 요약:
1. 재분석 결과 품질 평가 (리드 수와 매핑률 기준으로 실질적 평가)
2. 낮은 매핑률의 가능한 원인 (참조 게놈 미스매치, 오염, RNA 품질 등)
3. 논문 주장(인터페론 반응 지연, 과도한 염증)과의 비교 가능성
4. 추가로 필요한 분석 (DEG, pathway enrichment 등)
"""

    try:
        response = requests.post(
            "http://localhost:11434/api/generate",
            json={"model": "gemma3:27b", "prompt": prompt, "stream": False},
            timeout=120
        )
        summary = response.json().get('response', '')
        results['llm_summary'] = summary
        print(f"\n[AI 비교 분석]\n{summary}\n")
    except Exception as e:
        print(f"[WARN] LLM summary failed: {e}")

    return results

########################################
# 9. 전체 파이프라인
########################################

def paper_to_analysis(input_id, profile="apptainer", max_samples=None):
    check_environment()

    pmid = None

    if input_id.startswith("PRJNA") or input_id.startswith("GSE"):
        sra_ids = download_sra_runinfo(input_id, max_samples)
    else:
        print("[INFO] Trying PMID...")
        pmid = input_id
        sra_ids = paper_to_sra(pmid)

        if not sra_ids:
            print("[INFO] Trying GEO fallback...")
            sra_ids = pmid_to_srr_via_geo(input_id)

    if not sra_ids:
        raise RuntimeError("No SRA found")

    downloaded_via_recount3 = download_data(sra_ids, profile, pmid)

    if not downloaded_via_recount3:
        create_samplesheet()
        run_rnaseq(profile)

    return analyze_results_with_llm(pmid=pmid)

########################################
# 10. CLI
########################################

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description='Automated RNA-seq analysis')
    parser.add_argument('input_id', nargs='?', help='PRJNA/GSE/PMID')
    parser.add_argument('--max-samples', type=int, help='Max samples to process')
    parser.add_argument('--summarize-only', action='store_true',
                       help='Only run LLM summary on existing results')
    parser.add_argument('--pmid', help='PMID for paper comparison (summary only)')
    parser.add_argument('--results-dir', default='results',
                       help='Results directory path')

    args = parser.parse_args()

    try:
        if args.summarize_only:
            result = analyze_results_with_llm(
                pmid=args.pmid,
                results_dir=args.results_dir
            )
            print("\n[SUCCESS] Summary completed")
        else:
            if not args.input_id:
                parser.error("input_id required for full pipeline")
            result = paper_to_analysis(args.input_id, max_samples=args.max_samples)
            print("\n[SUCCESS] Pipeline completed")

        print(json.dumps(result, indent=2, ensure_ascii=False))

    except Exception as e:
        print(f"\n[FAILED] {e}")
        sys.exit(1)
