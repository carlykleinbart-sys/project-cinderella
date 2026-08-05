"""AlertManager — send the daily report to all configured channels."""
from __future__ import annotations

from loguru import logger

from alerts.discord_alert import DiscordAlert
from alerts.email_alert import EmailAlert
from alerts.slack_alert import SlackAlert
from reports.report_models import DailyReport


class AlertManager:
    """
    Sends a :class:`DailyReport` to every configured alert channel.

    Only sends if the report contains alerts or high-momentum books above
    the configured threshold.

    Usage
    -----
        manager = AlertManager()
        manager.send_all(report)
    """

    def __init__(self) -> None:
        self._channels = [EmailAlert(), DiscordAlert(), SlackAlert()]

    def send_all(self, report: DailyReport) -> dict[str, bool]:
        """
        Dispatch the report to all configured channels.

        Returns a dict of {channel_name: success} for observability.
        """
        if not report.books:
            logger.info("No books in report — skipping alerts")
            return {}

        results: dict[str, bool] = {}
        for channel in self._channels:
            results[channel.name] = channel.send_safe(report)

        sent = sum(results.values())
        logger.info("Alerts dispatched: {}/{} channels succeeded", sent, len(results))
        return results
