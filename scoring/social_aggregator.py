"""
SocialSignalAggregator — queries social tables and returns normalised 0-100 scores.

Kept separate from MomentumScorer so the scoring logic remains unit-testable
without a live database; the aggregator is injected (or mocked) at call time.

Signal definitions
------------------
booktok_velocity
    New TikTok video mentions in the past N days, normalised.
    Cap: 10 new mentions/day = score 100.  Rationale: a book getting
    10+ new TikTok videos per day is already viral.

reddit_buzz
    Combined score across Reddit posts:
      buzz = sum(upvotes + comment_count * 3) for posts in last N days
    Normalised with cap 5000. Comment weight is 3× because comments
    signal engaged discussion, not just passive upvotes.

goodreads_want_to_read
    Absolute Want-to-Read count from the most recent DailyMetrics row.
    Normalised with a soft cap at 5000 (log scale).
    Rationale: Housemaid had ~3k WTR before it exploded; 5k is comfortably
    above that threshold.
"""
from __future__ import annotations

import math
from datetime import date, timedelta
from typing import Optional

from loguru import logger
from sqlalchemy import select, func

from database import get_session
from models import DailyMetrics
from models.social_signals import BookTokMention, RedditMention


class SocialSignalAggregator:
    """
    Queries social tables for a book and returns normalised 0-100 component scores.
    """

    # Normalisation caps — tune these as data accumulates
    BOOKTOK_CAP_DAILY = 10.0      # mentions/day for score=100
    REDDIT_BUZZ_CAP = 5_000.0     # combined upvotes+comments for score=100
    GR_WTR_CAP_LOG = math.log(5_001)  # log(5001) for log-scale normalisation

    def __init__(self, window_days: int = 7) -> None:
        self._window = window_days

    def score_booktok(self, book_id: int, as_of: date) -> float:
        """New TikTok mentions over the window, normalised 0–100."""
        cutoff = as_of - timedelta(days=self._window)
        with get_session() as session:
            count = session.scalar(
                select(func.count(BookTokMention.id)).where(
                    BookTokMention.book_id == book_id,
                    BookTokMention.collected_at >= cutoff,
                )
            ) or 0

        daily_rate = count / max(self._window, 1)
        score = min(100.0, (daily_rate / self.BOOKTOK_CAP_DAILY) * 100)
        logger.debug("  booktok_velocity: {} mentions → {:.1f}", count, score)
        return score

    def score_reddit(self, book_id: int, as_of: date) -> float:
        """Weighted Reddit activity over the window, normalised 0–100."""
        cutoff = as_of - timedelta(days=self._window)
        with get_session() as session:
            rows = session.execute(
                select(RedditMention.upvotes, RedditMention.comment_count).where(
                    RedditMention.book_id == book_id,
                    RedditMention.posted_at >= cutoff,
                )
            ).fetchall()

        buzz = sum(
            (r.upvotes or 0) + (r.comment_count or 0) * 3
            for r in rows
        )
        score = min(100.0, (buzz / self.REDDIT_BUZZ_CAP) * 100)
        logger.debug("  reddit_buzz: buzz={} → {:.1f}", buzz, score)
        return score

    def score_goodreads_wtr(self, book_id: int, as_of: date) -> float:
        """
        Want-to-Read count from the most recent DailyMetrics row, log-normalised.
        Log scale prevents massive bestsellers from dominating; we care about
        the signal, not the absolute count.
        """
        with get_session() as session:
            wtr = session.scalar(
                select(DailyMetrics.goodreads_want_to_read)
                .where(
                    DailyMetrics.book_id == book_id,
                    DailyMetrics.goodreads_want_to_read.is_not(None),
                )
                .order_by(DailyMetrics.date.desc())
                .limit(1)
            )

        if not wtr:
            return 0.0

        log_wtr = math.log(wtr + 1)
        score = min(100.0, (log_wtr / self.GR_WTR_CAP_LOG) * 100)
        logger.debug("  goodreads_wtr: wtr={} → {:.1f}", wtr, score)
        return score
