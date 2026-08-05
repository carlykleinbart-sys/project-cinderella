"""
MomentumScore model — one row per (book_id, date), never overwritten.

Stores computed momentum scores historically so we can plot score
trajectories and detect when a book first entered breakout territory.
"""
from __future__ import annotations

from datetime import date
from typing import Any

from sqlalchemy import (
    Boolean,
    Date,
    Float,
    ForeignKey,
    Index,
    JSON,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from models.base import Base


class MomentumScore(Base):
    """Computed momentum score for a book on a given date."""

    __tablename__ = "momentum_scores"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    book_id: Mapped[int] = mapped_column(
        ForeignKey("books.id", ondelete="CASCADE"), nullable=False
    )
    date: Mapped[date] = mapped_column(Date, nullable=False)

    momentum_score: Mapped[float] = mapped_column(Float, nullable=False)
    components: Mapped[dict] = mapped_column(
        JSON, nullable=False, comment="ScoreComponents as JSON dict"
    )
    explanation: Mapped[str] = mapped_column(Text, nullable=False)
    snapshots_used: Mapped[int] = mapped_column(nullable=False, default=0)
    alert_triggered: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    alert_reasons: Mapped[list] = mapped_column(JSON, nullable=False, default=list)

    book: Mapped["Book"] = relationship()  # noqa: F821

    __table_args__ = (
        UniqueConstraint("book_id", "date", name="uq_momentum_score_book_date"),
        Index("ix_momentum_scores_date", "date"),
        Index("ix_momentum_scores_score", "momentum_score"),
    )

    def __repr__(self) -> str:
        return (
            f"<MomentumScore book_id={self.book_id} "
            f"date={self.date} score={self.momentum_score:.1f}>"
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "book_id": self.book_id,
            "date": self.date.isoformat(),
            "momentum_score": self.momentum_score,
            "components": self.components,
            "explanation": self.explanation,
            "snapshots_used": self.snapshots_used,
            "alert_triggered": self.alert_triggered,
            "alert_reasons": self.alert_reasons,
        }
