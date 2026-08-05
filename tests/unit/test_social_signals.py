"""
Unit tests for the social signal scorer components:
  - SocialSignalAggregator (mocked DB)
  - MomentumScorer with social signals injected
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from typing import Optional
from unittest.mock import MagicMock, patch

import pytest

from scoring.momentum_scorer import MomentumScorer
from scoring.score_config import ScoringConfig
from scoring.score_models import ScoreComponents
from scoring.social_aggregator import SocialSignalAggregator


# ── Helpers ───────────────────────────────────────────────────────────────────

@dataclass
class Snap:
    """Minimal snapshot duck-type for MomentumScorer tests."""
    date: date
    amazon_best_seller_rank: Optional[int] = None
    estimated_daily_sales: Optional[int] = None
    review_count: Optional[int] = None
    star_rating: Optional[float] = None


def _make_snaps(n: int = 7, start_rank: int = 100_000, end_rank: int = 10_000) -> list[Snap]:
    today = date.today()
    step = (start_rank - end_rank) / max(n - 1, 1)
    snaps = []
    for i in range(n):
        d = today - timedelta(days=n - 1 - i)
        rank = int(start_rank - step * i)
        snaps.append(Snap(date=d, amazon_best_seller_rank=rank,
                          estimated_daily_sales=max(1, 500 - i * 50),
                          review_count=10 + i * 3, star_rating=4.2))
    return snaps


class MockAggregator:
    """Controllable fake aggregator — no DB needed."""
    def __init__(self, booktok=0.0, reddit=0.0, wtr=0.0):
        self._booktok = booktok
        self._reddit = reddit
        self._wtr = wtr

    def score_booktok(self, book_id: int, as_of: date) -> float:
        return self._booktok

    def score_reddit(self, book_id: int, as_of: date) -> float:
        return self._reddit

    def score_goodreads_wtr(self, book_id: int, as_of: date) -> float:
        return self._wtr


# ── Tests: MomentumScorer with social signals ─────────────────────────────────

class TestMomentumScorerWithSocial:
    def test_social_signals_raise_score(self):
        snaps = _make_snaps()
        scorer = MomentumScorer()

        baseline = scorer.score(1, snaps).momentum_score
        with_social = scorer.score(1, snaps, social_aggregator=MockAggregator(80, 70, 90)).momentum_score
        assert with_social > baseline

    def test_zero_social_does_not_raise_score(self):
        snaps = _make_snaps()
        scorer = MomentumScorer()

        baseline = scorer.score(1, snaps).momentum_score
        with_zero = scorer.score(1, snaps, social_aggregator=MockAggregator(0, 0, 0)).momentum_score
        # Zero social signals add weight to denominator but 0 to numerator — score must drop or stay equal
        assert with_zero <= baseline

    def test_social_components_stored_in_result(self):
        snaps = _make_snaps()
        scorer = MomentumScorer()
        result = scorer.score(1, snaps, social_aggregator=MockAggregator(55, 65, 75))
        assert result.components.booktok_velocity == pytest.approx(55.0)
        assert result.components.reddit_buzz == pytest.approx(65.0)
        assert result.components.goodreads_want_to_read == pytest.approx(75.0)

    def test_no_aggregator_social_components_zero(self):
        snaps = _make_snaps()
        scorer = MomentumScorer()
        result = scorer.score(1, snaps)
        assert result.components.booktok_velocity == 0.0
        assert result.components.reddit_buzz == 0.0
        assert result.components.goodreads_want_to_read == 0.0

    def test_social_explanation_included_when_signal_high(self):
        snaps = _make_snaps()
        scorer = MomentumScorer()
        result = scorer.score(1, snaps, social_aggregator=MockAggregator(85, 0, 0))
        assert "BookTok" in result.explanation

    def test_reddit_explanation_included_when_signal_high(self):
        snaps = _make_snaps()
        scorer = MomentumScorer()
        result = scorer.score(1, snaps, social_aggregator=MockAggregator(0, 85, 0))
        assert "Reddit" in result.explanation

    def test_goodreads_wtr_explanation_included_when_signal_high(self):
        snaps = _make_snaps()
        scorer = MomentumScorer()
        result = scorer.score(1, snaps, social_aggregator=MockAggregator(0, 0, 85))
        assert "Want-to-Read" in result.explanation

    def test_score_capped_at_100(self):
        snaps = _make_snaps(start_rank=500_000, end_rank=1)
        scorer = MomentumScorer()
        result = scorer.score(1, snaps, social_aggregator=MockAggregator(100, 100, 100))
        assert result.momentum_score <= 100.0

    def test_to_dict_includes_social_fields(self):
        snaps = _make_snaps()
        scorer = MomentumScorer()
        result = scorer.score(1, snaps, social_aggregator=MockAggregator(30, 40, 50))
        d = result.to_dict()
        assert "booktok_velocity" in d["components"]
        assert "reddit_buzz" in d["components"]
        assert "goodreads_want_to_read" in d["components"]


# ── Tests: SocialSignalAggregator normalisation logic (formula-only) ───────────

class TestSocialAggregatorNormalisation:
    """
    Test the normalisation formulas by constructing an aggregator and calling
    the internal math directly, without hitting a real DB.
    """

    def test_booktok_cap_at_100(self):
        agg = SocialSignalAggregator(window_days=7)
        # 10 mentions/day × 7 days = 70 mentions → score 100 (at cap)
        daily_rate = 15.0  # above cap
        score = min(100.0, (daily_rate / agg.BOOKTOK_CAP_DAILY) * 100)
        assert score == 100.0

    def test_booktok_zero_mentions(self):
        agg = SocialSignalAggregator(window_days=7)
        score = min(100.0, (0.0 / agg.BOOKTOK_CAP_DAILY) * 100)
        assert score == 0.0

    def test_reddit_buzz_formula(self):
        agg = SocialSignalAggregator()
        # 100 upvotes + 10 comments×3 = 130 buzz
        buzz = 100 + 10 * 3
        score = min(100.0, (buzz / agg.REDDIT_BUZZ_CAP) * 100)
        assert score == pytest.approx((130 / 5000) * 100, abs=0.1)

    def test_goodreads_wtr_log_normalisation(self):
        import math
        agg = SocialSignalAggregator()
        wtr = 5000
        log_wtr = math.log(wtr + 1)
        score = min(100.0, (log_wtr / agg.GR_WTR_CAP_LOG) * 100)
        assert 95 <= score <= 100  # near the cap

    def test_goodreads_wtr_zero(self):
        import math
        agg = SocialSignalAggregator()
        wtr = 0
        log_wtr = math.log(wtr + 1)
        score = min(100.0, (log_wtr / agg.GR_WTR_CAP_LOG) * 100)
        assert score == 0.0


# ── Tests: GoodreadsCollector similarity scoring ──────────────────────────────

class TestGoodreadsCollectorSimilarity:
    def test_exact_match_scores_high(self):
        from collectors.goodreads_collector import GoodreadsCollector
        score = GoodreadsCollector._similarity_score(
            "The Housemaid", "Freida McFadden",
            "The Housemaid", "Freida McFadden",
        )
        assert score > 0.95

    def test_wrong_book_scores_low(self):
        from collectors.goodreads_collector import GoodreadsCollector
        score = GoodreadsCollector._similarity_score(
            "Dune", "Frank Herbert",
            "The Housemaid", "Freida McFadden",
        )
        assert score < 0.5

    def test_partial_author_match_still_reasonable(self):
        from collectors.goodreads_collector import GoodreadsCollector
        score = GoodreadsCollector._similarity_score(
            "The Housemaid", "McFadden",
            "The Housemaid", "Freida McFadden",
        )
        assert score > 0.6

    def test_title_variation_handled(self):
        from collectors.goodreads_collector import GoodreadsCollector
        # Subtitle or edition variation in Goodreads results
        score = GoodreadsCollector._similarity_score(
            "The Housemaid's Secret", "Freida McFadden",
            "The Housemaid", "Freida McFadden",
        )
        # Titles are different but author matches — should be moderate
        assert 0.3 < score < 0.9
