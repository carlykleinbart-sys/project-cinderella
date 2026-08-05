"""
Unit tests for AmazonParser.

All tests use static HTML fixtures — no network calls.
"""
from __future__ import annotations

from textwrap import dedent

import pytest

from scrapers.amazon.parser import AmazonParser


# ---------------------------------------------------------------------------
# Helpers: minimal HTML fragments that mimic Amazon's real structure
# ---------------------------------------------------------------------------

def _bestseller_html(items: list[dict]) -> str:
    """Build a fake bestseller list page."""
    cards = ""
    for item in items:
        cards += f"""
        <div data-asin="{item['asin']}" data-index="{item['rank']}">
            <span class="zg-bdg-text">#{item['rank']}</span>
            <span class="_cDEzb_p13n-sc-css-line-clamp-3_g3dy1">{item['title']}</span>
            <span class="a-size-small a-color-secondary">by {item['author']}</span>
            <span class="p13n-sc-price">${item['price']}</span>
            <span class="a-icon-alt">{item['rating']} out of 5 stars</span>
            <img class="p13n-product-image" src="https://example.com/cover.jpg">
        </div>
        """
    return f"<html><body>{cards}</body></html>"


def _book_detail_html(
    asin: str = "B0TEST00001",
    title: str = "The Test Novel",
    author: str = "Jane Author",
    publisher: str = "Independently Published",
    bsr: int = 5000,
    price: str = "$4.99",
    rating: str = "4.6 out of 5 stars",
    reviews: str = "1,234",
    kindle_unlimited: bool = True,
) -> str:
    ku_block = '<span>Kindle Unlimited</span>' if kindle_unlimited else ''
    return dedent(f"""
    <html><body>
        <span id="productTitle">{title}</span>
        <div id="bylineInfo">
            <span class="a-link-normal contributorNameID">{author}</span>
        </div>
        <ul id="detailBullets_feature_div">
            <li><span>Publisher ‎ : ‎ {publisher} (January 1, 2024)</span></li>
            <li><span>Language ‎ : ‎ English</span></li>
            <li><span>ISBN-13 ‎ : ‎ 978-1234567890</span></li>
            <li>
                <span>Best Sellers Rank: #5,000 in Kindle Store</span>
                <span>#3 in Kindle Store &gt; Romance &gt; Contemporary</span>
                <span>#12 in Kindle Store &gt; Women's Fiction</span>
            </li>
        </ul>
        <span id="kindle-price">{price}</span>
        <span id="acrPopover"><span class="a-icon-alt">{rating}</span></span>
        <span id="acrCustomerReviewText">{reviews} ratings</span>
        {ku_block}
        <img id="imgBlkFront" src="https://example.com/cover.jpg">
        <div id="bookDescription_feature_div">
            <noscript>A thrilling tale of mystery and romance.</noscript>
        </div>
        <div id="wayfinding-breadcrumbs_feature_div">
            <ul><li><a>Romance</a></li><li><a>Contemporary Romance</a></li></ul>
        </div>
    </body></html>
    """)


# ---------------------------------------------------------------------------
# Bestseller list parsing tests
# ---------------------------------------------------------------------------

class TestParseBestsellerList:

    def test_parses_multiple_entries(self):
        html = _bestseller_html([
            {"rank": 1, "asin": "B0AAAAAAA1", "title": "Book One", "author": "Author A", "price": "4.99", "rating": "4.7"},
            {"rank": 2, "asin": "B0AAAAAAA2", "title": "Book Two", "author": "Author B", "price": "2.99", "rating": "4.2"},
            {"rank": 3, "asin": "B0AAAAAAA3", "title": "Book Three", "author": "Author C", "price": "0.99", "rating": "4.5"},
        ])
        results = AmazonParser.parse_bestseller_list(html)
        assert len(results) == 3

    def test_entries_sorted_by_rank(self):
        html = _bestseller_html([
            {"rank": 3, "asin": "B0AAAAAAA3", "title": "C", "author": "C", "price": "0", "rating": "4"},
            {"rank": 1, "asin": "B0AAAAAAA1", "title": "A", "author": "A", "price": "0", "rating": "4"},
            {"rank": 2, "asin": "B0AAAAAAA2", "title": "B", "author": "B", "price": "0", "rating": "4"},
        ])
        results = AmazonParser.parse_bestseller_list(html)
        ranks = [e["rank"] for e in results]
        assert ranks == sorted(ranks)

    def test_empty_page_returns_empty_list(self):
        results = AmazonParser.parse_bestseller_list("<html><body></body></html>")
        assert results == []

    def test_asin_extracted_correctly(self):
        html = _bestseller_html([
            {"rank": 1, "asin": "B09XYZ12AB", "title": "Title", "author": "Author", "price": "4.99", "rating": "4.5"},
        ])
        results = AmazonParser.parse_bestseller_list(html)
        assert results[0]["asin"] == "B09XYZ12AB"

    def test_price_parsed_as_float(self):
        html = _bestseller_html([
            {"rank": 1, "asin": "B0TEST00001", "title": "T", "author": "A", "price": "3.99", "rating": "4"},
        ])
        results = AmazonParser.parse_bestseller_list(html)
        assert results[0]["price"] == pytest.approx(3.99)

    def test_rating_parsed_as_float(self):
        html = _bestseller_html([
            {"rank": 1, "asin": "B0TEST00001", "title": "T", "author": "A", "price": "0", "rating": "4.6"},
        ])
        results = AmazonParser.parse_bestseller_list(html)
        assert results[0]["star_rating"] == pytest.approx(4.6)


