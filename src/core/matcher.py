"""IILS (Interview Invitation Likelihood Score) Matchmaking Engine."""

import re
from typing import Dict, List, Optional, Set, Tuple
from pydantic import BaseModel, Field
from src.config import ScoringConfig, TargetCriteriaConfig
from src.core.cv_parser import CandidateProfile, KNOWN_SKILLS


class JobOpportunity(BaseModel):
    """Normalized LinkedIn Job Opportunity representation."""
    job_id: str
    title: str
    company: str
    location: str
    job_url: str
    is_easy_apply: bool = True
    posted_time_raw: str = "" # e.g. "2 hours ago", "1 day ago", "1 week ago"
    posted_hours_ago: Optional[float] = None
    applicant_count_raw: str = "" # e.g. "12 applicants", "Over 100 applicants"
    applicant_count: Optional[int] = None
    description: str = ""
    salary_raw: str = ""


class IILSScoreBreakdown(BaseModel):
    """Detailed breakdown of the IILS calculation."""
    skill_match_score: float = 0.0 # 0 - 100 (40% weight)
    time_posted_score: float = 0.0 # 0 - 100 (25% weight)
    applicant_count_score: float = 0.0 # 0 - 100 (20% weight)
    title_exactness_score: float = 0.0 # 0 - 100 (15% weight)
    total_iils: float = 0.0 # 0 - 100
    is_qualified_easy_apply: bool = False # IILS >= 70 & Easy Apply
    is_qualified_external_review: bool = False # IILS >= 80 & Non-Easy Apply
    matched_skills: List[str] = Field(default_factory=list)
    missing_skills: List[str] = Field(default_factory=list)
    is_remote_verified: bool = True
    disqualification_reason: Optional[str] = None


