"""LinkedIn Job Search & Opportunity Scraper."""

import asyncio
import logging
import re
import urllib.parse
from typing import List, Tuple
from playwright.async_api import Page
from src.config import AppConfig
from src.core.cv_parser import CandidateProfile
from src.core.matcher import IILSMatcher, IILSScoreBreakdown, JobOpportunity
from src.data.tracker import ApplicationTracker

logger = logging.getLogger(__name__)


class LinkedInJobScanner:
    """Scrapes and evaluates LinkedIn job search listings against IILS criteria."""

    def __init__(self, config: AppConfig, matcher: IILSMatcher, tracker: ApplicationTracker):
        self.config = config
        self.matcher = matcher
        self.tracker = tracker

    def build_search_url(self, keyword: str, remote_only: bool = True, easy_apply_only: bool = False, past_24h: bool = True) -> str:
        """Constructs LinkedIn Jobs search URL with appropriate filter parameters."""
        params = {
            "keywords": keyword,
            "location": "Worldwide",
            "sortBy": "DD" # Sort by most recent date
        }

        # Remote filter (f_WT=2 is Remote on LinkedIn)
        if remote_only:
            params["f_WT"] = "2"

        # Easy apply filter
        if easy_apply_only:
            params["f_AL"] = "true"

        # Past 24 hours filter
        if past_24h:
            params["f_TPR"] = "r86400"

        encoded = urllib.parse.urlencode(params)
        return f"https://www.linkedin.com/jobs/search/?{encoded}"

    async def scan_jobs_for_keyword(
        self,
        page: Page,
        keyword: str,
        candidate: CandidateProfile,
        max_jobs: int = 10
    ) -> List[Tuple[JobOpportunity, IILSScoreBreakdown]]:
        """Scans and scores job cards for a given target keyword."""
        search_url = self.build_search_url(keyword=keyword, remote_only=True, easy_apply_only=False)
        logger.info(f"Navigating to search URL: {search_url}")

        try:
            await page.goto(search_url, wait_until="domcontentloaded", timeout=30000)
            await asyncio.sleep(3)
        except Exception as e:
            logger.warning(f"Error loading search URL {search_url}: {e}")
            return []

        # Find job list container and cards
        card_selectors = [
            "li.jobs-search-results__list-item",
            "div.job-card-container",
            "li.scaffold-layout__list-item",
            "div[data-job-id]"
        ]

        cards = []
        for selector in card_selectors:
            cards = await page.query_selector_all(selector)
            if cards:
                break

        if not cards:
            logger.info(f"No job cards found for keyword: '{keyword}'")
            return []

        applied_ids = self.tracker.get_applied_job_ids()
        results: List[Tuple[JobOpportunity, IILSScoreBreakdown]] = []

        for index, card in enumerate(cards[:max_jobs]):
            try:
                # Scroll card into view
                await card.scroll_into_view_if_needed()
                await asyncio.sleep(0.5)

                # Extract Job ID
                job_id = None
                data_id = await card.get_attribute("data-occludable-job-id") or await card.get_attribute("data-job-id")
                if data_id:
                    job_id = data_id.strip()

                # Extract title and link
                title_elem = await card.query_selector("a.job-card-list__title, a.job-card-container__link, strong")
                title = (await title_elem.inner_text()).strip() if title_elem else "AI Engineer"

                link_elem = await card.query_selector("a[href*='/jobs/view/']")
                href = await link_elem.get_attribute("href") if link_elem else ""

                if not job_id and href:
                    match = re.search(r"/jobs/view/(\d+)", href)
                    if match:
                        job_id = match.group(1)

                if not job_id:
                    job_id = f"custom_{keyword.replace(' ', '_')}_{index}"

                # Skip if already processed
                if job_id in applied_ids:
                    logger.info(f"Skipping already processed job ID: {job_id}")
                    continue

                full_url = f"https://www.linkedin.com/jobs/view/{job_id}/" if job_id and not job_id.startswith("custom_") else (href or search_url)

                # Company
                company_elem = await card.query_selector(".job-card-container__primary-description, .artdeco-entity-lockup__subtitle")
                company = (await company_elem.inner_text()).strip() if company_elem else "Unknown Company"

                # Location
                loc_elem = await card.query_selector(".job-card-container__metadata-item, .artdeco-entity-lockup__caption")
                location = (await loc_elem.inner_text()).strip() if loc_elem else "Remote"

                # Click card to load detail pane
                await card.click()
                await asyncio.sleep(1.5)

                # Extract details from detail pane
                detail_pane = await page.query_selector(".jobs-search__job-details, .scaffold-layout__detail")

                # Easy Apply Badge check
                easy_apply_btn = await page.query_selector("button.jobs-apply-button")
                is_easy_apply = False
                if easy_apply_btn:
                    btn_text = (await easy_apply_btn.inner_text()).lower()
                    is_easy_apply = "easy apply" in btn_text

                # Posted time and applicant count
                posted_time_raw = "1 day ago"
                applicant_raw = "20 applicants"

                info_items = await page.query_selector_all(".jobs-unified-top-card__primary-description-container span, .jobs-unified-top-card__subtitle-primary span")
                for item in info_items:
                    text = (await item.inner_text()).strip()
                    if any(t in text.lower() for t in ["hour", "day", "week", "minute", "ago"]):
                        posted_time_raw = text
                    if "applicant" in text.lower():
                        applicant_raw = text

                # Job Description
                desc_elem = await page.query_selector("#job-details, .jobs-description__content, .jobs-box__html-content")
                desc_text = (await desc_elem.inner_text()).strip() if desc_elem else f"{title} at {company}. Remote AI automation engineering role."

                job = JobOpportunity(
                    job_id=job_id,
                    title=title,
                    company=company,
                    location=location,
                    job_url=full_url,
                    is_easy_apply=is_easy_apply,
                    posted_time_raw=posted_time_raw,
                    applicant_count_raw=applicant_raw,
                    description=desc_text
                )

                # Score with IILS Matcher
                score = self.matcher.evaluate(job, candidate)
                results.append((job, score))

            except Exception as e:
                logger.warning(f"Error parsing job card index {index}: {e}")
                continue

        return results

    async def scan_all_targets(
        self,
        page: Page,
        candidate: CandidateProfile,
        max_jobs_per_title: int = 5
    ) -> List[Tuple[JobOpportunity, IILSScoreBreakdown]]:
        """Scans across all target job titles configured for the candidate."""
        all_results = []
        seen_job_ids = set()

        for title in self.config.target.target_titles:
            logger.info(f"Scanning target title: '{title}'...")
            jobs = await self.scan_jobs_for_keyword(
                page=page,
                keyword=title,
                candidate=candidate,
                max_jobs=max_jobs_per_title
            )

            for job, score in jobs:
                if job.job_id not in seen_job_ids:
                    seen_job_ids.add(job.job_id)
                    all_results.append((job, score))

            await asyncio.sleep(2)

        return all_results
