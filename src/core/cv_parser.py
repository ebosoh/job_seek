"""CV and Resume Parser for extracting candidate metadata, skills, and experience."""

import os
import re
from pathlib import Path
from typing import Dict, List, Optional, Set
from pydantic import BaseModel, Field

try:
    from pypdf import PdfReader
except ImportError:
    PdfReader = None

try:
    import pdfplumber
except ImportError:
    pdfplumber = None


class CandidateProfile(BaseModel):
    """Structured Candidate Profile parsed from CV or configuration."""
    full_name: str = "Hudson E. Omunga"
    email: str = "hudson.eboso@techbrain.africa"
    phone: str = "+254727869396"
    location: str = "Nairobi, Kenya (Remote Worldwide)"
    linkedin_url: str = "https://www.linkedin.com/in/hudson-eboso"
    github_url: str = "https://github.com/ebosoh"
    portfolio_url: str = "https://techbrain.africa"
    total_years_experience: int = 5
    summary: str = ""
    skills: List[str] = Field(default_factory=list)
    raw_text: str = ""
    projects: List[str] = Field(default_factory=list)
    education: List[str] = Field(default_factory=list)
    experience_entries: List[Dict[str, str]] = Field(default_factory=list)

    def get_skill_set(self) -> Set[str]:
        """Returns normalized lowercase skill set."""
        return {s.strip().lower() for s in self.skills if s.strip()}


# Standard AI/Automation skill dictionary for keyword extraction and matching
KNOWN_SKILLS = [
    # AI / ML / LLMs
    "python", "prompt engineering", "llm", "large language models", "agentic workflows",
    "langchain", "langgraph", "llamaindex", "autogen", "crewai", "openai", "gemini",
    "anthropic", "claude", "rag", "retrieval augmented generation", "vector databases",
    "pinecone", "chromadb", "qdrant", "weaviate", "faiss", "pytorch", "tensorflow",
    "fine-tuning", "lora", "transformers", "huggingface", "machine learning", "deep learning",
    "nlp", "natural language processing", "computer vision",

    # Automation & Workflow Tools
    "n8n", "zapier", "make.com", "integromat", "browser automation", "playwright",
    "selenium", "puppeteer", "web scraping", "beautifulsoup", "scrapy", "rpa",
    "workflow automation", "process automation", "api integration",

    # Backend & Production Engineering
    "fastapi", "flask", "django", "rest api", "graphql", "microservices", "docker",
    "kubernetes", "git", "github", "ci/cd", "github actions", "linux", "bash",
    "postgresql", "mongodb", "redis", "sqlite", "aws", "gcp", "google cloud", "azure",
    "cloud functions", "lambda", "serverless", "event-driven architecture",

    # Soft / Engineering skills
    "system architecture", "agent engineering", "solutions engineering", "problem solving",
    "technical documentation", "agile", "scrum"
]


