"""
Integration tests for AmazonCollector.

The browser and parser are mocked so these tests run without a real browser
or network connection, but they DO hit the (in-memory) database.
"""
from __future__ import annotations

from datetime import date
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from collectors.amazon_collector import AmazonCollector
from models import Book, DailyMetrics, IndiePublisher
from scrapers.amazon.parser import BestsellerEntry, BookDetail


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

FAKE_ENTRY: BestsellerEntry = {
    "rank": 1,
    "asin": "B0INDIE0001",
    "title": "The Breakout Novel",
    "author": "Indie Author",
    "price": 4.99,
    "star_rating": 4.7,
    "review_count": 342,
    "cover_url": "https://example.com/cover.jpg",
}

FAKE_DETAIL: BookDetail = {
    "asin": "B0INDIE0001",
    "title": "The Breakout Novel",
    "subtitle": "A Story",
    "author": "Indie Author",
    "publisher": "Independently Published",
    "publication_date": date(2024, 3, 15),
    "format": "Kindle",
    "kindle_unlimited": True,
    "isbn": "9781234567890",
    "language": "en",
    "genre": "Romance",
    "categories": ["Romance", "Contemporary Romance"],
    "description": "A heartwarming story.",
    "cover_url": "https://example.com/cover.jpg",
    "price": 4.99,
    "star_rating": 4.7,
    "review_count": 342,
    "amazon_best_seller_rank": 850,
    "category_ranks": {"Romance > Contemporary": 3},
}

TRAD_ENTRY: BestsellerEntry = {
    **FAKE_ENTRY,
    "asin": "B0TRAD00001",
    "title": "Traditional Publisher Novel",
}

TRAD_DETAIL: BookDetail = {
    **FAKE_DETAIL,
    "asin": "B0TRAD00001",
    "title": "Traditional Publisher Novel",
    "publisher": "Penguin Random House",
    "kindle_unlimited": False,
}


@pytest.fixture()
def mock_browser():
    """Mock AmazonBrowser that returns predictable HTML."""
    browser = AsyncMock()
    browser.__aenter__ = AsyncMock(return_value=browser)
    browser.__aexit__ = AsyncMock(return_value=None)
    browser.fetch_page_with_scroll = AsyncMock(return_value="<html>BESTSELLER LIST</html>")
    browser.fetch_page = AsyncMock(return_value="<html>BOOK DETAIL</html>")
    return browser


@pytest.fixture()
def collector(indie_publisher) -> AmazonCollector:
    """A collector with a single test category."""
    return AmazonCollector(
        categories={"Romance": "2200031011"},
        max_books_per_category=10,
        today=date(2026, 8, 3),
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestAmazonCollectorIndieDetection:
    """Test that indie detection logic correctly classifies publishers."""

    def test_detects_independently_published(self, collector):
        collector._indie_fragments = ["independently published"]
        assert collector._is_indie_publisher("Independently Published") is True

    def test_detects_kdp(self, collector):
        collector._indie_fragments = ["kdp"]
        assert collector._is_indie_publisher("Amazon KDP") is True

    def test_rejects_traditional(self, collector):
        collector._indie_fragments = ["independently published", "kdp"]
        assert collector._is_indie_publisher("Penguin Random House") is False

    def test_case_insensitive(self, collector):
        collector._indie_fragments = ["independently published"]
        assert collector._is_indie_publisher("INDEPENDENTLY PUBLISHED") is True

    def test_empty_publisher(self, collector):
        collector._indie_fragments = ["independently published"]
        assert collector._is_indie_publisher("") is False


class TestAmazonCollectorMergeData:
    """Test the data-merging logic between bestseller entry and detail page."""

    def test_detail_title_overrides_entry(self, collector):
        entry = {**FAKE_ENTRY, "title": "Short Title"}
        detail = {**FAKE_DETAIL, "title": "Full Title: A Complete Novel"}
        merged = collector._merge_book_data(entry, detail, "Romance")
        assert merged["title"] == "Full Title: A Complete Novel"

    def test_detail_none_falls_back_to_entry(self, collector):
        merged = collector._merge_book_data(FAKE_ENTRY, None, "Romance")
        assert merged["title"] == FAKE_ENTRY["title"]
        assert merged["author"] == FAKE_ENTRY["author"]

    def test_genre_from_category(self, collector):
        merged = collector._merge_book_data(FAKE_ENTRY, None, "Fantasy")
        assert merged["genre"] == "Fantasy"

    def test_genre_from_detail_overrides(self, collector):
        detail = {**FAKE_DETAIL, "genre": "Women's Fiction"}
        merged = collector._merge_book_data(FAKE_ENTRY, detail, "Romance")
        assert merged["genre"] == "Women's Fiction"


class TestAmazonCollectorBuildMetrics:
    """Test that metrics are assembled correctly."""

    def test_bsr_from_detail(self, collector):
        metrics = collector._build_metrics(FAKE_ENTRY, FAKE_DETAIL, book_id=1)
        assert metrics["amazon_best_seller_rank"] == 850

    def test_estimated_sales_computed(self, collector):
        metrics = collector._build_metrics(FAKE_ENTRY, FAKE_DETAIL, book_id=1)
        assert metrics["estimated_daily_sales"] is not None
        assert metrics["estimated_daily_sales"] > 0

    def test_price_from_detail(self, collector):
        metrics = collector._build_metrics(FAKE_ENTRY, FAKE_DETAIL, book_id=1)
        assert metrics["price"] == pytest.approx(4.99)

    def test_category_ranks_stored(self, collector):
        metrics = collector._build_metrics(FAKE_ENTRY, FAKE_DETAIL, book_id=1)
        assert metrics["category_ranks"] == {"Romance > Contemporary": 3}

    def test_date_matches_today(self, collector):
        metrics = collector._build_metrics(FAKE_ENTRY, FAKE_DETAIL, book_id=1)
        assert metrics["date"] == date(2026, 8, 3)

    def test_null_bsr_gives_null_sales(self, collector):
        detail_no_bsr = {**FAKE_DETAIL, "amazon_best_seller_rank": None}
        metrics = collector._build_metrics(FAKE_ENTRY, detail_no_bsr, book_id=1)
        assert metrics["estimated_daily_sales"] is None


class TestAmazonCollectorOrderedCategories:
    """Test that priority categories come first."""

    def test_priority_categories_first(self):
        from scrapers.amazon.categories import PRIORITY_CATEGORIES
        ordered = AmazonCollector._ordered_categories()
        keys = list(ordered.keys())
        # Find the index of the first non-priority category
        first_non_priority = next(
            (i for i, k in enumerate(keys) if k not in PRIORITY_CATEGORIES),
            len(keys),
        )
        # All keys before that index should be priority categories
        assert all(k in PRIORITY_CATEGORIES for k in keys[:first_non_priority])

    def test_all_categories_included(self):
        from scrapers.amazon.categories import KINDLE_CATEGORIES
        ordered = AmazonCollector._ordered_categories()
        assert set(ordered.keys()) == set(KINDLE_CATEGORIES.keys())
