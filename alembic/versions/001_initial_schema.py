"""Initial schema — books, daily_metrics, social signals, indie_publishers

Revision ID: 001
Revises:
Create Date: 2026-08-03
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "001"
down_revision: str | None = None
branch_labels: str | tuple[str, ...] | None = None
depends_on: str | tuple[str, ...] | None = None


def upgrade() -> None:
    # ── indie_publishers ──────────────────────────────────────────────────────
    op.create_table(
        "indie_publishers",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("match_fragment", sa.String(200), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("name"),
        sa.UniqueConstraint("match_fragment"),
    )

    # ── books ─────────────────────────────────────────────────────────────────
    op.create_table(
        "books",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("asin", sa.String(20), nullable=False),
        sa.Column("isbn", sa.String(20), nullable=True),
        sa.Column("title", sa.String(500), nullable=False),
        sa.Column("subtitle", sa.String(500), nullable=True),
        sa.Column("author", sa.String(200), nullable=False),
        sa.Column("publisher", sa.String(200), nullable=True),
        sa.Column("publication_date", sa.Date(), nullable=True),
        sa.Column(
            "format",
            sa.Enum("Kindle", "Paperback", "Hardcover", "Audiobook", "Unknown", name="bookformat"),
            nullable=False,
            server_default="Unknown",
        ),
        sa.Column("kindle_unlimited", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("language", sa.String(10), nullable=False, server_default="en"),
        sa.Column("genre", sa.String(100), nullable=True),
        sa.Column("categories", postgresql.JSON(astext_type=sa.Text()), nullable=True),
        sa.Column("is_indie", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("cover_url", sa.String(1000), nullable=True),
        sa.Column("first_seen", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("last_updated", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("asin"),
    )
    op.create_index("ix_books_asin", "books", ["asin"])
    op.create_index("ix_books_isbn", "books", ["isbn"])
    op.create_index("ix_books_publisher", "books", ["publisher"])
    op.create_index("ix_books_genre", "books", ["genre"])
    op.create_index("ix_books_is_indie", "books", ["is_indie"])
    op.create_index("ix_books_author", "books", ["author"])
    op.create_index("ix_books_is_indie_genre", "books", ["is_indie", "genre"])

    # ── daily_metrics ─────────────────────────────────────────────────────────
    op.create_table(
        "daily_metrics",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("book_id", sa.Integer(), nullable=False),
        sa.Column("date", sa.Date(), nullable=False),
        sa.Column("amazon_best_seller_rank", sa.Integer(), nullable=True),
        sa.Column("estimated_daily_sales", sa.Integer(), nullable=True),
        sa.Column("price", sa.Numeric(10, 2), nullable=True),
        sa.Column("star_rating", sa.Float(), nullable=True),
        sa.Column("review_count", sa.Integer(), nullable=True),
        sa.Column("category_ranks", postgresql.JSON(astext_type=sa.Text()), nullable=True),
        sa.Column("goodreads_rating", sa.Float(), nullable=True),
        sa.Column("goodreads_reviews", sa.Integer(), nullable=True),
        sa.Column("goodreads_want_to_read", sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(["book_id"], ["books.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("book_id", "date", name="uq_daily_metrics_book_date"),
    )
    op.create_index("ix_daily_metrics_date", "daily_metrics", ["date"])
    op.create_index("ix_daily_metrics_book_id", "daily_metrics", ["book_id"])
    op.create_index("ix_daily_metrics_book_date", "daily_metrics", ["book_id", "date"])

    # ── booktok_mentions ──────────────────────────────────────────────────────
    op.create_table(
        "booktok_mentions",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("book_id", sa.Integer(), nullable=False),
        sa.Column("tiktok_video_id", sa.String(100), nullable=True),
        sa.Column("creator_username", sa.String(100), nullable=True),
        sa.Column("creator_follower_count", sa.Integer(), nullable=True),
        sa.Column("view_count", sa.BigInteger(), nullable=True),
        sa.Column("like_count", sa.BigInteger(), nullable=True),
        sa.Column("comment_count", sa.Integer(), nullable=True),
        sa.Column("share_count", sa.Integer(), nullable=True),
        sa.Column("caption", sa.Text(), nullable=True),
        sa.Column("hashtags", sa.String(500), nullable=True),
        sa.Column("video_url", sa.String(1000), nullable=True),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("collected_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["book_id"], ["books.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_booktok_book_id", "booktok_mentions", ["book_id"])
    op.create_index("ix_booktok_video_id", "booktok_mentions", ["tiktok_video_id"])
    op.create_index("ix_booktok_book_date", "booktok_mentions", ["book_id", "collected_at"])

    # ── reddit_mentions ───────────────────────────────────────────────────────
    op.create_table(
        "reddit_mentions",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("book_id", sa.Integer(), nullable=False),
        sa.Column("reddit_post_id", sa.String(50), nullable=True),
        sa.Column("subreddit", sa.String(100), nullable=True),
        sa.Column("title", sa.Text(), nullable=True),
        sa.Column("body", sa.Text(), nullable=True),
        sa.Column("author", sa.String(100), nullable=True),
        sa.Column("upvotes", sa.Integer(), nullable=True),
        sa.Column("downvotes", sa.Integer(), nullable=True),
        sa.Column("comment_count", sa.Integer(), nullable=True),
        sa.Column("is_comment", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("posted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("collected_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["book_id"], ["books.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_reddit_book_id", "reddit_mentions", ["book_id"])
    op.create_index("ix_reddit_post_id", "reddit_mentions", ["reddit_post_id"])
    op.create_index("ix_reddit_book_subreddit", "reddit_mentions", ["book_id", "subreddit"])

    # ── instagram_mentions ────────────────────────────────────────────────────
    op.create_table(
        "instagram_mentions",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("book_id", sa.Integer(), nullable=False),
        sa.Column("instagram_post_id", sa.String(100), nullable=True),
        sa.Column("username", sa.String(100), nullable=True),
        sa.Column("like_count", sa.Integer(), nullable=True),
        sa.Column("comment_count", sa.Integer(), nullable=True),
        sa.Column("caption", sa.Text(), nullable=True),
        sa.Column("posted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("collected_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["book_id"], ["books.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_instagram_book_id", "instagram_mentions", ["book_id"])
    op.create_index("ix_instagram_post_id", "instagram_mentions", ["instagram_post_id"])


def downgrade() -> None:
    op.drop_table("instagram_mentions")
    op.drop_table("reddit_mentions")
    op.drop_table("booktok_mentions")
    op.drop_table("daily_metrics")
    op.drop_table("books")
    op.drop_table("indie_publishers")
    op.execute("DROP TYPE IF EXISTS bookformat")
