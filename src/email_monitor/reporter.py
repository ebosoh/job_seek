"""Daily Accomplishment Performance Reporter & Dispatcher."""

import os
import smtplib
import logging
from datetime import datetime
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from pathlib import Path
from typing import Dict, List, Optional
from src.config import AppConfig
from src.data.tracker import ApplicationTracker

logger = logging.getLogger(__name__)


class DailyReporter:
    """Generates formatted daily agent performance reports and dispatches via email."""

    def __init__(self, config: AppConfig, tracker: ApplicationTracker):
        self.config = config
        self.tracker = tracker

    def generate_report(
        self,
        scanned_count: int = 0,
        qualified_count: int = 0,
        applied_count: int = 0,
        external_saved_count: int = 0,
        skipped_count: int = 0,
        inbox_emails: Optional[List] = None,
        date_str: Optional[str] = None
    ) -> str:
        """Constructs the exact formatted Daily Agent Performance Report."""
        today = date_str or datetime.now().strftime("%Y-%m-%d")
        all_apps = self.tracker.get_all_applications()
        all_external = self.tracker.get_all_external_jobs()

        # Compute today's metrics if not provided directly
        today_apps = [a for a in all_apps if str(a.get("applied_at", "")).startswith(today)]
        today_external = [e for e in all_external if str(e.get("discovered_at", "")).startswith(today)]

        if applied_count == 0:
            applied_count = len(today_apps)
        if external_saved_count == 0:
            external_saved_count = len(today_external)
        if qualified_count == 0:
            qualified_count = applied_count + external_saved_count
        if scanned_count == 0:
            scanned_count = max(qualified_count + skipped_count, len(today_apps) + len(today_external))

        # Score Breakdown
        iils_scores = [float(a.get("iils_score", 0.0)) for a in today_apps if a.get("iils_score")]
        avg_score = round(sum(iils_scores) / len(iils_scores), 1) if iils_scores else 0.0

        top_role_text = "None"
        if today_apps:
            sorted_apps = sorted(today_apps, key=lambda x: float(x.get("iils_score", 0.0)), reverse=True)
            top = sorted_apps[0]
            top_role_text = f"{top.get('job_title', 'Role')} at {top.get('company', 'Company')} (IILS: {top.get('iils_score', 0)}/100)"

        # Inbox summary
        interviews_count = 0
        assessments_count = 0
        rejections_count = 0
        confirmations_count = 0
        action_items = []

        if inbox_emails:
            for item in inbox_emails:
                cat = getattr(item, "classification", "")
                if cat == "INTERVIEW_INVITE":
                    interviews_count += 1
                    co = getattr(item, "matched_company", "") or getattr(item, "sender", "")
                    action_items.append(f"{co} - {getattr(item, 'action_item', 'Schedule interview call')}")
                elif cat == "ASSESSMENT_REQUEST":
                    assessments_count += 1
                    co = getattr(item, "matched_company", "") or getattr(item, "sender", "")
                    action_items.append(f"{co} - {getattr(item, 'action_item', 'Complete technical assessment')}")
                elif cat == "REJECTION":
                    rejections_count += 1
                elif cat == "ACKNOWLEDGMENT":
                    confirmations_count += 1
        else:
            # Check tracker records updated today
            for a in all_apps:
                status = str(a.get("status", ""))
                if status == "INTERVIEW_INVITE":
                    interviews_count += 1
                elif status == "ASSESSMENT_REQUEST":
                    assessments_count += 1
                elif status == "REJECTION":
                    rejections_count += 1
                elif status in ["APPLIED", "CONFIRMED", "ACKNOWLEDGMENT"]:
                    confirmations_count += 1

        # Add external jobs needing human review to action items
        for ext in today_external[:3]:
            action_items.append(f"{ext.get('company')} - Review high-match non-Easy Apply opportunity (IILS: {ext.get('iils_score')}): {ext.get('job_url')}")

        # Fallback if action items are empty
        if not action_items:
            action_items_text = "No immediate human action required. Agent running normally."
        else:
            action_items_text = "\n".join([f"{i+1}. {item}" for i, item in enumerate(action_items)])

        report = f"""====================================================
🤖 DAILY AGENT PERFORMANCE REPORT - {today}
====================================================

📊 APPLICATION METRICS:
- Jobs Scanned Today: {scanned_count}
- High-Match Jobs Qualified (IILS >= 70): {qualified_count}
- Total Successfully Applied (LinkedIn Easy Apply): {applied_count}
- External Jobs Saved for Review: {external_saved_count}
- Applications Skipped (Low Score / Outside Criteria): {skipped_count}

📈 SCORE BREAKDOWN OF TODAY'S APPLICATIONS:
- Average IILS Score: {avg_score}/100
- Top Matched Role Today: {top_role_text}

📬 INBOX & RESPONSE SUMMARY ({self.config.candidate.email}):
- 🟢 Interview Invitations / Recruiter Outreach: {interviews_count}
- 🟡 Technical Assessments / Take-homes: {assessments_count}
- 🔴 Application Rejections: {rejections_count}
- ⚪ Confirmation Emails Received: {confirmations_count}

🔔 ACTION ITEMS FOR HUMAN REVIEW:
{action_items_text}

====================================================
"""
        # Save report locally to disk
        self.save_report(today, report)
        return report

    def save_report(self, date_str: str, report_text: str):
        """Saves daily report to local disk in output/daily_reports/."""
        self.config.daily_reports_dir.mkdir(parents=True, exist_ok=True)
        txt_path = self.config.daily_reports_dir / f"daily_report_{date_str}.txt"
        txt_path.write_text(report_text, encoding="utf-8")
        logger.info(f"Daily report saved to: {txt_path}")

    def send_email_report(self, report_text: str, date_str: Optional[str] = None) -> bool:
        """Dispatches daily report via SMTP to candidate's email."""
        if not self.config.email.smtp_username or not self.config.email.smtp_password:
            logger.info("SMTP credentials not configured. Report saved locally only.")
            return False

        today = date_str or datetime.now().strftime("%Y-%m-%d")
        recipient = self.config.email.report_recipient_email or self.config.candidate.email

        msg = MIMEMultipart()
        msg["From"] = self.config.email.smtp_username
        msg["To"] = recipient
        msg["Subject"] = f"🤖 Daily Agent Performance Report - {today}"
        msg.attach(MIMEText(report_text, "plain", "utf-8"))

        try:
            if self.config.email.smtp_use_ssl:
                with smtplib.SMTP_SSL(self.config.email.smtp_server, self.config.email.smtp_port) as server:
                    server.login(self.config.email.smtp_username, self.config.email.smtp_password)
                    server.send_message(msg)
            else:
                with smtplib.SMTP(self.config.email.smtp_server, self.config.email.smtp_port) as server:
                    server.starttls()
                    server.login(self.config.email.smtp_username, self.config.email.smtp_password)
                    server.send_message(msg)

            logger.info(f"Successfully dispatched daily report to {recipient}")
            return True
        except Exception as e:
            logger.error(f"Failed to send email report: {e}")
            return False
