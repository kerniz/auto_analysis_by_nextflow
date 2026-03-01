"""
Tests for ProgressManager
진행 상태 관리자 테스트
"""

import json

import pytest

from core.progress_manager import ProgressManager


@pytest.fixture
def progress_file(tmp_path):
    return str(tmp_path / "progress.json")


@pytest.fixture
def manager(progress_file):
    return ProgressManager(progress_file=progress_file)


class TestProgressManagerInit:
    def test_initial_state(self, manager):
        assert manager.progress_data["current_pmid"] is None
        assert manager.progress_data["current_phase"] == "environment_setup"
        assert manager.progress_data["completed_phases"] == []
        assert manager.progress_data["failed_steps"] == []
        assert manager.progress_data["last_checkpoint"] is None
        assert manager.progress_data["total_execution_time"] == 0

    def test_initial_execution_id(self, manager):
        assert manager.progress_data["execution_id"].startswith("run_")

    def test_initial_pmid_status(self, manager):
        pmid_status = manager.progress_data["pmid_status"]
        assert "40315330" in pmid_status
        assert "32416070" in pmid_status
        for pmid in ["40315330", "32416070"]:
            for step in ["pubmed_done", "sra_discovery_done", "sra_download_done",
                         "pipeline_done", "llm_analysis_done", "final_report_done"]:
                assert pmid_status[pmid][step] is False


class TestProgressManagerLoadFromFile:
    def test_load_existing_file(self, progress_file):
        saved_data = {
            "execution_id": "run_saved",
            "start_time": "2025-01-01T00:00:00",
            "current_pmid": "40315330",
            "current_phase": "sra_discovery_40315330",
            "completed_phases": ["environment_setup", "llm_server_check"],
            "pmid_status": {
                "40315330": {
                    "pubmed_done": True,
                    "sra_discovery_done": False,
                    "sra_download_done": False,
                    "pipeline_done": False,
                    "llm_analysis_done": False,
                    "final_report_done": False,
                },
                "32416070": {
                    "pubmed_done": False,
                    "sra_discovery_done": False,
                    "sra_download_done": False,
                    "pipeline_done": False,
                    "llm_analysis_done": False,
                    "final_report_done": False,
                },
            },
            "failed_steps": [],
            "last_checkpoint": "2025-01-01T00:05:00",
            "total_execution_time": 300,
        }
        with open(progress_file, "w") as f:
            json.dump(saved_data, f)

        mgr = ProgressManager(progress_file=progress_file)
        assert mgr.progress_data["execution_id"] == "run_saved"
        assert mgr.progress_data["current_pmid"] == "40315330"
        assert "environment_setup" in mgr.progress_data["completed_phases"]
        assert mgr.progress_data["pmid_status"]["40315330"]["pubmed_done"] is True

    def test_load_corrupted_file(self, progress_file, capsys):
        with open(progress_file, "w") as f:
            f.write("{invalid json!!!")

        mgr = ProgressManager(progress_file=progress_file)
        captured = capsys.readouterr()
        assert "로드 실패" in captured.out
        assert mgr.progress_data["current_phase"] == "environment_setup"


class TestProgressManagerSave:
    def test_save_creates_file(self, manager, progress_file):
        manager.save_progress()
        assert json.loads(open(progress_file).read()) is not None

    def test_save_updates_checkpoint(self, manager, progress_file):
        assert manager.progress_data["last_checkpoint"] is None
        manager.save_progress()
        assert manager.progress_data["last_checkpoint"] is not None

    def test_save_preserves_data(self, manager, progress_file):
        manager.progress_data["current_pmid"] = "40315330"
        manager.save_progress()
        data = json.loads(open(progress_file).read())
        assert data["current_pmid"] == "40315330"

    def test_save_to_invalid_path(self, capsys):
        mgr = ProgressManager(progress_file="/nonexistent/path/progress.json")
        mgr.save_progress()
        captured = capsys.readouterr()
        assert "저장 실패" in captured.out


