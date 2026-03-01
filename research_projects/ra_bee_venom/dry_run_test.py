#!/usr/bin/env python3
"""
GSE185440 Dry-Run Test
RA synovial tissue RNA-seq 데이터로 파이프라인 전체 플로우 검증 (실행 없이)

Steps:
1. SRR accession 준비 (ENA API에서 이미 확인된 bulk RNA-seq 6개)
2. FetchNGS 커맨드 빌드 테스트
3. nf-core/rnaseq 커맨드 빌드 테스트
4. Slurm config 생성 테스트
5. Prerequisites 체크
6. Samplesheet 생성 테스트 (mock FASTQ)
7. 전체 플로우 요약
"""

import asyncio
import shutil
import sys
import tempfile
from pathlib import Path

# Add project root to path
PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))

from nextflow.config import NextflowExecutionConfig, SlurmConfig  # noqa: E402
from nextflow.executor import NextflowExecutor  # noqa: E402
from nextflow.fetchngs import FetchNGSRunner  # noqa: E402
from nextflow.samplesheet import SamplesheetGenerator  # noqa: E402
from plugins.base import PipelineDefinition  # noqa: E402

# GSE185440 bulk RNA-seq SRR accessions (RA vs OA synovial tissue)
SRR_ACCESSIONS = [
    "SRR16219828", "SRR16219829", "SRR16219830",
    "SRR16219831", "SRR16219832", "SRR16219833",
]

PASS = "\033[92m[PASS]\033[0m"
FAIL = "\033[91m[FAIL]\033[0m"
INFO = "\033[94m[INFO]\033[0m"


def step_header(num, title):
    print(f"\n{'='*60}")
    print(f"  Step {num}: {title}")
    print(f"{'='*60}")


