"""
GoodreadsBrowser — Playwright browser for Goodreads.

Goodreads is significantly less aggressive than Amazon about bot detection,
but still requires realistic browser behaviour.  We reuse the same stealth
patterns as AmazonBrowser but with shorter delays.
"""
from __future__ import annotations

import asyncio
import random
from contextlib import asynccontextmanager
from typing import AsyncGenerator, Optional

from loguru import logger
from playwright.async_api import Browser, BrowserContext, Page, Playwright, async_playwright
from tenacity import AsyncRetrying, retry_if_exception_type, stop_after_attempt, wait_exponential

_USER_AGENTS = [
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
]

GOODREADS_REQUEST_DELAY = (1.5, 3.5)  # (min, max) seconds


class GoodreadsBrowser:
    """Async context manager for Goodreads scraping sessions."""

    def __init__(self, headless: bool = True) -> None:
        self._headless = headless
        self._playwright: Optional[Playwright] = None
        self._browser: Optional[Browser] = None
        self._context: Optional[BrowserContext] = None

    async def __aenter__(self) -> "GoodreadsBrowser":
        self._playwright = await async_playwright().start()
        self._browser = await self._playwright.chromium.launch(
            headless=self._headless,
            args=["--disable-blink-features=AutomationControlled", "--no-sandbox"],
        )
        self._context = await self._browser.new_context(
            user_agent=random.choice(_USER_AGENTS),
            viewport={"width": 1280, "height": 800},
            locale="en-US",
        )
        await self._context.add_init_script(
            "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"
        )
        return self

    async def __aexit__(self, *_: object) -> None:
        if self._context:
            await self._context.close()
        if self._browser:
            await self._browser.close()
        if self._playwright:
            await self._playwright.stop()

    async def fetch_page(self, url: str) -> str:
        assert self._context is not None
        delay = random.uniform(*GOODREADS_REQUEST_DELAY)
        await asyncio.sleep(delay)

        async for attempt in AsyncRetrying(
            stop=stop_after_attempt(3),
            wait=wait_exponential(multiplier=2, min=3, max=20),
            retry=retry_if_exception_type((TimeoutError, ConnectionError)),
            reraise=True,
        ):
            with attempt:
                page: Page = await self._context.new_page()
                try:
                    await page.goto(url, wait_until="domcontentloaded", timeout=30_000)
                    # Brief scroll to trigger lazy content
                    await page.evaluate("window.scrollTo(0, 400)")
                    await asyncio.sleep(0.8)
                    return await page.content()
                finally:
                    await page.close()
        raise RuntimeError("fetch_page exhausted retries")


@asynccontextmanager
async def goodreads_browser(headless: bool = True) -> AsyncGenerator[GoodreadsBrowser, None]:
    b = GoodreadsBrowser(headless=headless)
    async with b:
        yield b
