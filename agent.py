#!/usr/bin/env python3
"""
Autonomous LinkedIn Job Search, Auto-Apply & Email Tracking Agent
Main CLI and Orchestration Pipeline.
"""

import argparse
import asyncio
import logging
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Optional, List
# UTF-8 Encoding compatibility for Windows console
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

from rich.console import Console
from rich.table import Table

console = Console(legacy_windows=False)

from src.config import get_config, AppConfig
from src.core.cv_parser import CVParser, CandidateProfile
from src.core.llm_client import LLMClient
from src.core.matcher import IILSMatcher
from src.data.tracker import ApplicationTracker
from src.browser.session_manager import LinkedInSessionManager
from src.browser.job_scanner import LinkedInJobScanner
from src.browser.easy_applier import LinkedInEasyApplier
from src.email_monitor.inbox_scanner import InboxScanner
from src.email_monitor.reporter import DailyReporter

console = Console()

# Ensure necessary directories exist
Path("logs").mkdir(parents=True, exist_ok=True)
Path("data").mkdir(parents=True, exist_ok=True)
Path("output/daily_reports").mkdir(parents=True, exist_ok=True)
Path("output/screenshots").mkdir(parents=True, exist_ok=True)
Path("sessions/linkedin_profile").mkdir(parents=True, exist_ok=True)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.FileHandler("logs/agent.log", encoding="utf-8"),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger("LinkedInAgent")


