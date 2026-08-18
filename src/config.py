"""Configuration and Settings Module."""

import os
from pathlib import Path
from typing import List, Optional
from pydantic import BaseModel, Field, ConfigDict
from pydantic_settings import BaseSettings
from dotenv import load_dotenv

# Load .env file from project root
ROOT_DIR = Path(__file__).resolve().parent.parent
load_dotenv(dotenv_path=ROOT_DIR / ".env")

class CandidateConfig(BaseModel):
    """Candidate details and profile metadata."""
    name: str = Field(default="Hudson E. Omunga")
    email: str = Field(default="hudson.eboso@techbrain.africa")
    phone: str = Field(default="+254727869396")
    location: str = Field(default="Nairobi, Kenya (Remote Worldwide)")
    linkedin_url: str = Field(default="https://www.linkedin.com/in/hudson-eboso")
    github_url: str = Field(default="https://github.com/ebosoh")
    portfolio_url: str = Field(default="https://techbrain.africa")
    resume_path: str = Field(default="data/Hudson E. Omunga- AI Engineer CV-2026.pdf")
    default_experience_years: int = Field(default=5)


class TargetCriteriaConfig(BaseModel):
    """Target job criteria and parameter settings."""
    target_titles: List[str] = Field(default_factory=lambda: [
        "AI Engineer",
        "AI Automation Engineer",
        "Applied AI Engineer",
        "AI Solutions Engineer (Verified job)",
        "AI Solutions Engineer",
        "Automation Specialist (n8n Expert)",
        "AI Workflow Engineer/Automation Architect",
        "Agentic Engineer",
        "AI Software Engineer (Agentic Workflows, Production Systems)",
        "AI Prompt Engineer",
        "Agent Engineer",
        "AI Workflow Engineer",
        "AI Developer",
        "Workflow Automation Engineer"
    ])
    location: str = Field(default="Remote")
    salary_min_monthly: float = Field(default=3000.0)
    salary_max_monthly: float = Field(default=7000.0)
    salary_min_yearly: float = Field(default=36000.0)
    salary_max_yearly: float = Field(default=84000.0)
    default_salary_yearly: float = Field(default=60000.0)
    default_salary_monthly: float = Field(default=5000.0)
    salary_currency: str = Field(default="USD")


class ScoringConfig(BaseModel):
    """Interview Invitation Likelihood Score (IILS) algorithm weights & thresholds."""
    skill_match_weight: float = 0.40
    time_posted_weight: float = 0.25
    applicant_count_weight: float = 0.20
    title_exactness_weight: float = 0.15

    # Thresholds
    auto_apply_threshold: float = 70.0
    external_review_threshold: float = 80.0
    skill_min_match_threshold: float = 75.0
    safety_confidence_threshold: float = 85.0


class LLMConfig(BaseModel):
    """LLM provider and model settings."""
    provider: str = Field(default="gemini") # "gemini" or "openai"
    gemini_api_key: Optional[str] = None
    gemini_model: str = Field(default="gemini-2.5-flash")
    openai_api_key: Optional[str] = None
    openai_model: str = Field(default="gpt-4o-mini")


class BrowserConfig(BaseModel):
    """Playwright persistent browser configuration."""
    user_data_dir: str = Field(default="sessions/linkedin_profile")
    headless: bool = Field(default=False)
    slow_mo_ms: int = Field(default=150)
    timeout_ms: int = Field(default=30000)


class EmailConfig(BaseModel):
    """IMAP and SMTP configuration for monitoring and reporting."""
    imap_server: str = Field(default="mail.techbrain.africa")
    imap_port: int = Field(default=993)
    imap_use_ssl: bool = Field(default=True)
    imap_username: str = Field(default="hudson.eboso@techbrain.africa")
    imap_password: str = Field(default="")

    smtp_server: str = Field(default="mail.techbrain.africa")
    smtp_port: int = Field(default=465)
    smtp_use_ssl: bool = Field(default=True)
    smtp_username: str = Field(default="hudson.eboso@techbrain.africa")
    smtp_password: str = Field(default="")
    report_recipient_email: str = Field(default="hudson.eboso@techbrain.africa")
    daily_schedule_time: str = Field(default="18:00")


class AppConfig(BaseSettings):
    """Main Application Configuration."""
    root_dir: Path = ROOT_DIR
    data_dir: Path = ROOT_DIR / "data"
    output_dir: Path = ROOT_DIR / "output"
    daily_reports_dir: Path = ROOT_DIR / "output" / "daily_reports"
    screenshots_dir: Path = ROOT_DIR / "output" / "screenshots"
    logs_dir: Path = ROOT_DIR / "logs"
    sessions_dir: Path = ROOT_DIR / "sessions"

    # CSV File paths
    application_tracker_path: Path = ROOT_DIR / "output" / "application_tracker.csv"
    external_jobs_path: Path = ROOT_DIR / "output" / "external_jobs_to_review.csv"

    # Sub-configurations
    candidate: CandidateConfig = Field(default_factory=CandidateConfig)
    target: TargetCriteriaConfig = Field(default_factory=TargetCriteriaConfig)
    scoring: ScoringConfig = Field(default_factory=ScoringConfig)
    llm: LLMConfig = Field(default_factory=LLMConfig)
    browser: BrowserConfig = Field(default_factory=BrowserConfig)
    email: EmailConfig = Field(default_factory=EmailConfig)

    max_applications_per_run: int = Field(default=15)
    dry_run: bool = Field(default=False)

    model_config = ConfigDict(arbitrary_types_allowed=True)


