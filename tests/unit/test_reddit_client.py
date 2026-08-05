"""Unit tests for the Reddit client.

praw is not installed in the test environment.  We inject a fake module into
sys.modules before importing RedditClient so the lazy `import praw` inside
RedditClient.__init__ picks up the mock.
"""
import sys
from datetime import datetime, timezone
from types import ModuleType
from unittest.mock import MagicMock

import pytest


# ---------------------------------------------------------------------------
# Inject a fake 'praw' module before any import of the real client
# ---------------------------------------------------------------------------

def _make_fake_praw() -> ModuleType:
    """Return a minimal fake praw module."""
    fake = ModuleType("praw")
    fake.Reddit = MagicMock()  # class-level mock; instances are MagicMock()
    return fake


# Patch sys.modules so the lazy `import praw` inside __init__ gets the mock
_fake_praw = _make_fake_praw()
sys.modules.setdefault("praw", _fake_praw)

# Now it's safe to import our client
from scrapers.reddit.client import RedditClient, DEFAULT_SUBREDDITS  # noqa: E402


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_submission(
    id: str = "abc123",
    title: str = "The Housemaid is incredible",
    selftext: str = "Just finished The Housemaid and wow",
    author_name: str = "redditor42",
    score: int = 250,
    num_comments: int = 40,
    created_utc: float = 1700000000.0,
    url: str = "https://reddit.com/r/books/comments/abc123",
) -> MagicMock:
    sub = MagicMock()
    sub.id = id
    sub.title = title
    sub.selftext = selftext
    sub.author = MagicMock()
    sub.author.__str__ = lambda _: author_name
    sub.score = score
    sub.num_comments = num_comments
    sub.created_utc = created_utc
    sub.url = url
    return sub


def _make_client(subreddits=None) -> tuple[RedditClient, MagicMock]:
    """Build a RedditClient backed by a fresh MagicMock reddit instance."""
    mock_reddit = MagicMock()
    _fake_praw.Reddit.return_value = mock_reddit
    client = RedditClient(
        client_id="fake_id",
        client_secret="fake_secret",
        user_agent="test-agent/1.0",
        subreddits=subreddits or ["books"],
        search_limit=5,
    )
    # Ensure it uses our mock (in case constructor caching is weird)
    client._reddit = mock_reddit
    return client, mock_reddit


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestRedditClientSearchBook:
    def test_returns_matching_posts(self):
        client, mock_reddit = _make_client()
        sub = _make_submission(title="The Housemaid is great", selftext="The Housemaid blew me away")
        mock_sub = MagicMock()
        mock_sub.search.return_value = [sub]
        mock_reddit.subreddit.return_value = mock_sub

        results = client.search_book("The Housemaid", "Freida McFadden")
        assert len(results) >= 1

    def test_filters_irrelevant_posts(self):
        """Posts that don't mention the title should be excluded."""
        client, mock_reddit = _make_client()
        sub = _make_submission(
            title="What's everyone reading?",
            selftext="Looking for romance recs please!",
        )
        mock_sub = MagicMock()
        mock_sub.search.return_value = [sub]
        mock_reddit.subreddit.return_value = mock_sub

        results = client.search_book("The Housemaid", "Freida McFadden")
        assert results == []

    def test_deduplicates_same_post_id(self):
        """Same post ID returned from two queries should appear only once."""
        client, mock_reddit = _make_client()
        sub = _make_submission(title="The Housemaid", selftext="The Housemaid is amazing")
        mock_sub = MagicMock()
        mock_sub.search.return_value = [sub]
        mock_reddit.subreddit.return_value = mock_sub

        results = client.search_book("The Housemaid", "Freida McFadden")
        ids = [r["post_id"] for r in results]
        assert len(ids) == len(set(ids))

    def test_maps_fields_correctly(self):
        client, mock_reddit = _make_client()
        sub = _make_submission(
            id="xyz789",
            title="The Housemaid review",
            selftext="The Housemaid is a page turner",
            score=150,
            num_comments=22,
        )
        mock_sub = MagicMock()
        mock_sub.search.return_value = [sub]
        mock_reddit.subreddit.return_value = mock_sub

        results = client.search_book("The Housemaid", "Freida McFadden")
        assert len(results) == 1
        post = results[0]
        assert post["post_id"] == "xyz789"
        assert post["upvotes"] == 150
        assert post["comment_count"] == 22
        assert post["is_comment"] is False

    def test_handles_api_error_gracefully(self):
        client, mock_reddit = _make_client()
        mock_sub = MagicMock()
        mock_sub.search.side_effect = Exception("API rate limited")
        mock_reddit.subreddit.return_value = mock_sub

        results = client.search_book("Any Book", "Any Author")
        assert isinstance(results, list)

    def test_posted_at_is_datetime(self):
        client, mock_reddit = _make_client()
        sub = _make_submission(
            title="The Housemaid",
            selftext="The Housemaid is brilliant",
            created_utc=1700000000.0,
        )
        mock_sub = MagicMock()
        mock_sub.search.return_value = [sub]
        mock_reddit.subreddit.return_value = mock_sub

        results = client.search_book("The Housemaid", "Freida McFadden")
        assert len(results) == 1
        assert isinstance(results[0]["posted_at"], datetime)


class TestBuildQueries:
    def test_includes_exact_phrase(self):
        queries = RedditClient._build_queries("The Housemaid", "Freida McFadden")
        assert any('"The Housemaid"' in q for q in queries)

    def test_includes_last_name(self):
        queries = RedditClient._build_queries("The Housemaid", "Freida McFadden")
        assert any("McFadden" in q for q in queries)

    def test_returns_multiple_queries(self):
        queries = RedditClient._build_queries("Dune", "Frank Herbert")
        assert len(queries) >= 2


class TestDefaultSubreddits:
    def test_contains_major_book_subreddits(self):
        assert "books" in DEFAULT_SUBREDDITS
        assert "Fantasy" in DEFAULT_SUBREDDITS
        assert "Romance" in DEFAULT_SUBREDDITS
        assert "kindleunlimited" in DEFAULT_SUBREDDITS
