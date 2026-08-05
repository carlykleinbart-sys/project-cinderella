"""
Typed output shapes for the momentum scoring pipeline.

ScoreComponents   — individual signal breakdown (all 0–100)
MomentumResult    — final score + components + explanation + alert flags
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Optional


@dataclass
class ScoreComponents:
    """Individual signal scores, each normalised to 0–100."""

    rank_velocity: float = 0.0
    """Rate of Amazon rank improvement over the lookback window."""

    rank_acceleration: float = 0.0
    """Whether rank improvement is accelerating (recent half vs earlier half)."""

    review_velocity: float = 0.0
    """New reviews per day over the lookback window, normalised."""

    review_acceleration: float = 0.0
    """Whether review growth rate is itself growing."""

    rating_stability: float = 0.0
    """High rating maintained under review volume pressure."""

    sales_growth: float = 0.0
    """Percentage growth in estimated daily sales."""

    age_factor: float = 0.0
    """Boost for recently published books."""

    kindle_unlimited: float = 0.0
    """Bonus for Kindle Unlimited participation."""

    booktok_velocity: float = 0.0
    """Rate of new TikTok video mentions over the lookback window, normalised."""

    reddit_buzz: float = 0.0
    """Weighted Reddit activity: upvotes + comment volume, normalised."""

    goodreads_want_to_read: float = 0.0
    """Normalised Want-to-Read count — leading indicator weeks ahead of sales."""

    def to_dict(self) -> dict[str, float]:
        return {
            "rank_velocity": round(self.rank_velocity, 2),
            "rank_acceleration": round(self.rank_acceleration, 2),
            "review_velocity": round(self.review_velocity, 2),
            "review_acceleration": round(self.review_acceleration, 2),
            "rating_stability": round(self.rating_stability, 2),
            "sales_growth": round(self.sales_growth, 2),
            "age_factor": round(self.age_factor, 2),
            "kindle_unlimited": round(self.kindle_unlimited, 2),
            "booktok_velocity": round(self.booktok_velocity, 2),
            "reddit_buzz": round(self.reddit_buzz, 2),
            "goodreads_want_to_read": round(self.goodreads_want_to_read, 2),
        }


@dataclass
class MomentumResult:
    """
    Complete momentum scoring result for a single book on a single date.

    Attributes
    ----------
    book_id:
        Database ID of the scored book.
    score_date:
        The date this score was calculated for.
    momentum_score:
        Weighted composite score, 0–100.  Higher = stronger breakout signal.
    components:
        Individual component breakdown.
    explanation:
        Human-readable summary of why this score was assigned.
    snapshots_used:
        Number of daily_metrics rows used to compute the score.
    alert_triggered:
        True if the score or any component breached an alert threshold.
    alert_reasons:
        List of specific threshold breaches that triggered alerts.
    """

    book_id: int
    score_date: date
    momentum_score: float
    components: ScoreComponents
    explanation: str
    snapshots_used: int
    alert_triggered: bool = False
    alert_reasons: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "book_id": self.book_id,
            "score_date": self.score_date.isoformat(),
            "momentum_score": round(self.momentum_score, 2),
            "components": self.components.to_dict(),
            "explanation": self.explanation,
            "snapshots_used": self.snapshots_used,
            "alert_triggered": self.alert_triggered,
            "alert_reasons": self.alert_reasons,
        }
