"""
Unit tests for MomentumScorer.

All tests use synthetic snapshot objects — no database required.
The snapshots follow a simple protocol: any object with the right attributes.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from typing import Optional

import pytest

from scoring.momentum_scorer import MomentumScorer
from scoring.score_config import ScoringConfig
from scoring.score_models import MomentumResult


# ---------------------------------------------------------------------------
# Minimal snapshot stub
# ---------------------------------------------------------------------------
@dataclass
class Snap:
    """Lightweight stand-in for a DailyMetrics row."""
    date: date
    amazon_best_seller_rank: Optional[int] = None
    estimated_daily_sales: Optional[int] = None
    review_count: Optional[int] = None
    star_rating: Optional[float] = None


def _day(n: int) -> date:
    """Return base_date + n days."""
    return date(2026, 1, 1) + timedelta(days=n)


def _snaps_improving(
    start_rank: int = 200_000,
    end_rank: int = 20_000,
    days: int = 7,
    start_reviews: int = 10,
    end_reviews: int = 80,
    star_rating: float = 4.5,
) -> list[Snap]:
    """Build a list of snapshots showing rank and review improvement."""
    result = []
    for i in range(days + 1):
        frac = i / days
        rank = int(start_rank - (start_rank - end_rank) * frac)
        reviews = int(start_reviews + (end_reviews - start_reviews) * frac)
        sales = max(1, 500 - int(rank / 400))
        result.append(Snap(
            date=_day(i),
            amazon_best_seller_rank=rank,
            estimated_daily_sales=sales,
            review_count=reviews,
            star_rating=star_rating,
        ))
    return result


def _snaps_flat(rank: int = 100_000, days: int = 7) -> list[Snap]:
    """Build snapshots with no movement."""
    return [
        Snap(date=_day(i), amazon_best_seller_rank=rank,
             estimated_daily_sales=5, review_count=50, star_rating=4.0)
        for i in range(days + 1)
    ]


# ---------------------------------------------------------------------------
# Basic scoring tests
# ---------------------------------------------------------------------------

class TestMomentumScorerBasics:

    def test_insufficient_data_returns_zero(self):
        scorer = MomentumScorer()
        result = scorer.score(book_id=1, snapshots=[Snap(date=_day(0), amazon_best_seller_rank=50_000)])
        assert result.momentum_score == 0.0
        assert "Insufficient" in result.explanation

    def test_returns_momentum_result_type(self):
        scorer = MomentumScorer()
        snaps = _snaps_improving()
        result = scorer.score(book_id=1, snapshots=snaps, score_date=_day(7))
        assert isinstance(result, MomentumResult)

    def test_score_in_valid_range(self):
        scorer = MomentumScorer()
        for snaps in [_snaps_improving(), _snaps_flat()]:
            result = scorer.score(book_id=1, snapshots=snaps, score_date=_day(7))
            assert 0.0 <= result.momentum_score <= 100.0

    def test_improving_book_scores_higher_than_flat(self):
        scorer = MomentumScorer()
        improving = scorer.score(book_id=1, snapshots=_snaps_improving(), score_date=_day(7))
        flat = scorer.score(book_id=2, snapshots=_snaps_flat(), score_date=_day(7))
        assert improving.momentum_score > flat.momentum_score

    def test_book_id_preserved_in_result(self):
        scorer = MomentumScorer()
        result = scorer.score(book_id=42, snapshots=_snaps_improving(), score_date=_day(7))
        assert result.book_id == 42

    def test_score_date_preserved(self):
        scorer = MomentumScorer()
        result = scorer.score(book_id=1, snapshots=_snaps_improving(), score_date=_day(7))
        assert result.score_date == _day(7)

    def test_snapshots_used_count(self):
        scorer = MomentumScorer()
        snaps = _snaps_improving(days=7)
        result = scorer.score(book_id=1, snapshots=snaps, score_date=_day(7))
        assert result.snapshots_used == len(snaps)


# ---------------------------------------------------------------------------
# Component tests
# ---------------------------------------------------------------------------

class TestRankVelocity:

    def test_improving_rank_gives_positive_velocity(self):
        scorer = MomentumScorer()
        snaps = _snaps_improving(start_rank=200_000, end_rank=10_000, days=7)
        result = scorer.score(book_id=1, snapshots=snaps, score_date=_day(7))
        assert result.components.rank_velocity > 30

    def test_flat_rank_gives_low_velocity(self):
        scorer = MomentumScorer()
        snaps = _snaps_flat(rank=50_000)
        result = scorer.score(book_id=1, snapshots=snaps, score_date=_day(7))
        assert result.components.rank_velocity < 10

    def test_dramatic_improvement_approaches_100(self):
        scorer = MomentumScorer()
        # Rank improves 100x in 7 days — exceptional
        snaps = _snaps_improving(start_rank=500_000, end_rank=1_000, days=7)
        result = scorer.score(book_id=1, snapshots=snaps, score_date=_day(7))
        assert result.components.rank_velocity > 70

    def test_none_ranks_give_zero_velocity(self):
        scorer = MomentumScorer()
        snaps = [Snap(date=_day(i), review_count=10) for i in range(7)]
        result = scorer.score(book_id=1, snapshots=snaps, score_date=_day(6))
        assert result.components.rank_velocity == 0.0


class TestRankAcceleration:

    def test_acceleration_detected(self):
        """Rank improves slowly then sharply — should show acceleration."""
        scorer = MomentumScorer()
        # First 4 days: modest improvement; last 4 days: dramatic
        early = [Snap(date=_day(i), amazon_best_seller_rank=200_000 - i * 1_000,
                      review_count=10, star_rating=4.0) for i in range(4)]
        late  = [Snap(date=_day(4 + i), amazon_best_seller_rank=196_000 - i * 20_000,
                      review_count=10, star_rating=4.0) for i in range(4)]
        snaps = early + late
        result = scorer.score(book_id=1, snapshots=snaps, score_date=_day(7))
        assert result.components.rank_acceleration > 50

    def test_deceleration_gives_low_acceleration(self):
        """Rank improves fast then slows — acceleration should be low/zero."""
        scorer = MomentumScorer()
        early = [Snap(date=_day(i), amazon_best_seller_rank=100_000 - i * 20_000,
                      review_count=10, star_rating=4.0) for i in range(4)]
        late  = [Snap(date=_day(4 + i), amazon_best_seller_rank=20_000 - i * 500,
                      review_count=10, star_rating=4.0) for i in range(4)]
        snaps = early + late
        result = scorer.score(book_id=1, snapshots=snaps, score_date=_day(7))
        assert result.components.rank_acceleration < 30

    def test_too_few_snaps_gives_zero_acceleration(self):
        scorer = MomentumScorer()
        snaps = _snaps_improving(days=2)
        result = scorer.score(book_id=1, snapshots=snaps, score_date=_day(2))
        assert result.components.rank_acceleration == 0.0


class TestReviewVelocity:

    def test_high_review_growth_scores_high(self):
        scorer = MomentumScorer()
        # 140 new reviews in 7 days = 20/day → should be near 100
        snaps = _snaps_improving(start_reviews=10, end_reviews=150, days=7)
        result = scorer.score(book_id=1, snapshots=snaps, score_date=_day(7))
        assert result.components.review_velocity > 70

    def test_no_review_growth_scores_zero(self):
        scorer = MomentumScorer()
        snaps = [Snap(date=_day(i), amazon_best_seller_rank=50_000,
                      review_count=100, star_rating=4.0) for i in range(8)]
        result = scorer.score(book_id=1, snapshots=snaps, score_date=_day(7))
        assert result.components.review_velocity == 0.0

    def test_missing_review_count_gives_zero(self):
        scorer = MomentumScorer()
        snaps = [Snap(date=_day(i), amazon_best_seller_rank=50_000) for i in range(8)]
        result = scorer.score(book_id=1, snapshots=snaps, score_date=_day(7))
        assert result.components.review_velocity == 0.0


class TestRatingStability:

    def test_high_rating_many_reviews_scores_well(self):
        scorer = MomentumScorer()
        snaps = [Snap(date=_day(i), amazon_best_seller_rank=50_000,
                      review_count=500, star_rating=4.7) for i in range(8)]
        result = scorer.score(book_id=1, snapshots=snaps, score_date=_day(7))
        assert result.components.rating_stability > 40

    def test_below_threshold_rating_scores_zero(self):
        scorer = MomentumScorer()
        snaps = [Snap(date=_day(i), amazon_best_seller_rank=50_000,
                      review_count=200, star_rating=3.8) for i in range(8)]
        result = scorer.score(book_id=1, snapshots=snaps, score_date=_day(7))
        assert result.components.rating_stability == 0.0

    def test_high_rating_few_reviews_moderate_score(self):
        scorer = MomentumScorer()
        snaps = [Snap(date=_day(i), amazon_best_seller_rank=50_000,
                      review_count=5, star_rating=5.0) for i in range(8)]
        result = scorer.score(book_id=1, snapshots=snaps, score_date=_day(7))
        # Should score but not max — low review count reduces confidence
        assert 0 < result.components.rating_stability < 60


class TestAgeFactor:

    def test_new_book_gets_age_bonus(self):
        scorer = MomentumScorer()
        snaps = _snaps_improving()
        result = scorer.score(book_id=1, snapshots=snaps, score_date=_day(7), book_age_days=30)
        assert result.components.age_factor > 60

    def test_old_book_gets_no_age_bonus(self):
        scorer = MomentumScorer()
        snaps = _snaps_improving()
        result = scorer.score(book_id=1, snapshots=snaps, score_date=_day(7), book_age_days=365)
        assert result.components.age_factor == 0.0

    def test_unknown_age_gets_default(self):
        scorer = MomentumScorer()
        snaps = _snaps_improving()
        result = scorer.score(book_id=1, snapshots=snaps, score_date=_day(7), book_age_days=None)
        assert result.components.age_factor == 30.0

    def test_just_published_near_100(self):
        scorer = MomentumScorer()
        snaps = _snaps_improving()
        result = scorer.score(book_id=1, snapshots=snaps, score_date=_day(7), book_age_days=1)
        assert result.components.age_factor > 95


class TestKindleUnlimited:

    def test_ku_true_gives_100(self):
        scorer = MomentumScorer()
        snaps = _snaps_improving()
        result = scorer.score(book_id=1, snapshots=snaps, score_date=_day(7), kindle_unlimited=True)
        assert result.components.kindle_unlimited == 100.0

    def test_ku_false_gives_zero(self):
        scorer = MomentumScorer()
        snaps = _snaps_improving()
        result = scorer.score(book_id=1, snapshots=snaps, score_date=_day(7), kindle_unlimited=False)
        assert result.components.kindle_unlimited == 0.0


# ---------------------------------------------------------------------------
# Alert tests
# ---------------------------------------------------------------------------

class TestAlerts:

    def test_high_score_triggers_alert(self):
        config = ScoringConfig(alert_momentum_threshold=40.0)  # low threshold for test
        scorer = MomentumScorer(config)
        snaps = _snaps_improving(start_rank=500_000, end_rank=5_000, days=7,
                                  start_reviews=5, end_reviews=100)
        result = scorer.score(book_id=1, snapshots=snaps, score_date=_day(7),
                              book_age_days=30, kindle_unlimited=True)
        assert result.alert_triggered is True
        assert len(result.alert_reasons) > 0

    def test_low_score_no_alert(self):
        scorer = MomentumScorer()
        snaps = _snaps_flat()
        result = scorer.score(book_id=1, snapshots=snaps, score_date=_day(7))
        assert result.alert_triggered is False

    def test_rank_improvement_alert(self):
        config = ScoringConfig(alert_rank_improvement_threshold=5_000)
        scorer = MomentumScorer(config)
        snaps = _snaps_improving(start_rank=100_000, end_rank=10_000, days=7)
        result = scorer.score(book_id=1, snapshots=snaps, score_date=_day(7))
        assert result.alert_triggered is True
        assert any("rank improved" in r.lower() for r in result.alert_reasons)

    def test_review_spike_alert(self):
        config = ScoringConfig(alert_review_spike_threshold=10)
        scorer = MomentumScorer(config)
        snaps = _snaps_improving(start_reviews=5, end_reviews=100, days=7)
        result = scorer.score(book_id=1, snapshots=snaps, score_date=_day(7))
        assert result.alert_triggered is True
        assert any("review" in r.lower() for r in result.alert_reasons)


# ---------------------------------------------------------------------------
# Explanation tests
# ---------------------------------------------------------------------------

class TestExplanation:

    def test_explanation_non_empty(self):
        scorer = MomentumScorer()
        result = scorer.score(book_id=1, snapshots=_snaps_improving(), score_date=_day(7))
        assert len(result.explanation) > 20

    def test_explanation_mentions_rank(self):
        scorer = MomentumScorer()
        snaps = _snaps_improving(start_rank=200_000, end_rank=50_000)
        result = scorer.score(book_id=1, snapshots=snaps, score_date=_day(7))
        assert "rank" in result.explanation.lower() or "positions" in result.explanation.lower()

    def test_explanation_mentions_reviews(self):
        scorer = MomentumScorer()
        snaps = _snaps_improving(start_reviews=10, end_reviews=80)
        result = scorer.score(book_id=1, snapshots=snaps, score_date=_day(7))
        assert "review" in result.explanation.lower()

    def test_insufficient_data_explanation_clear(self):
        scorer = MomentumScorer()
        result = scorer.score(book_id=1, snapshots=[Snap(date=_day(0))])
        assert "Insufficient" in result.explanation


# ---------------------------------------------------------------------------
# Config override tests
# ---------------------------------------------------------------------------

class TestScoringConfig:

    def test_custom_weights_affect_score(self):
        """Doubling rank_velocity weight should make improving-rank books score higher."""
        config_high = ScoringConfig(weight_rank_velocity=10.0)
        config_low  = ScoringConfig(weight_rank_velocity=0.1)
        snaps = _snaps_improving(start_rank=200_000, end_rank=10_000)

        high = MomentumScorer(config_high).score(1, snaps, score_date=_day(7))
        low  = MomentumScorer(config_low).score(1, snaps, score_date=_day(7))
        assert high.momentum_score > low.momentum_score

    def test_min_snapshots_respected(self):
        config = ScoringConfig(min_snapshots_required=5)
        scorer = MomentumScorer(config)
        snaps = _snaps_improving(days=3)  # only 4 snapshots
        result = scorer.score(1, snaps, score_date=_day(3))
        assert result.momentum_score == 0.0