class CVParser:
    """Parses CV / Resume files (PDF and TXT) into a structured CandidateProfile."""

    def __init__(self, resume_path: Optional[str] = None):
        self.resume_path = resume_path

    def locate_resume(self, project_root: Optional[Path] = None) -> Optional[Path]:
        """Locates the resume file from specified path or standard data directory."""
        if self.resume_path:
            p = Path(self.resume_path)
            if p.is_file():
                return p
            if project_root and (project_root / self.resume_path).is_file():
                return project_root / self.resume_path

        # Check standard data directory candidates
        if project_root:
            data_dir = project_root / "data"
            if data_dir.exists():
                # Check for exact name first
                preferred = data_dir / "Hudson E. Omunga- AI Engineer CV-2026.pdf"
                if preferred.is_file():
                    return preferred

                # Check for any .pdf in data
                pdf_files = list(data_dir.glob("*.pdf"))
                if pdf_files:
                    return pdf_files[0]

                # Check for .txt
                txt_files = list(data_dir.glob("*.txt"))
                if txt_files:
                    return txt_files[0]

        return None

    def extract_text_from_pdf(self, pdf_path: Path) -> str:
        """Extracts plain text from a PDF file using pdfplumber or pypdf."""
        text = ""
        if pdfplumber:
            try:
                with pdfplumber.open(pdf_path) as pdf:
                    for page in pdf.pages:
                        extracted = page.extract_text()
                        if extracted:
                            text += extracted + "\n"
                if text.strip():
                    return text
            except Exception:
                pass

        if PdfReader:
            try:
                reader = PdfReader(str(pdf_path))
                for page in reader.pages:
                    extracted = page.extract_text()
                    if extracted:
                        text += extracted + "\n"
                if text.strip():
                    return text
            except Exception:
                pass

        return text

    def extract_metadata(self, text: str) -> Dict:
        """Extracts contact information, years of experience, and skills from raw text."""
        extracted = {}

        # Email extraction
        email_match = re.search(r"[\w.+-]+@[\w-]+\.[\w.-]+", text)
        if email_match:
            extracted["email"] = email_match.group(0)

        # Phone extraction (labeled or standard international)
        phone_match = re.search(r"(?:phone|tel|mobile|cell)?\s*[:.-]?\s*(\+?\d{1,4}[\s.-]?\(?\d{1,4}\)?[\s.-]?\d{3,4}[\s.-]?\d{3,6})", text, re.IGNORECASE)
        if phone_match:
            extracted["phone"] = phone_match.group(1).strip()
        else:
            phone_fallback = re.search(r"(\+?\d{1,4}[\s.-]?\d{3,4}[\s.-]?\d{3,6})", text)
            if phone_fallback and len(phone_fallback.group(1).strip()) >= 9:
                extracted["phone"] = phone_fallback.group(1).strip()

        # URLs
        linkedin_match = re.search(r"(https?://(?:www\.)?linkedin\.com/in/[\w-]+)", text, re.IGNORECASE)
        if linkedin_match:
            extracted["linkedin_url"] = linkedin_match.group(1)

        github_match = re.search(r"(https?://(?:www\.)?github\.com/[\w-]+)", text, re.IGNORECASE)
        if github_match:
            extracted["github_url"] = github_match.group(1)

        portfolio_match = re.search(r"(https?://(?:www\.)?techbrain\.africa[\w/-]*)", text, re.IGNORECASE)
        if portfolio_match:
            extracted["portfolio_url"] = portfolio_match.group(1)

        # Experience extraction (e.g. "5+ years", "5 years of experience")
        exp_matches = re.findall(r"(\d+)\+?\s*(?:years|yrs)\b", text, re.IGNORECASE)
        if exp_matches:
            try:
                years = [int(y) for y in exp_matches if int(y) < 40]
                if years:
                    extracted["total_years_experience"] = max(years)
            except Exception:
                pass

        # Skill extraction
        lowered = text.lower()
        matched_skills = []
        for skill in KNOWN_SKILLS:
            # Word boundary regex search
            pattern = r"\b" + re.escape(skill) + r"\b"
            if re.search(pattern, lowered):
                matched_skills.append(skill.title())

        extracted["skills"] = list(set(matched_skills))
        return extracted

    def parse(self, project_root: Optional[Path] = None, fallback_defaults: Optional[CandidateProfile] = None) -> CandidateProfile:
        """Parses the resume and returns a structured CandidateProfile."""
        profile = fallback_defaults or CandidateProfile()
        resume_file = self.locate_resume(project_root)

        if not resume_file or not resume_file.is_file():
            # If no file exists yet, populate default high-match skills for Hudson Eboso
            if not profile.skills:
                profile.skills = [
                    "Python", "LangChain", "LangGraph", "LlamaIndex", "AutoGen", "CrewAI",
                    "OpenAI", "Gemini", "Claude", "RAG", "Vector Databases", "ChromaDB",
                    "Pinecone", "n8n", "Playwright", "Browser Automation", "FastAPI",
                    "Docker", "Prompt Engineering", "Agentic Workflows", "Workflow Automation",
                    "REST API", "PostgreSQL", "Git", "System Architecture"
                ]
            profile.summary = (
                f"{profile.full_name} is an experienced AI & Automation Engineer specializing in "
                "Agentic Workflows, LLM systems (Gemini, OpenAI, LangGraph, CrewAI), and production "
                "workflow automation (n8n, Python, Playwright). Highly skilled in building reliable, "
                "scalable autonomous agents, RAG architectures, and API integrations."
            )
            return profile

        # Extract text based on file format
        text = ""
        if resume_file.suffix.lower() == ".pdf":
            text = self.extract_text_from_pdf(resume_file)
        else:
            try:
                text = resume_file.read_text(encoding="utf-8", errors="ignore")
            except Exception:
                pass

        profile.raw_text = text

        if text.strip():
            metadata = self.extract_metadata(text)
            if fallback_defaults and fallback_defaults.email:
                profile.email = fallback_defaults.email
            elif "email" in metadata:
                profile.email = metadata["email"]

            if fallback_defaults and fallback_defaults.phone:
                profile.phone = fallback_defaults.phone
            elif "phone" in metadata:
                profile.phone = metadata["phone"]

            if fallback_defaults and fallback_defaults.linkedin_url:
                profile.linkedin_url = fallback_defaults.linkedin_url
            elif "linkedin_url" in metadata:
                profile.linkedin_url = metadata["linkedin_url"]

            if fallback_defaults and fallback_defaults.github_url:
                profile.github_url = fallback_defaults.github_url
            elif "github_url" in metadata:
                profile.github_url = metadata["github_url"]

            if fallback_defaults and fallback_defaults.portfolio_url:
                profile.portfolio_url = fallback_defaults.portfolio_url
            elif "portfolio_url" in metadata:
                profile.portfolio_url = metadata["portfolio_url"]

            if "total_years_experience" in metadata:
                profile.total_years_experience = metadata["total_years_experience"]
            if "skills" in metadata and metadata["skills"]:
                profile.skills = list(set(profile.skills + metadata["skills"]))

        # Guarantee foundational skills if list is sparse
        if len(profile.skills) < 5:
            profile.skills = list(set(profile.skills + [
                "Python", "LangChain", "LangGraph", "n8n", "Playwright", "Prompt Engineering",
                "Agentic Workflows", "LLM", "FastAPI", "Docker", "RAG", "Automation"
            ]))

        profile.summary = (
            f"{profile.full_name} - AI Engineer & Automation Specialist with {profile.total_years_experience} "
            f"years of experience building autonomous agents, n8n workflows, and production LLM applications."
        )
        return profile
