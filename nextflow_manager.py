#!/usr/bin/env python3
"""
Nextflow Pipeline Manager
nf-core 파이프라인 실행 관리
"""

import subprocess
import json
import os
import sys
import time
from typing import Dict, List, Optional, Tuple
from datetime import datetime

class NextflowManager:
    def __init__(self):
        """Nextflow 관리자 초기화"""
        self.nextflow_cmd = "nextflow"
        self.work_dir = "/workspace/nextflow_work"
        self.cache_dir = "/workspace/containers"
        self.results_dir = "/workspace/results"
        
        # 디렉토리 생성
        os.makedirs(self.work_dir, exist_ok=True)
        os.makedirs(self.cache_dir, exist_ok=True)
        os.makedirs(self.results_dir, exist_ok=True)
    
    def check_nextflow_installation(self) -> bool:
        """Nextflow 설치 확인"""
        try:
            result = subprocess.run([self.nextflow_cmd, "-version"], 
                                  capture_output=True, text=True, timeout=30)
            if result.returncode == 0:
                version = result.stdout.strip()
                print(f"✅ Nextflow 설치 확인: {version}")
                return True
            else:
                print("❌ Nextflow 설치되지 않음")
                return False
        except Exception as e:
            print(f"❌ Nextflow 확인 실패: {e}")
            return False
    
    def check_container_runtime(self) -> Tuple[str, bool]:
        """컨테이너 런타임 확인"""
        # Apptainer 확인
        try:
            result = subprocess.run(["apptainer", "--version"], 
                                  capture_output=True, text=True, timeout=10)
            if result.returncode == 0:
                version = result.stdout.strip()
                print(f"✅ Apptainer 확인: {version}")
                return "apptainer", True
        except Exception:
            pass
        
        # Singularity 확인
        try:
            result = subprocess.run(["singularity", "--version"], 
                                  capture_output=True, text=True, timeout=10)
            if result.returncode == 0:
                version = result.stdout.strip()
                print(f"✅ Singularity 확인: {version}")
                return "singularity", True
        except Exception:
            pass
        
        print("❌ 컨테이너 런타임 없음")
        return "none", False
    
    def pull_nfcore_pipeline(self, pipeline_name: str) -> bool:
        """nf-core 파이프라인 다운로드"""
        print(f"nf-core 파이프라인 다운로드: {pipeline_name}")
        
        try:
            # nf-core 설정
            cmd = [
                self.nextflow_cmd, "pull", pipeline_name,
                "-profile", "singularity"
            ]
            
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=600)  # 10분 타임아웃
            
            if result.returncode == 0:
                print(f"✅ 파이프라인 다운로드 성공: {pipeline_name}")
                return True
            else:
                print(f"❌ 파이프라인 다운로드 실패: {result.stderr}")
                return False
                
        except Exception as e:
            print(f"❌ 파이프라인 다운로드 예외: {e}")
            return False
    
    def generate_nextflow_config(self, pipeline_name: str, container_runtime: str) -> str:
        """Nextflow 설정 파일 생성"""
        config_content = f"""
# Nextflow Configuration for {pipeline_name}
# Generated at {datetime.now().isoformat()}

workDir = '{self.work_dir}'
cacheDir = '{self.cache_dir}'

# Process 설정
process {{
    executor = 'local'
    cpus = 4
    memory = '16 GB'
    time = '24h'
    
    // 컨테이너 설정
    if (workflow.containerEngine == '{container_runtime}') {{
        container = 'nf-core/{pipeline_name}:latest'
    }}
    
    // 에러 처리
    errorStrategy = 'retry'
    maxRetries = 3
    maxErrors = 5
}}

# 실행 설정
timeline {{
    enabled = true
    file = '{self.results_dir}/timeline_{pipeline_name}.html'
}}

trace {{
    enabled = true
    file = '{self.results_dir}/trace_{pipeline_name}.txt'
}}

report {{
    enabled = true
    file = '{self.results_dir}/report_{pipeline_name}.html'
}}
"""
        
        config_path = f"/workspace/nextflow_{pipeline_name.replace('/', '_')}.config"
        
        try:
            with open(config_path, 'w') as f:
                f.write(config_content)
            print(f"✅ Nextflow 설정 생성: {config_path}")
            return config_path
            
        except Exception as e:
            print(f"❌ 설정 파일 생성 실패: {e}")
            return ""
    
    def run_scrnaseq_pipeline(self, samplesheet_path: str, pmid: str) -> Dict:
        """scRNA-seq 파이프라인 실행"""
        print(f"nf-core/scrnaseq 파이프라인 실행: PMID {pmid}")
        
        results = {
            "pmid": pmid,
            "pipeline": "nf-core/scrnaseq",
            "samplesheet": samplesheet_path,
            "start_time": datetime.now().isoformat(),
            "status": "running",
            "exit_code": None,
            "execution_time_seconds": 0,
            "output_files": [],
            "log_file": "",
            "error_message": ""
        }
        
        try:
            # 실행 명령 구성
            cmd = [
                self.nextflow_cmd, "run", "nf-core/scrnaseq",
                "-profile", "singularity",
                "-c", f"/workspace/nextflow_nf-core_scrnaseq.config",
                "--input", samplesheet_path,
                "--outdir", f"{self.results_dir}/scrnaseq_{pmid}",
                "--skip_fastqc",  # 시간 단축을 위해 QC 스킵
                "--skip_multiqc"
            ]
            
            # 로그 파일 설정
            log_file = f"{self.results_dir}/nextflow_scrnaseq_{pmid}.log"
            results["log_file"] = log_file
            
            print(f"실행 명령: {' '.join(cmd)}")
            
            # 파이프라인 실행
            start_time = time.time()
            
            with open(log_file, 'w') as f:
                process = subprocess.Popen(cmd, stdout=f, stderr=subprocess.STDOUT, text=True)
                exit_code = process.wait(timeout=14400)  # 4시간 타임아웃
            
            execution_time = time.time() - start_time
            
            # 결과 업데이트
            results["exit_code"] = exit_code
            results["execution_time_seconds"] = execution_time
            results["end_time"] = datetime.now().isoformat()
            
            if exit_code == 0:
                results["status"] = "completed"
                results["output_files"] = self._collect_output_files(f"{self.results_dir}/scrnaseq_{pmid}")
                print(f"✅ scRNA-seq 파이프라인 완료: {execution_time/60:.1f}분")
            else:
                results["status"] = "failed"
                results["error_message"] = self._extract_error_from_log(log_file)
                print(f"❌ scRNA-seq 파이프라인 실패: exit_code {exit_code}")
            
            return results
            
        except subprocess.TimeoutExpired:
            results["status"] = "timeout"
            results["error_message"] = "파이프라인 실행 타임아웃 (4시간)"
            print("❌ 파이프라인 실행 타임아웃")
            return results
            
        except Exception as e:
            results["status"] = "error"
            results["error_message"] = str(e)
            print(f"❌ 파이프라인 실행 예외: {e}")
            return results
    
    def run_rnaseq_pipeline(self, samplesheet_path: str, pmid: str) -> Dict:
        """bulk RNA-seq 파이프라인 실행"""
        print(f"nf-core/rnaseq 파이프라인 실행: PMID {pmid}")
        
        results = {
            "pmid": pmid,
            "pipeline": "nf-core/rnaseq",
            "samplesheet": samplesheet_path,
            "start_time": datetime.now().isoformat(),
            "status": "running",
            "exit_code": None,
            "execution_time_seconds": 0,
            "output_files": [],
            "log_file": "",
            "error_message": ""
        }
        
        try:
            # 실행 명령 구성
            cmd = [
                self.nextflow_cmd, "run", "nf-core/rnaseq",
                "-profile", "singularity",
                "-c", f"/workspace/nextflow_nf-core_rnaseq.config",
                "--input", samplesheet_path,
                "--outdir", f"{self.results_dir}/rnaseq_{pmid}",
                "--skip_fastqc",  # 시간 단축을 위해 QC 스킵
                "--skip_multiqc"
            ]
            
            # 로그 파일 설정
            log_file = f"{self.results_dir}/nextflow_rnaseq_{pmid}.log"
            results["log_file"] = log_file
            
            print(f"실행 명령: {' '.join(cmd)}")
            
            # 파이프라인 실행
            start_time = time.time()
            
            with open(log_file, 'w') as f:
                process = subprocess.Popen(cmd, stdout=f, stderr=subprocess.STDOUT, text=True)
                exit_code = process.wait(timeout=10800)  # 3시간 타임아웃
            
            execution_time = time.time() - start_time
            
            # 결과 업데이트
            results["exit_code"] = exit_code
            results["execution_time_seconds"] = execution_time
            results["end_time"] = datetime.now().isoformat()
            
            if exit_code == 0:
                results["status"] = "completed"
                results["output_files"] = self._collect_output_files(f"{self.results_dir}/rnaseq_{pmid}")
                print(f"✅ bulk RNA-seq 파이프라인 완료: {execution_time/60:.1f}분")
            else:
                results["status"] = "failed"
                results["error_message"] = self._extract_error_from_log(log_file)
                print(f"❌ bulk RNA-seq 파이프라인 실패: exit_code {exit_code}")
            
            return results
            
        except subprocess.TimeoutExpired:
            results["status"] = "timeout"
            results["error_message"] = "파이프라인 실행 타임아웃 (3시간)"
            print("❌ 파이프라인 실행 타임아웃")
            return results
            
        except Exception as e:
            results["status"] = "error"
            results["error_message"] = str(e)
            print(f"❌ 파이프라인 실행 예외: {e}")
            return results
    
    def run_dry_run(self, pipeline_name: str, samplesheet_path: str) -> bool:
        """dry-run 실행"""
        print(f"dry-run 실행: {pipeline_name}")
        
        try:
            cmd = [
                self.nextflow_cmd, "run", f"nf-core/{pipeline_name}",
                "-profile", "singularity",
                "--input", samplesheet_path,
                "-dry-run"
            ]
            
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)  # 5분 타임아웃
            
            if result.returncode == 0:
                print(f"✅ dry-run 성공: {pipeline_name}")
                return True
            else:
                print(f"❌ dry-run 실패: {result.stderr}")
                return False
                
        except Exception as e:
            print(f"❌ dry-run 예외: {e}")
            return False
    
    def _collect_output_files(self, output_dir: str) -> List[str]:
        """출력 파일 수집"""
        output_files = []
        
        try:
            if os.path.exists(output_dir):
                for root, dirs, files in os.walk(output_dir):
                    for file in files:
                        file_path = os.path.join(root, file)
                        output_files.append(file_path)
            
            return output_files[:50]  # 최대 50개 파일
            
        except Exception as e:
            print(f"출력 파일 수집 실패: {e}")
            return []
    
    def _extract_error_from_log(self, log_file: str) -> str:
        """로그에서 에러 메시지 추출"""
        try:
            if os.path.exists(log_file):
                with open(log_file, 'r') as f:
                    content = f.read()
                    
                # ERROR 키워드로 에러 추출
                error_lines = []
                for line in content.split('\n'):
                    if 'ERROR' in line or 'Error' in line or 'error' in line:
                        error_lines.append(line.strip())
                
                if error_lines:
                    return '\n'.join(error_lines[-5:])  # 마지막 5개 에러 라인
            
            return "에러 로그를 찾을 수 없음"
            
        except Exception as e:
            return f"에러 로그 추출 실패: {e}"
    
    def save_pipeline_result(self, result: Dict) -> str:
        """파이프라인 실행 결과 저장"""
        pmid = result.get("pmid", "unknown")
        pipeline = result.get("pipeline", "unknown").replace("/", "_")
        filename = f"/workspace/results/pipeline_result_{pmid}_{pipeline}.json"
        
        try:
            with open(filename, 'w', encoding='utf-8') as f:
                json.dump(result, f, indent=2, ensure_ascii=False)
            print(f"파이프라인 결과 저장: {filename}")
            return filename
            
        except Exception as e:
            print(f"파이프라인 결과 저장 실패: {e}")
            return ""

def main():
    """테스트 실행"""
    print("=== Nextflow 관리자 테스트 ===")
    
    manager = NextflowManager()
    
    # Nextflow 설치 확인
    if not manager.check_nextflow_installation():
        print("Nextflow를 먼저 설치해야 합니다")
        return
    
    # 컨테이너 런타임 확인
    container_runtime, available = manager.check_container_runtime()
    if not available:
        print("컨테이너 런타임이 필요합니다")
        return
    
    # 설정 파일 생성 테스트
    config_path = manager.generate_nextflow_config("scrnaseq", container_runtime)
    print(f"설정 파일: {config_path}")

if __name__ == "__main__":
    main()