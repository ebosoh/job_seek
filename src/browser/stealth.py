"""Stealth and Anti-Bot bypass scripts for Playwright."""

from playwright.async_api import Page, BrowserContext

STEALTH_JS = """
// Overwrite the `languages` property to use a custom getter.
Object.defineProperty(navigator, 'languages', {
  get: () => ['en-US', 'en'],
});

// Overwrite the `plugins` property to use a custom getter.
Object.defineProperty(navigator, 'plugins', {
  get: () => [1, 2, 3, 4, 5],
});

// Pass webdriver test
Object.defineProperty(navigator, 'webdriver', {
  get: () => undefined,
});

// Chrome runtime mock
window.chrome = {
  runtime: {},
  app: {},
  loadTimes: function() {},
  csi: function() {}
};

// Notification permission mock
const originalQuery = window.navigator.permissions.query;
window.navigator.permissions.query = (parameters) => (
  parameters.name === 'notifications' ?
    Promise.resolve({ state: Notification.permission }) :
    originalQuery(parameters)
);
"""

async def apply_stealth(page: Page):
    """Applies stealth scripts and overrides to prevent bot detection."""
    await page.add_init_script(STEALTH_JS)
