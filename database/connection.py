"""
SQLAlchemy engine and session factory.

Usage
-----
    from database import get_session

    with get_session() as session:
        books = session.scalars(select(Book)).all()
"""
from __future__ import annotations

from contextlib import contextmanager
from typing import Generator

from loguru import logger
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session, sessionmaker

from config import settings


def _build_engine():
    """
    Build the SQLAlchemy engine with appropriate settings for the configured
    database dialect.  SQLite (used in tests) does not support connection
    pool parameters that PostgreSQL requires.
    """
    url = settings.database_url
    is_sqlite = url.startswith("sqlite")

    kwargs: dict = {
        "future": True,
        "echo": False,
    }
    if not is_sqlite:
        kwargs.update(
            pool_pre_ping=True,
            pool_size=5,
            max_overflow=10,
        )

    return create_engine(url, **kwargs)


engine = _build_engine()


@event.listens_for(engine, "connect")
def _on_connect(dbapi_connection, connection_record):  # type: ignore[no-untyped-def]
    """Set timezone to UTC on PostgreSQL connections."""
    # SQLite connections don't have a SET command; skip
    if settings.database_url.startswith("postgresql"):
        cursor = dbapi_connection.cursor()
        cursor.execute("SET timezone = 'UTC'")
        cursor.close()


SessionLocal = sessionmaker(
    bind=engine,
    autocommit=False,
    autoflush=False,
    expire_on_commit=False,
)


@contextmanager
def get_session() -> Generator[Session, None, None]:
    """
    Provide a transactional scope around a series of operations.

    Automatically commits on success and rolls back on any exception.
    """
    session: Session = SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        logger.exception("Session rolled back due to an unhandled exception")
        raise
    finally:
        session.close()
