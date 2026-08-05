"""FastAPI dependency injectors."""
from __future__ import annotations

from typing import Generator

from sqlalchemy.orm import Session

from database.connection import SessionLocal


def get_db() -> Generator[Session, None, None]:
    """Yield a database session for the lifetime of a single request."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
