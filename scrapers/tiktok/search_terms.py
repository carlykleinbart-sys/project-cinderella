"""
BookTok search term templates for TikTok scraping.

Strategy: search for book title/author variants plus high-signal hashtags
that correlate with organic indie discovery (not publisher-bought promo).
"""

# High-signal hashtags for indie breakout discovery
BOOKTOK_HASHTAGS = [
    "booktok",
    "booktokcommunity",
    "indieauthor",
    "kindleunlimited",
    "selfpublished",
    "bookrecommendations",
    "romantasy",
    "darkromance",
    "thrillerbooks",
    "mysterytok",
    "fantasybooks",
    "romancebooks",
    "sapphicbooks",
]

# Hashtags that specifically signal organic word-of-mouth momentum
BREAKOUT_SIGNALS = [
    "booktokwentoffagain",
    "booktokfamousalready",
    "readthisbook",
    "currentlyreading",
    "nextread",
    "bookrec",
]


def build_search_terms(title: str, author: str) -> list[str]:
    """
    Return ranked list of search queries for a book on TikTok.
    Try most specific first; fall back to broader terms.
    """
    title_clean = title.strip()
    author_parts = author.strip().split()
    last_name = author_parts[-1] if author_parts else author

    terms = [
        f"{title_clean} {author}",         # exact title + full author
        f"{title_clean} {last_name}",       # title + last name only
        f"#{title_clean.replace(' ', '')}",  # hashtag variant
        title_clean,                         # title only
    ]
    return [t for t in terms if t.strip()]
