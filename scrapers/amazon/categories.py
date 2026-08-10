"""
Amazon Kindle bestseller category definitions.

Each entry maps a human-readable genre name to its Amazon category node ID.
These IDs are stable but occasionally change; update here when Amazon
restructures its store.

URLs follow the pattern:
  https://www.amazon.com/gp/bestsellers/digital-text/<node_id>/

The `KINDLE_CATEGORIES` dict is used by the collector to decide which
bestseller lists to harvest.  To add a new genre, simply append an entry.
"""
from __future__ import annotations

# ---------------------------------------------------------------------------
# Category registry
# Mapping: genre label → Amazon category node ID (string)
# ---------------------------------------------------------------------------
KINDLE_CATEGORIES: dict[str, str] = {
    # Top-level
    "Kindle Overall": "154606011",

    # Romance
    "Romance": "2200031011",
    "Contemporary Romance": "6361470011",
    "Romantic Suspense": "6361472011",
    "Paranormal Romance": "6361471011",
    "Historical Romance": "6361469011",

    # Fantasy
    "Fantasy": "158591011",
    "Epic Fantasy": "6361040011",
    "Dark Fantasy": "6361038011",
    "Romantic Fantasy": "17358487011",

    # Mystery & Thriller
    "Mystery Thriller & Suspense": "172161011",
    "Psychological Thrillers": "6361139011",
    "Cozy Mysteries": "6361125011",

    # Science Fiction
    "Science Fiction": "694212011",

    # Horror
    "Horror": "6361063011",

    # Women's Fiction
    "Women's Fiction": "6361497011",

    # Young Adult
    "Teen & Young Adult": "155009011",
    "YA Romance": "16290093011",
    "YA Fantasy": "16290095011",

    # Literary Fiction
    "Literary Fiction": "6361095011",

    # New Adult & College
    "New Adult & College": "7620946011",
}

# ---------------------------------------------------------------------------
# Categories to check first — highest signal for indie breakouts
# ---------------------------------------------------------------------------
PRIORITY_CATEGORIES: list[str] = [
    "Romance",
    "Contemporary Romance",
    "Romantic Suspense",
    "Fantasy",
    "Romantic Fantasy",
    "Dark Fantasy",
    "Psychological Thrillers",
    "Women's Fiction",
    "New Adult & College",
    "YA Romance",
    "Cozy Mysteries",
]

# ---------------------------------------------------------------------------
# Base URLs
# ---------------------------------------------------------------------------
BESTSELLER_BASE_URL = "https://www.amazon.com/Best-Sellers-Kindle-Store/zgbs/digital-text/{node_id}"
BOOK_BASE_URL = "https://www.amazon.com/dp/{asin}/"
