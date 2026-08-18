"""LLM Client for Application Question Answering and Email Classification."""

import os
import json
import logging
from typing import Dict, Optional, Tuple
from src.config import LLMConfig
from src.core.cv_parser import CandidateProfile

logger = logging.getLogger(__name__)


class LLMClient:
    """Unified LLM Client supporting Google Gemini and OpenAI with robust rule-based fallbacks."""

    def __init__(self, config: LLMConfig):
        self.config = config
        self.provider = config.provider.lower()
        self._gemini_client = None
        self._openai_client = None
        self._init_client()

    def _init_client(self):
        """Initializes API clients based on available keys."""
        if self.provider == "gemini" and self.config.gemini_api_key:
            try:
                # Try google-genai SDK first
                from google import genai
                self._gemini_client = genai.Client(api_key=self.config.gemini_api_key)
            except Exception:
                try:
                    # Fallback to google.generativeai SDK
                    import google.generativeai as gai
                    gai.configure(api_key=self.config.gemini_api_key)
                    self._gemini_client = gai
                except Exception as e:
                    logger.warning(f"Could not initialize Gemini client: {e}")

        elif self.provider == "openai" and self.config.openai_api_key:
            try:
                from openai import OpenAI
                self._openai_client = OpenAI(api_key=self.config.openai_api_key)
            except Exception as e:
                logger.warning(f"Could not initialize OpenAI client: {e}")

    def generate_answer(
        self,
        question: str,
        job_title: str,
        company_name: str,
        job_description: str,
        candidate: CandidateProfile
    ) -> Tuple[str, float]:
        """
        Generates a concise, 2-3 sentence answer linking CV projects and skills to the job.
        Returns: (answer_text, confidence_score_0_to_100)
        """
        prompt = f"""
You are an expert AI Job Application Assistant acting on behalf of {candidate.full_name}.
Candidate Profile:
- Email: {candidate.email}
- Phone: {candidate.phone}
- Experience: {candidate.total_years_experience} years
- Key Skills: {", ".join(candidate.skills[:20])}
- Summary: {candidate.summary}

Target Job:
- Title: {job_title}
- Company: {company_name}
- Requirements / Excerpt: {job_description[:1000]}

Application Question: "{question}"

Instructions:
1. Write a professional, punchy 2-3 sentence answer.
2. Directly link the candidate's actual AI/automation skills and projects to this specific requirement.
3. Sound confident, authentic, and technically proficient.
4. Output JSON strictly with this schema:
{{
  "answer": "...",
  "confidence": 95
}}
"""
        # Try LLM generation
        if self._gemini_client:
            try:
                if hasattr(self._gemini_client, "models"):
                    response = self._gemini_client.models.generate_content(
                        model=self.config.gemini_model,
                        contents=prompt,
                    )
                    text = response.text
                else:
                    model = self._gemini_client.GenerativeModel(self.config.gemini_model)
                    response = model.generate_content(prompt)
                    text = response.text
                
                parsed = self._extract_json(text)
                if parsed and "answer" in parsed:
                    return parsed["answer"].strip(), float(parsed.get("confidence", 90))
            except Exception as e:
                logger.warning(f"Gemini generation error: {e}")

        if self._openai_client:
            try:
                response = self._openai_client.chat.completions.create(
                    model=self.config.openai_model,
                    messages=[
                        {"role": "system", "content": "You are a professional job application assistant. Respond in JSON."},
                        {"role": "user", "content": prompt}
                    ],
                    response_format={"type": "json_object"}
                )
                text = response.choices[0].message.content
                parsed = json.loads(text)
                return parsed.get("answer", "").strip(), float(parsed.get("confidence", 90))
            except Exception as e:
                logger.warning(f"OpenAI generation error: {e}")

        # Intelligent Rule-based contextual fallback
        return self._rule_based_answer(question, candidate, job_title)

    def _rule_based_answer(self, question: str, candidate: CandidateProfile, job_title: str) -> Tuple[str, float]:
        """Provides a safe, high-quality rule-based fallback answer."""
        q_lower = question.lower()

        if any(w in q_lower for w in ["experience", "years", "background"]):
            answer = (
                f"I have over {candidate.total_years_experience} years of experience designing and implementing "
                f"production AI systems, autonomous agentic workflows, and robust automation pipelines using Python, "
                f"LangChain, LangGraph, and n8n to deliver high-impact business outcomes."
            )
            return answer, 90.0

        if any(w in q_lower for w in ["why", "interest", "motivation", "company", "role"]):
            answer = (
                f"I am passionate about advancing applied AI engineering and creating reliable agentic architectures. "
                f"My expertise in building production-ready LLM workflows aligns directly with the goals of this {job_title} "
                f"role, making this an ideal opportunity to contribute immediate value."
            )
            return answer, 90.0

        if any(w in q_lower for w in ["challenge", "project", "accomplishment"]):
            answer = (
                f"In my recent work, I architected an autonomous multi-agent pipeline that streamlined complex multi-step "
                f"data analysis and workflow automation, achieving over 90% latency reduction and reliable enterprise integration."
            )
            return answer, 88.0

        if any(w in q_lower for w in ["salary", "compensation", "rate"]):
            return "$60,000 USD / year (flexible based on total compensation and responsibilities).", 95.0

        # General answer
        answer = (
            f"With deep hands-on expertise in {', '.join(candidate.skills[:4])}, I specialize in building "
            f"scalable, resilient AI automation solutions that solve complex technical and workflow challenges."
        )
        return answer, 86.0

    def classify_email(self, subject: str, sender: str, body: str) -> Tuple[str, float, str]:
        """
        Classifies incoming email into:
        - INTERVIEW_INVITE
        - ASSESSMENT_REQUEST
        - REJECTION
        - ACKNOWLEDGMENT
        - UNRELATED

        Returns: (classification, confidence, action_item)
        """
        prompt = f"""
You are an email classification agent monitoring job applications for candidate Hudson Eboso (hudson.eboso@techbrain.africa).

Email Details:
Sender: {sender}
Subject: {subject}
Body: {body[:1500]}

Classify this email into exactly ONE of the following categories:
1. INTERVIEW_INVITE (Interview requests, scheduling links like Calendly/Loom/Google Meet/Zoom, recruiter direct outreach)
2. ASSESSMENT_REQUEST (Technical tests, take-home projects, HackerRank/ByteByteGo links, coding challenges)
3. REJECTION (Standard rejection letters, position closed, moving forward with other applicants)
4. ACKNOWLEDGMENT (Application received confirmations, profile submission receipt)
5. UNRELATED (Newsletters, marketing, unrelated notifications)

Output JSON strictly with this schema:
{{
  "category": "INTERVIEW_INVITE",
  "confidence": 95,
  "action_item": "Schedule interview via Calendly link: https://calendly.com/..."
}}
"""
        # Try LLM
        if self._gemini_client:
            try:
                if hasattr(self._gemini_client, "models"):
                    response = self._gemini_client.models.generate_content(
                        model=self.config.gemini_model,
                        contents=prompt,
                    )
                    text = response.text
                else:
                    model = self._gemini_client.GenerativeModel(self.config.gemini_model)
                    response = model.generate_content(prompt)
                    text = response.text
                
                parsed = self._extract_json(text)
                if parsed and "category" in parsed:
                    return (
                        parsed["category"].upper(),
                        float(parsed.get("confidence", 90)),
                        parsed.get("action_item", "")
                    )
            except Exception as e:
                logger.warning(f"Gemini email classification error: {e}")

        if self._openai_client:
            try:
                response = self._openai_client.chat.completions.create(
                    model=self.config.openai_model,
                    messages=[
                        {"role": "system", "content": "You are an email classification assistant. Respond in JSON."},
                        {"role": "user", "content": prompt}
                    ],
                    response_format={"type": "json_object"}
                )
                text = response.choices[0].message.content
                parsed = json.loads(text)
                return (
                    parsed.get("category", "UNRELATED").upper(),
                    float(parsed.get("confidence", 90)),
                    parsed.get("action_item", "")
                )
            except Exception as e:
                logger.warning(f"OpenAI email classification error: {e}")

        # Rule-based fallback classifier
        return self._rule_based_classify(subject, body)

    def _rule_based_classify(self, subject: str, body: str) -> Tuple[str, float, str]:
        """Robust rule-based heuristic email classifier."""
        combined = f"{subject} {body}".lower()

        # Interview Invites
        interview_keywords = ["interview", "invitation to interview", "calendly.com", "calendar invite", "zoom.us", "meet.google", "speak with our team", "chat about your application", "schedule a call", "hiring manager"]
        if any(k in combined for k in interview_keywords) and not any(r in combined for r in ["not moving forward", "unfortunately", "declined"]):
            action = "Action Required: Check email and schedule interview call."
            return "INTERVIEW_INVITE", 92.0, action

        # Assessment Requests
        assessment_keywords = ["hackerrank", "bytebytego", "codility", "technical test", "take-home", "coding challenge", "assessment test", "technical assessment"]
        if any(k in combined for k in assessment_keywords):
            action = "Action Required: Complete technical assessment / coding challenge."
            return "ASSESSMENT_REQUEST", 95.0, action

        # Rejection
        rejection_keywords = ["unfortunately", "not moving forward", "decided to pursue other", "other candidates", "regret to inform", "not selected", "position has been filled"]
        if any(k in combined for k in rejection_keywords):
            return "REJECTION", 90.0, "No action required."

        # Acknowledgment
        ack_keywords = ["application received", "thank you for applying", "we have received your application", "application submitted", "thanks for your interest"]
        if any(k in combined for k in ack_keywords):
            return "ACKNOWLEDGMENT", 88.0, "Application logged by company."

        return "UNRELATED", 60.0, ""

    def _extract_json(self, text: str) -> Optional[Dict]:
        """Extracts JSON dictionary from response text containing markdown code blocks."""
        try:
            # Check for ```json ... ```
            if "```" in text:
                match = text.split("```")[1]
                if match.startswith("json"):
                    match = match[4:]
                return json.loads(match.strip())
            return json.loads(text.strip())
        except Exception:
            return None
