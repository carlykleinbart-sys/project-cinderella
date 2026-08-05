"""Abstract base for all alert senders."""
from __future__ import annotations

from abc import ABC, abstractmethod

from reports.report_models import DailyReport


class BaseAlert(ABC):
    """Every alert channel implements this interface."""

    name: str = "unnamed"

    @abstractmethod
    def is_configured(self) -> bool:
        """Return True if the required credentials/URLs are set."""
        ...

    @abstractmethod
    def send(self, report: DailyReport) -> None:
        """Send the alert.  Raise on failure."""
        ...

    def send_safe(self, report: DailyReport) -> bool:
        """Send, catching and logging exceptions.  Returns success bool."""
        from loguru import logger
        if not self.is_configured():
            logger.debug("{} alert not configured — skipping", self.name)
            return False
        try:
            self.send(report)
            logger.info("{} alert sent", self.name)
            return True
        except Exception:
            logger.exception("{} alert failed", self.name)
            return False
