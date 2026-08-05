"""Discord webhook alert — posts an embed for each high-momentum book."""
from __future__ import annotations

import json
import urllib.request
from urllib.error import URLError

from loguru import logger

from alerts.base_alert import BaseAlert
from config import settings
from reports.report_models import BookReportRow, DailyReport


class DiscordAlert(BaseAlert):
    """Sends top books as Discord embeds via an incoming webhook."""

    name = "discord"
    MAX_BOOKS_PER_MESSAGE = 5

    def is_configured(self) -> bool:
        return bool(settings.discord_webhook_url)

    def send(self, report: DailyReport) -> None:
        url = settings.discord_webhook_url
        assert url  # guarded by is_configured

        # Alert message first
        if report.alerts:
            payload = self._build_alert_payload(report)
            self._post(url, payload)

        # Top books embed
        top = report.books[: self.MAX_BOOKS_PER_MESSAGE]
        payload = self._build_top_books_payload(report, top)
        self._post(url, payload)

    # ── Payload builders ──────────────────────────────────────────────────────

    @staticmethod
    def _build_alert_payload(report: DailyReport) -> dict:
        embeds = []
        for r in report.alerts[:3]:
            rank_str = f"#{r.current_rank:,}" if r.current_rank else "N/A"
            chg = f" (▲{r.rank_7d_change:,})" if r.rank_7d_change and r.rank_7d_change > 0 else ""
            embeds.append({
                "title": f"🚨 {r.title}",
                "description": r.explanation,
                "url": r.amazon_url,
                "color": 0xF59E0B,
                "fields": [
                    {"name": "Author", "value": r.author, "inline": True},
                    {"name": "Momentum", "value": f"{r.momentum_score:.0f}/100", "inline": True},
                    {"name": "Amazon Rank", "value": f"{rank_str}{chg}", "inline": True},
                ],
            })
        d = report.report_date.strftime("%B %d, %Y")
        return {
            "content": f"🔮 **Project Cinderella Alert** — {d}",
            "embeds": embeds,
        }

    @staticmethod
    def _build_top_books_payload(report: DailyReport, books: list[BookReportRow]) -> dict:
        fields = []
        for i, r in enumerate(books, 1):
            rank_str = f"#{r.current_rank:,}" if r.current_rank else "N/A"
            chg = f" ▲{r.rank_7d_change:,}" if r.rank_7d_change and r.rank_7d_change > 0 else ""
            fields.append({
                "name": f"#{i} · {r.title[:50]}",
                "value": f"by {r.author} | Score: **{r.momentum_score:.0f}** | {rank_str}{chg}",
                "inline": False,
            })
        d = report.report_date.strftime("%B %d, %Y")
        return {
            "embeds": [{
                "title": f"🔮 Top Breakout Candidates — {d}",
                "color": 0x7C3AED,
                "fields": fields,
                "footer": {"text": f"{report.total_indie_books} indie books tracked"},
            }]
        }

    @staticmethod
    def _post(url: str, payload: dict) -> None:
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            url,
            data=data,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=15) as resp:
            if resp.status not in (200, 204):
                raise RuntimeError(f"Discord webhook returned HTTP {resp.status}")
