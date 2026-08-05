"""
Integration tests for the FastAPI dashboard.

FastAPI's TestClient runs route handlers in a background thread.
SQLite connections are not thread-safe by default, so we use a dedicated
in-memory engine with StaticPool (one shared connection) and
check_same_thread=False.  Each test class gets fresh tables.
"""
from __future__ import annotations

from datetime import date

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from api.app import create_app
from api.deps import get_db
from models import Base, Book, DailyMetrics
from models.book import BookFormat
from models.momentum_score import MomentumScore
from models.social_signals import BookTokMention, RedditMention


# ── Shared test engine (one per test module, tables re-created per class) ──────

TEST_DB_URL = "sqlite:///:memory:"


@pytest.fixture(scope="module")
def api_engine():
    engine = create_engine(
        TEST_DB_URL,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
        future=True,
    )
    Base.metadata.create_all(engine)
    yield engine
    Base.metadata.drop_all(engine)
    engine.dispose()


@pytest.fixture()
def api_session(api_engine):
    """Fresh session per test, rolled back afterward."""
    Session = sessionmaker(bind=api_engine, autocommit=False, autoflush=True)
    s = Session()
    yield s
    s.rollback()
    s.close()


@pytest.fixture()
def client(api_session):
    """TestClient with get_db overridden to use the test session."""
    app = create_app()

    def _override():
        yield api_session

    app.dependency_overrides[get_db] = _override
    with TestClient(app, raise_server_exceptions=True) as c:
        yield c


# ── Seed helpers ──────────────────────────────────────────────────────────────

def _book(session, asin="B0API001", title="Test Novel", author="Test Author",
          is_indie=True, genre="Romance") -> Book:
    b = Book(asin=asin, title=title, author=author, genre=genre,
             format=BookFormat.KINDLE, kindle_unlimited=True,
             language="en", is_indie=is_indie)
    session.add(b)
    session.flush()
    return b


def _metrics(session, book_id: int, **kw) -> DailyMetrics:
    defaults = dict(book_id=book_id, date=date.today(),
                    amazon_best_seller_rank=5000, estimated_daily_sales=12,
                    price=3.99, star_rating=4.4, review_count=200,
                    goodreads_rating=4.1, goodreads_reviews=500,
                    goodreads_want_to_read=1200)
    defaults.update(kw)
    m = DailyMetrics(**defaults)
    session.add(m)
    session.flush()
    return m


def _score(session, book_id: int, score=72.5, alert=False) -> MomentumScore:
    s = MomentumScore(
        book_id=book_id, date=date.today(), momentum_score=score,
        components={"rank_velocity": 80.0, "review_velocity": 60.0,
                    "booktok_velocity": 0.0, "reddit_buzz": 0.0,
                    "goodreads_want_to_read": 0.0},
        explanation=f"Strong momentum: {score}",
        snapshots_used=7,
        alert_triggered=alert,
        alert_reasons=["High score"] if alert else [],
    )
    session.add(s)
    session.flush()
    return s


# ── Health / stats ────────────────────────────────────────────────────────────

class TestHealth:
    def test_health_ok(self, client):
        r = client.get("/health")
        assert r.status_code == 200
        assert r.json()["status"] == "ok"
        assert r.json()["db_connected"] is True

    def test_health_has_version(self, client):
        assert "version" in client.get("/health").json()


class TestStats:
    def test_stats_returns_counts(self, client, api_session):
        b = _book(api_session, asin="B0ST001")
        _metrics(api_session, b.id)
        _score(api_session, b.id)
        r = client.get("/api/stats")
        assert r.status_code == 200
        d = r.json()
        assert d["total_books_tracked"] >= 1
        assert "last_collection_date" in d

    def test_stats_alert_count(self, client, api_session):
        b = _book(api_session, asin="B0ST002")
        _score(api_session, b.id, alert=True)
        r = client.get("/api/stats")
        assert r.json()["alerts_today"] >= 1


# ── Dashboard HTML ────────────────────────────────────────────────────────────

class TestDashboard:
    def test_root_returns_html(self, client):
        r = client.get("/")
        assert r.status_code == 200
        assert "text/html" in r.headers["content-type"]

    def test_dashboard_contains_branding(self, client):
        assert "CINDERELLA" in client.get("/").text

    def test_dashboard_contains_js(self, client):
        assert "<script>" in client.get("/").text

    def test_api_docs_available(self, client):
        r = client.get("/api/docs")
        assert r.status_code == 200


# ── Book list ─────────────────────────────────────────────────────────────────