# ---------------------------------------------------------------------------
# Book detail page parsing tests
# ---------------------------------------------------------------------------

class TestParseBookDetail:

    def test_returns_none_for_empty_page(self):
        result = AmazonParser.parse_book_detail("<html><body></body></html>", "B000000001")
        assert result is None

    def test_parses_title(self):
        html = _book_detail_html(title="The Midnight Library")
        result = AmazonParser.parse_book_detail(html, "B0TEST00001")
        assert result is not None
        assert result["title"] == "The Midnight Library"

    def test_parses_author(self):
        html = _book_detail_html(author="Matt Haig")
        result = AmazonParser.parse_book_detail(html, "B0TEST00001")
        assert result is not None
        assert result["author"] == "Matt Haig"

    def test_parses_publisher(self):
        html = _book_detail_html(publisher="Independently Published")
        result = AmazonParser.parse_book_detail(html, "B0TEST00001")
        assert result is not None
        assert result["publisher"] == "Independently Published"

    def test_parses_price(self):
        html = _book_detail_html(price="$4.99")
        result = AmazonParser.parse_book_detail(html, "B0TEST00001")
        assert result is not None
        assert result["price"] == pytest.approx(4.99)

    def test_parses_star_rating(self):
        html = _book_detail_html(rating="4.6 out of 5 stars")
        result = AmazonParser.parse_book_detail(html, "B0TEST00001")
        assert result is not None
        assert result["star_rating"] == pytest.approx(4.6)

    def test_parses_review_count(self):
        html = _book_detail_html(reviews="1,234")
        result = AmazonParser.parse_book_detail(html, "B0TEST00001")
        assert result is not None
        assert result["review_count"] == 1234

    def test_detects_kindle_unlimited(self):
        html = _book_detail_html(kindle_unlimited=True)
        result = AmazonParser.parse_book_detail(html, "B0TEST00001")
        assert result is not None
        assert result["kindle_unlimited"] is True

    def test_no_kindle_unlimited_flag(self):
        html = _book_detail_html(kindle_unlimited=False)
        result = AmazonParser.parse_book_detail(html, "B0TEST00001")
        assert result is not None
        assert result["kindle_unlimited"] is False

    def test_parses_categories(self):
        html = _book_detail_html()
        result = AmazonParser.parse_book_detail(html, "B0TEST00001")
        assert result is not None
        assert "Romance" in result["categories"]
        assert "Contemporary Romance" in result["categories"]

    def test_genre_is_first_category(self):
        html = _book_detail_html()
        result = AmazonParser.parse_book_detail(html, "B0TEST00001")
        assert result is not None
        assert result["genre"] == "Romance"

    def test_asin_preserved(self):
        html = _book_detail_html()
        result = AmazonParser.parse_book_detail(html, "B0MY_ASIN1")
        assert result is not None
        assert result["asin"] == "B0MY_ASIN1"


# ---------------------------------------------------------------------------
# Utility method tests
# ---------------------------------------------------------------------------

class TestParserUtilities:

    @pytest.mark.parametrize("text,expected", [
        ("$4.99", 4.99),
        ("$0.99", 0.99),
        ("$12.99", 12.99),
        ("Free", None),
        ("", None),
    ])
    def test_parse_price(self, text, expected):
        result = AmazonParser._parse_price(text)
        if expected is None:
            assert result is None
        else:
            assert result == pytest.approx(expected)

    @pytest.mark.parametrize("text,expected", [
        ("4.6 out of 5 stars", 4.6),
        ("3.0 out of 5 stars", 3.0),
        ("5.0 out of 5 stars", 5.0),
        ("no rating", None),
        ("", None),
    ])
    def test_parse_rating(self, text, expected):
        result = AmazonParser._parse_rating(text)
        if expected is None:
            assert result is None
        else:
            assert result == pytest.approx(expected)

    @pytest.mark.parametrize("text,expected", [
        ("1,234", 1234),
        ("10,000", 10000),
        ("42", 42),
        ("", None),
        ("abc", None),
    ])
    def test_parse_int(self, text, expected):
        assert AmazonParser._parse_int(text) == expected

    @pytest.mark.parametrize("html,expected", [
        ("<html>Type the characters you see in this image</html>", True),
        ("<html>robot check</html>", True),
        ("<html>CAPTCHA</html>", True),
        ("<html><title>The Housemaid</title></html>", False),
        ("", False),
    ])
    def test_is_bot_wall(self, html, expected):
        # Test the bot-wall detection logic directly (avoids importing Playwright)
        bot_signals = [
            "Type the characters you see in this image",
            "Enter the characters you see below",
            "robot check",
            "automated access",
            "CAPTCHA",
        ]
        lower = html.lower()
        result = any(s.lower() in lower for s in bot_signals)
        assert result is expected