async def main():
    print("=" * 60)
    print("  GSE185440 Dry-Run Pipeline Test")
    print("  RA vs OA Synovial Tissue RNA-seq (SRP340267)")
    print("=" * 60)

    results = {}
    tmpdir = Path(tempfile.mkdtemp(prefix="dryrun_gse185440_"))
    print(f"{INFO} Temp directory: {tmpdir}")

    try:
        # --- Step 1: SRR Accessions ---
        step_header(1, "SRR Accession 준비")
        print("  GSE185440 → SRP340267 bulk RNA-seq samples:")
        for i, srr in enumerate(SRR_ACCESSIONS, 1):
            print(f"    {i}. {srr}")
        print(f"  Total: {len(SRR_ACCESSIONS)} accessions")
        results["accessions"] = True
        print(f"  {PASS} Accessions ready")

        # --- Step 2: FetchNGS Command Build ---
        step_header(2, "FetchNGS 커맨드 빌드")
        nf_config = NextflowExecutionConfig(
            enabled=True,
            work_dir=tmpdir / "work",
            outdir=tmpdir / "output",
            profile="docker",
            genome="GRCh38",
        )
        fetchngs = FetchNGSRunner(nf_config)

        # Create accession file
        fetchngs_dir = tmpdir / "fetchngs"
        fetchngs_dir.mkdir(parents=True, exist_ok=True)
        acc_file = fetchngs._create_accession_file(SRR_ACCESSIONS, fetchngs_dir)
        print(f"  Accession file: {acc_file}")
        print("  Contents:")
        with open(acc_file) as f:
            for line in f:
                print(f"    {line.strip()}")

        # Build command
        cmd = fetchngs._build_command(acc_file, tmpdir / "fetchngs_out")
        print(f"\n  Command: {' '.join(cmd)}")

        expected_parts = ["nextflow", "run", "nf-core/fetchngs", "--input", "--outdir"]
        missing = [p for p in expected_parts if not any(p in c for c in cmd)]
        if not missing:
            results["fetchngs_cmd"] = True
            print(f"  {PASS} FetchNGS command correctly built")
        else:
            results["fetchngs_cmd"] = False
            print(f"  {FAIL} Missing parts: {missing}")

        # --- Step 3: nf-core/rnaseq Command Build ---
        step_header(3, "nf-core/rnaseq 커맨드 빌드")
        executor = NextflowExecutor(nf_config)
        pipeline_def = PipelineDefinition(
            nf_core_name="nf-core/rnaseq",
            timeout_hours=48,
            required_params=["input", "outdir", "genome"],
            analysis_type="deseq2",
        )
        dummy_samplesheet = tmpdir / "samplesheet.csv"
        dummy_samplesheet.write_text("sample,fastq_1,fastq_2,strandedness\n")

        rnaseq_cmd = executor._build_command(
            pipeline_def, dummy_samplesheet, tmpdir / "rnaseq_out"
        )
        print(f"  Command: {' '.join(rnaseq_cmd)}")

        expected_rnaseq = ["nf-core/rnaseq", "--genome", "GRCh38", "--input", "--outdir"]
        missing_rna = [p for p in expected_rnaseq if not any(p in c for c in rnaseq_cmd)]
        if not missing_rna:
            results["rnaseq_cmd"] = True
            print(f"  {PASS} RNA-seq command correctly built")
        else:
            results["rnaseq_cmd"] = False
            print(f"  {FAIL} Missing parts: {missing_rna}")

        # --- Step 4: Slurm Config Generation ---
        step_header(4, "Slurm 설정 생성")
        slurm_config = NextflowExecutionConfig(
            enabled=True,
            work_dir=tmpdir / "work",
            outdir=tmpdir / "output",
            profile="slurm",
            slurm=SlurmConfig(
                enabled=True,
                queue="bio",
                account="research_lab",
                qos="normal",
                time_limit="48:00:00",
                memory="32G",
                cpus_per_task=8,
                nodes=1,
                extra_args="--gres=gpu:1",
            ),
        )
        slurm_executor = NextflowExecutor(slurm_config)
        slurm_out = tmpdir / "slurm_test"
        slurm_out.mkdir(parents=True, exist_ok=True)
        slurm_path = slurm_executor._generate_slurm_config(slurm_out)

        if slurm_path and slurm_path.exists():
            content = slurm_path.read_text()
            print(f"  Generated: {slurm_path}")
            print("  Content:")
            for line in content.split("\n"):
                print(f"    {line}")

            checks = [
                ("executor = 'slurm'" in content, "executor = slurm"),
                ("queue = 'bio'" in content, "queue = bio"),
                ("--account=research_lab" in content, "--account"),
                ("--qos=normal" in content, "--qos"),
                ("cpus = 8" in content, "cpus = 8"),
                ("time = '48:00:00'" in content, "time_limit"),
                ("memory = '32G'" in content, "memory"),
                ("--gres=gpu:1" in content, "extra_args"),
            ]
            all_ok = True
            for check, label in checks:
                status = PASS if check else FAIL
                print(f"    {status} {label}")
                if not check:
                    all_ok = False

            results["slurm_config"] = all_ok
        else:
            results["slurm_config"] = False
            print(f"  {FAIL} Slurm config not generated")

        # --- Step 5: Prerequisites Check ---
        step_header(5, "Prerequisites 체크")
        prereqs = await executor.check_prerequisites()
        print("  Results:")
        for key, val in prereqs.items():
            status = PASS if val else "\033[93m[WARN]\033[0m"
            if key == "disk_space_gb":
                print(f"    {INFO} {key}: {val} GB")
            else:
                print(f"    {status} {key}: {val}")

        results["prerequisites"] = True  # Info-only step
        print(f"  {INFO} Prerequisites checked (missing tools expected in dev env)")

        # --- Step 6: Samplesheet Generation ---
        step_header(6, "Samplesheet 생성 (Mock FASTQ)")

        # Create mock FASTQ directory with dummy files
        mock_fastq_dir = tmpdir / "fastq"
        mock_fastq_dir.mkdir(parents=True, exist_ok=True)

        for srr in SRR_ACCESSIONS:
            # Create mock paired-end FASTQ files
            (mock_fastq_dir / f"{srr}_1.fastq.gz").write_text("mock")
            (mock_fastq_dir / f"{srr}_2.fastq.gz").write_text("mock")

        print(f"  Mock FASTQ dir: {mock_fastq_dir}")
        print(f"  Created {len(SRR_ACCESSIONS) * 2} mock FASTQ files")

        samplesheet_gen = SamplesheetGenerator()
        samplesheet_path = tmpdir / "rnaseq_samplesheet.csv"

        result_path = samplesheet_gen.generate(
            pipeline_name="nf-core/rnaseq",
            srr_accessions=SRR_ACCESSIONS,
            fastq_dir=mock_fastq_dir,
            output_path=samplesheet_path,
        )

        if result_path.exists():
            content = result_path.read_text()
            lines = content.strip().split("\n")
            print(f"\n  Generated samplesheet: {result_path}")
            print("  Content:")
            for line in lines:
                print(f"    {line}")

            # Validate
            header = lines[0].split(",")
            expected_cols = ["sample", "fastq_1", "fastq_2", "strandedness"]
            cols_match = header == expected_cols
            rows_count = len(lines) - 1  # minus header
            rows_match = rows_count == len(SRR_ACCESSIONS)

            print(f"\n    {PASS if cols_match else FAIL} Columns: {header}")
            print(f"    {PASS if rows_match else FAIL} Rows: {rows_count} (expected {len(SRR_ACCESSIONS)})")

            # Check each sample has correct paths
            all_paths_ok = True
            for i, line in enumerate(lines[1:], 1):
                parts = line.split(",")
                srr = parts[0]
                fq1 = parts[1]
                fq2 = parts[2]
                strandedness = parts[3]
                if srr not in SRR_ACCESSIONS:
                    all_paths_ok = False
                if "_1.fastq.gz" not in fq1:
                    all_paths_ok = False
                if "_2.fastq.gz" not in fq2:
                    all_paths_ok = False
                if strandedness != "auto":
                    all_paths_ok = False

            print(f"    {PASS if all_paths_ok else FAIL} All sample paths and strandedness correct")
            results["samplesheet"] = cols_match and rows_match and all_paths_ok
        else:
            results["samplesheet"] = False
            print(f"  {FAIL} Samplesheet not generated")

        # --- Step 7: Full Flow Summary ---
        step_header(7, "전체 플로우 요약")

        print("\n  Project: RA Bee Venom (GSE185440)")
        print("  Dataset: SRP340267 - RA vs OA synovial tissue")
        print(f"  Samples: {len(SRR_ACCESSIONS)} bulk RNA-seq")
        print("\n  Pipeline Flow:")
        print(f"    1. nf-core/fetchngs  → Download {len(SRR_ACCESSIONS)} SRR FASTQ files")
        print("    2. Samplesheet Gen   → Generate nf-core/rnaseq input CSV")
        print("    3. nf-core/rnaseq    → STAR alignment + Salmon quantification")
        print("    4. DESeq2 analysis   → RA vs OA differential expression")
        print("    5. Pathway analysis  → NF-κB, TNF-α, IL-6 (Melittin targets)")

        print("\n  Step Results:")
        all_pass = True
        step_names = {
            "accessions": "SRR Accessions",
            "fetchngs_cmd": "FetchNGS Command",
            "rnaseq_cmd": "RNA-seq Command",
            "slurm_config": "Slurm Config",
            "prerequisites": "Prerequisites",
            "samplesheet": "Samplesheet Gen",
        }
        for key, name in step_names.items():
            passed = results.get(key, False)
            status = PASS if passed else FAIL
            print(f"    {status} {name}")
            if not passed:
                all_pass = False

        print(f"\n{'='*60}")
        if all_pass:
            print(f"  {PASS} ALL STEPS PASSED - Pipeline ready for execution")
        else:
            failed = [n for k, n in step_names.items() if not results.get(k)]
            print(f"  {FAIL} Some steps failed: {', '.join(failed)}")
        print(f"{'='*60}")

    finally:
        # Cleanup
        shutil.rmtree(tmpdir, ignore_errors=True)
        print(f"\n{INFO} Temp directory cleaned up")


if __name__ == "__main__":
    asyncio.run(main())
