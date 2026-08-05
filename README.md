# Project Cinderella 🔮

> An early-warning intelligence system for independently published books.
> Identifies self-published titles quietly becoming tomorrow's bestsellers
> before the rest of the market notices.

---

## Table of Contents

1. [Overview](#overview)
2. [Milestone Roadmap](#milestone-roadmap)
3. [Architecture](#architecture)
4. [Database Schema](#database-schema)
5. [Quick Start (Local)](#quick-start-local)
6. [Docker Setup](#docker-setup)
7. [Configuration Reference](#configuration-reference)
8. [Running the Collector](#running-the-collector)
9. [Running Tests](#running-tests)
10. [Project Structure](#project-structure)
11. [Adding a New Data Source](#adding-a-new-data-source)
12. [Troubleshooting](#troubleshooting)

---

## Overview

Project Cinderella monitors the Kindle bestseller charts, tracks historical
performance data, and surfaces indie books that are **accelerating** — not
just books that are already popular.

The canonical example of a target signal is *The Housemaid* by Freida McFadden,
which gained enormous traction as an independently published title before
traditional acquisition. Cinderella is designed to identify the next one before
it becomes obvious.

---

## Milestone Roadmap

| Milestone | Status | Description |
|-----------|--------|-------------|
| **1** | ✅ **Complete** | Database, Amazon collection, historical storage |
| 2 | Planned | Momentum scoring, daily reports |
| 3 | Planned | Goodreads integration |
| 4 | Planned | BookTok integration |
| 5 | Planned | Reddit integration |
| 6 | Planned | Web dashboard |
| 7 | Planned | AI breakout prediction score |

---

## Architecture

```
┌─────────────────────────────────────────────────────────┐
│                   Collector Pipeline                     │
│                                                          │
│  AmazonBrowser (Playwright)                              │
│       │ raw HTML                                         │
│       ▼                                                  │
│  AmazonParser                                            │
│       │ BestsellerEntry / BookDetail dicts               │
│       ▼                                                  │
│  AmazonCollector                                         │
│       │  • Indie detection via IndiePublisher lookup     │
│       │  • Book upsert                                   │
│       │  • DailyMetrics INSERT (immutable snapshots)     │
│       ▼                                                  │
│  PostgreSQL                                              │
│       books / daily_metrics / indie_publishers           │
└─────────────────────────────────────────────────────────┘
```

**Key design principles:**

- **Historical data is sacred.** `daily_metrics` rows are never overwritten.
  The `(book_id, date)` unique constraint is the enforcement mechanism.
- **Indie detection is configurable.** The `indie_publishers` table is a
  database-backed lookup list — no code changes required to add new platforms.
- **Collectors are pluggable.** All collectors extend `BaseCollector` and
  implement a single `collect()` method. Adding Goodreads means adding one file.
- **No hardcoded secrets.** Every tunable value lives in `.env` / environment
  variables, surfaced through `config/settings.py`.

---

## Database Schema

### `books`
Canonical record for each tracked title, keyed by ASIN.

| Column | Type | Notes |
|--------|------|-------|
| `asin` | varchar(20) | Unique. Primary external key. |
| `isbn` | varchar(20) | ISBN-13 when available. |
| `title` / `subtitle` | varchar | |
| `author` | varchar(200) | |
| `publisher` | varchar(200) | Used for indie detection. |
| `publication_date` | date | |
| `format` | enum | Kindle / Paperback / Hardcover / Audiobook |
| `kindle_unlimited` | boolean | |
| `genre` | varchar(100) | Top-level genre. |
| `categories` | JSON | Full Amazon category breadcrumb. |
| `is_indie` | boolean | Derived from `indie_publishers` lookup. |
| `first_seen` | timestamptz | When we first discovered this book. |

### `daily_metrics`
One immutable row per `(book_id, date)`. Never updated after insert.

| Column | Type | Notes |
|--------|------|-------|
| `amazon_best_seller_rank` | integer | Overall Kindle store rank. |
| `estimated_daily_sales` | integer | Derived from BSR heuristic. |
| `price` | numeric(10,2) | USD at time of collection. |
| `star_rating` | float | Amazon average rating (0–5). |
| `review_count` | integer | Total Amazon reviews. |
| `category_ranks` | JSON | `{"Romance > Contemporary": 3}` |
| `goodreads_*` | float/int | Populated from Milestone 3. |

### `indie_publishers`
Configurable lookup table for indie detection.

| Column | Type | Notes |
|--------|------|-------|
| `name` | varchar | Human-readable label. |
| `match_fragment` | varchar | Lowercase substring matched against publisher. |
| `is_active` | boolean | Toggle without deleting. |

### Social signal tables
`booktok_mentions`, `reddit_mentions`, `instagram_mentions` — all
append-only. Schema stubs present; populated from Milestones 4 and 5.

---

## Quick Start (Local)

### Prerequisites

- Python 3.12+
- PostgreSQL 15+
- [Poetry](https://python-poetry.org/) (`pip install poetry`)

### 1. Clone and install

```bash
git clone <repo-url>
cd project-cinderella
poetry install
playwright install chromium
```

### 2. Configure environment

```bash
cp .env.example .env
# Edit .env — at minimum, set DATABASE_URL
```

### 3. Create the database

```bash
createdb cinderella   # or use psql / pgAdmin
```

### 4. Run migrations

```bash
alembic upgrade head
```

### 5. Seed indie publishers

```bash
python -m scripts.seed_publishers
```

### 6. Run the collector

```bash
python -m scripts.collect
```

---

## Docker Setup

The fastest way to get a fully working stack:

```bash
# 1. Copy and configure .env
cp .env.example .env

# 2. Start the database
docker compose up -d db

# 3. Wait for Postgres to be healthy, then run migrations
docker compose run --rm cinderella alembic upgrade head

# 4. Seed indie publishers
docker compose run --rm cinderella python -m scripts.seed_publishers

# 5. Run the collector
docker compose run --rm cinderella python -m scripts.collect
```

Subsequent daily runs:
```bash
docker compose run --rm cinderella python -m scripts.collect
```

---

## Configuration Reference

All values are set via environment variables or `.env`.

| Variable | Default | Description |
|----------|---------|-------------|
| `DATABASE_URL` | *(required)* | `postgresql://user:pass@host/db` |
| `AMAZON_REQUEST_DELAY_MIN` | `2.0` | Min seconds between Amazon requests |
| `AMAZON_REQUEST_DELAY_MAX` | `5.0` | Max seconds between Amazon requests |
| `AMAZON_MAX_BOOKS_PER_CATEGORY` | `100` | Books to collect per bestseller list |
| `AMAZON_HEADLESS` | `true` | Run browser headless |
| `AMAZON_USER_DATA_DIR` | *(empty)* | Path to Chromium user-data-dir |
| `COLLECTION_SCHEDULE` | `0 6 * * *` | Cron for daily collection (Milestone 2+) |
| `LOG_LEVEL` | `INFO` | DEBUG / INFO / WARNING / ERROR |
| `LOG_FILE` | *(empty)* | Log file path; empty = stdout only |
| `REPORTS_DIR` | `./reports` | Directory for generated reports |

Alert configuration (Milestone 2+): `SMTP_*`, `DISCORD_WEBHOOK_URL`, `SLACK_WEBHOOK_URL`.

---

## Running the Collector

```bash
# Full run — all categories
python -m scripts.collect

# Specific categories
python -m scripts.collect --categories "Romance,Fantasy"

# Limit books per category (useful for testing)
python -m scripts.collect --max-books 10

# Dry run — parse but don't write to DB
python -m scripts.collect --dry-run

# Help
python -m scripts.collect --help
```

---

## Running Tests

```bash
# All tests with coverage
pytest

# Unit tests only
pytest tests/unit/

# Integration tests only
pytest tests/integration/

# A specific test file
pytest tests/unit/test_parser.py -v

# Verbose with no coverage
pytest -v --no-cov
```

Tests use an in-memory SQLite database — no PostgreSQL connection required.

---

## Project Structure

```
project-cinderella/
├── config/
│   └── settings.py          # All configuration via pydantic-settings
├── database/
│   └── connection.py        # SQLAlchemy engine + get_session() context manager
├── models/
│   ├── book.py              # Book ORM model
│   ├── daily_metrics.py     # DailyMetrics ORM model (immutable snapshots)
│   ├── social_signals.py    # BookTok / Reddit / Instagram mention models
│   └── indie_publisher.py   # Indie publisher lookup table
├── scrapers/
│   └── amazon/
│       ├── browser.py       # Playwright browser manager (stealth, delays, retry)
│       ├── parser.py        # HTML parsers for bestseller lists and detail pages
│       └── categories.py    # Kindle category definitions
├── collectors/
│   ├── base.py              # BaseCollector abstract interface
│   └── amazon_collector.py  # Orchestrates scraping → DB pipeline
├── scoring/
│   └── sales_estimator.py   # BSR → estimated daily sales heuristic
├── scripts/
│   ├── collect.py           # CLI entry point
│   └── seed_publishers.py   # Seeds indie_publishers table
├── alembic/
│   ├── env.py               # Alembic config (DB URL injected from settings)
│   └── versions/
│       └── 001_initial_schema.py
├── tests/
│   ├── conftest.py          # Fixtures (in-memory SQLite, factory helpers)
│   ├── unit/
│   │   ├── test_parser.py   # Parser unit tests (no network)
│   │   └── test_models.py   # Model + estimator unit tests
│   └── integration/
│       └── test_collector.py # Collector tests with mocked browser
├── Dockerfile
├── docker-compose.yml
├── pyproject.toml
└── .env.example
```

---

## Adding a New Data Source

1. Create `collectors/my_source_collector.py` extending `BaseCollector`.
2. Implement `async def collect(self) -> CollectionResult`.
3. Add the new collector to `scripts/collect.py`.
4. Add any new models to `models/` and generate a migration:
   ```bash
   alembic revision --autogenerate -m "add my_source tables"
   alembic upgrade head
   ```

---

## Troubleshooting

**`BotWallError: Amazon bot wall detected`**

Amazon has served a CAPTCHA. Options:
- Increase `AMAZON_REQUEST_DELAY_MIN` / `AMAZON_REQUEST_DELAY_MAX`.
- Set `AMAZON_USER_DATA_DIR` to a Chromium profile that has been manually
  navigated to Amazon and solved any initial challenges.
- Run with `AMAZON_HEADLESS=false` temporarily to observe what's happening.

**`psycopg2.OperationalError: could not connect to server`**

Check that PostgreSQL is running and `DATABASE_URL` is correct.

```bash
psql $DATABASE_URL -c "SELECT 1"
```

**`alembic.util.exc.CommandError: Can't locate revision`**

Run `alembic upgrade head` from the project root (where `alembic.ini` lives).

**Collected books aren't marked as indie**

Make sure you've run `python -m scripts.seed_publishers`. The `indie_publishers`
table drives all indie detection — if it's empty, nothing will be flagged.

**Tests failing with `ModuleNotFoundError`**

Run pytest from the project root:
```bash
cd project-cinderella
pytest
```

---

## Legal Note

Web scraping Amazon is subject to their Terms of Service. This tool is intended
for personal research use. Use reasonable delays and do not overwhelm Amazon's
servers. Consider Amazon's Product Advertising API for production-scale access.

---

## Milestone 6: Web Dashboard

A dark-theme Bloomberg-terminal-style web UI for real-time monitoring.

### Start the dashboard

**With Docker Compose (recommended):**
```bash
docker compose up -d dashboard
# Open http://localhost:8000
```

**Standalone (dev mode):**
```bash
python -m scripts.serve --reload
# Or with custom port:
python -m scripts.serve --port 9000
```

### Dashboard features

- **Leaderboard** — top 50 indie books ranked by today's momentum score, with live score bars and alert highlighting
- **Book detail panel** — click any book to see:
  - 30-day momentum score sparkline
  - All 11 score component breakdown bars
  - Latest Amazon + Goodreads metrics
  - BookTok and Reddit social signal counts
  - AI-generated explanation of why the score is what it is
- **Alert badges** — books that breached alert thresholds are highlighted in orange
- **System header** — live counts of tracked books, scores today, and alerts

### REST API

The dashboard is powered by a REST API you can query directly:

| Endpoint | Description |
|---|---|
| `GET /` | Dashboard HTML |
| `GET /health` | Liveness probe |
| `GET /api/stats` | High-level system counts |
| `GET /api/books?genre=Romance&limit=50` | Paginated book list |
| `GET /api/books/{asin}` | Full book detail + 30d history |
| `GET /api/leaderboard?limit=25&as_of=2026-08-01` | Top books by score |
| `GET /api/social/{book_id}?window_days=7` | TikTok + Reddit + Goodreads signals |
| `GET /api/docs` | Interactive Swagger UI |
| `GET /api/redoc` | ReDoc documentation |

### Architecture

```
Browser
  └── GET /            → dashboard.html (vanilla JS, no build step)
       ├── /api/stats         → header pill counts
       ├── /api/leaderboard   → left panel rows
       └── /api/books/{asin}  → right detail panel
           /api/social/{id}   → social signal cards
```

The frontend is a single self-contained HTML file (`api/templates/dashboard.html`) with no npm, no bundler, and no external CDN dependencies — just vanilla JS and a `<canvas>` sparkline renderer.
