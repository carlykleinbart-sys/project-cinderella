"""
Book-related API routes.

GET /api/books              — paginated list of tracked indie books
GET /api/books/{asin}       — full detail + metric history for one book
GET /api/leaderboard        — top 25 by today's momentum score
GET /api/social/{book_id}   — BookTok + Reddit mentions for one book
"""
from __future__ import annotations

from datetime import date, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import desc, func, select
from sqlalchemy.orm import Session

from api.deps import get_db
from api.schemas import (
    BookDetail,
    BookSummary,
    DailyMetricsSchema,
    LeaderboardEntry,
    LeaderboardResponse,
    MomentumScoreSchema,
    SocialSummary,
    BookTokMentionSchema,
    RedditMentionSchema,
)
from models import Book, DailyMetrics
from models.momentum_score import MomentumScore
from models.social_signals import BookTokMention, RedditMention

router = APIRouter(prefix="/api", tags=["books"])


# ── Book list ─────────────────────────────────────────────────────────────────

@router.get("/books", response_model=list[BookSummary])
def list_books(
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    genre: Optional[str] = Query(None),
    db: Session = Depends(get_db),
):
    """List all tracked indie books, newest first."""
    q = select(Book).where(Book.is_indie.is_(True)).order_by(desc(Book.first_seen))
    if genre:
        q = q.where(Book.genre.ilike(f"%{genre}%"))
    return db.scalars(q.offset(skip).limit(limit)).all()


# ── Book detail ───────────────────────────────────────────────────────────────

@router.get("/books/{asin}", response_model=BookDetail)
def get_book(asin: str, db: Session = Depends(get_db)):
    """Full detail for a single book, including metrics and score history."""
    book = db.scalars(select(Book).where(Book.asin == asin)).first()
    if not book:
        raise HTTPException(status_code=404, detail=f"Book {asin!r} not found")

    # Last 30 days of metrics
    cutoff = date.today() - timedelta(days=30)
    metrics_rows = db.scalars(
        select(DailyMetrics)
        .where(DailyMetrics.book_id == book.id, DailyMetrics.date >= cutoff)
        .order_by(DailyMetrics.date)
    ).all()

    # Last 30 days of scores
    score_rows = db.scalars(
        select(MomentumScore)
        .where(MomentumScore.book_id == book.id, MomentumScore.date >= cutoff)
        .order_by(MomentumScore.date)
    ).all()

    detail = BookDetail.model_validate(book)
    detail.latest_metrics = DailyMetricsSchema.model_validate(metrics_rows[-1]) if metrics_rows else None
    detail.metrics_history = [DailyMetricsSchema.model_validate(m) for m in metrics_rows]
    detail.score_history = [MomentumScoreSchema.model_validate(s) for s in score_rows]
    return detail


# ── Leaderboard ───────────────────────────────────────────────────────────────

@router.get("/leaderboard", response_model=LeaderboardResponse)
def leaderboard(
    limit: int = Query(25, ge=1, le=100),
    as_of: Optional[date] = Query(None, description="Score date (defaults to today)"),
    db: Session = Depends(get_db),
):
    """Top N books by momentum score for a given date."""
    score_date = as_of or date.today()

    # Fall back to most recent date if today has no scores yet
    latest_date = db.scalar(select(func.max(MomentumScore.date)))
    if not latest_date:
        return LeaderboardResponse(as_of=score_date, total_tracked=0, entries=[])
    if score_date > latest_date:
        score_date = latest_date

    scores = db.execute(
        select(MomentumScore, Book, DailyMetrics)
        .join(Book, MomentumScore.book_id == Book.id)
        .outerjoin(
            DailyMetrics,
            (DailyMetrics.book_id == Book.id) & (DailyMetrics.date == score_date),
        )
        .where(MomentumScore.date == score_date)
        .order_by(desc(MomentumScore.momentum_score))
        .limit(limit)
    ).all()

    total_tracked = db.scalar(select(func.count(Book.id)).where(Book.is_indie.is_(True))) or 0

    entries = []
    for rank, (score, book, metrics) in enumerate(scores, start=1):
        components = score.components or {}
        entries.append(
            LeaderboardEntry(
                rank=rank,
                book_id=book.id,
                asin=book.asin,
                title=book.title,
                author=book.author,
                genre=book.genre,
                momentum_score=score.momentum_score,
                alert_triggered=score.alert_triggered,
                amazon_best_seller_rank=metrics.amazon_best_seller_rank if metrics else None,
                estimated_daily_sales=metrics.estimated_daily_sales if metrics else None,
                review_count=metrics.review_count if metrics else None,
                star_rating=metrics.star_rating if metrics else None,
                goodreads_want_to_read=metrics.goodreads_want_to_read if metrics else None,
                booktok_velocity=components.get("booktok_velocity"),
                reddit_buzz=components.get("reddit_buzz"),
                explanation=score.explanation,
            )
        )

    return LeaderboardResponse(as_of=score_date, total_tracked=total_tracked, entries=entries)


# ── Social signals ────────────────────────────────────────────────────────────

@router.get("/social/{book_id}", response_model=SocialSummary)
def social_summary(
    book_id: int,
    window_days: int = Query(7, ge=1, le=30),
    db: Session = Depends(get_db),
):
    """BookTok + Reddit mentions for a book over the last N days."""
    book = db.get(Book, book_id)
    if not book:
        raise HTTPException(status_code=404, detail=f"Book {book_id} not found")

    cutoff = date.today() - timedelta(days=window_days)

    tiktok_rows = db.scalars(
        select(BookTokMention)
        .where(BookTokMention.book_id == book_id)
        .order_by(desc(BookTokMention.published_at))
        .limit(10)
    ).all()

    reddit_rows = db.scalars(
        select(RedditMention)
        .where(RedditMention.book_id == book_id)
        .order_by(desc(RedditMention.posted_at))
        .limit(10)
    ).all()

    total_views = sum(r.view_count or 0 for r in tiktok_rows)
    total_upvotes = sum(r.upvotes or 0 for r in reddit_rows)

    # Latest WTR
    wtr = db.scalar(
        select(DailyMetrics.goodreads_want_to_read)
        .where(
            DailyMetrics.book_id == book_id,
            DailyMetrics.goodreads_want_to_read.is_not(None),
        )
        .order_by(desc(DailyMetrics.date))
        .limit(1)
    )

    return SocialSummary(
        book_id=book_id,
        window_days=window_days,
        booktok_mentions=len(tiktok_rows),
        booktok_total_views=total_views,
        reddit_posts=len(reddit_rows),
        reddit_total_upvotes=total_upvotes,
        goodreads_want_to_read=wtr,
        recent_tiktok=[BookTokMentionSchema.model_validate(r) for r in tiktok_rows],
        recent_reddit=[RedditMentionSchema.model_validate(r) for r in reddit_rows],
    )
