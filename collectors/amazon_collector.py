"""
AmazonCollector — orchestrates the full Amazon data pipeline.

Pipeline
--------
1. Load the configured bestseller categories (priority categories first).
2. For each category, fetch and parse the top-N bestseller list.
3. Filter to indie-published books only (using IndiePublisher lookup).
4. For each new or existing tracked book, fetch the full detail page.
5. Upsert the Book record.
6. INSERT a DailyMetrics snapshot — never overwrite an existing row.

The collector is safe to run multiple times on the same day; duplicate
metric rows are silently ignored via ON CONFLICT DO NOTHING.
"""
from __future__ import annotations

import asyncio
from datetime import date, datetime
from typing import Optional

from loguru import logger
from sqlalchemy import select, insert as generic_insert
from sqlalchemy.exc import IntegrityError

from collectors.base import BaseCollector, CollectionResult
from config import settings
from database import get_session
from models import Book, DailyMetrics, IndiePublisher
from models.book import BookFormat
from scrapers.amazon import KINDLE_CATEGORIES, AmazonParser
from scrapers.amazon.categories import BESTSELLER_BASE_URL, BOOK_BASE_URL, PRIORITY_CATEGORIES
from scrapers.amazon.parser import BookDetail, BestsellerEntry

# AmazonBrowser is imported lazily inside collect() to avoid requiring
# Playwright at import time (integration tests mock the browser).
TYPE_CHECKING = False
if TYPE_CHECKING:
    from scrapers.amazon.browser import AmazonBrowser  # noqa: F401
from scoring.sales_estimator import estimate_daily_sales


