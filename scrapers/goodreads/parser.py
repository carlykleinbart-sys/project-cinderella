"""
GoodreadsParser — HTML parsing for Goodreads book pages and search results.

Goodreads removed their public API in December 2020.  All data is gathered
by parsing their public-facing HTML, which is stable server-rendered markup.

Parsed data
-----------
Search results page  →  list of GoodreadsSearchResult
Book page            →  GoodreadsBookData
"""
from __future__ import annotations

import re
from typing import Optional, TypedDict

from bs4 import BeautifulSoup
from loguru import logger


class GoodreadsSearchResult(TypedDict):
    goodreads_id: str
    goodreads_url: str
    title: str
    author: str


class GoodreadsBookData(TypedDict):
    goodreads_id: str
    goodreads_url: str
    title: str
    author: str
    average_rating: Optional[float]
    ratings_count: Optional[int]
    reviews_count: Optional[int]
    want_to_read_count: Optional[int]
    description: Optional[str]
    genres: list[str]
    page_count: Optional[int]
    published_year: Optional[int]


class GoodreadsParser:
    """Stateless parser for Goodreads HTML pages."""

    BASE_URL = "https://www.goodreads.com"

    # ── Search results ────────────────────────────────────────────────────────

    @staticmethod
    def parse_search_results(html: str) -> list[GoodreadsSearchResult]:
        """
        Parse a Goodreads search results page.

        Returns up to 20 results (one page), ordered as Goodreads delivers them.
        """
        soup = BeautifulSoup(html, "html.parser")
        results: list[GoodreadsSearchResult] = []

        # Primary selector: table rows in search results
        for row in soup.select("tr[itemtype='http://schema.org/Book']"):
            try:
                result = GoodreadsParser._parse_search_row(row)
                if result:
                    results.append(result)
            except Exception as exc:
                logger.debug("Failed to parse search row: {}", exc)

        # Fallback: newer React-rendered list items
        if not results:
            for item in soup.select(".BookListItem, .bookTitle"):
                try:
                    result = GoodreadsParser._parse_search_item_fallback(item)
                    if result:
                        results.append(result)
                except Exception:
                    pass

        logger.debug("Parsed {} Goodreads search results", len(results))
        return results

    @staticmethod
    def _parse_search_row(row: BeautifulSoup) -> Optional[GoodreadsSearchResult]:
        link = row.select_one("a.bookTitle, a[href*='/book/show/']")
        if not link:
            return None

        href = link.get("href", "")
        gr_id = GoodreadsParser._extract_goodreads_id(href)
        if not gr_id:
            return None

        title_el = row.select_one("span[itemprop='name']") or link
        title = title_el.get_text(strip=True)

        author_el = row.select_one("span[itemprop='author'] .authorName span[itemprop='name']")
        author = author_el.get_text(strip=True) if author_el else ""

        return GoodreadsSearchResult(
            goodreads_id=gr_id,
            goodreads_url=f"https://www.goodreads.com{href}" if href.startswith("/") else href,
            title=title,
            author=author,
        )

    @staticmethod
    def _parse_search_item_fallback(item: BeautifulSoup) -> Optional[GoodreadsSearchResult]:
        link = item.select_one("a[href*='/book/show/']") or item
        href = link.get("href", "") if hasattr(link, "get") else ""
        gr_id = GoodreadsParser._extract_goodreads_id(href)
        if not gr_id:
            return None
        title = link.get_text(strip=True)
        return GoodreadsSearchResult(
            goodreads_id=gr_id,
            goodreads_url=f"https://www.goodreads.com{href}",
            title=title,
            author="",
        )

    # ── Book detail page ──────────────────────────────────────────────────────

    @staticmethod
    def parse_book_page(html: str, goodreads_url: str) -> Optional[GoodreadsBookData]:
        """
        Parse a Goodreads book detail page (/book/show/<id>).

        Returns ``None`` if the page doesn't contain recognisable book data.
        """
        soup = BeautifulSoup(html, "html.parser")

        gr_id = GoodreadsParser._extract_goodreads_id(goodreads_url)
        if not gr_id:
            return None

        title = GoodreadsParser._parse_gr_title(soup)
        if not title:
            logger.debug("Could not extract title from Goodreads page: {}", goodreads_url)
            return None

        author      = GoodreadsParser._parse_gr_author(soup)
        avg_rating  = GoodreadsParser._parse_gr_avg_rating(soup)
        ratings     = GoodreadsParser._parse_gr_ratings_count(soup)
        reviews     = GoodreadsParser._parse_gr_reviews_count(soup)
        want_to_read= GoodreadsParser._parse_gr_want_to_read(soup)
        description = GoodreadsParser._parse_gr_description(soup)
        genres      = GoodreadsParser._parse_gr_genres(soup)
        pages       = GoodreadsParser._parse_gr_pages(soup)
        pub_year    = GoodreadsParser._parse_gr_pub_year(soup)

        return GoodreadsBookData(
            goodreads_id=gr_id,
            goodreads_url=goodreads_url,
            title=title,
            author=author,
            average_rating=avg_rating,
            ratings_count=ratings,
            reviews_count=reviews,
            want_to_read_count=want_to_read,
            description=description,
            genres=genres,
            page_count=pages,
            published_year=pub_year,
        )

    # ── Book page sub-parsers ─────────────────────────────────────────────────

    @staticmethod
    def _parse_gr_title(soup: BeautifulSoup) -> Optional[str]:
        # New GR layout (2023+)
        for sel in [
            "h1[data-testid='bookTitle']",
            "h1.Text__title1",
            "#bookTitle",
            "h1.gr-h1",
        ]:
            el = soup.select_one(sel)
            if el:
                return el.get_text(strip=True)
        return None

    @staticmethod
    def _parse_gr_author(soup: BeautifulSoup) -> str:
        for sel in [
            "span.ContributorLink__name",
            ".authorName span[itemprop='name']",
            "[itemprop='author'] [itemprop='name']",
        ]:
            el = soup.select_one(sel)
            if el:
                return el.get_text(strip=True)
        return "Unknown"

    @staticmethod
    def _parse_gr_avg_rating(soup: BeautifulSoup) -> Optional[float]:
        for sel in [
            "div.RatingStatistics__rating",
            "#bookMeta span[itemprop='ratingValue']",
            "span.average",
        ]:
            el = soup.select_one(sel)
            if el:
                text = re.sub(r"[^0-9.]", "", el.get_text())
                try:
                    v = float(text)
                    return v if 0 < v <= 5 else None
                except ValueError:
                    pass
        return None

    @staticmethod
    def _parse_gr_ratings_count(soup: BeautifulSoup) -> Optional[int]:
        for sel in [
            "span[data-testid='ratingsCount']",
            "#bookMeta span[itemprop='ratingCount']",
            "span.votes",
        ]:
            el = soup.select_one(sel)
            if el:
                return GoodreadsParser._parse_count(el.get_text())
        return None

    @staticmethod
    def _parse_gr_reviews_count(soup: BeautifulSoup) -> Optional[int]:
        for sel in [
            "span[data-testid='reviewsCount']",
            "#bookMeta span[itemprop='reviewCount']",
        ]:
            el = soup.select_one(sel)
            if el:
                return GoodreadsParser._parse_count(el.get_text())
        return None

    @staticmethod
    def _parse_gr_want_to_read(soup: BeautifulSoup) -> Optional[int]:
        """
        'Want to Read' count — the most powerful breakout leading indicator.

        This appears in the shelf statistics section as the count for the
        'to-read' shelf.
        """
        for pattern in [
            r"([\d,]+)\s+people want to read",
            r"want to read[^0-9]*([\d,]+)",
        ]:
            m = re.search(pattern, soup.get_text(), re.IGNORECASE)
            if m:
                return GoodreadsParser._parse_count(m.group(1))

        # Try shelf stats table
        for el in soup.select(".shelfStat, [data-shelf='to-read']"):
            m = re.search(r"[\d,]+", el.get_text())
            if m:
                return GoodreadsParser._parse_count(m.group())

        return None

    @staticmethod
    def _parse_gr_description(soup: BeautifulSoup) -> Optional[str]:
        for sel in [
            "div[data-testid='description']",
            "#description span:not([style*='display:none'])",
            ".readable.stacked span",
        ]:
            el = soup.select_one(sel)
            if el:
                text = el.get_text(" ", strip=True)
                if len(text) > 30:
                    return text[:3000]
        return None

    @staticmethod
    def _parse_gr_genres(soup: BeautifulSoup) -> list[str]:
        genres: list[str] = []
        for el in soup.select(".BookPageMetadataSection__genres a, .left.genre a, .elementList .left a"):
            g = el.get_text(strip=True)
            if g and g not in genres:
                genres.append(g)
            if len(genres) >= 5:
                break
        return genres

    @staticmethod
    def _parse_gr_pages(soup: BeautifulSoup) -> Optional[int]:
        for sel in ["span[data-testid='pagesFormat']", "span[itemprop='numberOfPages']"]:
            el = soup.select_one(sel)
            if el:
                m = re.search(r"(\d+)\s+pages", el.get_text(), re.IGNORECASE)
                if m:
                    return int(m.group(1))
        return None

    @staticmethod
    def _parse_gr_pub_year(soup: BeautifulSoup) -> Optional[int]:
        for sel in ["div[data-testid='publicationInfo']", "#details .row"]:
            el = soup.select_one(sel)
            if el:
                m = re.search(r"\b(19|20)\d{2}\b", el.get_text())
                if m:
                    return int(m.group())
        return None

    # ── Utilities ─────────────────────────────────────────────────────────────

    @staticmethod
    def _extract_goodreads_id(url_or_path: str) -> Optional[str]:
        """Extract the numeric Goodreads book ID from a URL or path."""
        m = re.search(r"/book/show/(\d+)", url_or_path)
        return m.group(1) if m else None

    @staticmethod
    def _parse_count(text: str) -> Optional[int]:
        """Parse '1,234 ratings' → 1234."""
        clean = re.sub(r"[^0-9]", "", text.split()[0] if text.strip() else "")
        try:
            return int(clean) if clean else None
        except ValueError:
            return None

    @staticmethod
    def build_search_url(title: str, author: str) -> str:
        """Build a Goodreads search URL for a given title and author."""
        import urllib.parse
        query = urllib.parse.quote_plus(f"{title} {author}".strip())
        return f"https://www.goodreads.com/search?q={query}&search_type=books"

    @staticmethod
    def build_book_url(goodreads_id: str) -> str:
        return f"https://www.goodreads.com/book/show/{goodreads_id}"
