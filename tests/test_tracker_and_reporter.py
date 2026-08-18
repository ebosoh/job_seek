"""Tests for Application Tracker and Daily Performance Reporter."""

from datetime import datetime
from pathlib import Path
import pytest
from src.config import AppConfig
from src.core.matcher import IILSScoreBreakdown, JobOpportunity
from src.data.tracker import ApplicationTracker
from src.email_monitor.reporter import DailyReporter


@pytest.fixture
def temp_dirs(tmp_path):
    tracker_path = tmp_path / "output" / "application_tracker.csv"
    external_path = tmp_path / "output" / "external_jobs_to_review.csv"
    reports_dir = tmp_path / "output" / "daily_reports"
    return tracker_path, external_path, reports_dir


def test_tracker_record_and_read(temp_dirs):
    tracker_path, external_path, _ = temp_dirs
    tracker = ApplicationTracker(tracker_path=tracker_path, external_jobs_path=external_path)

    job = JobOpportunity(
        job_id="job_999",
        title="AI Engineer",
        company="Cognitive Labs",
        location="Remote",
        job_url="https://linkedin.com/jobs/view/999",
        is_easy_apply=True
    )
    score = IILSScoreBreakdown(
        total_iils=88.5,
        skill_match_score=90.0,
        time_posted_score=100.0,
        applicant_count_score=70.0,
        title_exactness_score=100.0
    )

    tracker.record_application(job, score, status="APPLIED")
    applied_ids = tracker.get_applied_job_ids()
    assert "job_999" in applied_ids

    # Update status by company
    updated = tracker.update_status_by_company(
        company_name="Cognitive Labs",
        new_status="INTERVIEW_INVITE",
        email_date=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        notes="Recruiter scheduled call"
    )
    assert updated is True

    apps = tracker.get_all_applications()
    assert len(apps) == 1
    assert apps[0]["status"] == "INTERVIEW_INVITE"


def test_reporter_formatting(temp_dirs):
    tracker_path, external_path, reports_dir = temp_dirs
    tracker = ApplicationTracker(tracker_path=tracker_path, external_jobs_path=external_path)

    cfg = AppConfig()
    cfg.daily_reports_dir = reports_dir
    reporter = DailyReporter(config=cfg, tracker=tracker)

    report_text = reporter.generate_report(
        scanned_count=25,
        qualified_count=8,
        applied_count=5,
        external_saved_count=3,
        skipped_count=17,
        date_str="2026-08-18"
    )

    assert "🤖 DAILY AGENT PERFORMANCE REPORT - 2026-08-18" in report_text
    assert "Jobs Scanned Today: 25" in report_text
    assert "High-Match Jobs Qualified (IILS >= 70): 8" in report_text
    assert "Total Successfully Applied (LinkedIn Easy Apply): 5" in report_text
    assert "External Jobs Saved for Review: 3" in report_text
    assert "hudson.eboso@techbrain.africa" in report_text

    # Verify saved to disk
    saved_file = reports_dir / "daily_report_2026-08-18.txt"
    assert saved_file.exists()
    assert saved_file.read_text(encoding="utf-8") == report_text
