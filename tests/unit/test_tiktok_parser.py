"""Unit tests for the TikTok parser."""
import json
import pytest
from scrapers.tiktok.parser import TikTokParser
from scrapers.tiktok.search_terms import build_search_terms


# ── Fixtures: static HTML / JSON payloads ─────────────────────────────────────

def _make_universal_data(items: list) -> str:
    """Wrap items in a __UNIVERSAL_DATA_FOR_REHYDRATION__ script block."""
    payload = {
        "__DEFAULT_SCOPE__": {
            "webapp.search-result-list": {
                "itemList": items
            }
        }
    }
    return f'<script>window.__UNIVERSAL_DATA_FOR_REHYDRATION__ = {json.dumps(payload)};</script>'


SAMPLE_ITEM = {
    "id": "7123456789",
    "author": {"uniqueId": "bookluver99", "nickname": "Book Lover"},
    "desc": "You NEED to read The Housemaid by Freida McFadden #booktok #thriller",
    "createTime": 1700000000,
    "stats": {
        "playCount": 250000,
        "diggCount": 18000,
        "commentCount": 430,
        "shareCount": 2100,
    },
}

VALID_HTML = _make_universal_data([SAMPLE_ITEM])

FALLBACK_HTML = """
<html><body>
<a href="https://www.tiktok.com/@reader_gal/video/111111">video 1</a>
<a href="https://www.tiktok.com/@booktok_fan/video/222222">video 2</a>
</body></html>
"""

EMPTY_HTML = "<html><body><p>No results</p></body></html>"


# ── Tests: JSON payload parsing ───────────────────────────────────────────────

class TestParseSearchResults:
    def test_parses_json_payload(self):
        results = TikTokParser.parse_search_results(VALID_HTML, "The Housemaid")
        assert len(results) == 1

    def test_extracts_video_id(self):
        results = TikTokParser.parse_search_results(VALID_HTML)
        assert results[0]["video_id"] == "7123456789"

    def test_extracts_author_handle(self):
        results = TikTokParser.parse_search_results(VALID_HTML)
        assert results[0]["author_handle"] == "bookluver99"

    def test_extracts_view_count(self):
        results = TikTokParser.parse_search_results(VALID_HTML)
        assert results[0]["view_count"] == 250_000

    def test_extracts_like_count(self):
        results = TikTokParser.parse_search_results(VALID_HTML)
        assert results[0]["like_count"] == 18_000

    def test_extracts_description(self):
        results = TikTokParser.parse_search_results(VALID_HTML)
        assert "Housemaid" in results[0]["description"]

    def test_builds_url(self):
        results = TikTokParser.parse_search_results(VALID_HTML)
        url = results[0]["url"]
        assert "tiktok.com" in url
        assert "7123456789" in url

    def test_extracts_created_at(self):
        results = TikTokParser.parse_search_results(VALID_HTML)
        assert results[0]["created_at"] is not None

    def test_empty_payload_returns_empty(self):
        results = TikTokParser.parse_search_results(EMPTY_HTML)
        assert results == []

    def test_multiple_items(self):
        html = _make_universal_data([SAMPLE_ITEM, {**SAMPLE_ITEM, "id": "9999"}])
        results = TikTokParser.parse_search_results(html)
        assert len(results) == 2


# ── Tests: HTML fallback ──────────────────────────────────────────────────────

class TestHtmlFallback:
    def test_extracts_video_ids_from_links(self):
        results = TikTokParser.parse_search_results(FALLBACK_HTML)
        assert len(results) == 2
        ids = {r["video_id"] for r in results}
        assert "111111" in ids
        assert "222222" in ids

    def test_extracts_author_handles_from_links(self):
        results = TikTokParser.parse_search_results(FALLBACK_HTML)
        handles = {r["author_handle"] for r in results}
        assert "reader_gal" in handles


# ── Tests: URL builder ────────────────────────────────────────────────────────

class TestBuildSearchUrl:
    def test_encodes_query(self):
        url = TikTokParser.build_search_url("The Housemaid")
        assert "tiktok.com" in url
        assert "Housemaid" in url or "Housemaid".replace(" ", "+") in url

    def test_returns_video_type(self):
        url = TikTokParser.build_search_url("test query")
        assert "type=video" in url


# ── Tests: search term builder ────────────────────────────────────────────────

class TestBuildSearchTerms:
    def test_returns_list(self):
        terms = build_search_terms("The Housemaid", "Freida McFadden")
        assert isinstance(terms, list)
        assert len(terms) >= 2

    def test_title_in_first_term(self):
        terms = build_search_terms("The Housemaid", "Freida McFadden")
        assert "The Housemaid" in terms[0]

    def test_handles_single_name_author(self):
        terms = build_search_terms("Dune", "Herbert")
        assert len(terms) >= 1