class TestBookList:
    def test_returns_list(self, client, api_session):
        _book(api_session, asin="B0BL001")
        r = client.get("/api/books")
        assert r.status_code == 200
        assert isinstance(r.json(), list)
        assert len(r.json()) >= 1

    def test_only_indie_books_returned(self, client, api_session):
        _book(api_session, asin="B0BL002", is_indie=True)
        _book(api_session, asin="B0BL003", is_indie=False)
        asins = [b["asin"] for b in client.get("/api/books").json()]
        assert "B0BL002" in asins
        assert "B0BL003" not in asins

    def test_pagination_limit(self, client, api_session):
        for i in range(5):
            _book(api_session, asin=f"B0BLP{i:02d}")
        r = client.get("/api/books?limit=2")
        assert len(r.json()) <= 2

    def test_genre_filter(self, client, api_session):
        _book(api_session, asin="B0BLG01", genre="Fantasy")
        asins = [b["asin"] for b in client.get("/api/books?genre=Fantasy").json()]
        assert "B0BLG01" in asins

    def test_unknown_genre_returns_empty(self, client, api_session):
        _book(api_session, asin="B0BLG02", genre="Romance")
        assert client.get("/api/books?genre=XYZABC").json() == []


# ── Book detail ───────────────────────────────────────────────────────────────

class TestBookDetail:
    def test_returns_detail(self, client, api_session):
        b = _book(api_session, asin="B0DT001")
        _metrics(api_session, b.id)
        _score(api_session, b.id)
        r = client.get("/api/books/B0DT001")
        assert r.status_code == 200
        assert r.json()["asin"] == "B0DT001"
        assert r.json()["title"] == "Test Novel"

    def test_includes_latest_metrics(self, client, api_session):
        b = _book(api_session, asin="B0DT002")
        _metrics(api_session, b.id)
        assert client.get("/api/books/B0DT002").json()["latest_metrics"] is not None

    def test_includes_score_history(self, client, api_session):
        b = _book(api_session, asin="B0DT003")
        _score(api_session, b.id)
        assert len(client.get("/api/books/B0DT003").json()["score_history"]) >= 1

    def test_404_for_unknown_asin(self, client):
        assert client.get("/api/books/BXXXXXXX").status_code == 404


# ── Leaderboard ───────────────────────────────────────────────────────────────

class TestLeaderboard:
    def test_returns_leaderboard_structure(self, client, api_session):
        b = _book(api_session, asin="B0LB001")
        _score(api_session, b.id, score=75.0)
        r = client.get("/api/leaderboard")
        assert r.status_code == 200
        d = r.json()
        assert "entries" in d and "total_tracked" in d and "as_of" in d

    def test_ordered_by_score_desc(self, client, api_session):
        b1 = _book(api_session, asin="B0LB002")
        b2 = _book(api_session, asin="B0LB003")
        _score(api_session, b1.id, score=40.0)
        _score(api_session, b2.id, score=85.0)
        scores = [e["momentum_score"] for e in client.get("/api/leaderboard").json()["entries"]]
        assert scores == sorted(scores, reverse=True)

    def test_alert_books_flagged(self, client, api_session):
        b = _book(api_session, asin="B0LB004")
        _score(api_session, b.id, score=80.0, alert=True)
        entries = client.get("/api/leaderboard").json()["entries"]
        entry = next((e for e in entries if e["asin"] == "B0LB004"), None)
        assert entry is not None
        assert entry["alert_triggered"] is True

    def test_limit_param_respected(self, client, api_session):
        for i in range(5):
            bk = _book(api_session, asin=f"B0LBL{i:02d}")
            _score(api_session, bk.id, score=float(50 + i))
        assert len(client.get("/api/leaderboard?limit=3").json()["entries"]) <= 3

    def test_empty_when_no_scores(self, client):
        r = client.get("/api/leaderboard")
        assert isinstance(r.json()["entries"], list)


# ── Social signals ────────────────────────────────────────────────────────────

class TestSocialSummary:
    def test_returns_summary(self, client, api_session):
        b = _book(api_session, asin="B0SC001")
        r = client.get(f"/api/social/{b.id}")
        assert r.status_code == 200
        d = r.json()
        assert d["book_id"] == b.id
        assert "booktok_mentions" in d
        assert "reddit_posts" in d
        assert "goodreads_want_to_read" in d

    def test_404_for_missing_book(self, client):
        assert client.get("/api/social/99999").status_code == 404

    def test_window_days_param(self, client, api_session):
        b = _book(api_session, asin="B0SC002")
        r = client.get(f"/api/social/{b.id}?window_days=14")
        assert r.status_code == 200
        assert r.json()["window_days"] == 14

    def test_goodreads_wtr_from_metrics(self, client, api_session):
        b = _book(api_session, asin="B0SC003")
        _metrics(api_session, b.id, goodreads_want_to_read=2500)
        r = client.get(f"/api/social/{b.id}")
        assert r.json()["goodreads_want_to_read"] == 2500