def get_config() -> AppConfig:
    """Factory to load and construct AppConfig from environment."""
    # Ensure standard directories exist on disk
    cfg = AppConfig()
    for directory in [
        cfg.data_dir,
        cfg.output_dir,
        cfg.daily_reports_dir,
        cfg.screenshots_dir,
        cfg.logs_dir,
        cfg.sessions_dir,
    ]:
        directory.mkdir(parents=True, exist_ok=True)

    # Candidate overrides from environment if present
    cfg.candidate.name = os.getenv("CANDIDATE_NAME", cfg.candidate.name)
    cfg.candidate.email = os.getenv("CANDIDATE_EMAIL", cfg.candidate.email)
    cfg.candidate.phone = os.getenv("CANDIDATE_PHONE", cfg.candidate.phone)
    cfg.candidate.location = os.getenv("CANDIDATE_LOCATION", cfg.candidate.location)
    cfg.candidate.linkedin_url = os.getenv("CANDIDATE_LINKEDIN", cfg.candidate.linkedin_url)
    cfg.candidate.github_url = os.getenv("CANDIDATE_GITHUB", cfg.candidate.github_url)
    cfg.candidate.portfolio_url = os.getenv("CANDIDATE_PORTFOLIO", cfg.candidate.portfolio_url)
    cfg.candidate.resume_path = os.getenv("RESUME_PATH", cfg.candidate.resume_path)

    # LLM overrides
    cfg.llm.provider = os.getenv("LLM_PROVIDER", cfg.llm.provider)
    cfg.llm.gemini_api_key = os.getenv("GEMINI_API_KEY", "")
    cfg.llm.gemini_model = os.getenv("GEMINI_MODEL", cfg.llm.gemini_model)
    cfg.llm.openai_api_key = os.getenv("OPENAI_API_KEY", "")
    cfg.llm.openai_model = os.getenv("OPENAI_MODEL", cfg.llm.openai_model)

    # Browser overrides
    cfg.browser.user_data_dir = os.getenv("BROWSER_USER_DATA_DIR", cfg.browser.user_data_dir)
    cfg.browser.headless = os.getenv("HEADLESS", "False").lower() in ("true", "1", "yes")
    cfg.browser.slow_mo_ms = int(os.getenv("SLOW_MO_MS", str(cfg.browser.slow_mo_ms)))

    # Target & Scoring overrides
    cfg.target.location = os.getenv("SEARCH_LOCATION", cfg.target.location)
    cfg.target.default_salary_yearly = float(os.getenv("DEFAULT_SALARY_YEARLY", str(cfg.target.default_salary_yearly)))
    cfg.target.default_salary_monthly = float(os.getenv("DEFAULT_SALARY_MONTHLY", str(cfg.target.default_salary_monthly)))
    cfg.scoring.auto_apply_threshold = float(os.getenv("IILS_AUTO_APPLY_THRESHOLD", str(cfg.scoring.auto_apply_threshold)))
    cfg.scoring.external_review_threshold = float(os.getenv("IILS_EXTERNAL_REVIEW_THRESHOLD", str(cfg.scoring.external_review_threshold)))
    cfg.scoring.safety_confidence_threshold = float(os.getenv("SAFETY_CONFIDENCE_THRESHOLD", str(cfg.scoring.safety_confidence_threshold)))

    cfg.max_applications_per_run = int(os.getenv("MAX_APPLICATIONS_PER_RUN", str(cfg.max_applications_per_run)))
    cfg.dry_run = os.getenv("DRY_RUN", "False").lower() in ("true", "1", "yes")

    # Email overrides
    cfg.email.imap_server = os.getenv("IMAP_SERVER", cfg.email.imap_server)
    cfg.email.imap_port = int(os.getenv("IMAP_PORT", str(cfg.email.imap_port)))
    cfg.email.imap_use_ssl = os.getenv("IMAP_USE_SSL", "True").lower() in ("true", "1", "yes")
    cfg.email.imap_username = os.getenv("IMAP_USERNAME", cfg.email.imap_username)
    cfg.email.imap_password = os.getenv("IMAP_PASSWORD", "")

    cfg.email.smtp_server = os.getenv("SMTP_SERVER", cfg.email.smtp_server)
    cfg.email.smtp_port = int(os.getenv("SMTP_PORT", str(cfg.email.smtp_port)))
    cfg.email.smtp_use_ssl = os.getenv("SMTP_USE_SSL", "True").lower() in ("true", "1", "yes")
    cfg.email.smtp_username = os.getenv("SMTP_USERNAME", cfg.email.smtp_username)
    cfg.email.smtp_password = os.getenv("SMTP_PASSWORD", "")
    cfg.email.report_recipient_email = os.getenv("REPORT_RECIPIENT_EMAIL", cfg.email.report_recipient_email)
    cfg.email.daily_schedule_time = os.getenv("DAILY_SCHEDULE_TIME", cfg.email.daily_schedule_time)

    return cfg
