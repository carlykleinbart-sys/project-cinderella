"""Add goodreads_id and goodreads_url to books table

Revision ID: 003
Revises: 002
Create Date: 2026-08-03
"""
from __future__ import annotations
import sqlalchemy as sa
from alembic import op

revision: str = "003"
down_revision: str | None = "002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("books", sa.Column("goodreads_id", sa.String(30), nullable=True))
    op.add_column("books", sa.Column("goodreads_url", sa.String(500), nullable=True))
    op.create_index("ix_books_goodreads_id", "books", ["goodreads_id"])


def downgrade() -> None:
    op.drop_index("ix_books_goodreads_id", "books")
    op.drop_column("books", "goodreads_url")
    op.drop_column("books", "goodreads_id")