class AutonomousJobAgent:
    """End-to-End Orchestrator for the Autonomous LinkedIn Job Search & Application Agent."""

    def __init__(self, config: Optional[AppConfig] = None):
        self.config = config or get_config()
        self.cv_parser = CVParser(resume_path=self.config.candidate.resume_path)
        self.candidate: CandidateProfile = self.cv_parser.parse(
            project_root=self.config.root_dir,
            fallback_defaults=CandidateProfile(
                full_name=self.config.candidate.name,
                email=self.config.candidate.email,
                phone=self.config.candidate.phone,
                location=self.config.candidate.location,
                linkedin_url=self.config.candidate.linkedin_url,
                github_url=self.config.candidate.github_url,
                portfolio_url=self.config.candidate.portfolio_url,
                total_years_experience=self.config.candidate.default_experience_years
            )
        )
        self.llm_client = LLMClient(config=self.config.llm)
        self.matcher = IILSMatcher(scoring_config=self.config.scoring, target_config=self.config.target)
        self.tracker = ApplicationTracker(
            tracker_path=self.config.application_tracker_path,
            external_jobs_path=self.config.external_jobs_path
        )
        self.session_manager = LinkedInSessionManager(config=self.config.browser, root_dir=self.config.root_dir)
        self.reporter = DailyReporter(config=self.config.reporter if hasattr(self.config, "reporter") else self.config, tracker=self.tracker)

    def print_banner(self):
        """Displays agent startup banner."""
        console.print("[bold cyan]==========================================================[/bold cyan]")
        console.print("[bold green]🤖 AUTONOMOUS LINKEDIN JOB SEARCH & AUTO-APPLY AGENT[/bold green]")
        console.print(f"[yellow]Candidate:[/yellow] {self.candidate.full_name} ({self.candidate.email})")
        console.print(f"[yellow]Phone:[/yellow] {self.candidate.phone} | [yellow]Experience:[/yellow] {self.candidate.total_years_experience}+ Years")
        console.print(f"[yellow]Auto-Apply Threshold:[/yellow] IILS >= {self.config.scoring.auto_apply_threshold} | [yellow]Skill Match Threshold:[/yellow] >= {self.config.scoring.skill_min_match_threshold}%")
        console.print("[bold cyan]==========================================================[/bold cyan]\n")

    async def run_interactive_login(self):
        """Launches interactive browser for user authentication."""
        self.print_banner()
        console.print("[bold yellow]Launching LinkedIn Interactive Login...[/bold yellow]")
        success = await self.session_manager.interactive_login()
        if success:
            console.print("[bold green]🎉 Session saved successfully! You are ready to run automated searches.[/bold green]")
        else:
            console.print("[bold red]❌ Login was not completed or timed out.[/bold red]")

    async def run_scan(self, max_per_title: int = 5):
        """Scans LinkedIn and outputs scored job opportunities table."""
        self.print_banner()
        console.print(f"[bold cyan]🔍 Scanning LinkedIn for {len(self.config.target.target_titles)} target titles...[/bold cyan]")

        page = await self.session_manager.new_page()
        is_logged_in = await self.session_manager.check_login_status(page)

        if not is_logged_in:
            console.print("[bold red]⚠️ Not authenticated on LinkedIn! Please run 'python agent.py login' first.[/bold red]")

        scanner = LinkedInJobScanner(config=self.config, matcher=self.matcher, tracker=self.tracker)
        results = await scanner.scan_all_targets(page=page, candidate=self.candidate, max_jobs_per_title=max_per_title)

        table = Table(title="📊 LinkedIn Job Opportunities & IILS Evaluation")
        table.add_column("ID", style="cyan", no_wrap=True)
        table.add_column("Title", style="white")
        table.add_column("Company", style="yellow")
        table.add_column("Easy Apply", style="green")
        table.add_column("Skill %", justify="right")
        table.add_column("IILS", justify="right", style="bold magenta")
        table.add_column("Status / Action", style="bold")

        for job, score in results:
            action = "[green]Qualified (Easy Apply)[/green]" if score.is_qualified_easy_apply else (
                "[blue]Qualified (Saved for Review)[/blue]" if score.is_qualified_external_review else f"[dim]{score.disqualification_reason or 'Below Threshold'}[/dim]"
            )
            table.add_row(
                job.job_id,
                job.title[:30],
                job.company[:20],
                "✅ Yes" if job.is_easy_apply else "❌ No",
                f"{score.skill_match_score}%",
                f"{score.total_iils}/100",
                action
            )

            # Auto-save qualified non-easy apply jobs
            if score.is_qualified_external_review:
                self.tracker.record_external_job(job, score)

        console.print(table)
        await self.session_manager.close()

    async def run_apply(self, dry_run: Optional[bool] = None):
        """Executes full search, matchmaking, and Easy Apply pipeline."""
        if dry_run is not None:
            self.config.dry_run = dry_run

        self.print_banner()
        mode_str = "[bold yellow][DRY RUN MODE - Form will be prepared but NOT submitted][/bold yellow]" if self.config.dry_run else "[bold green][LIVE MODE - Applications will be submitted][/bold green]"
        console.print(f"🚀 Starting Auto-Apply Pipeline: {mode_str}\n")

        # Locate resume file
        resume_file = self.cv_parser.locate_resume(self.config.root_dir)
        if resume_file:
            console.print(f"📄 Using Resume: [bold cyan]{resume_file.name}[/bold cyan]")
        else:
            console.print("⚠️ [bold yellow]No resume PDF found in ./data/. Auto-generating starter candidate profile.[/bold yellow]")

        page = await self.session_manager.new_page()
        is_logged_in = await self.session_manager.check_login_status(page)

        if not is_logged_in:
            console.print("[bold red]⚠️ Not authenticated! Please run 'python agent.py login' to log into LinkedIn.[/bold red]")
            await self.session_manager.close()
            return

        scanner = LinkedInJobScanner(config=self.config, matcher=self.matcher, tracker=self.tracker)
        applier = LinkedInEasyApplier(
            config=self.config,
            llm_client=self.llm_client,
            tracker=self.tracker,
            candidate_profile=self.candidate,
            resume_file=resume_file
        )

        results = await scanner.scan_all_targets(page=page, candidate=self.candidate, max_jobs_per_title=3)

        scanned_count = len(results)
        qualified_count = 0
        applied_count = 0
        external_saved_count = 0
        skipped_count = 0

        for job, score in results:
            if score.is_qualified_easy_apply:
                qualified_count += 1
                if applied_count >= self.config.max_applications_per_run:
                    console.print(f"Reached max application limit ({self.config.max_applications_per_run}).")
                    break

                console.print(f"\n[bold green]🎯 Applying for:[/bold green] {job.title} at {job.company} (IILS: {score.total_iils}/100)")
                success = await applier.apply(page, job, score)
                if success:
                    applied_count += 1
                    console.print(f"[bold green]✅ Successfully processed:[/bold green] {job.title} at {job.company}")
                else:
                    console.print(f"[bold red]❌ Application incomplete or flagged:[/bold red] {job.title}")

                await asyncio.sleep(4) # Humanized delay

            elif score.is_qualified_external_review:
                external_saved_count += 1
                self.tracker.record_external_job(job, score)
                console.print(f"[bold blue]📋 Saved non-Easy Apply job for review:[/bold blue] {job.title} at {job.company} (IILS: {score.total_iils})")
            else:
                skipped_count += 1

        await self.session_manager.close()

        # Generate summary report
        report_text = self.reporter.generate_report(
            scanned_count=scanned_count,
            qualified_count=qualified_count,
            applied_count=applied_count,
            external_saved_count=external_saved_count,
            skipped_count=skipped_count
        )
        console.print("\n" + report_text)

    def run_email_monitor(self):
        """Scans candidate inbox, classifies recruiter emails, and updates tracker."""
        self.print_banner()
        console.print(f"[bold cyan]📬 Scanning Inbox for {self.config.candidate.email}...[/bold cyan]")

        inbox_scanner = InboxScanner(config=self.config.email, llm_client=self.llm_client, tracker=self.tracker)
        emails = inbox_scanner.scan_inbox(hours_back=24)

        console.print(f"Processed {len(emails)} emails from the past 24 hours.")
        for item in emails:
            console.print(f"- [{item.classification}] {item.subject} (From: {item.sender})")

    def run_daily_report(self):
        """Generates and displays the daily accomplishment report."""
        self.print_banner()
        report = self.reporter.generate_report()
        console.print(report)
        self.reporter.send_email_report(report)

    async def run_full_daily_cycle(self):
        """Executes full daily cycle: Scan -> Apply -> Monitor Email -> Daily Report."""
        console.print("[bold green]🌟 Starting Full Daily Agent Cycle...[/bold green]")
        await self.run_apply()
        self.run_email_monitor()
        self.run_daily_report()
        console.print("[bold green]✅ Full Daily Cycle Completed Successfully![/bold green]")

    def run_scheduler(self):
        """Runs background scheduler triggering run_full_daily_cycle at scheduled time."""
        import schedule

        self.print_banner()
        sched_time = self.config.email.daily_schedule_time
        console.print(f"[bold cyan]⏰ Scheduler activated. Running full agent cycle daily at {sched_time} (Local Time)...[/bold cyan]")
        console.print("Press Ctrl+C to stop scheduler.\n")

        def job_wrapper():
            asyncio.run(self.run_full_daily_cycle())

        schedule.every().day.at(sched_time).do(job_wrapper)

        while True:
            schedule.run_pending()
            time.sleep(30)


