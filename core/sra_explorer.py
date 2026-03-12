#!/usr/bin/env python3
"""
SRA Explorer for Dataset Discovery
SRA/GEO 데이터셋 탐색 및 다운로드 관리
"""

import json
import os
import subprocess
import time

import pandas as pd
import requests


class SRAExplorer:
    # SRA 다운로드 기본 타임아웃 (초)
    DEFAULT_DOWNLOAD_TIMEOUT = 1800  # 30분

    def __init__(
        self,
        results_dir: str = "./results",
        download_timeout: int | None = None,
        api_timeout: int = 30,
    ):
        """SRA 탐색기 초기화

        Args:
            results_dir: 결과 저장 디렉토리
            download_timeout: SRA 다운로드 타임아웃 (초). None이면 기본값 사용.
            api_timeout: NCBI API 요청 타임아웃 (초).
        """
        self.base_url = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"
        self.sra_base_url = "https://www.ncbi.nlm.nih.gov/sra"
        self.raw_data_dir = os.path.join(results_dir, "raw_data")
        self.samplesheet_dir = results_dir
        self.download_timeout = download_timeout or self.DEFAULT_DOWNLOAD_TIMEOUT
        self.api_timeout = api_timeout

        # 디렉토리 생성
        os.makedirs(self.raw_data_dir, exist_ok=True)
        os.makedirs(self.samplesheet_dir, exist_ok=True)

    def explore_sra_datasets(self, pmid: str, sra_links: list[str]) -> dict:
        """SRA 데이터셋 탐색"""
        print(f"SRA 데이터셋 탐색: PMID {pmid}")

        results = {
            "pmid": pmid,
            "sra_links": sra_links,
            "public_sra_ids": [],
            "controlled_sra_ids": [],
            "metadata": {},
            "downloadable": False,
            "total_size_gb": 0,
            "samplesheet": ""
        }

        if not sra_links:
            print("SRA 링크 없음")
            return results

        try:
            # SRA 메타데이터 수집
            sra_metadata = self._fetch_sra_metadata(sra_links)
            results["metadata"] = sra_metadata

            # 공개 SRR ID 필터링
            public_ids, controlled_ids = self._filter_public_sra(sra_metadata)
            results["public_sra_ids"] = public_ids
            results["controlled_sra_ids"] = controlled_ids

            # 다운로드 가능 여부 확인
            if public_ids:
                results["downloadable"] = True
                # 데이터 크기 추정
                results["total_size_gb"] = self._estimate_data_size(public_ids)
                # samplesheet 생성
                samplesheet_path = self._create_samplesheet(pmid, public_ids, sra_metadata)
                results["samplesheet"] = samplesheet_path

            print(f"✅ SRA 탐색 완료: 공개 {len(public_ids)}, 제어 {len(controlled_ids)}")
            return results

        except Exception as e:
            print(f"❌ SRA 탐색 실패: {e}")
            return results

    def _fetch_sra_metadata(self, sra_links: list[str]) -> dict:
        """SRA 메타데이터 수집"""
        metadata = {}

        for sra_id in sra_links[:10]:  # 최대 10개로 제한
            try:
                print(f"SRA 메타데이터 수집: {sra_id}")

                # SRA summary API 호출
                url = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esummary.fcgi"
                params = {
                    "db": "sra",
                    "id": sra_id,
                    "retmode": "json"
                }

                response = requests.get(url, params=params, timeout=self.api_timeout)
                if response.status_code == 200:
                    data = response.json()
                    if "result" in data and sra_id in data["result"]:
                        metadata[sra_id] = data["result"][sra_id]

                time.sleep(0.5)  # API 레이트 리밋

            except Exception as e:
                print(f"SRA {sra_id} 메타데이터 수집 실패: {e}")
                continue

        return metadata

    def _filter_public_sra(self, metadata: dict) -> tuple[list[str], list[str]]:
        """공개 SRR ID 필터링"""
        public_ids = []
        controlled_ids = []

        for sra_id, meta in metadata.items():
            # SRR 접근번호 확인
            runs = meta.get("Runs", [])
            if runs:
                for run in runs:
                    run_id = run.get("acc", "")
                    if run_id.startswith("SRR"):
                        # 공개 데이터 확인 (간단한 체크)
                        if self._is_public_run(run_id):
                            public_ids.append(run_id)
                        else:
                            controlled_ids.append(run_id)

        return list(set(public_ids)), list(set(controlled_ids))

    def _is_public_run(self, run_id: str) -> bool:
        """공개 run 확인"""
        try:
            # 간단한 공개 여부 체크 (실제로는 더 복잡한 로직 필요)
            # 여기서는 모든 SRR을 공개로 가정
            return True

        except Exception:
            return False

    def _estimate_data_size(self, sra_ids: list[str]) -> float:
        """데이터 크기 추정 (GB)"""
        # 평균적으로 scRNA-seq는 5-10GB, bulk RNA-seq는 10-20GB
        # 여기서는 보수적으로 5GB per SRR로 추정
        return len(sra_ids) * 5.0

    def _create_samplesheet(self, pmid: str, sra_ids: list[str], metadata: dict) -> str:
        """samplesheet.csv 생성"""
        samplesheet_path = f"{self.samplesheet_dir}/samplesheet_{pmid}.csv"

        try:
            samples_data = []
            for sra_id in sra_ids:
                samples_data.append({
                    "sample_id": sra_id,
                    "sra_accession": sra_id,
                    "pmid": pmid,
                    "fastq_1": f"{sra_id}_1.fastq.gz",
                    "fastq_2": f"{sra_id}_2.fastq.gz"
                })

            df = pd.DataFrame(samples_data)
            df.to_csv(samplesheet_path, index=False)

            print(f"✅ Samplesheet 생성: {samplesheet_path}")
            return samplesheet_path

        except Exception as e:
            print(f"❌ Samplesheet 생성 실패: {e}")
            return ""

    def download_sra_data(self, sra_ids: list[str], max_parallel: int = 4) -> dict:
        """SRA 데이터 다운로드"""
        print(f"SRA 데이터 다운로드 시작: {len(sra_ids)}개")

        results = {
            "total_requested": len(sra_ids),
            "successful_downloads": [],
            "failed_downloads": [],
            "total_size_gb": 0,
            "download_time_seconds": 0
        }

        start_time = time.time()

        for i, sra_id in enumerate(sra_ids):
            print(f"다운로드 {i+1}/{len(sra_ids)}: {sra_id}")

            try:
                # prefetch로 SRA 다운로드
                success = self._download_single_sra(sra_id)

                if success:
                    results["successful_downloads"].append(sra_id)
                    print(f"✅ {sra_id} 다운로드 성공")
                else:
                    results["failed_downloads"].append(sra_id)
                    print(f"❌ {sra_id} 다운로드 실패")

            except Exception as e:
                results["failed_downloads"].append(sra_id)
                print(f"❌ {sra_id} 다운로드 예외: {e}")

        results["download_time_seconds"] = time.time() - start_time

        # 다운로드된 파일 크기 계산
        results["total_size_gb"] = self._calculate_downloaded_size(results["successful_downloads"])

        print(f"✅ 다운로드 완료: 성공 {len(results['successful_downloads'])}, 실패 {len(results['failed_downloads'])}")
        return results

    def _download_single_sra(self, sra_id: str) -> bool:
        """단일 SRA 다운로드"""
        try:
            # prefetch로 SRA 파일 다운로드
            cmd = ["prefetch", "--progress", sra_id]
            result = subprocess.run(
                cmd, capture_output=True, text=True,
                timeout=self.download_timeout,
            )

            if result.returncode == 0:
                # fasterq-dump로 FASTQ 변환
                cmd = ["fasterq-dump", "--split-files", "--progress", sra_id]
                result = subprocess.run(
                    cmd, capture_output=True, text=True,
                    timeout=self.download_timeout,
                )

                if result.returncode == 0:
                    # 압축
                    fastq_files = [f"{sra_id}_1.fastq", f"{sra_id}_2.fastq"]
                    for fastq_file in fastq_files:
                        if os.path.exists(fastq_file):
                            subprocess.run(["gzip", fastq_file], capture_output=True)
                    return True

            return False

        except subprocess.TimeoutExpired:
            print(f"다운로드 타임아웃: {sra_id}")
            return False
        except Exception as e:
            print(f"다운로드 실패: {sra_id} - {e}")
            return False

    def _calculate_downloaded_size(self, sra_ids: list[str]) -> float:
        """다운로드된 파일 크기 계산"""
        total_size = 0

        for sra_id in sra_ids:
            fastq_files = [f"{sra_id}_1.fastq.gz", f"{sra_id}_2.fastq.gz"]
            for fastq_file in fastq_files:
                if os.path.exists(fastq_file):
                    total_size += os.path.getsize(fastq_file)

        return total_size / (1024**3)  # GB로 변환

    def save_sra_results(self, results: dict, pmid: str) -> str:
        """SRA 탐색 결과 저장"""
        filename = os.path.join(self.samplesheet_dir, f"sra_exploration_{pmid}.json")

        try:
            with open(filename, 'w', encoding='utf-8') as f:
                json.dump(results, f, indent=2, ensure_ascii=False)
            print(f"SRA 결과 저장: {filename}")
            return filename

        except Exception as e:
            print(f"SRA 결과 저장 실패: {e}")
            return ""

def main():
    """테스트 실행"""
    print("=== SRA 탐색기 테스트 ===")

    explorer = SRAExplorer()

    # 테스트용 SRA 링크
    test_sra_links = ["SRR25872668", "SRR25872669"]  # 예시 ID

    # SRA 탐색
    results = explorer.explore_sra_datasets("40315330", test_sra_links)

    # 결과 출력
    print(f"공개 SRA: {results['public_sra_ids']}")
    print(f"제어 SRA: {results['controlled_sra_ids']}")
    print(f"다운로드 가능: {results['downloadable']}")
    print(f"예상 크기: {results['total_size_gb']} GB")

    # 결과 저장
    explorer.save_sra_results(results, "40315330")

if __name__ == "__main__":
    main()