class TestMarkPhaseCompleted:
    def test_mark_phase(self, manager, capsys):
        manager.mark_phase_completed("environment_setup")
        assert "environment_setup" in manager.progress_data["completed_phases"]
        assert manager.progress_data["current_phase"] == "environment_setup"
        captured = capsys.readouterr()
        assert "environment_setup" in captured.out

    def test_mark_phase_no_duplicate(self, manager):
        manager.mark_phase_completed("environment_setup")
        manager.mark_phase_completed("environment_setup")
        count = manager.progress_data["completed_phases"].count("environment_setup")
        assert count == 1

    def test_mark_phase_updates_current(self, manager):
        manager.mark_phase_completed("environment_setup")
        manager.mark_phase_completed("llm_server_check")
        assert manager.progress_data["current_phase"] == "llm_server_check"

    def test_mark_phase_saves(self, manager, progress_file):
        manager.mark_phase_completed("environment_setup")
        data = json.loads(open(progress_file).read())
        assert "environment_setup" in data["completed_phases"]


class TestMarkPmidStepCompleted:
    def test_mark_step(self, manager, capsys):
        manager.mark_pmid_step_completed("40315330", "pubmed_done")
        assert manager.progress_data["pmid_status"]["40315330"]["pubmed_done"] is True
        captured = capsys.readouterr()
        assert "40315330" in captured.out
        assert "pubmed_done" in captured.out

    def test_mark_step_unknown_pmid(self, manager, capsys):
        manager.mark_pmid_step_completed("99999999", "pubmed_done")
        captured = capsys.readouterr()
        assert captured.out == ""

    def test_mark_step_saves(self, manager, progress_file):
        manager.mark_pmid_step_completed("32416070", "sra_discovery_done")
        data = json.loads(open(progress_file).read())
        assert data["pmid_status"]["32416070"]["sra_discovery_done"] is True


class TestSetCurrentPmidAndPhase:
    def test_set_current_pmid(self, manager):
        manager.set_current_pmid("40315330")
        assert manager.progress_data["current_pmid"] == "40315330"

    def test_set_current_phase(self, manager):
        manager.set_current_phase("sra_download_40315330")
        assert manager.progress_data["current_phase"] == "sra_download_40315330"

    def test_set_pmid_saves(self, manager, progress_file):
        manager.set_current_pmid("32416070")
        data = json.loads(open(progress_file).read())
        assert data["current_pmid"] == "32416070"

    def test_set_phase_saves(self, manager, progress_file):
        manager.set_current_phase("final_report")
        data = json.loads(open(progress_file).read())
        assert data["current_phase"] == "final_report"


class TestAddFailedStep:
    def test_add_failed_step(self, manager, capsys):
        manager.add_failed_step("sra_download", "Timeout error")
        assert len(manager.progress_data["failed_steps"]) == 1
        failure = manager.progress_data["failed_steps"][0]
        assert failure["step"] == "sra_download"
        assert failure["error"] == "Timeout error"
        assert "timestamp" in failure
        captured = capsys.readouterr()
        assert "sra_download" in captured.out

    def test_add_multiple_failures(self, manager):
        manager.add_failed_step("step1", "err1")
        manager.add_failed_step("step2", "err2")
        assert len(manager.progress_data["failed_steps"]) == 2

    def test_add_failed_step_saves(self, manager, progress_file):
        manager.add_failed_step("test_step", "test_error")
        data = json.loads(open(progress_file).read())
        assert len(data["failed_steps"]) == 1


class TestIsPhaseCompleted:
    def test_not_completed(self, manager):
        assert manager.is_phase_completed("environment_setup") is False

    def test_completed(self, manager):
        manager.mark_phase_completed("environment_setup")
        assert manager.is_phase_completed("environment_setup") is True

    def test_unknown_phase(self, manager):
        assert manager.is_phase_completed("nonexistent_phase") is False


