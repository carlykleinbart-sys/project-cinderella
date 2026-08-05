"""
TikTok (BookTok) parser.

TikTok does not have a public API and aggressively blocks scraping.
We use a light-touch approach: scrape the public search results page
(https://www.tiktok.com/search?q=...) which renders enough data in the
initial HTML/JSON payload (the __UNIVERSAL_DATA_FOR_REHYDRATION__ script
block) without requiring a login.

When that payload is missing (e.g. bot detection), we fall back to
heuristic extraction from whatever HTML is available.

Data captured per video mention
--------------------------------
- video_id (TikTok's unique video identifier)
- author_handle
- description (caption text)
- view_count
- like_count
- comment_count
- share_count
- created_at (approximate, from embed metadata)
- url
"""
from __future__ import annotations

import json
import re
from datetime import datetime
from typing import Optional, TypedDict

from loguru import logger


class TikTokVideoMention(TypedDict, total=False):
    video_id: str
    author_handle: str
    description: str
    view_count: Optional[int]
    like_count: Optional[int]
    comment_count: Optional[int]
    share_count: Optional[int]
    created_at: Optional[datetime]
    url: str


class TikTokParser:
    """Parse TikTok search result pages for book mentions."""

    SEARCH_BASE = "https://www.tiktok.com/search?q={query}&type=video"

    @classmethod
    def build_search_url(cls, query: str) -> str:
        import urllib.parse
        return cls.SEARCH_BASE.format(query=urllib.parse.quote(query))

    @classmethod
    def parse_search_results(cls, html: str, query: str = "") -> list[TikTokVideoMention]:
        """
        Parse TikTok search results page.
        Tries JSON payload first, then falls back to regex extraction.
        """
        results = cls._parse_json_payload(html)
        if not results:
            results = cls._parse_html_fallback(html)

        logger.debug("TikTok: {} mentions found for '{}'", len(results), query)
        return results

    # ── JSON payload (primary path) ───────────────────────────────────────────

    @classmethod
    def _parse_json_payload(cls, html: str) -> list[TikTokVideoMention]:
        """Extract from __UNIVERSAL_DATA_FOR_REHYDRATION__ script block."""
        pattern = r"__UNIVERSAL_DATA_FOR_REHYDRATION__\s*=\s*(\{.*?\});\s*</script>"
        match = re.search(pattern, html, re.DOTALL)
        if not match:
            # Also try SIGI_STATE (older TikTok layout)
            match = re.search(r"SIGI_STATE\s*=\s*(\{.*?\});\s*</script>", html, re.DOTALL)
        if not match:
            return []

        try:
            data = json.loads(match.group(1))
        except json.JSONDecodeError:
            return []

        # Navigate to video items — structure varies by TikTok version
        items = (
            cls._dig(data, "itemList")
            or cls._dig(data, "__DEFAULT_SCOPE__", "webapp.search-result-list", "itemList")
            or cls._dig(data, "VideoFeedData", "itemList")
            or []
        )

        return [m for item in items if (m := cls._parse_item(item)) is not None]

    @classmethod
    def _parse_item(cls, item: dict) -> Optional[TikTokVideoMention]:
        try:
            video_id = str(item.get("id", ""))
            if not video_id:
                return None

            author = item.get("author", {})
            handle = author.get("uniqueId", author.get("nickname", ""))

            stats = item.get("stats", {})
            desc = item.get("desc", "")

            create_time = item.get("createTime")
            created_at = datetime.fromtimestamp(int(create_time)) if create_time else None

            return TikTokVideoMention(
                video_id=video_id,
                author_handle=handle,
                description=desc,
                view_count=cls._to_int(stats.get("playCount")),
                like_count=cls._to_int(stats.get("diggCount")),
                comment_count=cls._to_int(stats.get("commentCount")),
                share_count=cls._to_int(stats.get("shareCount")),
                created_at=created_at,
                url=f"https://www.tiktok.com/@{handle}/video/{video_id}",
            )
        except Exception as exc:
            logger.debug("Could not parse TikTok item: {}", exc)
            return None

    # ── HTML fallback ─────────────────────────────────────────────────────────

    @classmethod
    def _parse_html_fallback(cls, html: str) -> list[TikTokVideoMention]:
        """Best-effort extraction when JSON payload is absent."""
        results = []

        # Match video URLs embedded in the HTML
        video_pattern = re.compile(
            r'href="https://www\.tiktok\.com/@([^/]+)/video/(\d+)"'
        )
        seen: set[str] = set()

        for handle, vid_id in video_pattern.findall(html):
            if vid_id in seen:
                continue
            seen.add(vid_id)
            results.append(
                TikTokVideoMention(
                    video_id=vid_id,
                    author_handle=handle,
                    description="",
                    url=f"https://www.tiktok.com/@{handle}/video/{vid_id}",
                )
            )

        return results[:20]  # cap fallback results

    # ── Utilities ─────────────────────────────────────────────────────────────

    @staticmethod
    def _dig(data: dict, *keys: str):
        """Safe nested dict access."""
        cur = data
        for k in keys:
            if not isinstance(cur, dict):
                return None
            cur = cur.get(k)
        return cur

    @staticmethod
    def _to_int(val) -> Optional[int]:
        try:
            return int(val)
        except (TypeError, ValueError):
            return None
