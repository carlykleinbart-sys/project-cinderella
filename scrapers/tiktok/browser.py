"""
TikTok browser — lightweight stealth fetcher for public search pages.

TikTok is significantly more aggressive about bot detection than Amazon or
Goodreads.  We mitigate with:
  - Realistic desktop browser fingerprint (Chrome on macOS)
  - Longer, jittered delays (3–8 seconds between requests)
  - Cookie and localStorage priming to simulate a returning visitor
  - Abort of media/image/font requests (speeds up load, reduces fingerprint)
  - Single browser instance reused across all queries to build session state
"""
from __future__ import annotations

import asyncio
import random
from contextlib import asynccontextmanager
from typing import Optional

from loguru import logger
from tenacity import retry, stop_after_attempt, wait_exponential


TIKTOK_USER_AGENTS = [
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
]

# Request types to block — reduce load time and lower fingerprint surface
BLOCKED_RESOURCE_TYPES = {"image", "media", "font", "stylesheet"}


class TikTokBrowser:
    """Async context manager for TikTok public page scraping."""

    def __init__(
        self,
        headless: bool = True,
        request_delay_min: float = 3.0,
        request_delay_max: float = 8.0,
    ) -> None:
        self._headless = headless
        self._delay_min = request_delay_min
        self._delay_max = request_delay_max
        self._playwright = None
        self._browser = None
        self._context = None

    async def __aenter__(self) -> "TikTokBrowser":
        from playwright.async_api import async_playwright

        self._playwright = await async_playwright().start()
        self._browser = await self._playwright.chromium.launch(headless=self._headless)

        user_agent = random.choice(TIKTOK_USER_AGENTS)
        self._context = await self._browser.new_context(
            user_agent=user_agent,
            viewport={"width": 1440, "height": 900},
            locale="en-US",
            timezone_id="America/New_York",
            extra_http_headers={
                "Accept-Language": "en-US,en;q=0.9",
                "sec-ch-ua": '"Chromium";v="124", "Google Chrome";v="124"',
                "sec-ch-ua-mobile": "?0",
                "sec-ch-ua-platform": '"macOS"',
            },
        )

        # Mask webdriver
        await self._context.add_init_script(
            "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"
        )

        # Block heavy resource types
        await self._context.route(
            "**/*",
            lambda route: (
                route.abort()
                if route.request.resource_type in BLOCKED_RESOURCE_TYPES
                else route.continue_()
            ),
        )

        # Prime with a homepage visit to establish cookies
        page = await self._context.new_page()
        try:
            await page.goto("https://www.tiktok.com/", timeout=20_000, wait_until="domcontentloaded")
            await asyncio.sleep(random.uniform(1.5, 3.0))
        except Exception:
            pass  # OK if homepage fails; cookies may still be set
        finally:
            await page.close()

        return self

    async def __aexit__(self, *_) -> None:
        if self._context:
            await self._context.close()
        if self._browser:
            await self._browser.close()
        if self._playwright:
            await self._playwright.stop()

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1.5, min=4, max=20))
    async def fetch_page(self, url: str) -> str:
        """Fetch a TikTok page and return its HTML."""
        await asyncio.sleep(random.uniform(self._delay_min, self._delay_max))

        page = await self._context.new_page()
        try:
            await page.goto(url, timeout=30_000, wait_until="domcontentloaded")

            # Wait for search results to hydrate
            await asyncio.sleep(random.uniform(2.0, 4.0))

            if self._is_challenge_page(await page.content()):
                logger.warning("TikTok challenge/captcha detected at {}", url)
                raise RuntimeError("TikTok bot challenge")

            return await page.content()
        finally:
            await page.close()

    @staticmethod
    def _is_challenge_page(html: str) -> bool:
        signals = [
            "verify.tiktok.com",
            "captcha",
            "verifyCaptcha",
            "security-check",
        ]
        lower = html.lower()
        return any(s in lower for s in signals)


@asynccontextmanager
async def tiktok_browser(**kwargs):
    """Async context manager shorthand."""
    async with TikTokBrowser(**kwargs) as browser:
        yield browser