class TestIsPmidStepCompleted:
    def test_not_completed(self, manager):
        assert manager.is_pmid_step_completed("40315330", "pubmed_done") is False

    def test_completed(self, manager):
        manager.mark_pmid_step_completed("40315330", "pubmed_done")
        assert manager.is_pmid_step_completed("40315330", "pubmed_done") is True

    def test_unknown_pmid(self, manager):
        assert manager.is_pmid_step_completed("99999999", "pubmed_done") is False

    def test_unknown_step(self, manager):
        assert manager.is_pmid_step_completed("40315330", "nonexistent_step") is False


class TestGetNextPhase:
    def test_first_phase(self, manager):
        assert manager.get_next_phase() == "environment_setup"

    def test_after_first_completed(self, manager):
        manager.mark_phase_completed("environment_setup")
        assert manager.get_next_phase() == "llm_server_check"

    def test_after_several_completed(self, manager):
        for phase in ["environment_setup", "llm_server_check",
                       "pubmed_fetch_40315330", "sra_discovery_40315330"]:
            manager.mark_phase_completed(phase)
        assert manager.get_next_phase() == "sra_download_40315330"

    def test_all_completed(self, manager):
        all_phases = [
            "environment_setup", "llm_server_check",
            "pubmed_fetch_40315330", "sra_discovery_40315330",
            "sra_download_40315330", "pipeline_execution_40315330",
            "llm_analysis_40315330",
            "pubmed_fetch_32416070", "sra_discovery_32416070",
            "sra_download_32416070", "pipeline_execution_32416070",
            "llm_analysis_32416070",
            "final_report",
        ]
        for phase in all_phases:
            manager.mark_phase_completed(phase)
        assert manager.get_next_phase() is None


class TestGetResumePoint:
    def test_initial_resume_point(self, manager):
        rp = manager.get_resume_point()
        assert rp["current_pmid"] is None
        assert rp["current_phase"] == "environment_setup"
        assert rp["next_phase"] == "environment_setup"
        assert rp["completed_phases"] == []
        assert rp["failed_steps"] == []
        assert "execution_id" in rp
        assert "pmid_status" in rp

    def test_resume_after_progress(self, manager):
        manager.mark_phase_completed("environment_setup")
        manager.set_current_pmid("40315330")
        manager.mark_pmid_step_completed("40315330", "pubmed_done")
        rp = manager.get_resume_point()
        assert rp["current_pmid"] == "40315330"
        assert rp["next_phase"] == "llm_server_check"
        assert "environment_setup" in rp["completed_phases"]
        assert rp["pmid_status"]["40315330"]["pubmed_done"] is True


class TestPrintStatus:
    def test_print_initial(self, manager, capsys):
        manager.print_status()
        out = capsys.readouterr().out
        assert "현재 진행 상태" in out
        assert "environment_setup" in out
        assert "다음 단계" in out

    def test_print_with_failures(self, manager, capsys):
        manager.add_failed_step("step_x", "some error")
        capsys.readouterr()  # clear add_failed_step output
        manager.print_status()
        out = capsys.readouterr().out
        assert "실패 기록" in out
        assert "step_x" in out
        assert "some error" in out

    def test_print_all_completed(self, manager, capsys):
        all_phases = [
            "environment_setup", "llm_server_check",
            "pubmed_fetch_40315330", "sra_discovery_40315330",
            "sra_download_40315330", "pipeline_execution_40315330",
            "llm_analysis_40315330",
            "pubmed_fetch_32416070", "sra_discovery_32416070",
            "sra_download_32416070", "pipeline_execution_32416070",
            "llm_analysis_32416070",
            "final_report",
        ]
        for phase in all_phases:
            manager.mark_phase_completed(phase)
        capsys.readouterr()  # clear mark output
        manager.print_status()
        out = capsys.readouterr().out
        assert "모든 단계 완료" in out
