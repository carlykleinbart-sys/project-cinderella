"""
GoodreadsCollector — enriches tracked books with Goodreads data.

Pipeline
--------
1. Load all tracked indie books.
2. For books without a goodreads_id, search Goodreads to find the matching page.
   - Match title + author to avoid wrong-edition confusion.
3. For all books with a goodreads_id, fetch the current Goodreads stats.
4. Update today's DailyMetrics with:
   - goodreads_rating
   - goodreads_reviews  (ratings count — the larger, more stable number)
   - goodreads_want_to_read

Goodreads does not have a public API, so we scrape respectfully with delays.
The Want-to-Read count is the most predictive leading indicator: it often
spikes weeks before Amazon rank improvement becomes obvious.
"""
from __future__ import annotations

import asyncio
from datetime import date
from difflib import SequenceMatcher
from typing import Optional

from loguru import logger
from sqlalchemy import select, update

from collectors.base import BaseCollector, CollectionResult
from config import settings
from database import get_session
from models import Book, DailyMetrics
from scrapers.goodreads.parser import GoodreadsBookData, GoodreadsParser


class GoodreadsCollector(BaseCollector):
    """Collects Goodreads ratings, review counts, and Want-to-Read counts."""

    name = "goodreads"

    def __init__(
        self,
        today: Optional[date] = None,
        max_books: int = 200,
        headless: bool = True,
    ) -> None:
        self._today = today or date.today()
        self._max_books = max_books
        self._headless = headless

    async def collect(self) -> CollectionResult:
        result = CollectionResult(collector=self.name)

        from scrapers.goodreads.browser import GoodreadsBrowser

        books = self._load_books()
        logger.info("Goodreads collection: {} books to process", len(books))

        async with GoodreadsBrowser(headless=self._headless) as browser:
            for book in books[: self._max_books]:
                try:
                    await self._process_book(browser, book, result)
                except Exception as exc:
                    logger.error("Error processing {} on Goodreads: {}", book.asin, exc)
                    result.errors += 1

        return result

    # ── Internal ──────────────────────────────────────────────────────────────

    async def _process_book(self, browser, book: Book, result: CollectionResult) -> None:
        """Find and scrape a single book's Goodreads data."""

        # Step 1: find goodreads_id if not known
        if not book.goodreads_id:
            gr_id, gr_url = await self._find_goodreads_id(browser, book)
            if not gr_id:
                logger.debug("Could not find Goodreads match for: {}", book.title)
                return
            self._save_goodreads_id(book.id, gr_id, gr_url)
            book.goodreads_id = gr_id
            book.goodreads_url = gr_url
            logger.info("  Linked '{}' → Goodreads ID {}", book.title, gr_id)
            result.updated_books += 1

        # Step 2: scrape the book page
        gr_url = book.goodreads_url or GoodreadsParser.build_book_url(book.goodreads_id)
        html = await browser.fetch_page(gr_url)
        data = GoodreadsParser.parse_book_page(html, gr_url)

        if not data:
            logger.warning("Could not parse Goodreads page for {}", book.title)
            result.errors += 1
            return

        # Step 3: update today's DailyMetrics
        updated = self._update_metrics(book.id, data)
        if updated:
            result.metrics_written += 1
            logger.debug(
                "  Updated GR metrics: {} rating={} ratings={} wtr={}",
                book.title,
                data["average_rating"],
                data["ratings_count"],
                data["want_to_read_count"],
            )

    async def _find_goodreads_id(
        self, browser, book: Book
    ) -> tuple[Optional[str], Optional[str]]:
        """Search Goodreads and return (goodreads_id, goodreads_url) for the best match."""
        search_url = GoodreadsParser.build_search_url(book.title, book.author)
        html = await browser.fetch_page(search_url)
        candidates = GoodreadsParser.parse_search_results(html)

        if not candidates:
            return None, None

        # Score candidates by title+author similarity
        best = max(
            candidates,
            key=lambda c: self._similarity_score(
                c["title"], c["author"], book.title, book.author
            ),
        )

        # Only accept if similarity is good enough
        score = self._similarity_score(
            best["title"], best["author"], book.title, book.author
        )
        if score < 0.6:
            logger.debug(
                "Best Goodreads match for '{}' had similarity {:.2f} — skipping",
                book.title, score
            )
            return None, None

        return best["goodreads_id"], best["goodreads_url"]

    def _update_metrics(self, book_id: int, data: GoodreadsBookData) -> bool:
        """Update goodreads_* fields on today's DailyMetrics row."""
        with get_session() as session:
            metrics = session.scalars(
                select(DailyMetrics).where(
                    DailyMetrics.book_id == book_id,
                    DailyMetrics.date == self._today,
                )
            ).first()

            if not metrics:
                # Today's Amazon metrics haven't been collected yet — create stub
                metrics = DailyMetrics(book_id=book_id, date=self._today)
                session.add(metrics)
                session.flush()

            metrics.goodreads_rating = data["average_rating"]
            metrics.goodreads_reviews = data["ratings_count"]
            metrics.goodreads_want_to_read = data["want_to_read_count"]
            return True

    def _save_goodreads_id(self, book_id: int, gr_id: str, gr_url: Optional[str]) -> None:
        with get_session() as session:
            session.execute(
                update(Book)
                .where(Book.id == book_id)
                .values(goodreads_id=gr_id, goodreads_url=gr_url)
            )

    def _load_books(self) -> list[Book]:
        with get_session() as session:
            return list(
                session.scalars(select(Book).where(Book.is_indie.is_(True))).all()
            )

    @staticmethod
    def _similarity_score(
        cand_title: str, cand_author: str, target_title: str, target_author: str
    ) -> float:
        """Combined title + author similarity (0–1)."""
        def _sim(a: str, b: str) -> float:
            return SequenceMatcher(None, a.lower(), b.lower()).ratio()

        title_sim  = _sim(cand_title, target_title)
        author_sim = _sim(cand_author, target_author) if cand_author and target_author else 0.5
        # Weight title more heavily
        return title_sim * 0.7 + author_sim * 0.3
