"""
AmazonParser — HTML parsing for Amazon book pages and bestseller lists.

All methods are pure functions: they accept raw HTML strings and return
typed Python dicts.  No network I/O happens here — that belongs in the
browser layer.

Parsed data
-----------
Bestseller list page  →  list of BestsellerEntry dicts
Book detail page      →  BookDetail dict
"""
from __future__ import annotations

import re
from datetime import date, datetime
from typing import Optional, TypedDict

from bs4 import BeautifulSoup
from loguru import logger


# ---------------------------------------------------------------------------
# Typed output shapes
# ---------------------------------------------------------------------------

class BestsellerEntry(TypedDict):
    """Minimal data extracted from a single row in a bestseller list."""
    rank: int
    asin: str
    title: str
    author: str
    price: Optional[float]
    star_rating: Optional[float]
    review_count: Optional[int]
    cover_url: Optional[str]


class BookDetail(TypedDict):
    """Full data extracted from an individual Amazon book page."""
    asin: str
    title: str
    subtitle: Optional[str]
    author: str
    publisher: Optional[str]
    publication_date: Optional[date]
    format: str
    kindle_unlimited: bool
    isbn: Optional[str]
    language: str
    genre: Optional[str]
    categories: list[str]
    description: Optional[str]
    cover_url: Optional[str]
    price: Optional[float]
    star_rating: Optional[float]
    review_count: Optional[int]
    amazon_best_seller_rank: Optional[int]
    category_ranks: dict[str, int]


# ---------------------------------------------------------------------------
# Parser class
# ---------------------------------------------------------------------------

