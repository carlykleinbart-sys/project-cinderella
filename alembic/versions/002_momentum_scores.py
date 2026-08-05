"""Add momentum_scores table

Revision ID: 002
Revises: 001
Create Date: 2026-08-03
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "002"
down_revision: str | None = "001"
branch_labels: str | tuple[str, ...] | None = None
depends_on: str | tuple[str, ...] | None = None


def upgrade() -> None:
    op.create_table(
        "momentum_scores",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("book_id", sa.Integer(), nullable=False),
        sa.Column("date", sa.Date(), nullable=False),
        sa.Column("momentum_score", sa.Float(), nullable=False),
        sa.Column("components", postgresql.JSON(astext_type=sa.Text()), nullable=False),
        sa.Column("explanation", sa.Text(), nullable=False),
        sa.Column("snapshots_used", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("alert_triggered", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("alert_reasons", postgresql.JSON(astext_type=sa.Text()), nullable=False,
                  server_default="[]"),
        sa.ForeignKeyConstraint(["book_id"], ["books.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("book_id", "date", name="uq_momentum_score_book_date"),
    )
    op.create_index("ix_momentum_scores_date", "momentum_scores", ["date"])
    op.create_index("ix_momentum_scores_score", "momentum_scores", ["momentum_score"])
    op.create_index("ix_momentum_scores_book_id", "momentum_scores", ["book_id"])


def downgrade() -> None:
    op.drop_table("momentum_scores")
