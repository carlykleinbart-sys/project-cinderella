"""Unit tests for the Goodreads parser."""
import pytest
from scrapers.goodreads.parser import GoodreadsParser


# ── Fixtures: static HTML ─────────────────────────────────────────────────────

SEARCH_RESULTS_HTML = """
<html><body>
<table class="tableList">
  <tr itemtype="http://schema.org/Book">
    <td class="field title">
      <a class="bookTitle" href="/book/show/12345.The_Housemaid">
        <span itemprop="name">The Housemaid</span>
      </a>
    </td>
    <td class="field author">
      <span itemprop="author">
        <a class="authorName" href="/author/show/99.Freida_McFadden">
          <span itemprop="name">Freida McFadden</span>
        </a>
      </span>
    </td>
    <td class="field avg_rating">4.15</td>
    <td class="field num_ratings">500,000</td>
  </tr>
  <tr itemtype="http://schema.org/Book">
    <td class="field title">
      <a class="bookTitle" href="/book/show/99999.Other_Book">
        <span itemprop="name">Other Book</span>
      </a>
    </td>
    <td class="field author">
      <span itemprop="author">
        <a class="authorName" href="/author/show/88.Jane_Doe">
          <span itemprop="name">Jane Doe</span>
        </a>
      </span>
    </td>
    <td class="field avg_rating">3.80</td>
    <td class="field num_ratings">1,000</td>
  </tr>
</table>
</body></html>
"""

BOOK_PAGE_HTML = """
<html><body>
<h1 id="bookTitle" itemprop="name">The Housemaid</h1>
<div id="bookMeta">
  <span itemprop="ratingValue">4.15</span>
  <span itemprop="ratingCount">500000</span>
  <span itemprop="reviewCount">180000</span>
</div>
<div class="wantToReadCount">
  <span>12,500 people want to read this</span>
</div>
<div id="description">
  <span>A stunning psychological thriller.</span>
</div>
<div id="bookGenresList">
  <a href="/genres/thriller">Thriller</a>
  <a href="/genres/mystery">Mystery</a>
</div>
</body></html>
"""

WANT_TO_READ_REGEX_HTML = """
<html><body>
<h1 id="bookTitle" itemprop="name">The Housemaid</h1>
<div id="bookMeta">
  <span itemprop="ratingValue">4.0</span>
  <span itemprop="ratingCount">1000</span>
</div>
<span>8,321 people want to read</span>
</body></html>
"""


# ── Tests: search results ─────────────────────────────────────────────────────

class TestParseSearchResults:
    def test_finds_books(self):
        results = GoodreadsParser.parse_search_results(SEARCH_RESULTS_HTML)
        assert len(results) >= 1

    def test_extracts_title_and_author(self):
        results = GoodreadsParser.parse_search_results(SEARCH_RESULTS_HTML)
        first = results[0]
        assert "Housemaid" in first["title"]
        assert "McFadden" in first["author"]

    def test_extracts_goodreads_id(self):
        results = GoodreadsParser.parse_search_results(SEARCH_RESULTS_HTML)
        assert results[0]["goodreads_id"] == "12345"

    def test_extracts_goodreads_url(self):
        results = GoodreadsParser.parse_search_results(SEARCH_RESULTS_HTML)
        assert "12345" in results[0]["goodreads_url"]

    def test_empty_html_returns_empty_list(self):
        results = GoodreadsParser.parse_search_results("<html></html>")
        assert results == []

    def test_multiple_results_returned(self):
        results = GoodreadsParser.parse_search_results(SEARCH_RESULTS_HTML)
        assert len(results) == 2


# ── Tests: book page ──────────────────────────────────────────────────────────

class TestParseBookPage:
    def test_returns_data(self):
        data = GoodreadsParser.parse_book_page(BOOK_PAGE_HTML, "https://www.goodreads.com/book/show/12345")
        assert data is not None

    def test_extracts_rating(self):
        data = GoodreadsParser.parse_book_page(BOOK_PAGE_HTML, "https://www.goodreads.com/book/show/12345")
        assert data["average_rating"] == pytest.approx(4.15, abs=0.1)

    def test_extracts_want_to_read(self):
        data = GoodreadsParser.parse_book_page(WANT_TO_READ_REGEX_HTML, "https://www.goodreads.com/book/show/99")
        assert data["want_to_read_count"] == 8321

    def test_missing_page_returns_none(self):
        result = GoodreadsParser.parse_book_page("", "https://www.goodreads.com/book/show/0")
        assert result is None or result.get("average_rating") is None


# ── Tests: URL builders ───────────────────────────────────────────────────────

class TestUrlBuilders:
    def test_build_search_url(self):
        url = GoodreadsParser.build_search_url("The Housemaid", "Freida McFadden")
        assert "goodreads.com/search" in url
        assert "Housemaid" in url or "housemaid" in url.lower()

    def test_build_book_url(self):
        url = GoodreadsParser.build_book_url("12345")
        assert "12345" in url
        assert "goodreads.com" in url

    def test_extract_goodreads_id_from_url(self):
        url = "https://www.goodreads.com/book/show/12345.The_Housemaid"
        gid = GoodreadsParser._extract_goodreads_id(url)
        assert gid == "12345"

    def test_extract_goodreads_id_numeric_only(self):
        url = "https://www.goodreads.com/book/show/99999"
        gid = GoodreadsParser._extract_goodreads_id(url)
        assert gid == "99999"