class AmazonParser:
    """
    Stateless parser for Amazon HTML pages.

    All methods are ``@staticmethod`` — instantiate for namespace convenience
    or call on the class directly.
    """

    # ── Bestseller list ───────────────────────────────────────────────────────

    @staticmethod
    def parse_bestseller_list(html: str) -> list[BestsellerEntry]:
        """
        Parse an Amazon bestseller list page.

        Returns a list of :class:`BestsellerEntry` dicts, one per book,
        ordered by rank (1 = #1 bestseller).

        Handles Amazon's 2026 page structure: book cards are
        ``div[data-asin]`` elements whose class contains ``iveVideoWrapper``.
        Falls back to the older ``li.zg-item-immersion`` format, then to
        walking up from rank badges as a last resort.
        """
        soup = BeautifulSoup(html, "html.parser")
        entries: list[BestsellerEntry] = []

        # Primary: 2026 card style — div[data-asin] with iveVideoWrapper class
        items = soup.select('div[data-asin][class*="iveVideoWrapper"]')

        if not items:
            # Fallback: older list format
            items = soup.select("li.zg-item-immersion")

        if not items:
            # Last resort: walk up from rank badges to find data-asin ancestor
            seen: set[str] = set()
            for badge in soup.select("span.zg-bdg-text"):
                ancestor = badge.find_parent("div", attrs={"data-asin": True})
                if ancestor:
                    asin = ancestor.get("data-asin", "")
                    if asin and asin not in seen:
                        seen.add(asin)
                        items.append(ancestor)

        for item in items:
            try:
                entry = AmazonParser._parse_bestseller_item(item)
                if entry:
                    entries.append(entry)
            except Exception as exc:
                logger.warning("Failed to parse bestseller item: {}", exc)
                continue

        # Sort by rank ascending (sanity check)
        entries.sort(key=lambda e: e["rank"])
        logger.debug("Parsed {} bestseller entries", len(entries))
        return entries

    @staticmethod
    def _parse_bestseller_item(item: "BeautifulSoup") -> Optional[BestsellerEntry]:  # type: ignore[name-defined]
        """Parse a single item card from a bestseller list."""
        # ASIN
        asin = item.get("data-asin") or ""
        if not asin:
            link = item.select_one("a[href*='/dp/']")
            if link:
                m = re.search(r"/dp/([A-Z0-9]{10})", link["href"])
                asin = m.group(1) if m else ""
        if not asin:
            return None

        # Rank — stable class zg-bdg-text
        rank_el = item.select_one("span.zg-bdg-text")
        rank_text = rank_el.get_text(strip=True) if rank_el else ""
        rank = AmazonParser._parse_int(re.sub(r"[^0-9]", "", rank_text)) or 999

        # Title and Author — both use the p13n-sc-css-line-clamp class (first=title, second=author)
        line_clamps = item.select('[class*="p13n-sc-css-line-clamp"]')
        title = line_clamps[0].get_text(strip=True) if len(line_clamps) > 0 else "Unknown Title"
        author = line_clamps[1].get_text(strip=True) if len(line_clamps) > 1 else "Unknown Author"
        author = re.sub(r"^by\s+", "", author, flags=re.IGNORECASE).strip()

        # Rating
        rating_el = item.select_one("span.a-icon-alt")
        star_rating = AmazonParser._parse_rating(rating_el.get_text(strip=True) if rating_el else "")

        # Review count — first span.a-size-small whose text is purely numeric
        review_count: Optional[int] = None
        for el in item.select("span.a-size-small"):
            text = el.get_text(strip=True).replace(",", "")
            if text.isdigit():
                review_count = int(text)
                break

        # Price — span with p13n-sc-price in class name
        price_el = item.select_one('[class*="p13n-sc-price"]')
        price = AmazonParser._parse_price(price_el.get_text(strip=True) if price_el else "")

        # Cover image
        img_el = item.select_one("img")
        cover_url: Optional[str] = None
        if img_el:
            cover_url = img_el.get("src") or img_el.get("data-src")

        return BestsellerEntry(
            rank=rank,
            asin=asin,
            title=title,
            author=author,
            price=price,
            star_rating=star_rating,
            review_count=review_count,
            cover_url=cover_url,
        )

    # ── Book detail page ──────────────────────────────────────────────────────

    @staticmethod
    def parse_book_detail(html: str, asin: str) -> Optional[BookDetail]:
        """
        Parse an Amazon book detail page (``/dp/<ASIN>``).

        Returns a :class:`BookDetail` dict or ``None`` if the page doesn't
        contain sufficient data (e.g. region-blocked or product not found).
        """
        soup = BeautifulSoup(html, "html.parser")

        # Quick sanity check
        if soup.select_one("#productTitle") is None:
            logger.warning("No product title found for ASIN {}", asin)
            return None

        title, subtitle = AmazonParser._parse_title(soup)
        author = AmazonParser._parse_author(soup)
        pub_info = AmazonParser._parse_product_details(soup)
        bsr, category_ranks = AmazonParser._parse_ranks(soup)
        price = AmazonParser._parse_detail_price(soup)
        star_rating = AmazonParser._parse_detail_rating(soup)
        review_count = AmazonParser._parse_detail_review_count(soup)
        cover_url = AmazonParser._parse_cover(soup)
        description = AmazonParser._parse_description(soup)
        kindle_unlimited = AmazonParser._detect_kindle_unlimited(soup)
        categories = AmazonParser._parse_breadcrumbs(soup)
        genre = categories[0] if categories else None

        return BookDetail(
            asin=asin,
            title=title,
            subtitle=subtitle,
            author=author,
            publisher=pub_info.get("publisher"),
            publication_date=pub_info.get("publication_date"),
            format=pub_info.get("format", "Kindle"),
            kindle_unlimited=kindle_unlimited,
            isbn=pub_info.get("isbn"),
            language=pub_info.get("language", "en"),
            genre=genre,
            categories=categories,
            description=description,
            cover_url=cover_url,
            price=price,
            star_rating=star_rating,
            review_count=review_count,
            amazon_best_seller_rank=bsr,
            category_ranks=category_ranks,
        )

    # ── Detail page sub-parsers ───────────────────────────────────────────────

    @staticmethod
    def _parse_title(soup: BeautifulSoup) -> tuple[str, Optional[str]]:
        title_el = soup.select_one("#productTitle")
        title = title_el.get_text(strip=True) if title_el else "Unknown"

        subtitle_el = soup.select_one("#productSubtitle")
        subtitle = subtitle_el.get_text(strip=True) if subtitle_el else None
        if not subtitle:
            # Some pages embed subtitle after a colon in the title
            if ": " in title:
                parts = title.split(": ", 1)
                title, subtitle = parts[0], parts[1]

        return title, subtitle

    @staticmethod
    def _parse_author(soup: BeautifulSoup) -> str:
        # Try the structured author block first
        author_el = soup.select_one(".author .a-link-normal, #bylineInfo .author .contributorNameID")
        if author_el:
            return author_el.get_text(strip=True)
        # Fallback: first link in byline
        byline = soup.select_one("#bylineInfo")
        if byline:
            return byline.get_text(strip=True)[:200]
        return "Unknown Author"

    @staticmethod
    def _parse_product_details(soup: BeautifulSoup) -> dict:
        """Extract publisher, date, ISBN, language, format from the details table."""
        result: dict = {}

        # New-style detail bullets
        detail_list = soup.select("#detailBullets_feature_div li, #productDetails_feature_div li")
        for li in detail_list:
            text = li.get_text(" ", strip=True)
            AmazonParser._extract_detail_field(text, result)

        # Older table style
        rows = soup.select("#productDetailsTable tr, .content-grid-block table tr")
        for row in rows:
            cells = row.find_all("td")
            if len(cells) >= 2:
                text = cells[0].get_text(strip=True) + " " + cells[1].get_text(strip=True)
                AmazonParser._extract_detail_field(text, result)

        return result

    @staticmethod
    def _extract_detail_field(text: str, result: dict) -> None:
        """Parse a single key: value detail string into result dict."""
        lower = text.lower()

        if "publisher" in lower or "publication" in lower:
            # Extract publisher name (before the date parenthetical)
            # Amazon uses U+200E (left-to-right mark) around colons
            m = re.search(r"Publisher[\s‎:]+([A-Za-z][^(;\n]+)", text, re.IGNORECASE)
            if m:
                result["publisher"] = m.group(1).strip()
            # Extract date
            date_m = re.search(r"\(([A-Za-z]+\s+\d{1,2},\s+\d{4})\)", text)
            if date_m:
                try:
                    result["publication_date"] = datetime.strptime(
                        date_m.group(1), "%B %d, %Y"
                    ).date()
                except ValueError:
                    pass

        if "isbn-13" in lower or "isbn13" in lower:
            m = re.search(r"978[\d\-]{10,}", text)
            if m:
                result["isbn"] = re.sub(r"[^0-9]", "", m.group())

        if "isbn-10" in lower and "isbn" not in result:
            m = re.search(r"\b[\dX]{10}\b", text)
            if m:
                result["isbn"] = m.group()

        if "language" in lower:
            m = re.search(r"Language\s*[:‎]+\s*(\w+)", text, re.IGNORECASE)
            if m:
                lang = m.group(1).strip().lower()
                result["language"] = "en" if lang.startswith("eng") else lang

        if "format" in lower or "file size" in lower or "print length" in lower:
            if "kindle" in lower:
                result["format"] = "Kindle"
            elif "paperback" in lower:
                result["format"] = "Paperback"
            elif "hardcover" in lower:
                result["format"] = "Hardcover"
            elif "audio" in lower:
                result["format"] = "Audiobook"

    @staticmethod
    def _parse_ranks(soup: BeautifulSoup) -> tuple[Optional[int], dict[str, int]]:
        """Return (overall_BSR, {category_name: rank})."""
        overall_bsr: Optional[int] = None
        category_ranks: dict[str, int] = {}

        # Look for "Best Sellers Rank" in detail bullets
        for el in soup.select("#detailBullets_feature_div li, #SalesRank"):
            text = el.get_text(" ", strip=True)
            if "Best Sellers Rank" not in text and "Amazon Best Sellers Rank" not in text:
                continue

            # Overall rank: first number after "#"
            overall_m = re.search(r"#([\d,]+)\s+in\s+Kindle Store", text)
            if overall_m:
                overall_bsr = AmazonParser._parse_int(overall_m.group(1).replace(",", ""))

            # Category ranks: "#N in Category Name"
            for cat_m in re.finditer(r"#([\d,]+)\s+in\s+([^\(#\n]+)", text):
                rank_str, cat_name = cat_m.group(1), cat_m.group(2).strip()
                rank_val = AmazonParser._parse_int(rank_str.replace(",", ""))
                if rank_val:
                    category_ranks[cat_name] = rank_val

        return overall_bsr, category_ranks

    @staticmethod
    def _parse_detail_price(soup: BeautifulSoup) -> Optional[float]:
        for selector in [
            ".kindle-price .a-size-base.a-color-price",
            "#kindle-price",
            ".a-color-price",
            "#priceblock_ourprice",
        ]:
            el = soup.select_one(selector)
            if el:
                price = AmazonParser._parse_price(el.get_text(strip=True))
                if price is not None:
                    return price
        return None

    @staticmethod
    def _parse_detail_rating(soup: BeautifulSoup) -> Optional[float]:
        el = soup.select_one("#acrPopover span.a-icon-alt, #averageCustomerReviews span.a-icon-alt")
        return AmazonParser._parse_rating(el.get_text(strip=True) if el else "")

    @staticmethod
    def _parse_detail_review_count(soup: BeautifulSoup) -> Optional[int]:
        el = soup.select_one("#acrCustomerReviewText, #ratings-count")
        if el:
            return AmazonParser._parse_int(re.sub(r"[^0-9]", "", el.get_text()))
        return None

    @staticmethod
    def _parse_cover(soup: BeautifulSoup) -> Optional[str]:
        for selector in ["#imgBlkFront", "#ebooksImgBlkFront", "#main-image", "#landingImage"]:
            el = soup.select_one(selector)
            if el:
                return el.get("data-a-dynamic-image", "").split('"')[1] if el.get("data-a-dynamic-image") else el.get("src")
        return None

    @staticmethod
    def _parse_description(soup: BeautifulSoup) -> Optional[str]:
        for selector in ["#bookDescription_feature_div noscript", "#productDescription p", "#drengr-bookDescription_feature_div"]:
            el = soup.select_one(selector)
            if el:
                text = el.get_text(" ", strip=True)
                if len(text) > 50:
                    return text[:5000]  # cap at 5k chars
        return None

    @staticmethod
    def _parse_breadcrumbs(soup: BeautifulSoup) -> list[str]:
        """Extract category breadcrumb as a list of strings."""
        categories: list[str] = []
        for el in soup.select("#wayfinding-breadcrumbs_feature_div li a, .a-breadcrumb li a"):
            cat = el.get_text(strip=True)
            if cat and cat not in ("Kindle Store", "›"):
                categories.append(cat)
        return categories

    @staticmethod
    def _detect_kindle_unlimited(soup: BeautifulSoup) -> bool:
        """Return True if the page shows a Kindle Unlimited borrow button."""
        ku_signals = ["kindle unlimited", "borrow for free", "ku-lending"]
        text = soup.get_text().lower()
        return any(s in text for s in ku_signals)

    # ── Utility ───────────────────────────────────────────────────────────────

    @staticmethod
    def _parse_price(text: str) -> Optional[float]:
        m = re.search(r"\$([\d]+\.[\d]{2})", text)
        if m:
            try:
                return float(m.group(1))
            except ValueError:
                pass
        return None

    @staticmethod
    def _parse_rating(text: str) -> Optional[float]:
        """Parse '4.6 out of 5 stars' → 4.6"""
        m = re.search(r"([\d.]+)\s+out of\s+5", text)
        if m:
            try:
                val = float(m.group(1))
                return val if 0 <= val <= 5 else None
            except ValueError:
                pass
        return None

    @staticmethod
    def _parse_int(text: str) -> Optional[int]:
        try:
            clean = re.sub(r"[^0-9]", "", text)
            return int(clean) if clean else None
        except (ValueError, TypeError):
            return None
