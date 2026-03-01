#!/usr/bin/env python3
"""
Progress Manager for Resume Functionality
실행 상태 저장 및 복원 관리
"""

import json
import os
from datetime import datetime


class ProgressManager:
    def __init__(self, progress_file="./results/progress.json"):
        self.progress_file = progress_file
        self.progress_data = self.load_progress()

    def load_progress(self) -> dict:
        """진행 상태 로드"""
        if os.path.exists(self.progress_file):
            try:
                with open(self.progress_file, encoding='utf-8') as f:
                    return json.load(f)
            except Exception as e:
                print(f"진행 상태 로드 실패: {e}")
                return self.get_initial_progress()
        else:
            return self.get_initial_progress()

    def get_initial_progress(self) -> dict:
        """초기 진행 상태 구조"""
        return {
            "execution_id": f"run_{datetime.now().strftime('%Y%m%d_%H%M%S')}",
            "start_time": datetime.now().isoformat(),
            "current_pmid": None,
            "current_phase": "environment_setup",
            "completed_phases": [],
            "pmid_status": {
                "40315330": {
                    "pubmed_done": False,
                    "sra_discovery_done": False,
                    "sra_download_done": False,
                    "pipeline_done": False,
                    "llm_analysis_done": False,
                    "final_report_done": False
                },
                "32416070": {
                    "pubmed_done": False,
                    "sra_discovery_done": False,
                    "sra_download_done": False,
                    "pipeline_done": False,
                    "llm_analysis_done": False,
                    "final_report_done": False
                }
            },
            "failed_steps": [],
            "last_checkpoint": None,
            "total_execution_time": 0
        }

    def save_progress(self):
        """진행 상태 저장"""
        self.progress_data["last_checkpoint"] = datetime.now().isoformat()

        try:
            with open(self.progress_file, 'w', encoding='utf-8') as f:
                json.dump(self.progress_data, f, indent=2, ensure_ascii=False)
        except Exception as e:
            print(f"진행 상태 저장 실패: {e}")

    def mark_phase_completed(self, phase: str):
        """단계 완료 표시"""
        if phase not in self.progress_data["completed_phases"]:
            self.progress_data["completed_phases"].append(phase)
        self.progress_data["current_phase"] = phase
        self.save_progress()
        print(f"✅ 단계 완료: {phase}")

    def mark_pmid_step_completed(self, pmid: str, step: str):
        """PMID별 단계 완료 표시"""
        if pmid in self.progress_data["pmid_status"]:
            self.progress_data["pmid_status"][pmid][step] = True
            self.save_progress()
            print(f"✅ PMID {pmid} 단계 완료: {step}")

    def set_current_pmid(self, pmid: str):
        """현재 처리 중인 PMID 설정"""
        self.progress_data["current_pmid"] = pmid
        self.save_progress()

    def set_current_phase(self, phase: str):
        """현재 단계 설정"""
        self.progress_data["current_phase"] = phase
        self.save_progress()

    def add_failed_step(self, step: str, error_message: str):
        """실패 단계 기록"""
        failure_info = {
            "step": step,
            "error": error_message,
            "timestamp": datetime.now().isoformat()
        }
        self.progress_data["failed_steps"].append(failure_info)
        self.save_progress()
        print(f"❌ 단계 실패: {step} - {error_message}")

    def is_phase_completed(self, phase: str) -> bool:
        """단계 완료 여부 확인"""
        return phase in self.progress_data["completed_phases"]

    def is_pmid_step_completed(self, pmid: str, step: str) -> bool:
        """PMID별 단계 완료 여부 확인"""
        if pmid in self.progress_data["pmid_status"]:
            return self.progress_data["pmid_status"][pmid].get(step, False)
        return False

    def get_next_phase(self) -> str | None:
        """다음 실행할 단계 반환"""
        phase_order = [
            "environment_setup",
            "llm_server_check",
            "pubmed_fetch_40315330",
            "sra_discovery_40315330",
            "sra_download_40315330",
            "pipeline_execution_40315330",
            "llm_analysis_40315330",
            "pubmed_fetch_32416070",
            "sra_discovery_32416070",
            "sra_download_32416070",
            "pipeline_execution_32416070",
            "llm_analysis_32416070",
            "final_report"
        ]

        for phase in phase_order:
            if phase not in self.progress_data["completed_phases"]:
                return phase
        return None

    def get_resume_point(self) -> dict:
        """재시작 지점 정보 반환"""
        return {
            "execution_id": self.progress_data["execution_id"],
            "current_pmid": self.progress_data["current_pmid"],
            "current_phase": self.progress_data["current_phase"],
            "next_phase": self.get_next_phase(),
            "completed_phases": self.progress_data["completed_phases"],
            "failed_steps": self.progress_data["failed_steps"],
            "pmid_status": self.progress_data["pmid_status"]
        }

    def print_status(self):
        """현재 상태 출력"""
        print("\n=== 현재 진행 상태 ===")
        print(f"실행 ID: {self.progress_data['execution_id']}")
        print(f"시작 시간: {self.progress_data['start_time']}")
        print(f"현재 PMID: {self.progress_data['current_pmid']}")
        print(f"현재 단계: {self.progress_data['current_phase']}")
        print(f"완료된 단계: {len(self.progress_data['completed_phases'])}")
        print(f"실패한 단계: {len(self.progress_data['failed_steps'])}")

        if self.progress_data["failed_steps"]:
            print("\n실패 기록:")
            for failure in self.progress_data["failed_steps"]:
                print(f"  - {failure['step']}: {failure['error']}")

        next_phase = self.get_next_phase()
        if next_phase:
            print(f"\n다음 단계: {next_phase}")
        else:
            print("\n모든 단계 완료")
        print("==================\n")

def main():
    """테스트 실행"""
    manager = ProgressManager()
    manager.print_status()

    # 테스트: 단계 완료 표시
    manager.mark_phase_completed("environment_setup")
    manager.mark_pmid_step_completed("40315330", "pubmed_done")

    # 재시작 지점 확인
    resume_point = manager.get_resume_point()
    print(f"재시작 정보: {json.dumps(resume_point, indent=2, ensure_ascii=False)}")

if __name__ == "__main__":
    main()
