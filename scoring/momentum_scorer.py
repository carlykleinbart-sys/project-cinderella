"""
MomentumScorer — the core scoring engine for Project Cinderella.

Design philosophy
-----------------
We measure *acceleration*, not absolute popularity.

A book ranked #500,000 that improved to #50,000 in seven days is far more
interesting than a book that has sat at #1,000 for six months.

All component scores are normalised to 0–100 before weighting so that no
single signal dominates by virtue of its raw scale.

Score components
----------------
1. rank_velocity       — How fast is BSR improving? (log-scale, 7d window)
2. rank_acceleration   — Is improvement speeding up? (recent 3d vs prior 4d)
3. review_velocity     — New reviews per day over the lookback window
4. review_acceleration — Is review growth itself accelerating?
5. rating_stability    — High rating maintained under growing review volume
6. sales_growth        — % change in estimated daily sales (7d)
7. age_factor          — Boost for books < 180 days old (harder to discover)
8. kindle_unlimited    — KU participation bonus

Final score = weighted_sum(components) / sum(weights), clamped to [0, 100]
"""
from __future__ import annotations

import math
from datetime import date, timedelta
from typing import Optional

from loguru import logger

from scoring.score_config import ScoringConfig, default_config
from scoring.score_models import MomentumResult, ScoreComponents


# ---------------------------------------------------------------------------
# Type alias for the minimal snapshot shape the scorer needs
# (avoids importing the ORM model so this module stays testable in isolation)
# ---------------------------------------------------------------------------
class SnapshotLike:
    """Protocol-style duck-typed snapshot."""
    date: date
    amazon_best_seller_rank: Optional[int]
    estimated_daily_sales: Optional[int]
    review_count: Optional[int]
    star_rating: Optional[float]


