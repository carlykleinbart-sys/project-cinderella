"""
ReportGenerator — builds and saves the daily breakout report.

Pipeline
--------
1. Query all indie books with >= min_snapshots daily_metrics rows.
2. Run MomentumScorer on each book's historical snapshots.
3. Persist MomentumScore rows to DB (idempotent).
4. Build a DailyReport sorted by momentum_score descending.
5. Write Markdown and HTML outputs to reports_dir.

The HTML report is a standalone file — no server required to view it.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Optional

from loguru import logger
from sqlalchemy import insert as generic_insert, select
from sqlalchemy.exc import IntegrityError

from config import settings
from database import get_session
from models import Book, DailyMetrics, MomentumScore
from reports.report_models import BookReportRow, DailyReport
from scoring.momentum_scorer import MomentumScorer
from scoring.score_config import ScoringConfig
from scoring.social_aggregator import SocialSignalAggregator


class ReportGenerator:
    """
    Orchestrates scoring and report generation for a given date.

    Parameters
    ----------
    report_date:
        The date to generate a report for.  Defaults to today.
    config:
        Optional scoring config override.
    output_dir:
        Where to write reports.  Defaults to ``settings.reports_dir``.
    min_snapshots:
        Minimum historical snapshots a book must have to be included.
    """

    def __init__(
        self,
        report_date: Optional[date] = None,
        config: Optional[ScoringConfig] = None,
        output_dir: Optional[Path] = None,
        min_snapshots: int = 2,
    ) -> None:
        self._date = report_date or date.today()
        self._scorer = MomentumScorer(config)
        self._social_aggregator = SocialSignalAggregator()
        self._output_dir = output_dir or settings.reports_dir
        self._min_snapshots = min_snapshots

    # ── Public API ────────────────────────────────────────────────────────────

    def generate(self) -> DailyReport:
        """
        Score all eligible indie books and return a :class:`DailyReport`.

        Also persists :class:`MomentumScore` rows and writes report files.
        """
        logger.info("Generating report for {}", self._date)

        books_with_snapshots = self._load_books_with_snapshots()
        logger.info("Scoring {} books", len(books_with_snapshots))

        rows: list[BookReportRow] = []
        for book, snapshots in books_with_snapshots:
            try:
                row = self._score_and_build_row(book, snapshots)
                rows.append(row)
            except Exception as exc:
                logger.error("Error scoring book {}: {}", book.asin, exc)

        # Sort descending by momentum score
        rows.sort(key=lambda r: r.momentum_score, reverse=True)
        alerts = [r for r in rows if r.alert_triggered]

        report = DailyReport(
            report_date=self._date,
            total_books_tracked=self._count_all_books(),
            total_indie_books=len(rows),
            books=rows,
            alerts=alerts,
        )

        self._write_reports(report)
        logger.info(
            "Report complete — {} books scored, {} alerts triggered",
            len(rows), len(alerts)
        )
        return report

    # ── Data loading ──────────────────────────────────────────────────────────

    def _load_books_with_snapshots(self) -> list[tuple[Book, list[DailyMetrics]]]:
        """Load all indie books together with their DailyMetrics rows."""
        results: list[tuple[Book, list[DailyMetrics]]] = []
        with get_session() as session:
            books = session.scalars(
                select(Book).where(Book.is_indie.is_(True))
            ).all()

            for book in books:
                snapshots = session.scalars(
                    select(DailyMetrics)
                    .where(DailyMetrics.book_id == book.id)
                    .order_by(DailyMetrics.date.asc())
                ).all()

                if len(snapshots) >= self._min_snapshots:
                    results.append((book, list(snapshots)))

        return results

    def _count_all_books(self) -> int:
        with get_session() as session:
            return session.query(Book).count()

    # ── Scoring + row building ────────────────────────────────────────────────

    def _score_and_build_row(
        self, book: Book, snapshots: list[DailyMetrics]
    ) -> BookReportRow:
        # Compute age
        book_age_days: Optional[int] = None
        if book.publication_date:
            book_age_days = (self._date - book.publication_date).days

        result = self._scorer.score(
            book_id=book.id,
            snapshots=snapshots,
            score_date=self._date,
            book_age_days=book_age_days,
            kindle_unlimited=book.kindle_unlimited,
            social_aggregator=self._social_aggregator,
        )

        # Persist score
        self._save_score(result)

        # Build 7-day deltas
        latest = snapshots[-1]
        snap_7d_ago = self._find_snapshot_near(snapshots, self._date - timedelta(days=7))

        rank_7d = None
        sales_7d_pct = None
        review_7d_new = None

        if snap_7d_ago:
            if latest.amazon_best_seller_rank and snap_7d_ago.amazon_best_seller_rank:
                rank_7d = snap_7d_ago.amazon_best_seller_rank - latest.amazon_best_seller_rank
            if (latest.estimated_daily_sales and snap_7d_ago.estimated_daily_sales
                    and snap_7d_ago.estimated_daily_sales > 0):
                sales_7d_pct = (
                    (latest.estimated_daily_sales - snap_7d_ago.estimated_daily_sales)
                    / snap_7d_ago.estimated_daily_sales * 100
                )
            if latest.review_count is not None and snap_7d_ago.review_count is not None:
                review_7d_new = latest.review_count - snap_7d_ago.review_count

        # Top 3 category ranks
        top_cats: dict[str, int] = {}
        if latest.category_ranks:
            sorted_cats = sorted(latest.category_ranks.items(), key=lambda x: x[1])
            top_cats = dict(sorted_cats[:3])

        return BookReportRow(
            asin=book.asin,
            title=book.title,
            author=book.author,
            publisher=book.publisher,
            genre=book.genre,
            book_age_days=book_age_days,
            kindle_unlimited=book.kindle_unlimited,
            amazon_url=f"https://www.amazon.com/dp/{book.asin}/",
            current_rank=latest.amazon_best_seller_rank,
            current_sales_estimate=latest.estimated_daily_sales,
            current_review_count=latest.review_count,
            current_star_rating=latest.star_rating,
            current_price=float(latest.price) if latest.price else None,
            rank_7d_change=rank_7d,
            sales_7d_change_pct=sales_7d_pct,
            review_7d_new=review_7d_new,
            momentum_score=result.momentum_score,
            alert_triggered=result.alert_triggered,
            alert_reasons=result.alert_reasons,
            explanation=result.explanation,
            top_category_ranks=top_cats,
        )

    # ── Persistence ───────────────────────────────────────────────────────────

    def _save_score(self, result) -> None:
        """Persist a MomentumScore row (idempotent)."""
        data = {
            "book_id": result.book_id,
            "date": result.score_date,
            "momentum_score": result.momentum_score,
            "components": result.components.to_dict(),
            "explanation": result.explanation,
            "snapshots_used": result.snapshots_used,
            "alert_triggered": result.alert_triggered,
            "alert_reasons": result.alert_reasons,
        }
        try:
            # Try PostgreSQL upsert
            from sqlalchemy.dialects.postgresql import insert as pg_insert
            with get_session() as session:
                stmt = (
                    pg_insert(MomentumScore)
                    .values(**data)
                    .on_conflict_do_nothing(constraint="uq_momentum_score_book_date")
                )
                session.execute(stmt)
        except Exception:
            # SQLite fallback
            try:
                with get_session() as session:
                    session.execute(generic_insert(MomentumScore).values(**data))
            except IntegrityError:
                pass  # Already exists — idempotent

    # ── Report writers ────────────────────────────────────────────────────────

    def _write_reports(self, report: DailyReport) -> None:
        self._output_dir.mkdir(parents=True, exist_ok=True)
        date_str = report.report_date.strftime("%Y-%m-%d")

        md_path = self._output_dir / f"cinderella-{date_str}.md"
        html_path = self._output_dir / f"cinderella-{date_str}.html"

        md_path.write_text(self._render_markdown(report), encoding="utf-8")
        html_path.write_text(self._render_html(report), encoding="utf-8")

        logger.info("Report written → {} and {}", md_path.name, html_path.name)

    # ── Markdown renderer ─────────────────────────────────────────────────────

    def _render_markdown(self, report: DailyReport) -> str:
        d = report.report_date.strftime("%B %d, %Y")
        lines = [
            f"# Project Cinderella — Daily Breakout Report",
            f"**{d}** | {report.total_books_tracked} books tracked "
            f"| {report.total_indie_books} indie | {report.alert_count} alerts",
            "",
        ]

        if report.alerts:
            lines += ["## 🚨 Alerts", ""]
            for row in report.alerts:
                lines += self._md_book_block(row, alert=True)

        lines += ["## Top Breakout Candidates", ""]
        for i, row in enumerate(report.top_books, 1):
            lines += [f"### #{i} · {row.title}", ""]
            lines += self._md_book_block(row)

        return "\n".join(lines)

    def _md_book_block(self, row: BookReportRow, alert: bool = False) -> list[str]:
        rank_str = f"#{row.current_rank:,}" if row.current_rank else "N/A"
        change_str = ""
        if row.rank_7d_change is not None:
            arrow = "▲" if row.rank_7d_change > 0 else "▼"
            change_str = f" ({arrow}{abs(row.rank_7d_change):,} in 7d)"

        rating_str = f"{row.current_star_rating:.1f}★" if row.current_star_rating else "N/A"
        reviews_str = f"{row.current_review_count:,}" if row.current_review_count else "N/A"
        new_reviews = f" (+{row.review_7d_new} this week)" if row.review_7d_new else ""
        sales_str = f"~{row.current_sales_estimate}/day" if row.current_sales_estimate else "N/A"
        price_str = f"${row.current_price:.2f}" if row.current_price else "N/A"
        ku_str = " · KU" if row.kindle_unlimited else ""
        age_str = f" · {row.book_age_days}d old" if row.book_age_days else ""

        block = [
            f"**{row.title}** by {row.author}",
            f"*{row.publisher or 'Unknown Publisher'} · {row.genre or 'Unknown Genre'}{ku_str}{age_str}*",
            "",
            f"| Metric | Value |",
            f"|--------|-------|",
            f"| **Momentum Score** | **{row.momentum_score:.1f} / 100** |",
            f"| Amazon Rank | {rank_str}{change_str} |",
            f"| Est. Daily Sales | {sales_str} |",
            f"| Rating | {rating_str} ({reviews_str} reviews{new_reviews}) |",
            f"| Price | {price_str} |",
        ]

        if row.top_category_ranks:
            for cat, rank in list(row.top_category_ranks.items())[:2]:
                block.append(f"| {cat[:40]} | #{rank} |")

        block += [
            "",
            f"> {row.explanation}",
            "",
            f"[View on Amazon]({row.amazon_url})",
            "",
            "---",
            "",
        ]
        return block

    # ── HTML renderer ─────────────────────────────────────────────────────────

    def _render_html(self, report: DailyReport) -> str:
        d = report.report_date.strftime("%B %d, %Y")
        rows_html = "\n".join(self._html_book_card(i + 1, r) for i, r in enumerate(report.top_books))
        alert_html = ""
        if report.alerts:
            alert_cards = "\n".join(self._html_book_card(0, r, alert=True) for r in report.alerts)
            alert_html = f"""
            <section class="alerts">
              <h2>🚨 Alerts ({report.alert_count})</h2>
              {alert_cards}
            </section>"""

        return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Project Cinderella — {d}</title>
  <style>
    * {{ box-sizing: border-box; margin: 0; padding: 0; }}
    body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
            background: #0f0f13; color: #e8e8f0; min-height: 100vh; padding: 2rem; }}
    h1 {{ font-size: 1.8rem; color: #c084fc; margin-bottom: 0.25rem; }}
    .subtitle {{ color: #6b7280; font-size: 0.9rem; margin-bottom: 2rem; }}
    h2 {{ font-size: 1.3rem; color: #a78bfa; margin: 2rem 0 1rem; }}
    .card {{ background: #1a1a24; border: 1px solid #2d2d3d; border-radius: 12px;
             padding: 1.5rem; margin-bottom: 1rem; transition: border-color 0.2s; }}
    .card:hover {{ border-color: #7c3aed; }}
    .card.alert {{ border-color: #f59e0b; }}
    .rank-badge {{ display: inline-block; background: #7c3aed; color: white;
                  font-size: 0.75rem; font-weight: 700; padding: 2px 8px;
                  border-radius: 999px; margin-right: 0.5rem; }}
    .score {{ font-size: 2rem; font-weight: 800; color: #c084fc; float: right; }}
    .score span {{ font-size: 0.9rem; color: #6b7280; font-weight: 400; }}
    .title {{ font-size: 1.1rem; font-weight: 700; color: #f0f0ff; }}
    .author {{ color: #9ca3af; font-size: 0.85rem; margin-top: 0.2rem; }}
    .meta {{ color: #6b7280; font-size: 0.8rem; margin-top: 0.4rem; }}
    .metrics {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(140px, 1fr));
                gap: 0.75rem; margin-top: 1rem; }}
    .metric {{ background: #12121a; border-radius: 8px; padding: 0.6rem 0.8rem; }}
    .metric-label {{ font-size: 0.7rem; color: #6b7280; text-transform: uppercase;
                     letter-spacing: 0.05em; }}
    .metric-value {{ font-size: 1rem; font-weight: 600; color: #e8e8f0;
                     margin-top: 0.2rem; }}
    .metric-value.up {{ color: #34d399; }}
    .metric-value.down {{ color: #f87171; }}
    .explanation {{ color: #9ca3af; font-size: 0.85rem; margin-top: 1rem;
                    font-style: italic; line-height: 1.5; }}
    .amazon-link {{ display: inline-block; margin-top: 0.8rem; color: #a78bfa;
                    text-decoration: none; font-size: 0.8rem; }}
    .amazon-link:hover {{ text-decoration: underline; }}
    .clearfix::after {{ content: ""; display: table; clear: both; }}
  </style>
</head>
<body>
  <h1>🔮 Project Cinderella</h1>
  <p class="subtitle">Daily Breakout Report — {d} &nbsp;·&nbsp;
    {report.total_books_tracked} tracked &nbsp;·&nbsp;
    {report.total_indie_books} indie &nbsp;·&nbsp;
    {report.alert_count} alerts</p>
  {alert_html}
  <section>
    <h2>Top Breakout Candidates</h2>
    {rows_html}
  </section>
</body>
</html>"""

    def _html_book_card(self, rank: int, row: BookReportRow, alert: bool = False) -> str:
        rank_badge = f'<span class="rank-badge">#{rank}</span>' if rank > 0 else \
                     '<span class="rank-badge" style="background:#f59e0b">ALERT</span>'

        rank_str = f"#{row.current_rank:,}" if row.current_rank else "N/A"
        if row.rank_7d_change:
            arrow = "▲" if row.rank_7d_change > 0 else "▼"
            rank_str += f" <small>({arrow}{abs(row.rank_7d_change):,})</small>"

        rank_class = "up" if (row.rank_7d_change or 0) > 0 else ""
        reviews_str = f"{row.current_review_count:,}" if row.current_review_count else "N/A"
        if row.review_7d_new:
            reviews_str += f" <small>(+{row.review_7d_new})</small>"

        meta_parts = [row.publisher or "Unknown Publisher", row.genre or ""]
        if row.kindle_unlimited:
            meta_parts.append("KU")
        if row.book_age_days:
            meta_parts.append(f"{row.book_age_days}d old")

        alert_class = " alert" if alert else ""

        return f"""<div class="card{alert_class}">
  <div class="clearfix">
    <div class="score">{row.momentum_score:.0f}<span>/100</span></div>
    <div>
      {rank_badge}
      <span class="title">{row.title}</span>
    </div>
    <div class="author">by {row.author}</div>
    <div class="meta">{" · ".join(p for p in meta_parts if p)}</div>
  </div>
  <div class="metrics">
    <div class="metric">
      <div class="metric-label">Amazon Rank</div>
      <div class="metric-value {rank_class}">{rank_str}</div>
    </div>
    <div class="metric">
      <div class="metric-label">Est. Daily Sales</div>
      <div class="metric-value">{"~" + str(row.current_sales_estimate) if row.current_sales_estimate else "N/A"}</div>
    </div>
    <div class="metric">
      <div class="metric-label">Rating</div>
      <div class="metric-value">{"%.1f★" % row.current_star_rating if row.current_star_rating else "N/A"}</div>
    </div>
    <div class="metric">
      <div class="metric-label">Reviews</div>
      <div class="metric-value">{reviews_str}</div>
    </div>
    <div class="metric">
      <div class="metric-label">Price</div>
      <div class="metric-value">{"$%.2f" % row.current_price if row.current_price else "N/A"}</div>
    </div>
  </div>
  <p class="explanation">{row.explanation}</p>
  <a class="amazon-link" href="{row.amazon_url}" target="_blank">View on Amazon →</a>
</div>"""

    # ── Utility ───────────────────────────────────────────────────────────────

    @staticmethod
    def _find_snapshot_near(
        snapshots: list[DailyMetrics], target_date: date
    ) -> Optional[DailyMetrics]:
        """Find the snapshot closest to target_date (within ±2 days)."""
        best = None
        best_delta = timedelta(days=3)
        for snap in snapshots:
            delta = abs(snap.date - target_date)
            if delta < best_delta:
                best_delta = delta
                best = snap
        return best
