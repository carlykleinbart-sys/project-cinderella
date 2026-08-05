"""
Amazon scraper package.

AmazonParser and KINDLE_CATEGORIES are imported eagerly (no external deps).
AmazonBrowser is imported lazily to avoid requiring Playwright in
environments where only the parser is needed (e.g., unit tests).
"""
from scrapers.amazon.parser import AmazonParser
from scrapers.amazon.categories import KINDLE_CATEGORIES

# AmazonBrowser imported on demand to keep Playwright optional in tests:
#   from scrapers.amazon.browser import AmazonBrowser

__all__ = ["AmazonParser", "KINDLE_CATEGORIES"]
