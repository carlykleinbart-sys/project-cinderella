"""
DailyMetrics model — one immutable row per (book, date).

NEVER overwrite existing rows.  Historical data is the most valuable
asset in the system.  Use INSERT … ON CONFLICT DO NOTHING at the
database level and upsert=False in the collector.

Goodreads fields are stubbed out here so the schema is stable through
Milestone 3, but will be populated only once that collector is built.
"""
from __future__ import annotations

from datetime import date
from typing import Any, Optional

from sqlalchemy import (
    Date,
    Float,
    ForeignKey,
    Index,
    Integer,
    JSON,
    Numeric,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from models.base import Base


class DailyMetrics(Base):
    """
    Daily performance snapshot for a single book.

    One row per (book_id, date).  Once written, a row is never mutated.
    """

    __tablename__ = "daily_metrics"

    # ── Primary key ───────────────────────────────────────────────────────────
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)

    # ── Foreign key ───────────────────────────────────────────────────────────
    book_id: Mapped[int] = mapped_column(
        ForeignKey("books.id", ondelete="CASCADE"),
        nullable=False,
    )

    # ── Date of snapshot ──────────────────────────────────────────────────────
    date: Mapped[date] = mapped_column(Date, nullable=False)

    # ── Amazon metrics ────────────────────────────────────────────────────────
    amazon_best_seller_rank: Mapped[Optional[int]] = mapped_column(
        Integer,
        nullable=True,
        comment="Overall Kindle store best-seller rank at time of collection",
    )
    estimated_daily_sales: Mapped[Optional[int]] = mapped_column(
        Integer,
        nullable=True,
        comment="Sales estimate derived from BSR using calibrated lookup table",
    )
    price: Mapped[Optional[float]] = mapped_column(
        Numeric(10, 2),
        nullable=True,
        comment="Kindle price in USD at time of collection",
    )
    star_rating: Mapped[Optional[float]] = mapped_column(
        Float,
        nullable=True,
        comment="Amazon star rating (0–5) at time of collection",
    )
    review_count: Mapped[Optional[int]] = mapped_column(
        Integer,
        nullable=True,
        comment="Total number of Amazon customer reviews",
    )
    category_ranks: Mapped[Optional[dict[str, int]]] = mapped_column(
        JSON,
        nullable=True,
        comment='Mapping of category name → rank, e.g. {"Kindle > Romance > Romantic Suspense": 3}',
    )

    # ── Goodreads metrics (populated from Milestone 3 onwards) ───────────────
    goodreads_rating: Mapped[Optional[float]] = mapped_column(
        Float, nullable=True, comment="Goodreads average rating (0–5)"
    )
    goodreads_reviews: Mapped[Optional[int]] = mapped_column(
        Integer, nullable=True, comment="Goodreads total ratings count"
    )
    goodreads_want_to_read: Mapped[Optional[int]] = mapped_column(
        Integer, nullable=True, comment="Goodreads 'Want to Read' shelf count"
    )

    # ── Relationships ─────────────────────────────────────────────────────────
    book: Mapped["Book"] = relationship(back_populates="daily_metrics")  # noqa: F821

    # ── Constraints & indices ─────────────────────────────────────────────────
    __table_args__ = (
        # The core immutability guarantee: one snapshot per book per day
        UniqueConstraint("book_id", "date", name="uq_daily_metrics_book_date"),
        Index("ix_daily_metrics_date", "date"),
        Index("ix_daily_metrics_book_date", "book_id", "date"),
    )

    def __repr__(self) -> str:
        return (
            f"<DailyMetrics book_id={self.book_id} date={self.date} "
            f"bsr={self.amazon_best_seller_rank}>"
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "book_id": self.book_id,
            "date": self.date.isoformat(),
            "amazon_best_seller_rank": self.amazon_best_seller_rank,
            "estimated_daily_sales": self.estimated_daily_sales,
            "price": float(self.price) if self.price is not None else None,
            "star_rating": self.star_rating,
            "review_count": self.review_count,
            "category_ranks": self.category_ranks,
            "goodreads_rating": self.goodreads_rating,
            "goodreads_reviews": self.goodreads_reviews,
            "goodreads_want_to_read": self.goodreads_want_to_read,
        }
