"""
Book model — the canonical record for each tracked title.

One row per ASIN.  All mutable fields are updated on re-scrape (title
corrections, publisher clarifications, etc.).  Historical performance data
lives in DailyMetrics, never here.
"""
from __future__ import annotations

import enum
from datetime import date, datetime
from typing import Any, Optional

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    Enum,
    Index,
    JSON,
    String,
    Text,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from models.base import Base


class BookFormat(str, enum.Enum):
    KINDLE = "Kindle"
    PAPERBACK = "Paperback"
    HARDCOVER = "Hardcover"
    AUDIOBOOK = "Audiobook"
    UNKNOWN = "Unknown"


class Book(Base):
    """Canonical book record keyed by Amazon ASIN."""

    __tablename__ = "books"

    # ── Primary key ───────────────────────────────────────────────────────────
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)

    # ── Identifiers ───────────────────────────────────────────────────────────
    asin: Mapped[str] = mapped_column(
        String(20),
        unique=True,
        nullable=False,
        index=True,
        comment="Amazon Standard Identification Number — primary external key",
    )
    isbn: Mapped[Optional[str]] = mapped_column(
        String(20),
        nullable=True,
        index=True,
        comment="ISBN-10 or ISBN-13 when available",
    )

    # ── Bibliographic ─────────────────────────────────────────────────────────
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    subtitle: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    author: Mapped[str] = mapped_column(String(200), nullable=False)
    publisher: Mapped[Optional[str]] = mapped_column(String(200), nullable=True, index=True)
    publication_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    format: Mapped[BookFormat] = mapped_column(
        Enum(BookFormat, native_enum=False, values_callable=lambda obj: [e.value for e in obj]),
        default=BookFormat.UNKNOWN,
        nullable=False,
    )
    kindle_unlimited: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        nullable=False,
        comment="True if the book participates in Kindle Unlimited",
    )
    language: Mapped[str] = mapped_column(String(10), default="en", nullable=False)

    # ── Classification ────────────────────────────────────────────────────────
    genre: Mapped[Optional[str]] = mapped_column(
        String(100),
        nullable=True,
        index=True,
        comment="Top-level genre (e.g. Romance, Fantasy)",
    )
    categories: Mapped[Optional[list[str]]] = mapped_column(
        JSON,
        nullable=True,
        comment="Full Amazon category breadcrumb list as JSON array",
    )

    # ── Indie flag ────────────────────────────────────────────────────────────
    is_indie: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        nullable=False,
        index=True,
        comment="True if publisher matches the IndiePublisher lookup table",
    )

    # ── Description ───────────────────────────────────────────────────────────
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    cover_url: Mapped[Optional[str]] = mapped_column(String(1000), nullable=True)

    # ── Goodreads ─────────────────────────────────────────────────────────────
    goodreads_id: Mapped[Optional[str]] = mapped_column(
        String(30), nullable=True, index=True,
        comment="Goodreads book ID (numeric string)",
    )
    goodreads_url: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)

    # ── Housekeeping ──────────────────────────────────────────────────────────
    first_seen: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
        comment="Timestamp when we first discovered this book",
    )
    last_updated: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    # ── Relationships ─────────────────────────────────────────────────────────
    daily_metrics: Mapped[list["DailyMetrics"]] = relationship(  # noqa: F821
        back_populates="book",
        cascade="all, delete-orphan",
        order_by="DailyMetrics.date",
    )
    booktok_mentions: Mapped[list["BookTokMention"]] = relationship(  # noqa: F821
        back_populates="book",
        cascade="all, delete-orphan",
    )
    reddit_mentions: Mapped[list["RedditMention"]] = relationship(  # noqa: F821
        back_populates="book",
        cascade="all, delete-orphan",
    )
    instagram_mentions: Mapped[list["InstagramMention"]] = relationship(  # noqa: F821
        back_populates="book",
        cascade="all, delete-orphan",
    )

    # ── Indices ───────────────────────────────────────────────────────────────
    __table_args__ = (
        Index("ix_books_author", "author"),
        Index("ix_books_is_indie_genre", "is_indie", "genre"),
    )

    def __repr__(self) -> str:
        return f"<Book asin={self.asin!r} title={self.title!r} author={self.author!r}>"

    def to_dict(self) -> dict[str, Any]:
        """Serialise to a plain dict (useful for reports/logging)."""
        return {
            "id": self.id,
            "asin": self.asin,
            "isbn": self.isbn,
            "title": self.title,
            "subtitle": self.subtitle,
            "author": self.author,
            "publisher": self.publisher,
            "publication_date": self.publication_date.isoformat() if self.publication_date else None,
            "format": self.format.value if self.format else None,
            "kindle_unlimited": self.kindle_unlimited,
            "genre": self.genre,
            "categories": self.categories,
            "language": self.language,
            "is_indie": self.is_indie,
            "first_seen": self.first_seen.isoformat(),
            "last_updated": self.last_updated.isoformat(),
        }
