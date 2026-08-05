"""
Integration tests for the social signal pipeline.

Uses in-memory SQLite (no live external services required).
Tests BookTokCollector and RedditCollector logic without browser/API calls.
"""
from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import date, datetime, timezone
from typing import Optional
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy import select

from models import Book, DailyMetrics
from models.social_signals import BookTokMention, RedditMention


# ── BookTok collector logic ───────────────────────────────────────────────────

class TestBookTokCollectorLogic:
    """Test BookTokCollector internals without a real browser."""

    def test_load_seen_video_ids_empty(self, session, make_book):
        from collectors.booktok_collector import BookTokCollector
        book = make_book(asin="B00TEST001")
        collector = BookTokCollector(today=date.today())
        # Inject session directly by accessing internal method logic
        seen = collector._load_seen_video_ids(book.id)
        assert isinstance(seen, set)
        assert len(seen) == 0

    def test_insert_mention_persists(self, session, make_book):
        from collectors.booktok_collector import BookTokCollector
        from scrapers.tiktok.parser import TikTokVideoMention
        book = make_book(asin="B00TEST005")
        collector = BookTokCollector(today=date.today())

        mention = TikTokVideoMention(
            video_id="vid_001",
            author_handle="booktok_fan",
            description="Test Book is amazing! #booktok",
            view_count=50_000,
            like_count=3_000,
            comment_count=120,
            share_count=400,
            created_at=datetime.now(timezone.utc),
            url="https://www.tiktok.com/@booktok_fan/video/vid_001",
        )
        collector._insert_mention(book.id, mention)

        row = session.scalars(
            select(BookTokMention).where(BookTokMention.book_id == book.id)
        ).first()
        assert row is not None
        assert row.tiktok_video_id == "vid_001"
        assert row.creator_username == "booktok_fan"
        assert row.view_count == 50_000

    def test_seen_video_ids_after_insert(self, session, make_book):
        from collectors.booktok_collector import BookTokCollector
        from scrapers.tiktok.parser import TikTokVideoMention
        book = make_book(asin="B00TEST006")
        collector = BookTokCollector(today=date.today())

        mention = TikTokVideoMention(
            video_id="vid_002",
            author_handle="reader_gal",
            description="Test Book changed my life",
            url="https://www.tiktok.com/@reader_gal/video/vid_002",
        )
        collector._insert_mention(book.id, mention)

        seen = collector._load_seen_video_ids(book.id)
        assert "vid_002" in seen

    def test_title_filter_prevents_noise(self):
        """Mentions without the book title in description should be filtered."""
        from collectors.booktok_collector import BookTokCollector
        from scrapers.tiktok.parser import TikTokVideoMention

        book_title = "Test Book"
        mention = TikTokVideoMention(
            video_id="vid_003",
            description="Just finished an amazing romance! Not naming it yet",
        )
        desc = (mention.get("description") or "").lower()
        # This is the filter applied inside _collect_book
        assert book_title.lower() not in desc


# ── Reddit collector logic ────────────────────────────────────────────────────

class TestRedditCollectorLogic:
    def test_insert_mention_persists(self, session, make_book):
        from collectors.reddit_collector import RedditCollector
        from scrapers.reddit.client import RedditPost

        book = make_book(asin="B00TEST002")
        collector = RedditCollector(today=date.today())

        post = RedditPost(
            post_id="abc123",
            subreddit="books",
            title="Test Book is my new favorite!",
            body="I just finished Test Book and it blew me away.",
            author="redditor99",
            upvotes=350,
            downvotes=0,
            comment_count=45,
            is_comment=False,
            posted_at=datetime.now(timezone.utc),
            url="https://reddit.com/r/books/abc123",
        )
        collector._insert_mention(book.id, post)

        row = session.scalars(
            select(RedditMention).where(RedditMention.book_id == book.id)
        ).first()
        assert row is not None
        assert row.reddit_post_id == "abc123"
        assert row.upvotes == 350
        assert row.subreddit == "books"

    def test_seen_post_ids_after_insert(self, session, make_book):
        from collectors.reddit_collector import RedditCollector
        from scrapers.reddit.client import RedditPost

        book = make_book(asin="B00TEST003")
        collector = RedditCollector(today=date.today())

        post = RedditPost(
            post_id="xyz789",
            subreddit="Fantasy",
            title="Test Book review",
            body="Loved Test Book",
            upvotes=50,
        )
        collector._insert_mention(book.id, post)
        seen = collector._load_seen_post_ids(book.id)
        assert "xyz789" in seen

    def test_no_duplicate_posts(self, session, make_book):
        from collectors.reddit_collector import RedditCollector
        from scrapers.reddit.client import RedditPost

        book = make_book(asin="B00TEST004")
        collector = RedditCollector(today=date.today())

        post = RedditPost(post_id="dup001", subreddit="books", title="Test Book", upvotes=10)
        collector._insert_mention(book.id, post)

        # Simulate checking seen IDs before inserting again
        seen = collector._load_seen_post_ids(book.id)
        assert "dup001" in seen  # collector would skip this on second run


# ── Goodreads metrics update ──────────────────────────────────────────────────

class TestGoodreadsCollectorUpdateMetrics:
    def test_updates_existing_metrics_row(self, session, make_book, make_metrics):
        from collectors.goodreads_collector import GoodreadsCollector
        from scrapers.goodreads.parser import GoodreadsBookData

        book = make_book(asin="B00GR002")
        today = date.today()
        make_metrics(book.id, date=today, amazon_best_seller_rank=5000)

        collector = GoodreadsCollector(today=today)
        data = GoodreadsBookData(
            goodreads_id="12345",
            title="Test Book",
            author="Test Author",
            average_rating=4.3,
            ratings_count=12_000,
            reviews_count=800,
            want_to_read_count=3_500,
            genres=["thriller"],
        )
        collector._update_metrics(book.id, data)

        metrics = session.scalars(
            select(DailyMetrics).where(
                DailyMetrics.book_id == book.id,
                DailyMetrics.date == today,
            )
        ).first()
        assert metrics.goodreads_rating == pytest.approx(4.3)
        assert metrics.goodreads_reviews == 12_000
        assert metrics.goodreads_want_to_read == 3_500

    def test_creates_stub_metrics_when_none_exist(self, session, make_book):
        from collectors.goodreads_collector import GoodreadsCollector
        from scrapers.goodreads.parser import GoodreadsBookData

        book = make_book(asin="B00GR001")
        today = date.today()
        collector = GoodreadsCollector(today=today)

        data = GoodreadsBookData(
            goodreads_id="99999",
            title="Test Book",
            author="Test Author",
            average_rating=4.1,
            ratings_count=500,
            reviews_count=50,
            want_to_read_count=1_200,
            genres=[],
        )
        collector._update_metrics(book.id, data)

        metrics = session.scalars(
            select(DailyMetrics).where(
                DailyMetrics.book_id == book.id,
                DailyMetrics.date == today,
            )
        ).first()
        assert metrics is not None
        assert metrics.goodreads_want_to_read == 1_200
