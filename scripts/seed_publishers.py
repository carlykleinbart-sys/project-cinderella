"""
Seed the indie_publishers table with default entries.

Run once after `alembic upgrade head`:

    python -m scripts.seed_publishers

Safe to re-run — existing rows are skipped (INSERT … ON CONFLICT DO NOTHING).
"""
from __future__ import annotations

import sys
from pathlib import Path

# Ensure project root is on sys.path when run as a script
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from loguru import logger
from sqlalchemy.dialects.postgresql import insert as pg_insert

from database import get_session
from models.indie_publisher import DEFAULT_INDIE_PUBLISHERS, IndiePublisher


def seed() -> None:
    inserted = 0
    skipped = 0

    with get_session() as session:
        for entry in DEFAULT_INDIE_PUBLISHERS:
            stmt = (
                pg_insert(IndiePublisher)
                .values(
                    name=entry["name"],
                    match_fragment=entry["match_fragment"],
                    notes=entry.get("notes"),
                    is_active=True,
                )
                .on_conflict_do_nothing(index_elements=["name"])
            )
            result = session.execute(stmt)
            if result.rowcount:
                inserted += 1
                logger.info("  Inserted: {}", entry["name"])
            else:
                skipped += 1

    logger.info(
        "Seed complete — {} inserted, {} already existed", inserted, skipped
    )


def main() -> None:
    logger.info("Seeding indie publishers…")
    seed()


if __name__ == "__main__":
    main()
