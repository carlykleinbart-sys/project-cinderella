"""SMTP email alert."""
from __future__ import annotations

import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from loguru import logger

from alerts.base_alert import BaseAlert
from config import settings
from reports.report_models import DailyReport


class EmailAlert(BaseAlert):
    """Sends the daily report via SMTP email (plain-text + HTML multipart)."""

    name = "email"

    def is_configured(self) -> bool:
        return bool(
            settings.smtp_host
            and settings.smtp_user
            and settings.smtp_password
            and settings.alert_email_to
        )

    def send(self, report: DailyReport) -> None:
        if not report.alerts and report.top_books[0].momentum_score < 50:
            logger.debug("Email: no significant activity, skipping")
            return

        subject = self._build_subject(report)
        body_text = self._build_plain_text(report)
        body_html = self._build_html_summary(report)

        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"]    = settings.smtp_user
        msg["To"]      = settings.alert_email_to
        msg.attach(MIMEText(body_text, "plain"))
        msg.attach(MIMEText(body_html, "html"))

        with smtplib.SMTP(settings.smtp_host, settings.smtp_port) as server:
            server.ehlo()
            server.starttls()
            server.login(settings.smtp_user, settings.smtp_password)
            server.sendmail(
                settings.smtp_user,
                settings.alert_email_to,
                msg.as_string(),
            )

    # ── Formatters ────────────────────────────────────────────────────────────

    @staticmethod
    def _build_subject(report: DailyReport) -> str:
        d = report.report_date.strftime("%b %d")
        if report.alerts:
            titles = ", ".join(r.title[:25] for r in report.alerts[:2])
            return f"🔮 Cinderella Alert [{d}]: {titles}"
        top = report.books[0] if report.books else None
        if top:
            return f"🔮 Cinderella [{d}]: {top.title[:40]} ({top.momentum_score:.0f}/100)"
        return f"🔮 Project Cinderella Daily Report — {d}"

    @staticmethod
    def _build_plain_text(report: DailyReport) -> str:
        d = report.report_date.strftime("%B %d, %Y")
        lines = [
            f"PROJECT CINDERELLA — {d}",
            f"{report.total_indie_books} indie books scored | {report.alert_count} alerts",
            "=" * 60,
            "",
        ]
        if report.alerts:
            lines.append("ALERTS")
            for r in report.alerts:
                lines += [
                    f"  {r.title} by {r.author}",
                    f"  Score: {r.momentum_score:.0f}/100",
                    f"  {r.explanation}",
                    "",
                ]
        lines.append("TOP 10 BY MOMENTUM SCORE")
        for i, r in enumerate(report.books[:10], 1):
            rank_str = f"#{r.current_rank:,}" if r.current_rank else "N/A"
            chg = f" (▲{r.rank_7d_change:,})" if r.rank_7d_change and r.rank_7d_change > 0 else ""
            lines.append(
                f"  {i:2}. {r.title[:45]} — {r.momentum_score:.0f}/100 "
                f"| {rank_str}{chg}"
            )
        return "\n".join(lines)

    @staticmethod
    def _build_html_summary(report: DailyReport) -> str:
        rows = ""
        for i, r in enumerate(report.books[:10], 1):
            rank = f"#{r.current_rank:,}" if r.current_rank else "—"
            chg = f" +{r.rank_7d_change:,}" if r.rank_7d_change and r.rank_7d_change > 0 else ""
            alert_bg = "#fff3cd" if r.alert_triggered else ""
            rows += f"""<tr style="background:{alert_bg}">
              <td>{i}</td>
              <td><a href="{r.amazon_url}">{r.title}</a></td>
              <td>{r.author}</td>
              <td><strong>{r.momentum_score:.0f}</strong></td>
              <td>{rank}{chg}</td>
              <td>{r.current_review_count or "—"}</td>
            </tr>"""
        d = report.report_date.strftime("%B %d, %Y")
        return f"""<html><body style="font-family:sans-serif;max-width:700px;margin:auto">
<h2>🔮 Project Cinderella — {d}</h2>
<p>{report.total_indie_books} indie books · {report.alert_count} alerts</p>
<table border="1" cellpadding="6" cellspacing="0" style="border-collapse:collapse;width:100%">
  <thead style="background:#7c3aed;color:white">
    <tr><th>#</th><th>Title</th><th>Author</th><th>Score</th><th>Rank</th><th>Reviews</th></tr>
  </thead>
  <tbody>{rows}</tbody>
</table>
</body></html>"""
