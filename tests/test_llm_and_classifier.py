"""Tests for LLM question generation and email classification logic."""

import pytest
from src.config import LLMConfig
from src.core.cv_parser import CandidateProfile
from src.core.llm_client import LLMClient


@pytest.fixture
def candidate():
    return CandidateProfile(
        full_name="Hudson E. Omunga",
        email="hudson.eboso@techbrain.africa",
        phone="+254727869396",
        total_years_experience=5,
        skills=["Python", "LangChain", "n8n", "Playwright", "FastAPI"]
    )


@pytest.fixture
def llm_client():
    return LLMClient(config=LLMConfig())


def test_rule_based_question_answering(llm_client, candidate):
    # Experience question
    ans, conf = llm_client.generate_answer(
        question="How many years of experience do you have in AI?",
        job_title="AI Engineer",
        company_name="Acme Inc",
        job_description="AI Engineer role with Python and LLMs",
        candidate=candidate
    )
    assert "5 years" in ans or "experience" in ans
    assert conf >= 85.0

    # Motivation question
    ans2, conf2 = llm_client.generate_answer(
        question="Why are you interested in this role?",
        job_title="AI Automation Engineer",
        company_name="Acme Inc",
        job_description="Automation role",
        candidate=candidate
    )
    assert "AI Automation Engineer" in ans2 or "applied AI" in ans2
    assert conf2 >= 85.0


def test_email_classification_interview_invite(llm_client):
    subject = "Invitation to Interview: AI Engineer position at AnthroTech"
    body = "Hi Hudson, we were impressed with your application and would like to invite you to an interview. Please schedule a call via our Calendly link: https://calendly.com/anthrotech/interview"
    cat, conf, action = llm_client.classify_email(subject=subject, sender="recruiting@anthrotech.com", body=body)

    assert cat == "INTERVIEW_INVITE"
    assert conf >= 80.0
    assert "interview" in action.lower() or "schedule" in action.lower()


def test_email_classification_assessment_request(llm_client):
    subject = "Action Required: Complete Technical Assessment for AI Engineer role"
    body = "Please complete your HackerRank coding challenge within 48 hours: https://www.hackerrank.com/tests/123"
    cat, conf, action = llm_client.classify_email(subject=subject, sender="assessments@techcorp.com", body=body)

    assert cat == "ASSESSMENT_REQUEST"
    assert "assessment" in action.lower() or "challenge" in action.lower()


def test_email_classification_rejection(llm_client):
    subject = "Update on your application for AI Engineer"
    body = "Unfortunately, we have decided to move forward with other candidates whose profiles more closely match our current requirements."
    cat, conf, action = llm_client.classify_email(subject=subject, sender="no-reply@company.com", body=body)

    assert cat == "REJECTION"


def test_email_classification_acknowledgment(llm_client):
    subject = "Thank you for applying to AI Solutions Engineer"
    body = "We have received your application and will review your profile shortly."
    cat, conf, action = llm_client.classify_email(subject=subject, sender="jobs@solutions.io", body=body)

    assert cat == "ACKNOWLEDGMENT"
