"""
Social signal models — BookTok, Reddit, Instagram mentions.

Each table is append-only.  Never update existing rows.
All timestamps are UTC.
"""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import (
    BigInteger,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from models.base import Base


# ---------------------------------------------------------------------------
# BookTok (TikTok)
# ---------------------------------------------------------------------------
class BookTokMention(Base):
    """
    A single TikTok video mentioning a tracked book.

    Rows are keyed by (book_id, tiktok_video_id) to ensure idempotency.
    """

    __tablename__ = "booktok_mentions"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    book_id: Mapped[int] = mapped_column(
        ForeignKey("books.id", ondelete="CASCADE"), nullable=False, index=True
    )

    # TikTok identifiers
    tiktok_video_id: Mapped[Optional[str]] = mapped_column(
        String(100), nullable=True, index=True, comment="TikTok unique video ID"
    )
    creator_username: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    creator_follower_count: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    # Engagement at time of collection
    view_count: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True)
    like_count: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True)
    comment_count: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    share_count: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    # Video metadata
    caption: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    hashtags: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    video_url: Mapped[Optional[str]] = mapped_column(String(1000), nullable=True)
    published_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    # When we collected this record
    collected_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    book: Mapped["Book"] = relationship(back_populates="booktok_mentions")  # noqa: F821

    __table_args__ = (
        Index("ix_booktok_book_date", "book_id", "collected_at"),
    )

    def __repr__(self) -> str:
        return f"<BookTokMention book_id={self.book_id} creator={self.creator_username!r}>"


# ---------------------------------------------------------------------------
# Reddit
# ---------------------------------------------------------------------------
class RedditMention(Base):
    """
    A Reddit post or comment that mentions a tracked book.
    """

    __tablename__ = "reddit_mentions"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    book_id: Mapped[int] = mapped_column(
        ForeignKey("books.id", ondelete="CASCADE"), nullable=False, index=True
    )

    reddit_post_id: Mapped[Optional[str]] = mapped_column(
        String(50), nullable=True, index=True
    )
    subreddit: Mapped[Optional[str]] = mapped_column(String(100), nullable=True, index=True)
    title: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    body: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    author: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)

    upvotes: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    downvotes: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    comment_count: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    is_comment: Mapped[bool] = mapped_column(
        default=False, nullable=False,
        comment="True if this row is a comment rather than a top-level post"
    )

    posted_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    collected_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    book: Mapped["Book"] = relationship(back_populates="reddit_mentions")  # noqa: F821

    __table_args__ = (
        Index("ix_reddit_book_subreddit", "book_id", "subreddit"),
    )

    def __repr__(self) -> str:
        return f"<RedditMention book_id={self.book_id} sub={self.subreddit!r}>"


# ---------------------------------------------------------------------------
# Instagram
# ---------------------------------------------------------------------------
class InstagramMention(Base):
    """
    An Instagram post mentioning a tracked book.
    """

    __tablename__ = "instagram_mentions"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    book_id: Mapped[int] = mapped_column(
        ForeignKey("books.id", ondelete="CASCADE"), nullable=False, index=True
    )

    instagram_post_id: Mapped[Optional[str]] = mapped_column(
        String(100), nullable=True, index=True
    )
    username: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)

    like_count: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    comment_count: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    caption: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    posted_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    collected_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    book: Mapped["Book"] = relationship(back_populates="instagram_mentions")  # noqa: F821

    def __repr__(self) -> str:
        return f"<InstagramMention book_id={self.book_id} user={self.username!r}>"
