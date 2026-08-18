"""Tests for IILS Matchmaking Engine and Scoring Rules."""

import pytest
from src.config import ScoringConfig, TargetCriteriaConfig
from src.core.cv_parser import CandidateProfile
from src.core.matcher import IILSMatcher, JobOpportunity


@pytest.fixture
def candidate():
    return CandidateProfile(
        full_name="Hudson E. Omunga",
        email="hudson.eboso@techbrain.africa",
        phone="+254727869396",
        total_years_experience=5,
        skills=["Python", "LangChain", "LangGraph", "n8n", "Playwright", "Docker", "FastAPI", "Prompt Engineering", "LLM", "Agentic Workflows"]
    )


@pytest.fixture
def matcher():
    return IILSMatcher(
        scoring_config=ScoringConfig(),
        target_config=TargetCriteriaConfig()
    )


def test_time_posted_scoring(matcher):
    # < 24h = 100
    assert matcher.calculate_time_score(2.0) == 100.0
    assert matcher.calculate_time_score(23.9) == 100.0
    # 24 - 48h = 75
    assert matcher.calculate_time_score(24.0) == 75.0
    assert matcher.calculate_time_score(47.0) == 75.0
    # 3 - 7 days (48 - 168h) = 40
    assert matcher.calculate_time_score(72.0) == 40.0
    # > 7 days = 0
    assert matcher.calculate_time_score(200.0) == 0.0


def test_applicant_count_scoring(matcher):
    # < 25 = 100
    assert matcher.calculate_applicant_score(10) == 100.0
    assert matcher.calculate_applicant_score(24) == 100.0
    # 25 - 50 = 70
    assert matcher.calculate_applicant_score(25) == 70.0
    assert matcher.calculate_applicant_score(50) == 70.0
    # 51 - 100 = 40
    assert matcher.calculate_applicant_score(75) == 40.0
    # > 100 = 10
    assert matcher.calculate_applicant_score(150) == 10.0


def test_title_exactness_scoring(matcher):
    # Exact match from target list
    assert matcher.calculate_title_score("AI Engineer") == 100.0
    assert matcher.calculate_title_score("AI Automation Engineer") == 100.0
    assert matcher.calculate_title_score("Automation Specialist (n8n Expert)") == 100.0
    # Substring / variation
    assert matcher.calculate_title_score("Senior AI Engineer") == 85.0
    # Core keywords
    assert matcher.calculate_title_score("AI Agent Architect") >= 70.0


def test_iils_high_match_auto_apply(matcher, candidate):
    job = JobOpportunity(
        job_id="test_001",
        title="AI Engineer",
        company="TechCorp",
        location="Remote Worldwide",
        job_url="https://linkedin.com/jobs/view/123",
        is_easy_apply=True,
        posted_hours_ago=5.0, # 100 pts
        applicant_count=12,   # 100 pts
        description="We are seeking an AI Engineer skilled in Python, LangChain, LLMs, and workflow automation."
    )

    breakdown = matcher.evaluate(job, candidate)
    assert breakdown.is_remote_verified is True
    assert breakdown.time_posted_score == 100.0
    assert breakdown.applicant_count_score == 100.0
    assert breakdown.title_exactness_score == 100.0
    assert breakdown.skill_match_score >= 75.0
    assert breakdown.total_iils >= 70.0
    assert breakdown.is_qualified_easy_apply is True


def test_iils_non_easy_apply_external_review(matcher, candidate):
    job = JobOpportunity(
        job_id="test_002",
        title="AI Solutions Engineer",
        company="GlobalAI",
        location="Remote",
        job_url="https://linkedin.com/jobs/view/456",
        is_easy_apply=False, # External application
        posted_hours_ago=10.0,
        applicant_count=15,
        description="Looking for an AI Solutions Engineer experienced with Python, LangGraph, LLM agents, and n8n."
    )

    breakdown = matcher.evaluate(job, candidate)
    assert breakdown.total_iils >= 80.0
    assert breakdown.is_qualified_easy_apply is False
    assert breakdown.is_qualified_external_review is True


def test_geographic_restriction_filter(matcher, candidate):
    job = JobOpportunity(
        job_id="test_003",
        title="AI Engineer",
        company="USOnlyCorp",
        location="Remote (US)",
        job_url="https://linkedin.com/jobs/view/789",
        is_easy_apply=True,
        posted_hours_ago=2.0,
        applicant_count=5,
        description="Must reside in the US. US Citizens only. Security clearance required."
    )

    breakdown = matcher.evaluate(job, candidate)
    assert breakdown.is_remote_verified is False
    assert breakdown.is_qualified_easy_apply is False
