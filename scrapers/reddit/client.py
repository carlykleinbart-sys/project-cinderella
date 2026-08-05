"""
Reddit client for finding book mentions.

Uses PRAW (Python Reddit API Wrapper) which requires:
  - REDDIT_CLIENT_ID
  - REDDIT_CLIENT_SECRET
  - REDDIT_USER_AGENT

Reddit's API terms of service permit automated reading of public posts
with proper rate limiting (<1 req/sec for unauthenticated; 60/min for OAuth).
PRAW handles rate limiting automatically.

Subreddits monitored by default
---------------------------------
- r/books          — 23M+ members, high signal for breakout word-of-mouth
- r/Fantasy        — primary fiction discovery community
- r/Romance        — dominant for indie romance breakouts
- r/DarkRomance    — fastest-growing fiction sub; indie-first
- r/RomanceBooks   — curated, taste-making community
- r/kindleunlimited — intent-driven: readers actively seeking new reads
- r/scifi          — secondary genre signal
- r/Mystery        — secondary genre signal
- r/YAlit          — young adult crossover breakouts
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional, TypedDict

from loguru import logger


DEFAULT_SUBREDDITS = [
    "books",
    "Fantasy",
    "Romance",
    "DarkRomance",
    "RomanceBooks",
    "kindleunlimited",
    "scifi",
    "Mystery",
    "YAlit",
    "Bookclub",
    "suggestmeabook",
    "whatshouldiread",
]


class RedditPost(TypedDict, total=False):
    post_id: str
    subreddit: str
    title: str
    body: str
    author: str
    upvotes: int
    downvotes: int
    comment_count: int
    is_comment: bool
    posted_at: Optional[datetime]
    url: str


class RedditClient:
    """
    Wraps PRAW to search Reddit for book mentions.

    Parameters
    ----------
    client_id, client_secret, user_agent:
        Reddit API credentials.
    subreddits:
        List of subreddit names to search.  Defaults to DEFAULT_SUBREDDITS.
    search_limit:
        Max posts per query per subreddit.  Reddit allows max 100.
    """

    def __init__(
        self,
        client_id: str,
        client_secret: str,
        user_agent: str,
        subreddits: Optional[list[str]] = None,
        search_limit: int = 25,
    ) -> None:
        import praw as _praw

        self._reddit = _praw.Reddit(
            client_id=client_id,
            client_secret=client_secret,
            user_agent=user_agent,
            # Read-only mode — we never post or vote
            read_only=True,
        )
        self._subreddits = subreddits or DEFAULT_SUBREDDITS
        self._limit = search_limit

    def search_book(self, title: str, author: str) -> list[RedditPost]:
        """
        Search monitored subreddits for posts mentioning a book.

        Tries multiple query variants and deduplicates by post_id.
        """
        queries = self._build_queries(title, author)
        seen: set[str] = set()
        results: list[RedditPost] = []

        for subreddit_name in self._subreddits:
            subreddit = self._reddit.subreddit(subreddit_name)
            for query in queries[:2]:  # top 2 queries per subreddit
                try:
                    for submission in subreddit.search(
                        query, sort="new", time_filter="month", limit=self._limit
                    ):
                        if submission.id in seen:
                            continue
                        # Relevance check — title must appear in post title or body
                        if title.lower() not in (
                            submission.title + " " + (submission.selftext or "")
                        ).lower():
                            continue
                        seen.add(submission.id)
                        results.append(self._submission_to_post(submission, subreddit_name))
                except Exception as exc:
                    logger.warning("Reddit search error in r/{}: {}", subreddit_name, exc)

        logger.debug(
            "Reddit: {} mentions for '{}' across {} subreddits",
            len(results), title, len(self._subreddits)
        )
        return results

    # ── Helpers ───────────────────────────────────────────────────────────────

    @staticmethod
    def _build_queries(title: str, author: str) -> list[str]:
        """Return prioritized search queries."""
        author_parts = author.strip().split()
        last_name = author_parts[-1] if author_parts else author
        return [
            f'"{title}"',              # exact title phrase
            f'"{title}" {last_name}',  # title + last name
            title,                     # plain title (broadest)
        ]

    @staticmethod
    def _submission_to_post(submission, subreddit: str) -> RedditPost:
        posted_at = (
            datetime.fromtimestamp(submission.created_utc, tz=timezone.utc)
            if submission.created_utc
            else None
        )
        return RedditPost(
            post_id=submission.id,
            subreddit=subreddit,
            title=submission.title,
            body=submission.selftext or "",
            author=str(submission.author) if submission.author else "[deleted]",
            upvotes=submission.score,
            downvotes=0,  # Reddit no longer exposes raw downvotes
            comment_count=submission.num_comments,
            is_comment=False,
            posted_at=posted_at,
            url=submission.url,
        )
