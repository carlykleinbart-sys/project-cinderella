"""
AmazonBrowser — Playwright-based browser manager for Amazon scraping.

Design goals
------------
* Mimic a real human browser session to avoid bot detection.
* Expose a simple async context-manager interface.
* Handle rate limiting via configurable random delays.
* Retry transient failures with exponential back-off.
* Surface clear errors when Amazon serves a CAPTCHA or bot wall.

Usage
-----
    async with AmazonBrowser() as browser:
        html = await browser.fetch_page("https://www.amazon.com/dp/B08XYZ")
"""
from __future__ import annotations

import asyncio
import random
import re
from contextlib import asynccontextmanager
from typing import AsyncGenerator, Optional

from loguru import logger
from playwright.async_api import (
    Browser,
    BrowserContext,
    Page,
    Playwright,
    async_playwright,
)
from tenacity import (
    AsyncRetrying,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from config import settings

# ---------------------------------------------------------------------------
# User-agent rotation pool — all real Chrome UA strings
# ---------------------------------------------------------------------------
_USER_AGENTS: list[str] = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
]

# ---------------------------------------------------------------------------
# Viewport pool — standard desktop resolutions
# ---------------------------------------------------------------------------
_VIEWPORTS: list[dict[str, int]] = [
    {"width": 1920, "height": 1080},
    {"width": 1440, "height": 900},
    {"width": 1366, "height": 768},
    {"width": 1280, "height": 800},
]


class BotWallError(Exception):
    """Raised when Amazon returns a CAPTCHA or bot-detection page."""


