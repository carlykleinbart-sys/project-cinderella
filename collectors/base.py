"""
BaseCollector — abstract interface all data collectors must implement.

Adding a new data source (Goodreads, Reddit, etc.) means:
  1. Subclassing BaseCollector
  2. Implementing collect()
  3. Registering in scripts/collect.py
"""
from __future__ import annotations

from abc import ABC, abstractmethod

from loguru import logger


class BaseCollector(ABC):
    """Abstract base for all data collectors."""

    name: str = "unnamed"

    @abstractmethod
    async def collect(self) -> CollectionResult:
        """
        Run the collection job.

        Returns a :class:`CollectionResult` summarising what was gathered.
        """
        ...

    async def run(self) -> "CollectionResult":
        """Wrapper that logs start/end and handles top-level exceptions."""
        logger.info("Starting {} collector", self.name)
        try:
            result = await self.collect()
            logger.info(
                "{} collector finished — {} new books, {} metrics rows",
                self.name,
                result.new_books,
                result.metrics_written,
            )
            return result
        except Exception:
            logger.exception("{} collector failed", self.name)
            raise


class CollectionResult:
    """Summary of a single collection run."""

    def __init__(
        self,
        *,
        collector: str,
        new_books: int = 0,
        updated_books: int = 0,
        metrics_written: int = 0,
        errors: int = 0,
    ) -> None:
        self.collector = collector
        self.new_books = new_books
        self.updated_books = updated_books
        self.metrics_written = metrics_written
        self.errors = errors

    def __repr__(self) -> str:
        return (
            f"<CollectionResult collector={self.collector!r} "
            f"new={self.new_books} updated={self.updated_books} "
            f"metrics={self.metrics_written} errors={self.errors}>"
        )
