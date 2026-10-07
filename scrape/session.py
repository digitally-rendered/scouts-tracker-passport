"""Shared Playwright session for ScoutsTracker (persistent, manually logged-in profile)."""
from __future__ import annotations

from contextlib import contextmanager
import sys
from pathlib import Path

from playwright.sync_api import Page, sync_playwright

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from paths import PROFILE_DIR  # noqa: E402  (private: holds the login session)
BASE_URL = "https://scoutstracker.ca/cubs/"


def is_logged_in(page: Page) -> bool:
    """Logged in once the app sidebar shows the Reports link."""
    return page.locator("a", has_text="Reports").first.is_visible()


@contextmanager
def open_tracker(headless: bool = True):
    with sync_playwright() as p:
        ctx = p.chromium.launch_persistent_context(
            str(PROFILE_DIR), headless=headless, viewport={"width": 1400, "height": 1000}
        )
        page = ctx.pages[0] if ctx.pages else ctx.new_page()
        page.goto(BASE_URL, wait_until="domcontentloaded")
        try:
            yield page
        finally:
            ctx.close()