class MomentumScorer:
    """
    Compute a momentum score for a book from its historical metric snapshots.

    Usage
    -----
        scorer = MomentumScorer()
        result = scorer.score(book_id=42, snapshots=daily_metrics_rows, book_age_days=90)
    """

    def __init__(self, config: Optional[ScoringConfig] = None) -> None:
        self._cfg = config or default_config

    # ── Public API ────────────────────────────────────────────────────────────

    def score(
        self,
        book_id: int,
        snapshots: list,
        score_date: Optional[date] = None,
        book_age_days: Optional[int] = None,
        kindle_unlimited: bool = False,
        social_aggregator=None,
    ) -> MomentumResult:
        """
        Compute a :class:`MomentumResult` for one book.

        Parameters
        ----------
        book_id:
            DB primary key of the book being scored.
        snapshots:
            ``DailyMetrics`` rows (or any objects with the same attributes),
            ordered by date ascending.  At least
            ``config.min_snapshots_required`` rows are needed for a score;
            fewer returns a near-zero result.
        score_date:
            The date this score represents.  Defaults to today.
        book_age_days:
            Age of the book in days from publication date to today.
            ``None`` means unknown.
        kindle_unlimited:
            Whether the book participates in Kindle Unlimited.
        social_aggregator:
            Optional :class:`~scoring.social_aggregator.SocialSignalAggregator`
            instance.  When provided, BookTok, Reddit, and Goodreads Want-to-Read
            signals are included in the composite score.  When ``None``, those
            three components default to 0 (backward-compatible).
        """
        score_date = score_date or date.today()

        # Filter to the velocity window
        window_start = score_date - timedelta(days=self._cfg.velocity_window_days)
        window_snaps = [s for s in snapshots if s.date >= window_start]
        all_snaps_sorted = sorted(snapshots, key=lambda s: s.date)

        if len(all_snaps_sorted) < self._cfg.min_snapshots_required:
            return self._insufficient_data_result(book_id, score_date, len(all_snaps_sorted))

        # ── Compute components ────────────────────────────────────────────────
        c = ScoreComponents()
        c.rank_velocity     = self._rank_velocity(all_snaps_sorted)
        c.rank_acceleration = self._rank_acceleration(all_snaps_sorted)
        c.review_velocity   = self._review_velocity(all_snaps_sorted)
        c.review_acceleration = self._review_acceleration(all_snaps_sorted)
        c.rating_stability  = self._rating_stability(all_snaps_sorted)
        c.sales_growth      = self._sales_growth(all_snaps_sorted)
        c.age_factor        = self._age_factor(book_age_days)
        c.kindle_unlimited  = 100.0 if kindle_unlimited else 0.0

        # ── Social signals (optional — injected aggregator) ───────────────────
        if social_aggregator is not None:
            c.booktok_velocity        = social_aggregator.score_booktok(book_id, score_date)
            c.reddit_buzz             = social_aggregator.score_reddit(book_id, score_date)
            c.goodreads_want_to_read  = social_aggregator.score_goodreads_wtr(book_id, score_date)

        # ── Weighted composite ────────────────────────────────────────────────
        cfg = self._cfg
        weights = {
            "rank_velocity":         cfg.weight_rank_velocity,
            "rank_acceleration":     cfg.weight_rank_acceleration,
            "review_velocity":       cfg.weight_review_velocity,
            "review_acceleration":   cfg.weight_review_acceleration,
            "rating_stability":      cfg.weight_rating_stability,
            "sales_growth":          cfg.weight_sales_growth,
            "age_factor":            cfg.weight_age_factor,
            "kindle_unlimited":      cfg.weight_kindle_unlimited,
            "booktok_velocity":      cfg.weight_booktok_velocity,
            "reddit_buzz":           cfg.weight_reddit_buzz,
            "goodreads_want_to_read":cfg.weight_goodreads_want_to_read,
        }
        # Zero-weight components when social aggregator is absent (backward compat)
        if social_aggregator is None:
            weights["booktok_velocity"]       = 0.0
            weights["reddit_buzz"]            = 0.0
            weights["goodreads_want_to_read"] = 0.0
        total_weight = sum(weights.values())
        raw_score = sum(getattr(c, k) * w for k, w in weights.items())
        momentum_score = min(100.0, max(0.0, raw_score / total_weight))

        # ── Explanation ───────────────────────────────────────────────────────
        explanation = self._build_explanation(
            c, momentum_score, all_snaps_sorted, book_age_days, kindle_unlimited
        )

        # ── Alert detection ───────────────────────────────────────────────────
        alert_triggered, alert_reasons = self._check_alerts(
            momentum_score, c, all_snaps_sorted
        )

        logger.debug(
            "book_id={} score={:.1f} rank_v={:.0f} rev_v={:.0f} alerts={}",
            book_id, momentum_score, c.rank_velocity, c.review_velocity, alert_triggered
        )

        return MomentumResult(
            book_id=book_id,
            score_date=score_date,
            momentum_score=round(momentum_score, 2),
            components=c,
            explanation=explanation,
            snapshots_used=len(all_snaps_sorted),
            alert_triggered=alert_triggered,
            alert_reasons=alert_reasons,
        )

    # ── Component calculators ─────────────────────────────────────────────────

    def _rank_velocity(self, snaps: list) -> float:
        """
        Log-scale rate of Amazon rank improvement.

        Uses a log ratio so that improving from #100k → #50k (a 2× gain) and
        from #10k → #5k score equally — both represent the same proportional
        visibility increase.
        """
        earliest = self._first_valid_rank(snaps)
        latest   = self._last_valid_rank(snaps)
        if earliest is None or latest is None or earliest <= 0 or latest <= 0:
            return 0.0

        days = max(1, (snaps[-1].date - snaps[0].date).days)
        # log(baseline/recent): positive = rank improved (number went down)
        log_improvement = math.log(earliest / latest)
        daily_log_rate = log_improvement / days

        # Calibration: log(2)/7d ≈ 0.099/d = 60 pts (rank halved in a week)
        # log(10)/7d ≈ 0.329/d = 100 pts (rank improved 10× in a week)
        score = daily_log_rate * 300
        return min(100.0, max(0.0, score))

    def _rank_acceleration(self, snaps: list) -> float:
        """
        Is rank improvement speeding up in the recent vs prior period?

        Splits snapshots at the midpoint and compares log-rate in each half.
        A book accelerating into a breakout will show faster improvement
        in the second half than the first.
        """
        if len(snaps) < 4:
            return 0.0

        mid = len(snaps) // 2
        earlier = snaps[:mid]
        recent  = snaps[mid:]

        def _half_velocity(half: list) -> float:
            e = self._first_valid_rank(half)
            l = self._last_valid_rank(half)
            if not e or not l or e <= 0 or l <= 0:
                return 0.0
            days = max(1, (half[-1].date - half[0].date).days)
            return math.log(e / l) / days

        early_rate  = _half_velocity(earlier)
        recent_rate = _half_velocity(recent)

        if early_rate <= 0:
            # No improvement in early window — check if recent is positive
            return min(100.0, max(0.0, recent_rate * 200)) if recent_rate > 0 else 0.0

        # Acceleration ratio: how much faster is recent vs early?
        acceleration = recent_rate / early_rate
        # 1.0 = same pace, 2.0 = twice as fast, 0.5 = slowing down
        score = (acceleration - 1.0) * 50.0  # 2× faster → 50 pts, 3× → 100
        return min(100.0, max(0.0, score))

    def _review_velocity(self, snaps: list) -> float:
        """New reviews per day over the window."""
        earliest_count = self._first_valid_review_count(snaps)
        latest_count   = self._last_valid_review_count(snaps)
        if earliest_count is None or latest_count is None:
            return 0.0

        days = max(1, (snaps[-1].date - snaps[0].date).days)
        new_reviews = max(0, latest_count - earliest_count)
        daily_rate = new_reviews / days

        # Calibration: 5 reviews/day = 50 pts, 20/day = 100 pts
        score = daily_rate * 10.0
        return min(100.0, max(0.0, score))

    def _review_acceleration(self, snaps: list) -> float:
        """Is the rate of new reviews itself growing?"""
        if len(snaps) < 4:
            return 0.0

        mid = len(snaps) // 2
        earlier = snaps[:mid]
        recent  = snaps[mid:]

        def _review_rate(half: list) -> float:
            e = self._first_valid_review_count(half)
            l = self._last_valid_review_count(half)
            if e is None or l is None:
                return 0.0
            days = max(1, (half[-1].date - half[0].date).days)
            return max(0.0, (l - e) / days)

        early_rate  = _review_rate(earlier)
        recent_rate = _review_rate(recent)

        if early_rate <= 0:
            return min(100.0, recent_rate * 15) if recent_rate > 0 else 0.0

        acceleration = recent_rate / early_rate
        score = (acceleration - 1.0) * 50.0
        return min(100.0, max(0.0, score))

    def _rating_stability(self, snaps: list) -> float:
        """
        High rating maintained under increasing review pressure.

        A book that holds ≥4.2 stars while accumulating hundreds of reviews
        is a strong quality signal.
        """
        latest = snaps[-1]
        rating = latest.star_rating
        reviews = latest.review_count or 0

        if rating is None:
            return 0.0

        # Base: rating above threshold
        if rating < self._cfg.min_rating_for_stability_bonus:
            return 0.0

        # Score: rating × review volume weight
        # 4.0 stars with 10 reviews = low confidence; 4.5 stars with 500 = high
        review_weight = min(1.0, reviews / 200.0)  # caps out at 200 reviews
        rating_score  = (rating - 4.0) / 1.0       # 4.0→0, 5.0→1.0
        score = (0.4 + review_weight * 0.6) * rating_score * 100
        return min(100.0, max(0.0, score))

    def _sales_growth(self, snaps: list) -> float:
        """Percentage growth in estimated daily sales over the window."""
        earliest = self._first_valid_sales(snaps)
        latest   = self._last_valid_sales(snaps)

        if earliest is None or latest is None or earliest <= 0:
            return 0.0

        pct_growth = (latest - earliest) / earliest  # 0.5 = 50% growth
        # Calibration: 50% growth over window = 50 pts, 100% = 100 pts
        score = pct_growth * 100.0
        return min(100.0, max(0.0, score))

    def _age_factor(self, book_age_days: Optional[int]) -> float:
        """
        Discovery boost for recently published books.

        Newer books are harder to discover, so breakout momentum there is a
        stronger signal.  Books older than the threshold get no bonus.
        """
        if book_age_days is None:
            return 30.0  # unknown age: moderate default

        threshold = self._cfg.new_book_age_days
        if book_age_days >= threshold:
            return 0.0
        # Linear from 100 (just published) to 0 (at threshold)
        return max(0.0, (1.0 - book_age_days / threshold) * 100.0)

    # ── Explanation builder ───────────────────────────────────────────────────

    def _build_explanation(
        self,
        c: ScoreComponents,
        score: float,
        snaps: list,
        book_age_days: Optional[int],
        kindle_unlimited: bool,
    ) -> str:
        """Build a human-readable explanation of the momentum score."""
        parts: list[str] = []

        # Rank movement
        earliest_rank = self._first_valid_rank(snaps)
        latest_rank   = self._last_valid_rank(snaps)
        days = max(1, (snaps[-1].date - snaps[0].date).days)

        if earliest_rank and latest_rank:
            rank_change = earliest_rank - latest_rank
            if rank_change > 0:
                parts.append(
                    f"Amazon rank improved by {rank_change:,} positions "
                    f"over {days} days (#{earliest_rank:,} → #{latest_rank:,})"
                )
            elif rank_change < 0:
                parts.append(
                    f"Amazon rank declined {abs(rank_change):,} positions "
                    f"over {days} days"
                )

        # Review growth
        earliest_reviews = self._first_valid_review_count(snaps)
        latest_reviews   = self._last_valid_review_count(snaps)
        if earliest_reviews is not None and latest_reviews is not None:
            new_reviews = latest_reviews - earliest_reviews
            if new_reviews > 0:
                parts.append(f"gained {new_reviews} new reviews in {days} days")

        # Rating
        if snaps[-1].star_rating and snaps[-1].star_rating >= 4.0:
            parts.append(
                f"maintaining a {snaps[-1].star_rating:.1f}★ rating "
                f"({snaps[-1].review_count or 0:,} total reviews)"
            )

        # Acceleration signals
        if c.rank_acceleration > 60:
            parts.append("rank improvement is accelerating")
        if c.review_acceleration > 60:
            parts.append("review growth is accelerating")

        # Age
        if book_age_days is not None and book_age_days < self._cfg.new_book_age_days:
            parts.append(f"book is {book_age_days} days old (discovery bonus applied)")

        # KU
        if kindle_unlimited:
            parts.append("participates in Kindle Unlimited")

        # Social signals
        if c.booktok_velocity > 40:
            parts.append(f"strong BookTok activity (score {c.booktok_velocity:.0f}/100)")
        if c.reddit_buzz > 40:
            parts.append(f"Reddit buzz detected (score {c.reddit_buzz:.0f}/100)")
        if c.goodreads_want_to_read > 40:
            parts.append(
                f"elevated Goodreads Want-to-Read momentum (score {c.goodreads_want_to_read:.0f}/100)"
            )

        if not parts:
            return f"Momentum score: {score:.0f}/100 (insufficient signal to explain)."

        summary = "; ".join(parts[:6])  # cap at 4 clauses
        return f"This book {summary}. Momentum score: {score:.0f}/100."

    # ── Alert detection ───────────────────────────────────────────────────────

    def _check_alerts(
        self,
        score: float,
        c: ScoreComponents,
        snaps: list,
    ) -> tuple[bool, list[str]]:
        reasons: list[str] = []
        cfg = self._cfg

        if score >= cfg.alert_momentum_threshold:
            reasons.append(
                f"Momentum score {score:.1f} exceeds threshold {cfg.alert_momentum_threshold}"
            )

        # Rank improvement in positions (raw)
        earliest_rank = self._first_valid_rank(snaps)
        latest_rank   = self._last_valid_rank(snaps)
        if earliest_rank and latest_rank:
            rank_change = earliest_rank - latest_rank
            if rank_change >= cfg.alert_rank_improvement_threshold:
                reasons.append(
                    f"Amazon rank improved {rank_change:,} positions "
                    f"(threshold: {cfg.alert_rank_improvement_threshold:,})"
                )

        # Review spike
        earliest_reviews = self._first_valid_review_count(snaps)
        latest_reviews   = self._last_valid_review_count(snaps)
        if earliest_reviews is not None and latest_reviews is not None:
            new_reviews = latest_reviews - earliest_reviews
            if new_reviews >= cfg.alert_review_spike_threshold:
                reasons.append(
                    f"{new_reviews} new reviews in the lookback window "
                    f"(threshold: {cfg.alert_review_spike_threshold})"
                )

        return bool(reasons), reasons

    # ── Fallback ──────────────────────────────────────────────────────────────

    def _insufficient_data_result(
        self, book_id: int, score_date: date, n_snaps: int
    ) -> MomentumResult:
        return MomentumResult(
            book_id=book_id,
            score_date=score_date,
            momentum_score=0.0,
            components=ScoreComponents(),
            explanation=(
                f"Insufficient data to score: only {n_snaps} snapshot(s) available. "
                f"At least {self._cfg.min_snapshots_required} required."
            ),
            snapshots_used=n_snaps,
            alert_triggered=False,
            alert_reasons=[],
        )

    # ── Helpers ───────────────────────────────────────────────────────────────

    @staticmethod
    def _first_valid_rank(snaps: list) -> Optional[int]:
        for s in snaps:
            if s.amazon_best_seller_rank:
                return s.amazon_best_seller_rank
        return None

    @staticmethod
    def _last_valid_rank(snaps: list) -> Optional[int]:
        for s in reversed(snaps):
            if s.amazon_best_seller_rank:
                return s.amazon_best_seller_rank
        return None

    @staticmethod
    def _first_valid_review_count(snaps: list) -> Optional[int]:
        for s in snaps:
            if s.review_count is not None:
                return s.review_count
        return None

    @staticmethod
    def _last_valid_review_count(snaps: list) -> Optional[int]:
        for s in reversed(snaps):
            if s.review_count is not None:
                return s.review_count
        return None

    @staticmethod
    def _first_valid_sales(snaps: list) -> Optional[int]:
        for s in snaps:
            if s.estimated_daily_sales is not None:
                return s.estimated_daily_sales
        return None

    @staticmethod
    def _last_valid_sales(snaps: list) -> Optional[int]:
        for s in reversed(snaps):
            if s.estimated_daily_sales is not None:
                return s.estimated_daily_sales
        return None
