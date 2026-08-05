"""
Unit tests for ORM models and database logic.

Uses an in-memory SQLite session (from conftest.py).  No external
dependencies required.
"""
from __future__ import annotations

from datetime import date

import pytest
from sqlalchemy import select

from models import Book, DailyMetrics, IndiePublisher
from models.book import BookFormat
from models.indie_publisher import DEFAULT_INDIE_PUBLISHERS
from scoring.sales_estimator import estimate_daily_sales


class TestBookModel:

    def test_create_book(self, session, make_book):
        book = make_book(asin="B0NEWBOOK01", title="New Book")
        assert book.id is not None
        assert book.title == "New Book"

    def test_asin_is_unique(self, session, make_book):
        make_book(asin="B0DUPLICATE")
        from sqlalchemy.exc import IntegrityError
        with pytest.raises(IntegrityError):
            make_book(asin="B0DUPLICATE")

    def test_to_dict(self, session, make_book):
        book = make_book(asin="B0DICTTEST1", title="Dict Test")
        d = book.to_dict()
        assert d["asin"] == "B0DICTTEST1"
        assert d["title"] == "Dict Test"
        assert d["is_indie"] is True

    def test_first_seen_set_automatically(self, session, make_book):
        book = make_book()
        assert book.first_seen is not None

    def test_default_format(self, session, make_book):
        book = make_book()
        assert book.format == BookFormat.KINDLE

    def test_default_kindle_unlimited_false(self, session, make_book):
        book = make_book(asin="B0KUTEST001")
        assert book.kindle_unlimited is False

    def test_repr(self, session, make_book):
        book = make_book(asin="B0REPR00001", title="Repr Book")
        assert "B0REPR00001" in repr(book)
        assert "Repr Book" in repr(book)


class TestDailyMetricsModel:

    def test_create_metrics(self, session, make_book, make_metrics):
        book = make_book(asin="B0METRICS001")
        m = make_metrics(book.id, amazon_best_seller_rank=1000)
        assert m.id is not None
        assert m.amazon_best_seller_rank == 1000

    def test_metrics_unique_per_book_per_day(self, session, make_book, make_metrics):
        book = make_book(asin="B0UNIQMET01")
        make_metrics(book.id, date=date(2026, 1, 1))
        from sqlalchemy.exc import IntegrityError
        with pytest.raises(IntegrityError):
            make_metrics(book.id, date=date(2026, 1, 1))

    def test_multiple_days_allowed(self, session, make_book, make_metrics):
        book = make_book(asin="B0MULTIDAY1")
        m1 = make_metrics(book.id, date=date(2026, 1, 1))
        m2 = make_metrics(book.id, date=date(2026, 1, 2))
        assert m1.id != m2.id

    def test_to_dict(self, session, make_book, make_metrics):
        book = make_book(asin="B0DICTMET01")
        m = make_metrics(book.id)
        d = m.to_dict()
        assert d["book_id"] == book.id
        assert "date" in d
        assert "amazon_best_seller_rank" in d

    def test_book_relationship(self, session, make_book, make_metrics):
        book = make_book(asin="B0RELATION1")
        m = make_metrics(book.id)
        assert m.book is not None
        assert m.book.asin == "B0RELATION1"

    def test_goodreads_fields_nullable(self, session, make_book, make_metrics):
        book = make_book(asin="B0GRFIELDS1")
        m = make_metrics(book.id)
        assert m.goodreads_rating is None
        assert m.goodreads_reviews is None
        assert m.goodreads_want_to_read is None


class TestIndiePublisherModel:

    def test_create_indie_publisher(self, session):
        pub = IndiePublisher(
            name="Test Publisher",
            match_fragment="test publisher",
            is_active=True,
        )
        session.add(pub)
        session.flush()
        assert pub.id is not None

    def test_default_publishers_list_non_empty(self):
        assert len(DEFAULT_INDIE_PUBLISHERS) > 0

    def test_default_publishers_have_required_fields(self):
        for entry in DEFAULT_INDIE_PUBLISHERS:
            assert "name" in entry
            assert "match_fragment" in entry

    def test_match_fragment_is_lowercase(self):
        for entry in DEFAULT_INDIE_PUBLISHERS:
            assert entry["match_fragment"] == entry["match_fragment"].lower()

    def test_repr(self, session):
        pub = IndiePublisher(
            name="Repr Publisher",
            match_fragment="repr publisher",
        )
        session.add(pub)
        session.flush()
        assert "Repr Publisher" in repr(pub)


class TestIndiePublisherMatching:
    """Validate the indie-detection logic used by the collector."""

    INDIE_FRAGMENTS = [
        "independently published",
        "kdp",
        "draft2digital",
        "ingramspark",
        "lulu",
    ]

    def _is_indie(self, publisher: str) -> bool:
        lower = publisher.lower()
        return any(f in lower for f in self.INDIE_FRAGMENTS)

    @pytest.mark.parametrize("publisher,expected", [
        ("Independently Published", True),
        ("Amazon KDP", True),
        ("Draft2Digital", True),
        ("IngramSpark", True),
        ("Lulu Press", True),
        ("Penguin Random House", False),
        ("Simon & Schuster", False),
        ("HarperCollins", False),
        ("Tor Books", False),
        ("", False),
    ])
    def test_indie_detection(self, publisher: str, expected: bool):
        assert self._is_indie(publisher) is expected


class TestSalesEstimator:

    def test_none_input_returns_none(self):
        assert estimate_daily_sales(None) is None

    def test_zero_returns_none(self):
        assert estimate_daily_sales(0) is None

    def test_rank_1_high_sales(self):
        assert estimate_daily_sales(1) > 1000

    def test_higher_rank_lower_sales(self):
        s100 = estimate_daily_sales(100)
        s1000 = estimate_daily_sales(1000)
        s10000 = estimate_daily_sales(10000)
        assert s100 > s1000 > s10000  # type: ignore

    def test_very_high_rank_near_zero(self):
        assert estimate_daily_sales(400_000) == 1

    def test_million_plus_returns_zero(self):
        assert estimate_daily_sales(1_500_000) == 0

    @pytest.mark.parametrize("bsr", [1, 10, 100, 1000, 10000, 100000, 500000])
    def test_always_non_negative(self, bsr: int):
        result = estimate_daily_sales(bsr)
        assert result is not None
        assert result >= 0