class IILSMatcher:
    """Calculates Interview Invitation Likelihood Score (IILS) and evaluates candidate eligibility."""

    def __init__(self, scoring_config: ScoringConfig, target_config: TargetCriteriaConfig):
        self.scoring = scoring_config
        self.target = target_config
        self.normalized_target_titles = [t.lower().strip() for t in target_config.target_titles]

    def parse_time_posted_hours(self, raw_time: str) -> float:
        """Converts raw relative time string (e.g. '2 hours ago', '1 day ago') into hours."""
        if not raw_time:
            return 12.0 # Default fallback to recent

        raw = raw_time.lower().strip()
        num_match = re.search(r"(\d+)", raw)
        num = float(num_match.group(1)) if num_match else 1.0

        if "minute" in raw or "min" in raw or "second" in raw or "just now" in raw:
            return 0.5
        elif "hour" in raw or "hr" in raw:
            return num
        elif "day" in raw:
            return num * 24.0
        elif "week" in raw:
            return num * 24.0 * 7.0
        elif "month" in raw:
            return num * 24.0 * 30.0

        return 24.0

    def parse_applicant_count(self, raw_applicants: str) -> int:
        """Parses applicant count string into an integer."""
        if not raw_applicants:
            return 15 # Default fallback

        raw = raw_applicants.lower().strip()
        if "over" in raw or "+" in raw or ">" in raw:
            num_match = re.search(r"(\d+)", raw)
            return int(num_match.group(1)) + 10 if num_match else 101

        num_match = re.search(r"(\d+)", raw)
        if num_match:
            return int(num_match.group(1))

        return 20

    def calculate_time_score(self, hours_ago: float) -> float:
        """
        Time Posted (25%):
        < 24h = 100 pts
        24–48h = 75 pts
        3–7 days (48h - 168h) = 40 pts
        > 7 days (168h+) = 0 pts
        """
        if hours_ago < 24.0:
            return 100.0
        elif hours_ago <= 48.0:
            return 75.0
        elif hours_ago <= 168.0: # 7 days
            return 40.0
        else:
            return 0.0

    def calculate_applicant_score(self, count: int) -> float:
        """
        Applicant Count (20%):
        < 25 = 100 pts
        25–50 = 70 pts
        51–100 = 40 pts
        > 100 = 10 pts
        """
        if count < 25:
            return 100.0
        elif count <= 50:
            return 70.0
        elif count <= 100:
            return 40.0
        else:
            return 10.0

    def calculate_title_score(self, job_title: str) -> float:
        """
        Title Exactness (15%):
        Exact match from target list = 100 pts
        Semantic / substring close match = 85 pts
        Relevant AI/Automation keywords = 70 pts
        Otherwise = 20 pts
        """
        title_lower = job_title.lower().strip()

        # Exact match
        for target in self.normalized_target_titles:
            # Clean parentheses like "(verified job)" for comparison
            clean_target = re.sub(r"\(.*?\)", "", target).strip()
            clean_title = re.sub(r"\(.*?\)", "", title_lower).strip()

            if clean_target == clean_title:
                return 100.0
            if clean_target in clean_title or clean_title in clean_target:
                return 85.0

        # Core keywords
        core_keywords = ["ai engineer", "automation engineer", "agent engineer", "agentic", "n8n", "prompt engineer", "workflow engineer", "solutions engineer"]
        for kw in core_keywords:
            if kw in title_lower:
                return 80.0

        if "ai" in title_lower or "automation" in title_lower or "agent" in title_lower:
            return 70.0

        return 20.0

    def calculate_skill_match(self, job_description: str, candidate: CandidateProfile) -> Tuple[float, List[str], List[str]]:
        """
        Skill Match (40%):
        Compare CV skills against job requirements.
        Returns: (skill_score_0_to_100, matched_skills, missing_skills)
        """
        desc_lower = job_description.lower()
        candidate_skills = candidate.get_skill_set()

        # Find which known skills appear in the job description
        job_required_skills = set()
        for skill in KNOWN_SKILLS:
            pattern = r"\b" + re.escape(skill) + r"\b"
            if re.search(pattern, desc_lower):
                job_required_skills.add(skill)

        # If job description has very few specific skills identified, use default AI tech stack
        if len(job_required_skills) < 3:
            job_required_skills.update({"python", "llm", "automation", "api integration", "prompt engineering"})

        matched = []
        missing = []

        for req in job_required_skills:
            # Check if any candidate skill matches requirement
            if any(req in c or c in req for c in candidate_skills):
                matched.append(req.title())
            else:
                missing.append(req.title())

        total_reqs = len(job_required_skills)
        if total_reqs == 0:
            return 85.0, list(candidate_skills)[:5], []

        match_ratio = (len(matched) / total_reqs) * 100.0
        # Boost if candidate has strong AI agentic foundations
        if any(core in candidate_skills for core in ["python", "langchain", "n8n", "playwright", "gemini"]):
            match_ratio = min(100.0, match_ratio + 10.0)

        return round(match_ratio, 2), matched, missing

    def verify_remote_eligibility(self, job: JobOpportunity) -> Tuple[bool, Optional[str]]:
        """Verifies remote criteria and screens for strict geographic restrictions."""
        text = f"{job.title} {job.location} {job.description}".lower()

        # Check for strict country-only restrictions if outside Africa/Global
        us_only_patterns = [
            r"\bmust reside in the (us|united states|usa)\b",
            r"\bus citizens only\b",
            r"\bno c2c\b",
            r"\bsecurity clearance required\b",
            r"\bauthorized to work in the us without sponsorship\b"
        ]
        for pattern in us_only_patterns:
            if re.search(pattern, text):
                return False, f"Geographic restriction detected: '{pattern}'"

        # Verify remote indicator
        if "remote" not in text and "anywhere" not in text and "work from home" not in text:
            # If location explicitly states an on-site city without remote
            if any(c in job.location.lower() for c in ["on-site", "hybrid", "in-person"]):
                return False, f"Non-remote job type: {job.location}"

        return True, None

    def evaluate(self, job: JobOpportunity, candidate: CandidateProfile) -> IILSScoreBreakdown:
        """
        Calculates the complete IILS score using the exact formula:
        IILS = (Skill_Match * 0.40) + (Time_Score * 0.25) + (Applicant_Score * 0.20) + (Title_Score * 0.15)
        """
        breakdown = IILSScoreBreakdown()

        # Remote Check
        is_remote, geo_reason = self.verify_remote_eligibility(job)
        breakdown.is_remote_verified = is_remote
        if not is_remote:
            breakdown.disqualification_reason = geo_reason

        # 1. Skill Match (40%)
        skill_score, matched, missing = self.calculate_skill_match(job.description, candidate)
        breakdown.skill_match_score = skill_score
        breakdown.matched_skills = matched
        breakdown.missing_skills = missing

        # 2. Time Posted (25%)
        hours_ago = job.posted_hours_ago if job.posted_hours_ago is not None else self.parse_time_posted_hours(job.posted_time_raw)
        time_score = self.calculate_time_score(hours_ago)
        breakdown.time_posted_score = time_score

        # 3. Applicant Count (20%)
        applicant_count = job.applicant_count if job.applicant_count is not None else self.parse_applicant_count(job.applicant_count_raw)
        applicant_score = self.calculate_applicant_score(applicant_count)
        breakdown.applicant_count_score = applicant_score

        # 4. Title Exactness (15%)
        title_score = self.calculate_title_score(job.title)
        breakdown.title_exactness_score = title_score

        # Weighted Total
        total = (
            (skill_score * self.scoring.skill_match_weight) +
            (time_score * self.scoring.time_posted_weight) +
            (applicant_score * self.scoring.applicant_count_weight) +
            (title_score * self.scoring.title_exactness_weight)
        )
        breakdown.total_iils = round(total, 2)

        # Qualification rules
        # Must meet remote criteria
        if is_remote:
            # Skill threshold check >= 75%
            has_min_skills = skill_score >= self.scoring.skill_min_match_threshold

            if job.is_easy_apply and breakdown.total_iils >= self.scoring.auto_apply_threshold and has_min_skills:
                breakdown.is_qualified_easy_apply = True
            elif not job.is_easy_apply and breakdown.total_iils >= self.scoring.external_review_threshold:
                breakdown.is_qualified_external_review = True
            elif not has_min_skills:
                breakdown.disqualification_reason = f"Skill match ({skill_score}%) below threshold ({self.scoring.skill_min_match_threshold}%)"
            elif breakdown.total_iils < self.scoring.auto_apply_threshold:
                breakdown.disqualification_reason = f"IILS ({breakdown.total_iils}) below threshold ({self.scoring.auto_apply_threshold})"
        else:
            breakdown.is_qualified_easy_apply = False
            breakdown.is_qualified_external_review = False

        return breakdown