def main():
    """Command Line Argument Parser and Entry Point."""
    parser = argparse.ArgumentParser(
        description="Autonomous LinkedIn Job Search, Auto-Apply & Email Tracking Agent"
    )
    subparsers = parser.add_subparsers(dest="command", help="Agent Command")

    # login
    subparsers.add_parser("login", help="Open browser to log into LinkedIn interactively and save session")

    # scan
    scan_parser = subparsers.add_parser("scan", help="Scan and score LinkedIn jobs against IILS algorithm")
    scan_parser.add_argument("--max", type=int, default=5, help="Max jobs per target title")

    # apply
    apply_parser = subparsers.add_parser("apply", help="Search, score, and auto-apply for qualified jobs")
    apply_parser.add_argument("--dry-run", action="store_true", help="Prepare application and save screenshot without submitting")
    apply_parser.add_argument("--live", action="store_true", help="Submit applications live")

    # monitor-email
    subparsers.add_parser("monitor-email", help="Scan candidate inbox for recruiter responses and interview invites")

    # report
    subparsers.add_parser("report", help="Generate and print/send the daily performance report")

    # run-daily
    daily_parser = subparsers.add_parser("run-daily", help="Run full pipeline (apply -> monitor -> report)")
    daily_parser.add_argument("--dry-run", action="store_true", help="Run daily cycle in dry-run mode")

    # schedule
    subparsers.add_parser("schedule", help="Start background scheduler for 18:00 daily runs")

    args = parser.parse_args()
    agent = AutonomousJobAgent()

    if args.command == "login":
        asyncio.run(agent.run_interactive_login())
    elif args.command == "scan":
        asyncio.run(agent.run_scan(max_per_title=args.max))
    elif args.command == "apply":
        dry = True if args.dry_run else (False if args.live else None)
        asyncio.run(agent.run_apply(dry_run=dry))
    elif args.command == "monitor-email":
        agent.run_email_monitor()
    elif args.command == "report":
        agent.run_daily_report()
    elif args.command == "run-daily":
        if args.dry_run:
            agent.config.dry_run = True
        asyncio.run(agent.run_full_daily_cycle())
    elif args.command == "schedule":
        agent.run_scheduler()
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
