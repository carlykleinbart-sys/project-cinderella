"""
Shared pytest fixtures.

The test suite uses an in-memory SQLite database so tests run without a
live PostgreSQL instance.  The `pg_insert … on_conflict_do_nothing` calls
in the collector are patched for SQLite compatibility in integration tests.
"""
from __future__ import annotations

import os
from datetime import date
from typing import Generator

import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session, sessionmaker

# Point at a lightweight SQLite test DB before any app imports touch settings
os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("AMAZON_HEADLESS", "true")
os.environ.setdefault("AMAZON_REQUEST_DELAY_MIN", "0")
os.environ.setdefault("AMAZON_REQUEST_DELAY_MAX", "0")

from models import Base, Book, DailyMetrics, IndiePublisher  # noqa: E402
from models.book import BookFormat  # noqa: E402


# ---------------------------------------------------------------------------
# In-memory SQLite engine (no external dependencies required for tests)
# ---------------------------------------------------------------------------

@pytest.fixture(scope="session")
def engine():
    _engine = create_engine("sqlite:///:memory:", echo=False, future=True)
    Base.metadata.create_all(_engine)
    yield _engine
    Base.metadata.drop_all(_engine)
    _engine.dispose()


@pytest.fixture()
def session(engine) -> Generator[Session, None, None]:
    """Provide a transaction-scoped session that rolls back after each test."""
    connection = engine.connect()
    transaction = connection.begin()
    _Session = sessionmaker(bind=connection, autoflush=False)
    sess = _Session()
    yield sess
    sess.close()
    transaction.rollback()
    connection.close()


# ---------------------------------------------------------------------------
# Fixture factories
# ---------------------------------------------------------------------------

@pytest.fixture()
def make_book(session):
    """Factory fixture: create and persist a Book."""
    def _factory(**kwargs) -> Book:
        defaults = dict(
            asin="B0TEST00001",
            title="Test Book",
            author="Test Author",
            genre="Romance",
            format=BookFormat.KINDLE,
            kindle_unlimited=False,
            language="en",
            is_indie=True,
        )
        defaults.update(kwargs)
        book = Book(**defaults)
        session.add(book)
        session.flush()
        return book
    return _factory


@pytest.fixture()
def make_metrics(session):
    """Factory fixture: create and persist a DailyMetrics row."""
    def _factory(book_id: int, **kwargs) -> DailyMetrics:
        defaults = dict(
            book_id=book_id,
            date=date.today(),
            amazon_best_seller_rank=5000,
            estimated_daily_sales=10,
            price=4.99,
            star_rating=4.5,
            review_count=150,
        )
        defaults.update(kwargs)
        m = DailyMetrics(**defaults)
        session.add(m)
        session.flush()
        return m
    return _factory


@pytest.fixture()
def indie_publisher(session) -> IndiePublisher:
    """A single seeded indie publisher."""
    pub = IndiePublisher(
        name="Independently Published",
        match_fragment="independently published",
        is_active=True,
    )
    session.add(pub)
    session.flush()
    return pub
