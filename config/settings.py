"""
Application settings loaded from environment variables / .env file.

All secrets and tuneable parameters live here.  No hardcoded values
anywhere in the codebase — import `settings` from this module.
"""
from __future__ import annotations

from pathlib import Path
from typing import Optional

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ── Database ──────────────────────────────────────────────────────────────
    database_url: str = Field(
        ...,
        description="PostgreSQL connection URL (postgresql://user:pass@host/db)",
    )

    # ── Amazon scraping ───────────────────────────────────────────────────────
    amazon_request_delay_min: float = Field(
        2.0, description="Minimum seconds between Amazon page requests"
    )
    amazon_request_delay_max: float = Field(
        5.0, description="Maximum seconds between Amazon page requests"
    )
    amazon_max_books_per_category: int = Field(
        100, description="Maximum books to collect per bestseller category"
    )
    amazon_headless: bool = Field(
        True, description="Run Playwright browser in headless mode"
    )
    amazon_user_data_dir: Optional[str] = Field(
        None, description="Path to a Chromium user-data-dir for session reuse"
    )

    # ── Collection ────────────────────────────────────────────────────────────
    collection_schedule: str = Field(
        "0 6 * * *", description="Cron expression for the daily collection job"
    )

    # ── Alerts ────────────────────────────────────────────────────────────────
    smtp_host: Optional[str] = None
    smtp_port: int = 587
    smtp_user: Optional[str] = None
    smtp_password: Optional[str] = None
    alert_email_to: Optional[str] = None
    discord_webhook_url: Optional[str] = None
    slack_webhook_url: Optional[str] = None

    # ── Reddit API ────────────────────────────────────────────────────────────
    reddit_client_id: Optional[str] = Field(None, description="Reddit OAuth2 client ID")
    reddit_client_secret: Optional[str] = Field(None, description="Reddit OAuth2 client secret")
    reddit_user_agent: str = Field(
        "cinderella-bot/1.0 (by /u/cinderella_bot)",
        description="Reddit API user agent string (must be unique per app)",
    )

    # ── Goodreads / TikTok scraping ───────────────────────────────────────────
    goodreads_headless: bool = Field(True, description="Run Goodreads browser headless")
    tiktok_headless: bool = Field(True, description="Run TikTok browser headless")
    tiktok_max_books: int = Field(
        100, description="Max books to search on TikTok per collection run"
    )

    # ── Output ────────────────────────────────────────────────────────────────
    reports_dir: Path = Field(Path("./reports"), description="Directory for reports")

    # ── Logging ───────────────────────────────────────────────────────────────
    log_level: str = Field("INFO", description="Loguru log level")
    log_file: Optional[Path] = Field(None, description="Log file path; None → stdout only")

    @field_validator("amazon_request_delay_min", "amazon_request_delay_max")
    @classmethod
    def _positive_delay(cls, v: float) -> float:
        if v < 0:
            raise ValueError("Request delay must be non-negative")
        return v

    @field_validator("log_level")
    @classmethod
    def _upper_log_level(cls, v: str) -> str:
        return v.upper()


settings = Settings()  # type: ignore[call-arg]
