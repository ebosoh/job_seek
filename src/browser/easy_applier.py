"""LinkedIn Easy Apply Multi-Step Form Automation Engine."""

import asyncio
import logging
import os
import re
from pathlib import Path
from typing import Optional, Tuple
from playwright.async_api import Page
from src.config import AppConfig
from src.core.cv_parser import CandidateProfile
from src.core.llm_client import LLMClient
from src.core.matcher import IILSScoreBreakdown, JobOpportunity
from src.data.tracker import ApplicationTracker

logger = logging.getLogger(__name__)


class LinkedInEasyApplier:
    """Automates multi-step LinkedIn Easy Apply modal form-filling and submission."""

    def __init__(
        self,
        config: AppConfig,
        llm_client: LLMClient,
        tracker: ApplicationTracker,
        candidate_profile: CandidateProfile,
        resume_file: Optional[Path] = None
    ):
        self.config = config
        self.llm = llm_client
        self.tracker = tracker
        self.candidate = candidate_profile
        self.resume_file = resume_file

    async def apply(self, page: Page, job: JobOpportunity, score: IILSScoreBreakdown) -> bool:
        """
        Executes the full Easy Apply flow for a qualified job.
        Returns True if successfully submitted (or successfully prepared in dry-run mode).
        """
        logger.info(f"Starting Easy Apply for: {job.title} at {job.company} (IILS: {score.total_iils})")

        try:
            # Navigate to job URL if not already there
            if page.url != job.job_url:
                await page.goto(job.job_url, wait_until="domcontentloaded", timeout=25000)
                await asyncio.sleep(2)

            # Locate Easy Apply button
            apply_btn = await page.query_selector("button.jobs-apply-button")
            if not apply_btn:
                logger.warning(f"Easy Apply button not found on {job.job_url}")
                return False

            btn_text = (await apply_btn.inner_text()).lower()
            if "easy apply" not in btn_text:
                logger.info(f"Not an Easy Apply role: {job.title}")
                return False

            # Click Easy Apply to open modal
            await apply_btn.click()
            await asyncio.sleep(2)

            # Wait for modal dialog
            modal = await page.query_selector(".jobs-easy-apply-modal, [role='dialog']")
            if not modal:
                logger.warning("Easy apply modal did not open.")
                return False

            # Form navigation loop (up to 12 steps)
            max_steps = 12
            for step in range(max_steps):
                await asyncio.sleep(1)

                # Fill current visible form inputs
                fill_success, low_conf_reason = await self._fill_current_step(page, modal, job)
                if not fill_success:
                    logger.warning(f"Safety gate triggered: {low_conf_reason}")
                    self.tracker.record_application(
                        job, score, status="MANUAL_REVIEW_REQUIRED",
                        notes=f"Safety confidence check flagged: {low_conf_reason}"
                    )
                    await self._dismiss_modal(page)
                    return False

                # Check if we are on the final Submit step
                submit_btn = await page.query_selector("button[aria-label*='Submit application'], button:has-text('Submit application')")
                if submit_btn and await submit_btn.is_visible():
                    if self.config.dry_run:
                        # Save screenshot in dry run mode
                        screenshot_path = self.config.screenshots_dir / f"dry_run_{job.job_id}.png"
                        await page.screenshot(path=str(screenshot_path))
                        logger.info(f"[DRY RUN] Easy Apply form filled successfully. Screenshot saved to {screenshot_path}")
                        self.tracker.record_application(
                            job, score, status="DRY_RUN_PREPARED",
                            notes=f"Form completed in dry-run mode. Screenshot: {screenshot_path.name}"
                        )
                        await self._dismiss_modal(page)
                        return True
                    else:
                        # Click final submit
                        await submit_btn.click()
                        await asyncio.sleep(3)
                        logger.info(f"Successfully submitted Easy Apply for {job.title} at {job.company}!")
                        self.tracker.record_application(job, score, status="APPLIED", notes="Successfully submitted via Easy Apply")
                        await self._dismiss_modal(page)
                        return True

                # Look for 'Next' or 'Review' button
                next_btn = await page.query_selector("button[aria-label*='Continue to next step'], button[aria-label*='Review your application'], button:has-text('Next'), button:has-text('Review')")
                if next_btn and await next_btn.is_visible():
                    await next_btn.click()
                    await asyncio.sleep(1.5)
                    continue

                # If no next or submit button, break
                break

            # If loop finished without submitting
            await self._dismiss_modal(page)
            return False

        except Exception as e:
            logger.error(f"Error during Easy Apply for {job.job_id}: {e}", exc_info=True)
            try:
                await self._dismiss_modal(page)
            except Exception:
                pass
            return False

    async def _fill_current_step(self, page: Page, modal, job: JobOpportunity) -> Tuple[bool, Optional[str]]:
        """Handles all inputs on the current visible modal screen."""

        # 1. Text and Number Inputs
        text_inputs = await page.query_selector_all(".jobs-easy-apply-modal input[type='text'], .jobs-easy-apply-modal input[type='number'], .jobs-easy-apply-modal input:not([type])")
        for inp in text_inputs:
            if not await inp.is_visible():
                continue

            current_val = await inp.input_value()
            label_text = await self._get_input_label(page, inp)
            label_lower = label_text.lower()

            # Contact Fields
            if any(k in label_lower for k in ["phone", "mobile", "contact"]):
                if not current_val:
                    await inp.fill(self.candidate.phone)
                continue

            if any(k in label_lower for k in ["email", "e-mail"]):
                if not current_val:
                    await inp.fill(self.candidate.email)
                continue

            if any(k in label_lower for k in ["first name", "given name"]):
                if not current_val:
                    await inp.fill(self.candidate.full_name.split()[0])
                continue

            if any(k in label_lower for k in ["last name", "family name", "surname"]):
                if not current_val:
                    parts = self.candidate.full_name.split()
                    await inp.fill(parts[-1] if len(parts) > 1 else "")
                continue

            if any(k in label_lower for k in ["city", "location", "address"]):
                if not current_val:
                    await inp.fill(self.candidate.location)
                continue

            # Experience numeric questions
            if any(k in label_lower for k in ["how many years", "years of experience", "years"]):
                if not current_val:
                    await inp.fill(str(self.candidate.total_years_experience))
                continue

            # Salary numeric questions
            if any(k in label_lower for k in ["salary", "compensation", "desired", "rate", "expected"]):
                if not current_val:
                    if "month" in label_lower:
                        await inp.fill(str(int(self.config.target.default_salary_monthly)))
                    else:
                        await inp.fill(str(int(self.config.target.default_salary_yearly)))
                continue

            # Custom single-line open question
            if not current_val and label_text:
                answer, conf = self.llm.generate_answer(
                    question=label_text,
                    job_title=job.title,
                    company_name=job.company,
                    job_description=job.description,
                    candidate=self.candidate
                )
                if conf < self.config.scoring.safety_confidence_threshold:
                    return False, f"Low confidence ({conf}%) for question: '{label_text}'"
                await inp.fill(answer[:150]) # Short text input

        # 2. Textarea Inputs (Open-ended questions)
        textareas = await page.query_selector_all(".jobs-easy-apply-modal textarea")
        for ta in textareas:
            if not await ta.is_visible():
                continue
            current_val = await ta.input_value()
            if not current_val:
                label_text = await self._get_input_label(page, ta)
                answer, conf = self.llm.generate_answer(
                    question=label_text or "Why are you a good fit for this role?",
                    job_title=job.title,
                    company_name=job.company,
                    job_description=job.description,
                    candidate=self.candidate
                )
                if conf < self.config.scoring.safety_confidence_threshold:
                    return False, f"Low confidence ({conf}%) for textarea question: '{label_text}'"
                await ta.fill(answer)

        # 3. Radio Buttons & Checkboxes
        radios = await page.query_selector_all(".jobs-easy-apply-modal fieldset")
        for fieldset in radios:
            if not await fieldset.is_visible():
                continue
            legend = await fieldset.query_selector("legend")
            legend_text = (await legend.inner_text()).lower() if legend else ""

            # Check if any option is already selected
            checked = await fieldset.query_selector("input:checked")
            if checked:
                continue

            # Sponsorship questions: "Will you require sponsorship?" -> Select No
            if any(k in legend_text for k in ["sponsorship", "visa sponsorship", "require sponsorship"]):
                no_opt = await fieldset.query_selector("label:has-text('No'), input[value='No']")
                if no_opt:
                    await no_opt.click()
                continue

            # Authorization & Experience questions: "Are you authorized?" / "Do you have experience?" -> Select Yes
            if any(k in legend_text for k in ["authorized", "eligible", "remote", "experience", "comfortable", "agree", "background"]):
                yes_opt = await fieldset.query_selector("label:has-text('Yes'), input[value='Yes']")
                if yes_opt:
                    await yes_opt.click()
                continue

            # Default safe selection: Yes
            default_opt = await fieldset.query_selector("label:has-text('Yes'), input[value='Yes'], label")
            if default_opt:
                await default_opt.click()

        # 4. Dropdowns / Selects
        selects = await page.query_selector_all(".jobs-easy-apply-modal select")
        for sel in selects:
            if not await sel.is_visible():
                continue
            label_text = (await self._get_input_label(page, sel)).lower()
            val = await sel.input_value()
            if not val:
                options = await sel.query_selector_all("option")
                # Look for 'Yes' or positive option
                for opt in options:
                    opt_text = (await opt.inner_text()).strip().lower()
                    if opt_text in ["yes", "authorized", "expert", "senior", "5+ years", "5"]:
                        opt_val = await opt.get_attribute("value")
                        if opt_val:
                            await sel.select_option(opt_val)
                            break

        # 5. Resume Attachment Upload
        file_inputs = await page.query_selector_all(".jobs-easy-apply-modal input[type='file']")
        for finp in file_inputs:
            if self.resume_file and self.resume_file.is_file():
                try:
                    await finp.set_input_files(str(self.resume_file.resolve()))
                    logger.info(f"Attached resume file: {self.resume_file.name}")
                    await asyncio.sleep(1)
                except Exception as e:
                    logger.warning(f"Could not upload resume file: {e}")

        return True, None

    async def _get_input_label(self, page: Page, element) -> str:
        """Retrieves associated label text for an input or textarea element."""
        try:
            # Check aria-label
            aria = await element.get_attribute("aria-label")
            if aria:
                return aria.strip()

            elem_id = await element.get_attribute("id")
            if elem_id:
                label_elem = await page.query_selector(f"label[for='{elem_id}']")
                if label_elem:
                    return (await label_elem.inner_text()).strip()

            # Check parent container label
            parent_label = await element.evaluate("""
                el => {
                    let p = el.closest('div.fb-dash-form-element, div.jobs-easy-apply-form-section__grouping, div');
                    let lbl = p ? p.querySelector('label, span.fb-dash-form-element__label') : null;
                    return lbl ? lbl.innerText : '';
                }
            """)
            if parent_label:
                return parent_label.strip()
        except Exception:
            pass
        return ""

    async def _dismiss_modal(self, page: Page):
        """Safely dismisses and closes the Easy Apply modal dialog."""
        try:
            dismiss_btn = await page.query_selector("button[aria-label='Dismiss'], button.artdeco-modal__dismiss")
            if dismiss_btn:
                await dismiss_btn.click()
                await asyncio.sleep(1)

                # Check for discard confirmation dialog
                discard_btn = await page.query_selector("button[data-control-name='discard_application_confirm_btn'], button:has-text('Discard')")
                if discard_btn:
                    await discard_btn.click()
                    await asyncio.sleep(1)
        except Exception:
            pass
