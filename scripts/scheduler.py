"""
APScheduler daemon — runs collect + report on a configurable cron schedule.

Usage
-----
    # Run as a long-lived daemon (blocks until killed)
    python -m scripts.scheduler

    # Override the schedule
    COLLECTION_SCHEDULE="0 8 * * *" python -m scripts.scheduler

The default schedule (from settings) runs at 06:00 UTC daily:
  1. 06:00 — Collect Amazon data
  2. 06:15 — Collect Goodreads data  (enriches Amazon books with GR stats)
  3. 06:30 — Collect BookTok data
  4. 06:45 — Collect Reddit data
  5. 07:00 — Score + generate report + send alerts

Social jobs are staggered 15 min apart so that the async scrapers
don't overwhelm a single host and respect rate limits naturally.

Logs are written to stdout (and optionally LOG_FILE).
"""
from __future__ import annotations

import asyncio
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from loguru import logger

try:
    from apscheduler.schedulers.blocking import BlockingScheduler
    from apscheduler.triggers.cron import CronTrigger
except ImportError:
    raise SystemExit(
        "APScheduler not installed. Run: pip install apscheduler"
    )

from config import settings


def _configure_logging() -> None:
    logger.remove()
    logger.add(
        sys.stderr,
        level=settings.log_level,
        format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level:<8}</level> | {message}",
    )
    if settings.log_file:
        logger.add(settings.log_file, level=settings.log_level, rotation="50 MB")


def run_collection_job() -> None:
    """Run the Amazon collector synchronously (called by APScheduler)."""
    logger.info("Scheduled collection job starting")
    from collectors.amazon_collector import AmazonCollector

    collector = AmazonCollector()
    result = asyncio.run(collector.run())
    logger.info(
        "Collection complete — {} new, {} updated, {} metrics",
        result.new_books, result.updated_books, result.metrics_written,
    )


def run_goodreads_job() -> None:
    """Run the Goodreads collector (called by APScheduler)."""
    logger.info("Scheduled Goodreads collection job starting")
    from collectors.goodreads_collector import GoodreadsCollector

    result = asyncio.run(GoodreadsCollector().run())
    logger.info(
        "Goodreads collection complete — {} new, {} updated",
        result.new_books, result.updated_books,
    )


def run_booktok_job() -> None:
    """Run the BookTok collector (called by APScheduler)."""
    logger.info("Scheduled BookTok collection job starting")
    from collectors.booktok_collector import BookTokCollector

    result = asyncio.run(BookTokCollector().run())
    logger.info(
        "BookTok collection complete — {} new, {} updated",
        result.new_books, result.updated_books,
    )


def run_reddit_job() -> None:
    """Run the Reddit collector (called by APScheduler)."""
    logger.info("Scheduled Reddit collection job starting")
    from collectors.reddit_collector import RedditCollector

    result = asyncio.run(RedditCollector().run())
    logger.info(
        "Reddit collection complete — {} new, {} updated",
        result.new_books, result.updated_books,
    )


def run_report_job() -> None:
    """Run the report generator and send alerts (called by APScheduler)."""
    logger.info("Scheduled report job starting")
    from alerts.alert_manager import AlertManager
    from reports.report_generator import ReportGenerator

    report = ReportGenerator().generate()
    AlertManager().send_all(report)
    logger.info("Report job complete — {} books, {} alerts", len(report.books), report.alert_count)


def _offset_time(base_minute: int, base_hour: int, offset_minutes: int) -> tuple[int, int]:
    """Return (minute, hour) after adding offset_minutes, wrapping at 60."""
    total = base_minute + base_hour * 60 + offset_minutes
    return total % 60, (total // 60) % 24


def main() -> None:
    _configure_logging()

    # Parse cron from settings (e.g. "0 6 * * *")
    cron_parts = settings.collection_schedule.strip().split()
    if len(cron_parts) != 5:
        raise ValueError(
            f"COLLECTION_SCHEDULE must be a 5-part cron expression, got: "
            f"{settings.collection_schedule!r}"
        )
    minute, hour, day, month, day_of_week = cron_parts
    base_minute, base_hour = int(minute), int(hour)

    scheduler = BlockingScheduler(timezone="UTC")

    def _add(func, offset: int, job_id: str, name: str) -> None:
        m, h = _offset_time(base_minute, base_hour, offset)
        scheduler.add_job(
            func,
            CronTrigger(minute=m, hour=h, day=day, month=month,
                        day_of_week=day_of_week, timezone="UTC"),
            id=job_id,
            name=name,
            misfire_grace_time=3600,
        )
        logger.info("Registered '{}' at {:02d}:{:02d} UTC", name, h, m)

    # Stagger jobs 15 minutes apart:
    #   +0  min — Amazon
    #   +15 min — Goodreads
    #   +30 min — BookTok
    #   +45 min — Reddit
    #   +60 min — Report + alerts
    _add(run_collection_job, 0,  "amazon_collect",   "Amazon bestseller collection")
    _add(run_goodreads_job,  15, "goodreads_collect", "Goodreads enrichment")
    _add(run_booktok_job,    30, "booktok_collect",   "BookTok mentions")
    _add(run_reddit_job,     45, "reddit_collect",    "Reddit mentions")
    _add(run_report_job,     60, "daily_report",      "Daily report + alerts")

    logger.info(
        "Scheduler started. Base schedule: {} UTC",
        settings.collection_schedule,
    )

    try:
        scheduler.start()
    except (KeyboardInterrupt, SystemExit):
        logger.info("Scheduler stopped")


if __name__ == "__main__":
    main()