class AmazonCollector(BaseCollector):
    """
    Collects Amazon bestseller data and stores it historically.

    Parameters
    ----------
    categories:
        Override which categories to collect.  Defaults to all categories in
        ``KINDLE_CATEGORIES`` with priority categories first.
    max_books_per_category:
        Override the per-category book limit.  Defaults to
        ``settings.amazon_max_books_per_category``.
    today:
        Override the collection date.  Defaults to ``date.today()``.
        Useful for testing.
    """

    name = "amazon"

    def __init__(
        self,
        categories: Optional[dict[str, str]] = None,
        max_books_per_category: Optional[int] = None,
        today: Optional[date] = None,
    ) -> None:
        self._categories = categories or self._ordered_categories()
        self._max_books = max_books_per_category or settings.amazon_max_books_per_category
        self._today = today or date.today()
        self._indie_fragments: list[str] = []  # loaded lazily from DB

    # ── Public interface ──────────────────────────────────────────────────────

    async def collect(self) -> CollectionResult:
        result = CollectionResult(collector=self.name)

        # Load indie publisher patterns from the database once
        self._indie_fragments = self._load_indie_fragments()
        logger.info(
            "Loaded {} indie publisher patterns",
            len(self._indie_fragments),
        )

        from scrapers.amazon.browser import AmazonBrowser  # lazy import

        async with AmazonBrowser() as browser:
            seen_asins: set[str] = set()  # deduplicate across categories

            for genre, node_id in self._categories.items():
                logger.info("Collecting category: {} (node {})", genre, node_id)
                url = BESTSELLER_BASE_URL.format(node_id=node_id)

                try:
                    html = await browser.fetch_page_with_scroll(url)
                    entries = AmazonParser.parse_bestseller_list(html)
                    entries = entries[: self._max_books]
                    logger.info("  → {} entries parsed", len(entries))
                except Exception as exc:
                    logger.error("  Failed to fetch/parse {}: {}", genre, exc)
                    result.errors += 1
                    continue

                for entry in entries:
                    asin = entry["asin"]
                    if asin in seen_asins:
                        continue
                    seen_asins.add(asin)

                    try:
                        new, updated, wrote_metrics = await self._process_book(
                            browser, entry, genre
                        )
                        result.new_books += int(new)
                        result.updated_books += int(updated)
                        result.metrics_written += int(wrote_metrics)
                    except Exception as exc:
                        logger.error("  Error processing ASIN {}: {}", asin, exc)
                        result.errors += 1

        return result

    # ── Internal helpers ──────────────────────────────────────────────────────

    async def _process_book(
        self,
        browser: AmazonBrowser,
        entry: BestsellerEntry,
        genre: str,
    ) -> tuple[bool, bool, bool]:
        """
        Upsert a Book record and write today's DailyMetrics snapshot.

        Returns (is_new, is_updated, metrics_written).
        """
        asin = entry["asin"]

        # ── Fetch full detail page ─────────────────────────────────────────
        detail_url = BOOK_BASE_URL.format(asin=asin)
        try:
            detail_html = await browser.fetch_page(detail_url)
            detail = AmazonParser.parse_book_detail(detail_html, asin)
        except Exception as exc:
            logger.warning("Could not fetch detail for {}: {}", asin, exc)
            detail = None

        # Merge bestseller entry data with detail page data
        book_data = self._merge_book_data(entry, detail, genre)

        # ── Determine indie status ─────────────────────────────────────────
        publisher = book_data.get("publisher") or ""
        is_indie = self._is_indie_publisher(publisher)
        book_data["is_indie"] = is_indie

        # ── Upsert Book ────────────────────────────────────────────────────
        is_new = False
        is_updated = False

        with get_session() as session:
            existing = session.scalars(
                select(Book).where(Book.asin == asin)
            ).first()

            if existing is None:
                book = Book(**book_data)
                session.add(book)
                session.flush()  # get the ID
                book_id = book.id
                is_new = True
                logger.debug("  New book: {} — {}", asin, book_data["title"])
            else:
                # Update mutable fields (leave first_seen intact)
                for field, value in book_data.items():
                    if field != "first_seen" and hasattr(existing, field):
                        setattr(existing, field, value)
                existing.last_updated = datetime.utcnow()
                book_id = existing.id
                is_updated = True
                logger.debug("  Updated book: {} — {}", asin, book_data["title"])

            # ── Write DailyMetrics (idempotent) ────────────────────────────
            metrics_data = self._build_metrics(entry, detail, book_id)
            wrote_metrics = self._insert_metrics(session, metrics_data)

        return is_new, is_updated, wrote_metrics

    def _merge_book_data(
        self,
        entry: BestsellerEntry,
        detail: Optional[BookDetail],
        genre: str,
    ) -> dict:
        """Merge a bestseller entry with optional detail page data."""
        data: dict = {
            "asin": entry["asin"],
            "title": entry["title"],
            "author": entry["author"],
            "genre": genre,
            "cover_url": entry.get("cover_url"),
        }
        if detail:
            data.update({
                "title": detail["title"],
                "subtitle": detail.get("subtitle"),
                "author": detail["author"],
                "publisher": detail.get("publisher"),
                "publication_date": detail.get("publication_date"),
                "format": self._parse_format(detail.get("format", "Kindle")),
                "kindle_unlimited": detail.get("kindle_unlimited", False),
                "isbn": detail.get("isbn"),
                "language": detail.get("language", "en"),
                "genre": detail.get("genre") or genre,
                "categories": detail.get("categories", []),
                "description": detail.get("description"),
                "cover_url": detail.get("cover_url") or entry.get("cover_url"),
            })
        return data

    def _build_metrics(
        self,
        entry: BestsellerEntry,
        detail: Optional[BookDetail],
        book_id: int,
    ) -> dict:
        """Assemble a DailyMetrics dict from scraped data."""
        bsr = detail["amazon_best_seller_rank"] if detail else None
        price = detail["price"] if detail else entry.get("price")
        star_rating = detail["star_rating"] if detail else entry.get("star_rating")
        review_count = detail["review_count"] if detail else entry.get("review_count")
        category_ranks = detail["category_ranks"] if detail else {}

        return {
            "book_id": book_id,
            "date": self._today,
            "amazon_best_seller_rank": bsr,
            "estimated_daily_sales": estimate_daily_sales(bsr) if bsr else None,
            "price": price,
            "star_rating": star_rating,
            "review_count": review_count,
            "category_ranks": category_ranks or None,
        }

    @staticmethod
    def _insert_metrics(session, metrics_data: dict) -> bool:
        """
        Insert a DailyMetrics row, ignoring conflicts.

        Uses PostgreSQL's ON CONFLICT DO NOTHING when available; falls back
        to a try/except IntegrityError for SQLite (used in tests).

        Returns True if a new row was written, False if it already existed.
        """
        try:
            # Try PostgreSQL-native upsert first (production path)
            from sqlalchemy.dialects.postgresql import insert as pg_insert
            stmt = (
                pg_insert(DailyMetrics)
                .values(**metrics_data)
                .on_conflict_do_nothing(constraint="uq_daily_metrics_book_date")
            )
            result = session.execute(stmt)
            return result.rowcount > 0  # type: ignore[return-value]
        except Exception:
            # Fallback: standard INSERT — catch IntegrityError on duplicate
            try:
                stmt = generic_insert(DailyMetrics).values(**metrics_data)
                session.execute(stmt)
                return True
            except IntegrityError:
                session.rollback()
                return False

    def _is_indie_publisher(self, publisher: str) -> bool:
        """Return True if publisher matches any known indie fragment."""
        lower = publisher.lower()
        return any(fragment in lower for fragment in self._indie_fragments)

    @staticmethod
    def _load_indie_fragments() -> list[str]:
        """Load active indie publisher match fragments from the database."""
        with get_session() as session:
            rows = session.scalars(
                select(IndiePublisher.match_fragment).where(IndiePublisher.is_active.is_(True))
            ).all()
        return list(rows)

    @staticmethod
    def _parse_format(fmt: str) -> BookFormat:
        try:
            return BookFormat(fmt)
        except ValueError:
            return BookFormat.UNKNOWN

    @staticmethod
    def _ordered_categories() -> dict[str, str]:
        """Return categories dict with priority categories first."""
        ordered: dict[str, str] = {}
        for name in PRIORITY_CATEGORIES:
            if name in KINDLE_CATEGORIES:
                ordered[name] = KINDLE_CATEGORIES[name]
        for name, node_id in KINDLE_CATEGORIES.items():
            if name not in ordered:
                ordered[name] = node_id
        return ordered