class AmazonBrowser:
    """
    Async context manager that owns a Playwright browser session.

    All page fetches go through :meth:`fetch_page`, which applies
    random delays, stealth headers, and retry logic automatically.
    """

    def __init__(self) -> None:
        self._playwright: Optional[Playwright] = None
        self._browser: Optional[Browser] = None
        self._context: Optional[BrowserContext] = None

    # ── Lifecycle ─────────────────────────────────────────────────────────────

    async def __aenter__(self) -> "AmazonBrowser":
        await self._start()
        return self

    async def __aexit__(self, *_: object) -> None:
        await self._stop()

    async def _start(self) -> None:
        """Launch Playwright and create a stealth browser context."""
        self._playwright = await async_playwright().start()

        viewport = random.choice(_VIEWPORTS)
        user_agent = random.choice(_USER_AGENTS)

        launch_kwargs: dict = {
            "headless": settings.amazon_headless,
            "args": [
                "--disable-blink-features=AutomationControlled",
                "--disable-infobars",
                "--no-sandbox",
                f"--window-size={viewport['width']},{viewport['height']}",
            ],
        }
        if settings.amazon_user_data_dir:
            launch_kwargs["user_data_dir"] = settings.amazon_user_data_dir

        self._browser = await self._playwright.chromium.launch(**launch_kwargs)

        self._context = await self._browser.new_context(
            user_agent=user_agent,
            viewport=viewport,
            locale="en-US",
            timezone_id="America/New_York",
            extra_http_headers={
                "Accept-Language": "en-US,en;q=0.9",
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
                "Sec-Fetch-Dest": "document",
                "Sec-Fetch-Mode": "navigate",
                "Sec-Fetch-Site": "none",
                "Sec-Fetch-User": "?1",
                "Upgrade-Insecure-Requests": "1",
            },
        )

        # Mask webdriver flag
        await self._context.add_init_script(
            "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"
        )

        logger.debug("Playwright browser started (headless={})", settings.amazon_headless)

    async def _stop(self) -> None:
        """Cleanly shut down the browser."""
        if self._context:
            await self._context.close()
        if self._browser:
            await self._browser.close()
        if self._playwright:
            await self._playwright.stop()
        logger.debug("Playwright browser stopped")

    # ── Public API ────────────────────────────────────────────────────────────

    async def fetch_page(self, url: str, wait_for: str = "domcontentloaded") -> str:
        """
        Navigate to `url` and return the full page HTML.

        Applies a random delay before each request and retries up to 3 times
        on transient network errors.  Raises :class:`BotWallError` if Amazon
        responds with a CAPTCHA or robot-check page.

        Parameters
        ----------
        url:
            Fully-qualified URL to fetch.
        wait_for:
            Playwright ``wait_until`` event.  ``"domcontentloaded"`` is
            sufficient for server-rendered pages; use ``"networkidle"`` for
            heavily dynamic content.

        Returns
        -------
        str
            Raw HTML of the page.
        """
        assert self._context is not None, "Browser not started — use as async context manager"

        await self._random_delay()

        async for attempt in AsyncRetrying(
            stop=stop_after_attempt(3),
            wait=wait_exponential(multiplier=2, min=4, max=30),
            retry=retry_if_exception_type((TimeoutError, ConnectionError)),
            reraise=True,
        ):
            with attempt:
                page: Page = await self._context.new_page()
                try:
                    logger.debug("Fetching: {}", url)
                    await page.goto(url, wait_until=wait_for, timeout=30_000)
                    html = await page.content()

                    if self._is_bot_wall(html):
                        raise BotWallError(f"Amazon bot wall detected at {url}")

                    return html
                finally:
                    await page.close()

        # Should never reach here (tenacity re-raises), but satisfies mypy
        raise RuntimeError("fetch_page exhausted all retries")

    async def fetch_page_with_scroll(self, url: str) -> str:
        """
        Fetch a page and simulate a human scrolling through it.

        Useful for bestseller list pages that lazy-load content.
        Uses ``networkidle`` so JavaScript XHR calls finish before we
        capture HTML, then scrolls to trigger any lazy-loaded images.
        """
        assert self._context is not None

        await self._random_delay()

        page: Page = await self._context.new_page()
        try:
            # Use "load" (all resources) rather than "networkidle" —
            # Amazon has persistent background XHR that prevents networkidle
            # from ever settling within the timeout window.
            await page.goto(url, wait_until="load", timeout=60_000)

            # Wait until the page has rendered at least 10 rank badges — this
            # rules out CSS-only occurrences and confirms the book grid loaded.
            # Some categories need a scroll trigger first, so we interleave
            # scroll attempts with the wait.
            grid_loaded = False
            for attempt in range(4):
                try:
                    await page.wait_for_function(
                        "document.querySelectorAll('span.zg-bdg-text').length >= 10",
                        timeout=8_000,
                    )
                    grid_loaded = True
                    break
                except Exception:
                    # Trigger a scroll to wake lazy-load, then retry
                    scroll_pct = (attempt + 1) * 0.25
                    await page.evaluate(
                        f"window.scrollTo(0, document.body.scrollHeight * {scroll_pct})"
                    )
                    await asyncio.sleep(random.uniform(1.0, 2.0))

            if not grid_loaded:
                logger.warning("Book grid did not render for {}; capturing anyway", url)

            # Small buffer for any trailing XHR
            await asyncio.sleep(random.uniform(1.0, 2.0))

            # Scroll in three steps to trigger lazy loads
            for scroll_pct in (0.33, 0.66, 1.0):
                await page.evaluate(
                    f"window.scrollTo(0, document.body.scrollHeight * {scroll_pct})"
                )
                await asyncio.sleep(random.uniform(0.8, 1.8))

            # Scroll back to top (some pages only render rank badges when visible)
            await page.evaluate("window.scrollTo(0, 0)")
            await asyncio.sleep(1.0)

            html = await page.content()
            if self._is_bot_wall(html):
                raise BotWallError(f"Amazon bot wall detected at {url}")

            return html
        finally:
            await page.close()

    # ── Helpers ───────────────────────────────────────────────────────────────

    async def _random_delay(self) -> None:
        """Wait a random number of seconds between min and max delay settings."""
        delay = random.uniform(
            settings.amazon_request_delay_min,
            settings.amazon_request_delay_max,
        )
        logger.debug("Waiting {:.1f}s before next request", delay)
        await asyncio.sleep(delay)

    @staticmethod
    def _is_bot_wall(html: str) -> bool:
        """Return True if the page looks like an Amazon robot check."""
        bot_signals = [
            "Type the characters you see in this image",
            "Enter the characters you see below",
            "robot check",
            "automated access",
            "CAPTCHA",
            "api-services-support@amazon.com",
        ]
        lower = html.lower()
        return any(signal.lower() in lower for signal in bot_signals)


# ---------------------------------------------------------------------------
# Convenience async context manager (thin wrapper for use in scripts)
# ---------------------------------------------------------------------------
@asynccontextmanager
async def amazon_browser() -> AsyncGenerator[AmazonBrowser, None]:
    """
    Async context manager shorthand::

        async with amazon_browser() as browser:
            html = await browser.fetch_page(url)
    """
    b = AmazonBrowser()
    async with b:
        yield b
