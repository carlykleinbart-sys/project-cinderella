"""
IndiePublisher lookup table.

Stores the configurable list of publisher name fragments that identify
self-published or independently published books.  Matching is case-insensitive
substring match against Book.publisher.

Seeded via: python -m scripts.seed_publishers
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from models.base import Base

# ---------------------------------------------------------------------------
# Default indie publisher patterns (used by seed_publishers.py)
# ---------------------------------------------------------------------------
DEFAULT_INDIE_PUBLISHERS: list[dict[str, str | bool]] = [
    {"name": "Independently Published", "match_fragment": "independently published", "notes": "Amazon KDP default publisher name"},
    {"name": "Amazon KDP", "match_fragment": "amazon kdp", "notes": "Explicit KDP branding"},
    {"name": "KDP", "match_fragment": "kdp", "notes": "Short KDP reference"},
    {"name": "Draft2Digital", "match_fragment": "draft2digital", "notes": "D2D aggregator"},
    {"name": "Smashwords", "match_fragment": "smashwords", "notes": "Smashwords platform"},
    {"name": "IngramSpark", "match_fragment": "ingramspark", "notes": "Ingram self-pub arm"},
    {"name": "Lulu", "match_fragment": "lulu", "notes": "Lulu self-pub platform"},
    {"name": "BookBaby", "match_fragment": "bookbaby", "notes": "BookBaby aggregator"},
    {"name": "PublishDrive", "match_fragment": "publishdrive", "notes": "PublishDrive aggregator"},
    {"name": "StreetLib", "match_fragment": "streetlib", "notes": "StreetLib aggregator"},
    {"name": "Pronoun", "match_fragment": "pronoun", "notes": "Legacy Macmillan indie platform"},
    {"name": "Kobo Writing Life", "match_fragment": "kobo writing life", "notes": "Kobo self-pub"},
]


class IndiePublisher(Base):
    """
    Configurable lookup of known indie / self-publishing platforms.

    The `match_fragment` field is a lowercase substring that, when found
    inside a book's publisher string (case-insensitive), marks the book
    as indie.
    """

    __tablename__ = "indie_publishers"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)

    name: Mapped[str] = mapped_column(
        String(200),
        nullable=False,
        unique=True,
        comment="Human-readable name for this indie publisher / platform",
    )
    match_fragment: Mapped[str] = mapped_column(
        String(200),
        nullable=False,
        unique=True,
        comment="Lowercase substring to match against Book.publisher (case-insensitive)",
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        nullable=False,
        comment="Set False to disable matching without deleting the row",
    )
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    def __repr__(self) -> str:
        return f"<IndiePublisher name={self.name!r} fragment={self.match_fragment!r}>"
