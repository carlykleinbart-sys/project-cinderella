"""
Unit tests for the report rendering logic.

We test the Markdown and HTML renderers in isolation by constructing
DailyReport / BookReportRow objects directly — no DB or scorer needed.
"""
from __future__ import annotations

from datetime import date

import pytest

from reports.report_models import BookReportRow, DailyReport


def _make_row(**kwargs) -> BookReportRow:
    defaults = dict(
        asin="B0TEST00001",
        title="The Breakout Novel",
        author="Indie Author",
        publisher="Independently Published",
        genre="Romance",
        book_age_days=45,
        kindle_unlimited=True,
        amazon_url="https://www.amazon.com/dp/B0TEST00001/",
        current_rank=15_000,
        current_sales_estimate=55,
        current_review_count=320,
        current_star_rating=4.6,
        current_price=4.99,
        rank_7d_change=18_000,
        sales_7d_change_pct=85.0,
        review_7d_new=57,
        momentum_score=78.4,
        alert_triggered=False,
        alert_reasons=[],
        explanation="This book improved 18,000 Amazon ranking positions in five days.",
        top_category_ranks={"Romance > Contemporary": 3, "Women's Fiction": 12},
    )
    defaults.update(kwargs)
    return BookReportRow(**defaults)


def _make_report(n_books: int = 5, **kwargs) -> DailyReport:
    books = [_make_row(asin=f"B0TEST{i:05d}", momentum_score=80 - i * 5) for i in range(n_books)]
    return DailyReport(
        report_date=date(2026, 8, 3),
        total_books_tracked=200,
        total_indie_books=n_books,
        books=books,
        **kwargs,
    )


class TestDailyReportModel:

    def test_top_books_returns_max_25(self):
        report = _make_report(n_books=30)
        assert len(report.top_books) == 25

    def test_top_books_fewer_than_25(self):
        report = _make_report(n_books=5)
        assert len(report.top_books) == 5

    def test_alert_count(self):
        alert_row = _make_row(alert_triggered=True, alert_reasons=["Score exceeded threshold"])
        report = _make_report()
        report.alerts = [alert_row]
        assert report.alert_count == 1

    def test_books_sorted_by_score(self):
        report = _make_report(n_books=5)
        scores = [b.momentum_score for b in report.books]
        assert scores == sorted(scores, reverse=True)


class TestMarkdownRenderer:

    def setup_method(self):
        from reports.report_generator import ReportGenerator
        import tempfile, pathlib
        self.tmp = pathlib.Path(tempfile.mkdtemp())
        self.gen = ReportGenerator(
            report_date=date(2026, 8, 3),
            output_dir=self.tmp,
        )

    def test_render_contains_title(self):
        report = _make_report()
        md = self.gen._render_markdown(report)
        assert "Project Cinderella" in md

    def test_render_contains_date(self):
        report = _make_report()
        md = self.gen._render_markdown(report)
        assert "August 03, 2026" in md

    def test_render_contains_book_title(self):
        report = _make_report(n_books=1)
        md = self.gen._render_markdown(report)
        assert "The Breakout Novel" in md

    def test_render_contains_momentum_score(self):
        report = _make_report(n_books=1)
        report.books[0].momentum_score = 78.4
        md = self.gen._render_markdown(report)
        assert "78" in md

    def test_render_alert_section_when_alerts(self):
        alert_row = _make_row(alert_triggered=True, title="Alert Book")
        report = _make_report()
        report.alerts = [alert_row]
        md = self.gen._render_markdown(report)
        assert "Alerts" in md
        assert "Alert Book" in md

    def test_render_no_alert_section_when_no_alerts(self):
        report = _make_report()
        report.alerts = []
        md = self.gen._render_markdown(report)
        assert "## 🚨 Alerts" not in md

    def test_render_amazon_link(self):
        report = _make_report(n_books=1)
        md = self.gen._render_markdown(report)
        assert "amazon.com" in md

    def test_render_rank_change_positive(self):
        report = _make_report(n_books=1)
        report.books[0].rank_7d_change = 18_000
        md = self.gen._render_markdown(report)
        assert "▲" in md or "18,000" in md


class TestHtmlRenderer:

    def setup_method(self):
        from reports.report_generator import ReportGenerator
        import tempfile, pathlib
        self.tmp = pathlib.Path(tempfile.mkdtemp())
        self.gen = ReportGenerator(
            report_date=date(2026, 8, 3),
            output_dir=self.tmp,
        )

    def test_html_is_valid_html(self):
        report = _make_report()
        html = self.gen._render_html(report)
        assert "<!DOCTYPE html>" in html
        assert "</html>" in html

    def test_html_contains_book_title(self):
        report = _make_report(n_books=1)
        html = self.gen._render_html(report)
        assert "The Breakout Novel" in html

    def test_html_contains_score(self):
        report = _make_report(n_books=1)
        report.books[0].momentum_score = 78.0
        html = self.gen._render_html(report)
        assert "78" in html

    def test_html_contains_amazon_link(self):
        report = _make_report(n_books=1)
        html = self.gen._render_html(report)
        assert 'href="https://www.amazon.com' in html

    def test_html_alert_class_for_alert_books(self):
        alert_row = _make_row(alert_triggered=True)
        report = _make_report()
        report.alerts = [alert_row]
        html = self.gen._render_html(report)
        assert 'class="card alert"' in html or "ALERT" in html


class TestBookReportRow:

    def test_ku_flag(self):
        row = _make_row(kindle_unlimited=True)
        assert row.kindle_unlimited is True

    def test_rank_delta_positive(self):
        row = _make_row(rank_7d_change=10_000)
        assert row.rank_7d_change == 10_000

    def test_none_rank_ok(self):
        row = _make_row(current_rank=None, rank_7d_change=None)
        assert row.current_rank is None
