"""
CLI entry point for the data collection pipeline.

Usage
-----
    # Run all collectors
    python -m scripts.collect

    # Amazon only, limiting to 20 books per category
    python -m scripts.collect --source amazon --max-books 20

    # Social sources only
    python -m scripts.collect --source goodreads
    python -m scripts.collect --source booktok
    python -m scripts.collect --source reddit

    # Dry-run: scrape but don't write to DB
    python -m scripts.collect --dry-run

    # Specific categories only (Amazon)
    python -m scripts.collect --source amazon --categories "Romance,Fantasy"
"""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import click
from loguru import logger
from rich.console import Console
from rich.table import Table

from collectors.base import CollectionResult
from collectors.amazon_collector import AmazonCollector
from config import settings

console = Console()

SOCIAL_SOURCES = ("goodreads", "booktok", "reddit")


def _configure_logging() -> None:
    logger.remove()
    logger.add(
        sys.stderr,
        level=settings.log_level,
        format="<green>{time:HH:mm:ss}</green> | <level>{level: <8}</level> | {message}",
    )
    if settings.log_file:
        logger.add(settings.log_file, level=settings.log_level, rotation="10 MB")


@click.command()
@click.option(
    "--source",
    default="all",
    type=click.Choice(["all", "amazon", "goodreads", "booktok", "reddit"], case_sensitive=False),
    show_default=True,
    help="Which data source to collect from.",
)
@click.option(
    "--max-books",
    default=None,
    type=int,
    help="Override max books per category (Amazon) or max books to process (social).",
)
@click.option(
    "--categories",
    default=None,
    help="Comma-separated list of genre names to collect (Amazon only, e.g. 'Romance,Fantasy').",
)
@click.option(
    "--dry-run",
    is_flag=True,
    default=False,
    help="Parse data but skip database writes.",
)
def main(
    source: str,
    max_books: int | None,
    categories: str | None,
    dry_run: bool,
) -> None:
    """Project Cinderella — data collection pipeline."""
    _configure_logging()

    if dry_run:
        logger.warning("DRY RUN mode — no data will be written to the database")

    results: list[CollectionResult] = []

    # ── Amazon ────────────────────────────────────────────────────────────────
    if source in ("all", "amazon"):
        from scrapers.amazon.categories import KINDLE_CATEGORIES

        cat_filter: dict[str, str] | None = None
        if categories:
            names = [c.strip() for c in categories.split(",")]
            cat_filter = {k: v for k, v in KINDLE_CATEGORIES.items() if k in names}
            if not cat_filter:
                logger.error("No matching categories found for: {}", categories)
                sys.exit(1)

        collector = AmazonCollector(
            categories=cat_filter,
            max_books_per_category=max_books,
        )

        if not dry_run:
            result = asyncio.run(collector.run())
        else:
            result = asyncio.run(_dry_run_collect(collector))

        results.append(result)

    # ── Goodreads ─────────────────────────────────────────────────────────────
    if source in ("all", "goodreads") and not dry_run:
        from collectors.goodreads_collector import GoodreadsCollector

        gr_kwargs = {"max_books": max_books} if max_books is not None else {}
        result = asyncio.run(GoodreadsCollector(**gr_kwargs).run())
        results.append(result)

    # ── BookTok ───────────────────────────────────────────────────────────────
    if source in ("all", "booktok") and not dry_run:
        from collectors.booktok_collector import BookTokCollector

        bt_kwargs = {"max_books": max_books} if max_books is not None else {}
        result = asyncio.run(BookTokCollector(**bt_kwargs).run())
        results.append(result)

    # ── Reddit ────────────────────────────────────────────────────────────────
    if source in ("all", "reddit") and not dry_run:
        from collectors.reddit_collector import RedditCollector

        rd_kwargs = {"max_books": max_books} if max_books is not None else {}
        result = asyncio.run(RedditCollector(**rd_kwargs).run())
        results.append(result)

    if dry_run and source in SOCIAL_SOURCES:
        logger.info("Dry-run skipped social collector: {}", source)

    _print_summary(results)


async def _dry_run_collect(collector: AmazonCollector) -> CollectionResult:
    """Run collection without DB writes — for validation/debugging."""
    from scrapers.amazon import AmazonBrowser, AmazonParser
    from scrapers.amazon.categories import BESTSELLER_BASE_URL

    result = CollectionResult(collector=collector.name)
    async with AmazonBrowser() as browser:
        for genre, node_id in list(collector._categories.items())[:3]:  # limit in dry-run
            url = BESTSELLER_BASE_URL.format(node_id=node_id)
            try:
                html = await browser.fetch_page_with_scroll(url)
                entries = AmazonParser.parse_bestseller_list(html)
                logger.info("[DRY RUN] {} — parsed {} entries", genre, len(entries))
                for e in entries[:5]:
                    logger.info("  #{} {} by {} (ASIN: {})", e["rank"], e["title"], e["author"], e["asin"])
                result.new_books += len(entries)
            except Exception as exc:
                logger.error("Error in dry run for {}: {}", genre, exc)
                result.errors += 1
    return result


def _print_summary(results: list[CollectionResult]) -> None:
    table = Table(title="Collection Summary", show_header=True, header_style="bold cyan")
    table.add_column("Collector")
    table.add_column("New Books", justify="right")
    table.add_column("Updated", justify="right")
    table.add_column("Metrics Written", justify="right")
    table.add_column("Errors", justify="right")

    for r in results:
        table.add_row(
            r.collector,
            str(r.new_books),
            str(r.updated_books),
            str(r.metrics_written),
            f"[red]{r.errors}[/red]" if r.errors else "0",
        )

    console.print(table)


if __name__ == "__main__":
    main()
