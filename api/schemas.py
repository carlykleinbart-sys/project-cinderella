"""
Pydantic response schemas for the Project Cinderella API.

All schemas inherit from BaseModel with model_config = {"from_attributes": True}
so they can be constructed directly from SQLAlchemy ORM objects.
"""
from __future__ import annotations

from datetime import date, datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict


# ── Base ──────────────────────────────────────────────────────────────────────

class _Base(BaseModel):
    model_config = ConfigDict(from_attributes=True)


# ── Book schemas ──────────────────────────────────────────────────────────────

class BookSummary(_Base):
    """Lightweight book row used in lists and leaderboard."""
    id: int
    asin: str
    title: str
    author: Optional[str]
    publisher: Optional[str]
    genre: Optional[str]
    kindle_unlimited: bool
    first_seen: datetime
    goodreads_url: Optional[str]


class DailyMetricsSchema(_Base):
    date: date
    amazon_best_seller_rank: Optional[int]
    estimated_daily_sales: Optional[int]
    price: Optional[float]
    star_rating: Optional[float]
    review_count: Optional[int]
    goodreads_rating: Optional[float]
    goodreads_reviews: Optional[int]
    goodreads_want_to_read: Optional[int]


class MomentumScoreSchema(_Base):
    date: date
    momentum_score: float
    components: Optional[dict]
    explanation: Optional[str]
    alert_triggered: bool
    alert_reasons: Optional[list]


class BookDetail(_Base):
    """Full book object with latest metrics and score history."""
    id: int
    asin: str
    title: str
    author: Optional[str]
    publisher: Optional[str]
    genre: Optional[str]
    description: Optional[str]
    cover_url: Optional[str]
    kindle_unlimited: bool
    goodreads_url: Optional[str]
    first_seen: datetime
    # Injected by the endpoint (not ORM fields)
    latest_metrics: Optional[DailyMetricsSchema] = None
    score_history: list[MomentumScoreSchema] = []
    metrics_history: list[DailyMetricsSchema] = []


# ── Leaderboard schemas ───────────────────────────────────────────────────────

class LeaderboardEntry(_Base):
    """One row in the leaderboard — book + today's score + key metrics."""
    rank: int
    book_id: int
    asin: str
    title: str
    author: Optional[str]
    genre: Optional[str]
    momentum_score: float
    alert_triggered: bool
    amazon_best_seller_rank: Optional[int]
    estimated_daily_sales: Optional[int]
    review_count: Optional[int]
    star_rating: Optional[float]
    goodreads_want_to_read: Optional[int]
    booktok_velocity: Optional[float]
    reddit_buzz: Optional[float]
    explanation: Optional[str]


class LeaderboardResponse(BaseModel):
    as_of: date
    total_tracked: int
    entries: list[LeaderboardEntry]


# ── Social signal schemas ─────────────────────────────────────────────────────

class BookTokMentionSchema(_Base):
    id: int
    tiktok_video_id: Optional[str]
    creator_username: Optional[str]
    caption: Optional[str]
    view_count: Optional[int]
    like_count: Optional[int]
    comment_count: Optional[int]
    video_url: Optional[str]
    published_at: Optional[datetime]


class RedditMentionSchema(_Base):
    id: int
    reddit_post_id: Optional[str]
    subreddit: Optional[str]
    title: Optional[str]
    author: Optional[str]
    upvotes: Optional[int]
    comment_count: Optional[int]
    posted_at: Optional[datetime]


class SocialSummary(BaseModel):
    book_id: int
    window_days: int
    booktok_mentions: int
    booktok_total_views: int
    reddit_posts: int
    reddit_total_upvotes: int
    goodreads_want_to_read: Optional[int]
    recent_tiktok: list[BookTokMentionSchema]
    recent_reddit: list[RedditMentionSchema]


# ── Stats / health schemas ────────────────────────────────────────────────────

class SystemStats(BaseModel):
    total_books_tracked: int
    books_with_scores_today: int
    alerts_today: int
    last_collection_date: Optional[date]
    last_score_date: Optional[date]


class HealthResponse(BaseModel):
    status: str
    version: str = "1.0.0"
    db_connected: bool
