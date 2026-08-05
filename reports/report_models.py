"""
Typed data shapes for the daily report.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Optional


@dataclass
class BookReportRow:
    """All data needed to render one book's entry in the daily report."""

    # Identity
    asin: str
    title: str
    author: str
    publisher: Optional[str]
    genre: Optional[str]
    book_age_days: Optional[int]
    kindle_unlimited: bool
    amazon_url: str

    # Current metrics
    current_rank: Optional[int]
    current_sales_estimate: Optional[int]
    current_review_count: Optional[int]
    current_star_rating: Optional[float]
    current_price: Optional[float]

    # 7-day deltas
    rank_7d_change: Optional[int]        # positive = improvement
    sales_7d_change_pct: Optional[float] # percentage
    review_7d_new: Optional[int]

    # Scores
    momentum_score: float
    alert_triggered: bool
    alert_reasons: list[str] = field(default_factory=list)
    explanation: str = ""

    # Category ranks (top 3)
    top_category_ranks: dict[str, int] = field(default_factory=dict)


@dataclass
class DailyReport:
    """The full daily report."""

    report_date: date
    total_books_tracked: int
    total_indie_books: int
    books: list[BookReportRow]  # sorted by momentum_score descending
    alerts: list[BookReportRow] = field(default_factory=list)

    @property
    def top_books(self) -> list[BookReportRow]:
        """Top 25 books by momentum score."""
        return self.books[:25]

    @property
    def alert_count(self) -> int:
        return len(self.alerts)
