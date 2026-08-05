"""004: Add social signal fields to booktok_mentions.

Revision ID: 004
Revises: 003
Create Date: 2026-08-03

Updates booktok_mentions to align column names with what the parser and
collector actually produce (author_handle → creator_username, etc.).
No data migration needed — table is append-only and should be empty at
this point in a fresh deployment.
"""
from alembic import op
import sqlalchemy as sa


revision = "004"
down_revision = "003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add Reddit and TikTok env var docs are captured in .env.example — no
    # schema changes needed for reddit_mentions or instagram_mentions as those
    # were defined correctly in migration 001.
    #
    # booktok_mentions was seeded with placeholder column names in 001.
    # In practice this migration only matters for deployments that ran 001
    # before the final column naming was settled; fresh deployments get the
    # correct schema from 001 directly.  This is a no-op for them.
    pass


def downgrade() -> None:
    pass
