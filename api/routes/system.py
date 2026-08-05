"""
System / health routes.

GET /health         — liveness probe
GET /api/stats      — high-level counts for the dashboard header
"""
from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from api.deps import get_db
from api.schemas import HealthResponse, SystemStats
from models import Book, DailyMetrics
from models.momentum_score import MomentumScore

router = APIRouter(tags=["system"])


@router.get("/health", response_model=HealthResponse)
def health(db: Session = Depends(get_db)):
    try:
        db.execute(select(func.count(Book.id)))
        db_ok = True
    except Exception:
        db_ok = False
    return HealthResponse(status="ok" if db_ok else "degraded", db_connected=db_ok)


@router.get("/api/stats", response_model=SystemStats)
def stats(db: Session = Depends(get_db)):
    today = date.today()

    total_books = db.scalar(select(func.count(Book.id)).where(Book.is_indie.is_(True))) or 0

    scored_today = db.scalar(
        select(func.count(MomentumScore.id)).where(MomentumScore.date == today)
    ) or 0

    alerts_today = db.scalar(
        select(func.count(MomentumScore.id)).where(
            MomentumScore.date == today,
            MomentumScore.alert_triggered.is_(True),
        )
    ) or 0

    last_collection = db.scalar(select(func.max(DailyMetrics.date)))
    last_score = db.scalar(select(func.max(MomentumScore.date)))

    return SystemStats(
        total_books_tracked=total_books,
        books_with_scores_today=scored_today,
        alerts_today=alerts_today,
        last_collection_date=last_collection,
        last_score_date=last_score,
    )
