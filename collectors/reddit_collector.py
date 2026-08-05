"""
RedditCollector — mines Reddit for indie book mentions.

Pipeline
--------
1. Load all tracked indie books.
2. For each book, call RedditClient.search_book(title, author) across all
   configured subreddits.
3. Skip posts already in the DB (idempotent via post_id check).
4. Insert new matches into `reddit_mentions`.

Reddit data is available 24+ hours old via the API (new sort), which is
fine — we're measuring cumulative buzz, not real-time velocity.
"""
from __future__ import annotations

from datetime import date
from typing import Optional

from loguru import logger
from sqlalchemy import select

from collectors.base import BaseCollector, CollectionResult
from config import settings
from database import get_session
from models import Book
from models.social_signals import RedditMention
from scrapers.reddit.client import RedditClient, RedditPost


class RedditCollector(BaseCollector):
    """Collects Reddit post mentions for tracked indie books."""

    name = "reddit"

    def __init__(
        self,
        today: Optional[date] = None,
        max_books: int = 200,
        subreddits: Optional[list[str]] = None,
    ) -> None:
        self._today = today or date.today()
        self._max_books = max_books
        self._subreddits = subreddits  # None → use RedditClient defaults

    async def collect(self) -> CollectionResult:
        result = CollectionResult(collector=self.name)

        client = RedditClient(
            client_id=settings.reddit_client_id,
            client_secret=settings.reddit_client_secret,
            user_agent=settings.reddit_user_agent,
            subreddits=self._subreddits,
        )

        books = self._load_books()
        logger.info("Reddit collection: {} books to search", len(books))

        for book in books[: self._max_books]:
            try:
                written = self._collect_book(client, book)
                result.metrics_written += written
            except Exception as exc:
                logger.error("Reddit error for '{}': {}", book.title, exc)
                result.errors += 1

        return result

    def _collect_book(self, client: RedditClient, book: Book) -> int:
        """Search Reddit for a book and persist new mentions. Returns count written."""
        seen_post_ids = self._load_seen_post_ids(book.id)
        posts = client.search_book(book.title, book.author or "")

        written = 0
        for post in posts:
            pid = post.get("post_id", "")
            if not pid or pid in seen_post_ids:
                continue
            self._insert_mention(book.id, post)
            seen_post_ids.add(pid)
            written += 1
            logger.debug("  New Reddit mention: {} for '{}'", pid, book.title)

        return written

    # ── DB helpers ────────────────────────────────────────────────────────────

    def _load_books(self) -> list[Book]:
        with get_session() as session:
            return list(
                session.scalars(select(Book).where(Book.is_indie.is_(True))).all()
            )

    def _load_seen_post_ids(self, book_id: int) -> set[str]:
        with get_session() as session:
            rows = session.scalars(
                select(RedditMention.reddit_post_id).where(
                    RedditMention.book_id == book_id
                )
            ).all()
        return set(rows)

    def _insert_mention(self, book_id: int, post: RedditPost) -> None:
        with get_session() as session:
            row = RedditMention(
                book_id=book_id,
                reddit_post_id=post.get("post_id"),
                subreddit=post.get("subreddit"),
                title=post.get("title"),
                body=post.get("body"),
                author=post.get("author"),
                upvotes=post.get("upvotes"),
                downvotes=post.get("downvotes"),
                comment_count=post.get("comment_count"),
                is_comment=post.get("is_comment", False),
                posted_at=post.get("posted_at"),
            )
            session.add(row)
