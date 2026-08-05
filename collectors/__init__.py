"""Collectors package."""
from collectors.amazon_collector import AmazonCollector
from collectors.goodreads_collector import GoodreadsCollector
from collectors.booktok_collector import BookTokCollector
from collectors.reddit_collector import RedditCollector

__all__ = ["AmazonCollector", "GoodreadsCollector", "BookTokCollector", "RedditCollector"]
