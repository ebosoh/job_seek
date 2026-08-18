"""LinkedIn Browser Session and Persistent Profile Manager."""

import asyncio
import logging
import time
from pathlib import Path
from typing import Optional
from playwright.async_api import async_playwright, BrowserContext, Page, Playwright
from src.config import BrowserConfig
from src.browser.stealth import apply_stealth

logger = logging.getLogger(__name__)


class LinkedInSessionManager:
    """Manages persistent browser sessions and authentication state on local disk."""

    def __init__(self, config: BrowserConfig, root_dir: Path):
        self.config = config
        self.root_dir = root_dir
        self.user_data_path = (root_dir / config.user_data_dir).resolve()
        self.user_data_path.mkdir(parents=True, exist_ok=True)
        self.playwright: Optional[Playwright] = None
        self.context: Optional[BrowserContext] = None

    async def get_context(self, headless_override: Optional[bool] = None) -> BrowserContext:
        """Launches or returns persistent browser context with anti-detection flags."""
        if self.context:
            return self.context

        self.playwright = await async_playwright().start()

        is_headless = self.config.headless if headless_override is None else headless_override

        args = [
            "--disable-blink-features=AutomationControlled",
            "--disable-infobars",
            "--no-sandbox",
            "--disable-dev-shm-usage",
            "--disable-extensions",
            "--start-maximized"
        ]

        self.context = await self.playwright.chromium.launch_persistent_context(
            user_data_dir=str(self.user_data_path),
            headless=is_headless,
            slow_mo=self.config.slow_mo_ms,
            viewport=None, # Maximized window
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
            args=args,
            accept_downloads=True
        )

        return self.context

    async def new_page(self, headless_override: Optional[bool] = None) -> Page:
        """Creates a new page with stealth scripts applied."""
        context = await self.get_context(headless_override=headless_override)
        pages = context.pages
        page = pages[0] if pages else await context.new_page()
        await apply_stealth(page)
        return page

    async def check_login_status(self, page: Page) -> bool:
        """Verifies if the current session is logged into LinkedIn."""
        try:
            await page.goto("https://www.linkedin.com/feed/", wait_until="domcontentloaded", timeout=20000)
            await asyncio.sleep(2)

            # Check if feed or profile navigation bar exists
            nav_selector = "nav.global-nav, .feed-identity-module, a[href*='/in/'], button#global-nav-typeahead"
            element = await page.query_selector(nav_selector)
            if element:
                logger.info("LinkedIn session is authenticated.")
                return True

            # If redirected to login page or sign in button visible
            login_form = await page.query_selector("input#username, form.login__form, a[href*='linkedin.com/login']")
            if login_form:
                logger.warning("LinkedIn session is NOT authenticated.")
                return False

            return False
        except Exception as e:
            logger.warning(f"Error checking LinkedIn login status: {e}")
            return False

    async def interactive_login(self):
        """
        Launches headful browser for interactive user login.
        Waits until user completes login, 2FA, or CAPTCHA and reaches the LinkedIn Feed.
        """
        print("\n=======================================================")
        print("🔑 LINKEDIN INTERACTIVE LOGIN MODE")
        print("=======================================================")
        print("Launching browser window...")
        print("Please log into your LinkedIn account and solve any 2FA/CAPTCHA.")
        print("Your session will be saved to disk automatically.")
        print("=======================================================\n")

        page = await self.new_page(headless_override=False)
        await page.goto("https://www.linkedin.com/login", wait_until="domcontentloaded")

        max_wait_seconds = 300 # 5 minutes
        poll_interval = 2
        elapsed = 0

        while elapsed < max_wait_seconds:
            await asyncio.sleep(poll_interval)
            elapsed += poll_interval

            # Check if user reached feed or jobs page
            current_url = page.url
            if "linkedin.com/feed" in current_url or "linkedin.com/jobs" in current_url:
                print("\n✅ Login successful! Authenticated session saved.")
                await asyncio.sleep(3)
                await self.close()
                return True

            nav = await page.query_selector("nav.global-nav, .feed-identity-module")
            if nav:
                print("\n✅ Navigation detected! Authenticated session saved.")
                await asyncio.sleep(3)
                await self.close()
                return True

        print("❌ Login timed out. Please try again.")
        await self.close()
        return False

    async def pause_for_selector_debug(self, page: Page, reason: str = "Selector failed"):
        """
        Debugging helper: Pauses script execution when CSS selectors fail
        to allow manual inspection with developer tools.
        """
        logger.warning(f"[DEBUG PAUSE] {reason}. Pausing browser for manual inspection...")
        print(f"\n⚠️ [SELECTOR DEBUG PAUSE]: {reason}")
        print("Opening developer tools / inspect live page. Script paused for 20 seconds...")
        await asyncio.sleep(20)

    async def close(self):
        """Closes browser context and playwright."""
        if self.context:
            try:
                await self.context.close()
            except Exception:
                pass
            self.context = None

        if self.playwright:
            try:
                await self.playwright.stop()
            except Exception:
                pass
            self.playwright = None
