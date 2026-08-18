"""Application and External Jobs Tracker managing local CSV storage."""

import csv
import os
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Set
import pandas as pd
from src.core.matcher import IILSScoreBreakdown, JobOpportunity


class ApplicationTracker:
    """Manages recording and updating job applications and external jobs on disk."""

    TRACKER_COLUMNS = [
        "job_id",
        "job_title",
        "company",
        "location",
        "job_url",
        "iils_score",
        "skill_match",
        "time_score",
        "applicant_score",
        "title_score",
        "applied_at",
        "status",
        "last_email_date",
        "notes"
    ]

    EXTERNAL_COLUMNS = [
        "job_id",
        "job_title",
        "company",
        "location",
        "job_url",
        "iils_score",
        "skill_match",
        "time_score",
        "applicant_score",
        "title_score",
        "discovered_at",
        "notes"
    ]

    def __init__(self, tracker_path: Path, external_jobs_path: Path):
        self.tracker_path = tracker_path
        self.external_jobs_path = external_jobs_path
        self._ensure_files()

    def _ensure_files(self):
        """Creates CSV files with headers if they don't exist."""
        self.tracker_path.parent.mkdir(parents=True, exist_ok=True)
        self.external_jobs_path.parent.mkdir(parents=True, exist_ok=True)

        if not self.tracker_path.exists() or self.tracker_path.stat().st_size == 0:
            with open(self.tracker_path, "w", newline="", encoding="utf-8") as f:
                writer = csv.DictWriter(f, fieldnames=self.TRACKER_COLUMNS)
                writer.writeheader()

        if not self.external_jobs_path.exists() or self.external_jobs_path.stat().st_size == 0:
            with open(self.external_jobs_path, "w", newline="", encoding="utf-8") as f:
                writer = csv.DictWriter(f, fieldnames=self.EXTERNAL_COLUMNS)
                writer.writeheader()

    def get_applied_job_ids(self) -> Set[str]:
        """Returns set of all job IDs already applied or saved."""
        applied = set()
        if self.tracker_path.exists() and self.tracker_path.stat().st_size > 0:
            try:
                df = pd.read_csv(self.tracker_path, dtype=str)
                if "job_id" in df.columns:
                    applied.update(df["job_id"].dropna().tolist())
            except Exception:
                pass

        if self.external_jobs_path.exists() and self.external_jobs_path.stat().st_size > 0:
            try:
                df_ext = pd.read_csv(self.external_jobs_path, dtype=str)
                if "job_id" in df_ext.columns:
                    applied.update(df_ext["job_id"].dropna().tolist())
            except Exception:
                pass

        return applied

    def record_application(
        self,
        job: JobOpportunity,
        score: IILSScoreBreakdown,
        status: str = "APPLIED",
        notes: str = ""
    ):
        """Records an Easy Apply application entry in application_tracker.csv."""
        entry = {
            "job_id": job.job_id,
            "job_title": job.title,
            "company": job.company,
            "location": job.location,
            "job_url": job.job_url,
            "iils_score": score.total_iils,
            "skill_match": score.skill_match_score,
            "time_score": score.time_posted_score,
            "applicant_score": score.applicant_count_score,
            "title_score": score.title_exactness_score,
            "applied_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "status": status,
            "last_email_date": "",
            "notes": notes
        }

        # Append to CSV
        with open(self.tracker_path, "a", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=self.TRACKER_COLUMNS)
            writer.writerow(entry)

    def record_external_job(
        self,
        job: JobOpportunity,
        score: IILSScoreBreakdown,
        notes: str = "Qualified Non-Easy Apply (IILS >= 80)"
    ):
        """Records a high-match non-Easy Apply job in external_jobs_to_review.csv."""
        entry = {
            "job_id": job.job_id,
            "job_title": job.title,
            "company": job.company,
            "location": job.location,
            "job_url": job.job_url,
            "iils_score": score.total_iils,
            "skill_match": score.skill_match_score,
            "time_score": score.time_posted_score,
            "applicant_score": score.applicant_count_score,
            "title_score": score.title_exactness_score,
            "discovered_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "notes": notes
        }

        with open(self.external_jobs_path, "a", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=self.EXTERNAL_COLUMNS)
            writer.writerow(entry)

    def update_status_by_company(self, company_name: str, new_status: str, email_date: str, notes: str = "") -> bool:
        """Updates status of applications matching company name."""
        if not self.tracker_path.exists():
            return False

        try:
            df = pd.read_csv(self.tracker_path, dtype=str)
            if df.empty:
                return False

            clean_co = company_name.lower().strip()
            # Match company containing or contained in
            mask = df["company"].str.lower().str.contains(clean_co, regex=False, na=False)
            if not mask.any():
                return False

            df.loc[mask, "status"] = new_status
            df.loc[mask, "last_email_date"] = email_date
            if notes:
                df.loc[mask, "notes"] = df.loc[mask, "notes"].fillna("") + f" | {notes}"

            df.to_csv(self.tracker_path, index=False, encoding="utf-8")
            return True
        except Exception:
            return False

    def get_all_applications(self) -> List[Dict]:
        """Loads all applications as list of dicts."""
        if not self.tracker_path.exists():
            return []
        try:
            df = pd.read_csv(self.tracker_path)
            return df.fillna("").to_dict(orient="records")
        except Exception:
            return []

    def get_all_external_jobs(self) -> List[Dict]:
        """Loads all external jobs for review."""
        if not self.external_jobs_path.exists():
            return []
        try:
            df = pd.read_csv(self.external_jobs_path)
            return df.fillna("").to_dict(orient="records")
        except Exception:
            return []
