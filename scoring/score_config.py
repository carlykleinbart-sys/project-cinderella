"""
Momentum scoring configuration — all weights and thresholds in one place.

Weights are normalised inside MomentumScorer; you do not need them to sum
to any particular value here.  Increase a weight to give that signal more
influence on the final score.

Override any value by subclassing ScoringConfig or by passing keyword
arguments to MomentumScorer.
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class ScoringConfig:
    """Weights and hyper-parameters for the momentum scoring model."""

    # ── Component weights (relative, not summing to 1) ────────────────────────
    weight_rank_velocity: float = 3.0
    """How fast the Amazon rank is improving."""

    weight_rank_acceleration: float = 2.0
    """Whether rank improvement is *speeding up* (early breakout signal)."""

    weight_review_velocity: float = 2.0
    """New reviews per day over the lookback window."""

    weight_review_acceleration: float = 1.5
    """Whether review growth is speeding up."""

    weight_rating_stability: float = 1.0
    """High rating (≥4.0) maintained while reviews pour in."""

    weight_sales_growth: float = 2.0
    """Percentage growth in estimated daily sales."""

    weight_age_factor: float = 1.5
    """Boost for recently published books where discovery is harder."""

    weight_kindle_unlimited: float = 0.5
    """Small bonus for KU participation (drives page reads / visibility)."""

    # ── Social signal weights ─────────────────────────────────────────────────
    weight_booktok_velocity: float = 2.5
    """Rate of new TikTok video mentions; very high signal for fiction breakouts."""

    weight_reddit_buzz: float = 1.5
    """Weighted Reddit activity (upvotes + comments) across book subreddits."""

    weight_goodreads_want_to_read: float = 2.0
    """Goodreads Want-to-Read count; leading indicator weeks ahead of sales."""

    # ── Lookback windows ──────────────────────────────────────────────────────
    velocity_window_days: int = 7
    """Days to use for velocity calculations."""

    acceleration_split_days: int = 3
    """Recent window (days) vs prior window for acceleration detection."""

    # ── Thresholds ────────────────────────────────────────────────────────────
    min_snapshots_required: int = 2
    """Minimum daily_metrics rows needed to compute a score."""

    min_rating_for_stability_bonus: float = 4.0
    """Star rating threshold for the rating stability component."""

    new_book_age_days: int = 180
    """Books younger than this (days) receive an age factor boost."""

    # ── Alert thresholds ──────────────────────────────────────────────────────
    alert_momentum_threshold: float = 65.0
    """Trigger an alert when momentum_score exceeds this."""

    alert_rank_improvement_threshold: int = 10_000
    """Trigger an alert when 7-day rank improvement exceeds this many positions."""

    alert_review_spike_threshold: int = 20
    """Trigger an alert when a book gains more than N new reviews in 7 days."""


# Singleton used throughout the app; can be overridden in tests
default_config = ScoringConfig()
