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

    Railway (and some other hosts) provide DATABASE_URL with the legacy
    ``postgres://`` scheme.  SQLAlchemy 2.0 requires ``postgresql://``, so
    we normalise the scheme here.
    """
    url = settings.database_url
    # Normalise legacy postgres:// → postgresql:// (Railway, Heroku, Render)
    if url.startswith("postgres://"):
        url = "postgresql://" + url[len("postgres://"):]
    is_sqlite = url.startswith("sqlite")

    kwargs: dict = {
        "future": True,
        "echo": False,
    }
    if not is_sqlite:
        kwargs.update(
            pool_pre_ping=True,
            pool_size=2,
            max_overflow=5,
            pool_recycle=60,  # recycle connections every 60s to beat Railway's proxy timeout
            connect_args={
                # TCP keepalives keep the connection alive through Railway's NAT/proxy
                "keepalives": 1,
                "keepalives_idle": 30,
                "keepalives_interval": 10,
                "keepalives_count": 5,
            },
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
