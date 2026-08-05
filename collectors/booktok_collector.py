"""
BookTokCollector — mines TikTok for indie book mentions.

Pipeline
--------
1. Load all tracked indie books.
2. For each book, build ranked search queries (title+author, then fallbacks).
3. For each query, fetch and parse TikTok search results.
4. Filter videos: must mention the book title (case-insensitive) in the
   video description to reduce false positives.
5. Insert matching videos into `booktok_mentions` — append-only.

Why TikTok matters
------------------
BookTok (the #BookTok corner of TikTok) is the single most powerful
organic discovery channel for indie fiction right now.  A single viral
video can add 5–10k readers overnight.  The velocity of new mentions —
especially view counts — is our earliest leading indicator of breakout
momentum.
"""
from __future__ import annotations

import asyncio
from datetime import date
from typing import Optional

from loguru import logger
from sqlalchemy import select

from collectors.base import BaseCollector, CollectionResult
from database import get_session
from models import Book
from models.social_signals import BookTokMention
from scrapers.tiktok.parser import TikTokParser, TikTokVideoMention
from scrapers.tiktok.search_terms import build_search_terms


class BookTokCollector(BaseCollector):
    """Collects TikTok video mentions for tracked indie books."""

    name = "booktok"

    def __init__(
        self,
        today: Optional[date] = None,
        max_books: int = 100,
        max_queries_per_book: int = 2,
        headless: bool = True,
    ) -> None:
        self._today = today or date.today()
        self._max_books = max_books
        self._max_queries = max_queries_per_book
        self._headless = headless

    async def collect(self) -> CollectionResult:
        result = CollectionResult(collector=self.name)
        books = self._load_books()
        logger.info("BookTok collection: {} books to search", len(books))

        from scrapers.tiktok.browser import TikTokBrowser

        async with TikTokBrowser(headless=self._headless) as browser:
            for book in books[: self._max_books]:
                try:
                    written = await self._collect_book(browser, book)
                    result.metrics_written += written
                except Exception as exc:
                    logger.error("Error collecting TikTok for '{}': {}", book.title, exc)
                    result.errors += 1

        return result

    async def _collect_book(self, browser, book: Book) -> int:
        """Search TikTok for a book and persist new mentions. Returns count written."""
        queries = build_search_terms(book.title, book.author or "")
        seen_video_ids = self._load_seen_video_ids(book.id)

        written = 0
        for query in queries[: self._max_queries]:
            url = TikTokParser.build_search_url(query)
            try:
                html = await browser.fetch_page(url)
                mentions = TikTokParser.parse_search_results(html, query)
            except Exception as exc:
                logger.warning("TikTok search failed for '{}': {}", query, exc)
                continue

            for mention in mentions:
                vid_id = mention.get("video_id", "")
                if not vid_id or vid_id in seen_video_ids:
                    continue

                # Must mention book title in description to filter noise
                desc = (mention.get("description") or "").lower()
                if book.title.lower() not in desc:
                    continue

                self._insert_mention(book.id, mention)
                seen_video_ids.add(vid_id)
                written += 1
                logger.debug("  New BookTok mention: {} for '{}'", vid_id, book.title)

        return written

    # ── DB helpers ────────────────────────────────────────────────────────────

    def _load_books(self) -> list[Book]:
        with get_session() as session:
            return list(
                session.scalars(select(Book).where(Book.is_indie.is_(True))).all()
            )

    def _load_seen_video_ids(self, book_id: int) -> set[str]:
        with get_session() as session:
            rows = session.scalars(
                select(BookTokMention.tiktok_video_id).where(
                    BookTokMention.book_id == book_id
                )
            ).all()
        return set(rows)

    def _insert_mention(self, book_id: int, mention: TikTokVideoMention) -> None:
        with get_session() as session:
            row = BookTokMention(
                book_id=book_id,
                tiktok_video_id=mention.get("video_id", ""),
                creator_username=mention.get("author_handle"),
                caption=mention.get("description"),
                view_count=mention.get("view_count"),
                like_count=mention.get("like_count"),
                comment_count=mention.get("comment_count"),
                share_count=mention.get("share_count"),
                published_at=mention.get("created_at"),
                video_url=mention.get("url"),
            )
            session.add(row)
