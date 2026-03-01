#!/usr/bin/env python3
"""
Test Data Generator for Pipeline Testing
테스트용 가상 데이터 생성
"""

import json
from datetime import datetime


def create_test_pubmed_data(pmid):
    """테스트용 PubMed 데이터 생성"""

    if pmid == "40315330":
        return {
            "pmid": pmid,
            "title": "Single-cell RNA sequencing reveals cellular heterogeneity in tumor microenvironment",
            "authors": ["Smith J", "Johnson K", "Lee M"],
            "journal": "Nature Biotechnology",
            "pub_date": "2024 Jan",
            "abstract": "We performed single-cell RNA sequencing using 10x Genomics platform to analyze cellular heterogeneity in tumor microenvironment. Our analysis identified distinct cell populations including T cells, B cells, and cancer-associated fibroblasts. The scRNA-seq data revealed novel therapeutic targets and provided insights into immune evasion mechanisms. UMI-based counting was used for accurate quantification of gene expression across thousands of single cells.",
            "keywords": ["single-cell", "RNA-seq", "10x Genomics", "tumor microenvironment", "UMI"],
            "sra_links": ["SRR25872668", "SRR25872669"],
            "geo_links": [],
            "doi": "10.1038/nbt.2024.123",
            "retrieved_at": datetime.now().isoformat()
        }
    elif pmid == "32416070":
        return {
            "pmid": pmid,
            "title": "Bulk RNA-seq analysis of gene expression changes in response to immunotherapy",
            "authors": ["Chen X", "Wang Y", "Zhang L"],
            "journal": "Cancer Research",
            "pub_date": "2024 Feb",
            "abstract": "We conducted bulk RNA-seq analysis to investigate gene expression changes in cancer patients responding to immunotherapy. Total RNA was extracted from tumor samples before and after treatment, and polyA-selected libraries were prepared. Differential expression analysis identified key pathways involved in treatment response. The bulk RNA-seq data showed consistent upregulation of interferon-stimulated genes in responders compared to non-responders.",
            "keywords": ["bulk RNA-seq", "gene expression", "immunotherapy", "polyA selection"],
            "sra_links": ["SRR25872670", "SRR25872671"],
            "geo_links": [],
            "doi": "10.1158/0008-5472.CAN-24-123",
            "retrieved_at": datetime.now().isoformat()
        }
    else:
        return None

def create_test_sra_data(pmid, sra_links):
    """테스트용 SRA 데이터 생성"""
    return {
        "pmid": pmid,
        "sra_links": sra_links,
        "public_sra_ids": sra_links,
        "controlled_sra_ids": [],
        "metadata": {
            sra_id: {
                "LibStrategy": "SINGLE_CELL" if "40315330" in pmid else "RNA-SEQ",
                "LibSource": "TRANSCRIPTOMIC",
                "LibSelection": "cDNA" if "40315330" in pmid else "POLY_A"
            } for sra_id in sra_links
        },
        "downloadable": True,
        "total_size_gb": len(sra_links) * 8.5,
        "samplesheet": f"/workspace/results/samplesheet_{pmid}.csv"
    }

def save_test_data():
    """테스트 데이터 저장"""
    # PMID 40315330 데이터 (scRNA-seq)
    pubmed_40315330 = create_test_pubmed_data("40315330")
    sra_40315330 = create_test_sra_data("40315330", ["SRR25872668", "SRR25872669"])

    # PMID 32416070 데이터 (bulk RNA-seq)
    pubmed_32416070 = create_test_pubmed_data("32416070")
    sra_32416070 = create_test_sra_data("32416070", ["SRR25872670", "SRR25872671"])

    # 저장
    with open("/workspace/results/pubmed_40315330.json", 'w') as f:
        json.dump(pubmed_40315330, f, indent=2)

    with open("/workspace/results/pubmed_32416070.json", 'w') as f:
        json.dump(pubmed_32416070, f, indent=2)

    with open("/workspace/results/sra_exploration_40315330.json", 'w') as f:
        json.dump(sra_40315330, f, indent=2)

    with open("/workspace/results/sra_exploration_32416070.json", 'w') as f:
        json.dump(sra_32416070, f, indent=2)

    # samplesheet 생성
    create_samplesheet("40315330", ["SRR25872668", "SRR25872669"])
    create_samplesheet("32416070", ["SRR25872670", "SRR25872671"])

    print("✅ 테스트 데이터 생성 완료")

def create_samplesheet(pmid, sra_ids):
    """samplesheet.csv 생성"""
    import csv

    filename = f"/workspace/results/samplesheet_{pmid}.csv"

    with open(filename, 'w', newline='') as f:
        writer = csv.writer(f)
        writer.writerow(['sample_id', 'sra_accession', 'pmid', 'fastq_1', 'fastq_2'])

        for sra_id in sra_ids:
            writer.writerow([
                sra_id,
                sra_id,
                pmid,
                f"{sra_id}_1.fastq.gz",
                f"{sra_id}_2.fastq.gz"
            ])

    print(f"✅ Samplesheet 생성: {filename}")

if __name__ == "__main__":
    import os
    os.makedirs("/workspace/results", exist_ok=True)
    save_test_data()
