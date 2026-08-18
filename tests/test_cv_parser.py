"""Tests for CV Parser and Candidate Profile extraction."""

from pathlib import Path
import pytest
from src.core.cv_parser import CVParser, CandidateProfile


def test_candidate_profile_defaults():
    profile = CandidateProfile(
        full_name="Hudson E. Omunga",
        email="hudson.eboso@techbrain.africa",
        phone="+254727869396",
        total_years_experience=5,
        skills=["Python", "LangChain", "n8n", "Playwright", "Gemini"]
    )
    skill_set = profile.get_skill_set()
    assert "python" in skill_set
    assert "langchain" in skill_set
    assert "n8n" in skill_set
    assert profile.email == "hudson.eboso@techbrain.africa"
    assert profile.phone == "+254727869396"


def test_cv_parser_metadata_extraction():
    parser = CVParser()
    sample_text = """
    Hudson E. Omunga
    Email: hudson.eboso@techbrain.africa
    Phone: +254727869396
    LinkedIn: https://www.linkedin.com/in/hudson-eboso
    GitHub: https://github.com/ebosoh
    5+ years of experience in AI Engineering, LangChain, LangGraph, n8n, Python, Docker, FastApi, Playwright.
    """
    metadata = parser.extract_metadata(sample_text)
    assert metadata["email"] == "hudson.eboso@techbrain.africa"
    assert metadata["phone"] == "+254727869396"
    assert metadata["total_years_experience"] == 5
    assert "Python" in metadata["skills"]
    assert "Langchain" in metadata["skills"]
    assert "N8N" in [s.upper() for s in metadata["skills"]]


def test_cv_parser_from_file(tmp_path):
    cv_file = tmp_path / "Hudson E. Omunga- AI Engineer CV-2026.txt"
    cv_file.write_text("""
    Hudson E. Omunga
    Email: hudson.eboso@techbrain.africa
    Phone: +254727869396
    Over 6 years of experience building autonomous agents with Python, LangGraph, n8n, and Playwright.
    """, encoding="utf-8")

    parser = CVParser(resume_path=str(cv_file))
    profile = parser.parse(project_root=tmp_path)
    assert profile.email == "hudson.eboso@techbrain.africa"
    assert profile.phone == "+254727869396"
    assert profile.total_years_experience == 6
    assert "Python" in profile.skills
