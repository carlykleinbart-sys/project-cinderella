"""Slack incoming webhook alert."""
from __future__ import annotations

import json
import urllib.request

from alerts.base_alert import BaseAlert
from config import settings
from reports.report_models import DailyReport


class SlackAlert(BaseAlert):
    """Sends a Slack message via an incoming webhook."""

    name = "slack"

    def is_configured(self) -> bool:
        return bool(settings.slack_webhook_url)

    def send(self, report: DailyReport) -> None:
        url = settings.slack_webhook_url
        assert url
        payload = self._build_payload(report)
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            url,
            data=data,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=15) as resp:
            if resp.status not in (200, 204):
                raise RuntimeError(f"Slack webhook returned HTTP {resp.status}")

    @staticmethod
    def _build_payload(report: DailyReport) -> dict:
        d = report.report_date.strftime("%B %d, %Y")
        blocks = [
            {
                "type": "header",
                "text": {"type": "plain_text", "text": f"🔮 Project Cinderella — {d}"},
            },
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": (
                        f"*{report.total_indie_books}* indie books scored · "
                        f"*{report.alert_count}* alert(s)"
                    ),
                },
            },
            {"type": "divider"},
        ]

        for i, r in enumerate(report.books[:5], 1):
            rank_str = f"#{r.current_rank:,}" if r.current_rank else "N/A"
            chg = f" ▲{r.rank_7d_change:,}" if r.rank_7d_change and r.rank_7d_change > 0 else ""
            alert_prefix = "🚨 " if r.alert_triggered else ""
            blocks.append({
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": (
                        f"*{i}. {alert_prefix}<{r.amazon_url}|{r.title}>*\n"
                        f"by {r.author} · Score: *{r.momentum_score:.0f}/100* · "
                        f"Rank: {rank_str}{chg}"
                    ),
                },
            })

        return {"blocks": blocks}
