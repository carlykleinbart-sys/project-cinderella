"""
CLI entry point for generating the daily report.

Usage
-----
    # Generate for today, send all alerts
    python -m scripts.report

    # Specific date
    python -m scripts.report --date 2026-07-28

    # Skip alerts (report file only)
    python -m scripts.report --no-alerts

    # Show top N results in terminal
    python -m scripts.report --preview 10
"""
from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import click
from loguru import logger
from rich.console import Console
from rich.table import Table
from rich import box

from alerts.alert_manager import AlertManager
from config import settings
from reports.report_generator import ReportGenerator

console = Console()


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
    "--date",
    "report_date",
    default=None,
    help="Report date in YYYY-MM-DD format (default: today).",
)
@click.option(
    "--no-alerts",
    is_flag=True,
    default=False,
    help="Generate report files but skip sending alerts.",
)
@click.option(
    "--preview",
    default=0,
    type=int,
    help="Print top N books to terminal (0 = no preview).",
)
@click.option(
    "--output-dir",
    default=None,
    help="Override output directory for report files.",
)
@click.option(
    "--min-snapshots",
    default=2,
    type=int,
    show_default=True,
    help="Minimum historical snapshots required to score a book.",
)
def main(
    report_date: str | None,
    no_alerts: bool,
    preview: int,
    output_dir: str | None,
    min_snapshots: int,
) -> None:
    """Project Cinderella — daily breakout report generator."""
    _configure_logging()

    parsed_date = date.fromisoformat(report_date) if report_date else date.today()
    out = Path(output_dir) if output_dir else None

    generator = ReportGenerator(
        report_date=parsed_date,
        output_dir=out,
        min_snapshots=min_snapshots,
    )
    report = generator.generate()

    if preview:
        _print_preview(report, preview)

    if not no_alerts:
        manager = AlertManager()
        manager.send_all(report)
    else:
        logger.info("--no-alerts set, skipping alert dispatch")

    d_str = settings.reports_dir / f"cinderella-{parsed_date}.html"
    console.print(f"\n[bold green]✓[/bold green] Report saved → {d_str}")
    console.print(
        f"[dim]{len(report.books)} books scored · "
        f"{report.alert_count} alerts · "
        f"top score: {report.books[0].momentum_score:.0f}/100[/dim]"
        if report.books else "[dim]No books scored.[/dim]"
    )


def _print_preview(report, n: int) -> None:
    table = Table(
        title=f"Top {n} Breakout Candidates — {report.report_date}",
        box=box.SIMPLE_HEAVY,
        show_header=True,
        header_style="bold magenta",
    )
    table.add_column("Rank", style="dim", width=4)
    table.add_column("Title", max_width=35)
    table.add_column("Author", max_width=20)
    table.add_column("Score", justify="right", style="bold cyan")
    table.add_column("BSR", justify="right")
    table.add_column("7d Δ BSR", justify="right")
    table.add_column("Reviews", justify="right")
    table.add_column("Alert", justify="center")

    for i, r in enumerate(report.books[:n], 1):
        rank_str = f"#{r.current_rank:,}" if r.current_rank else "—"
        chg_str = ""
        if r.rank_7d_change:
            chg_str = (
                f"[green]+{r.rank_7d_change:,}[/green]"
                if r.rank_7d_change > 0
                else f"[red]{r.rank_7d_change:,}[/red]"
            )
        rev_str = f"{r.current_review_count:,}" if r.current_review_count else "—"
        alert_str = "[yellow]🚨[/yellow]" if r.alert_triggered else ""

        table.add_row(
            str(i),
            r.title,
            r.author,
            f"{r.momentum_score:.0f}",
            rank_str,
            chg_str,
            rev_str,
            alert_str,
        )

    console.print(table)


if __name__ == "__main__":
    main()
