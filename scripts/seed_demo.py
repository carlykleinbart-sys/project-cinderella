"""
Seed the database with realistic demo data so the dashboard is functional
before live Amazon collection is working.

Usage (Railway Console):
    python -m scripts.seed_demo

Safe to re-run — uses INSERT OR IGNORE semantics (skips existing ASINs).
"""
from __future__ import annotations

import sys
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from loguru import logger

from database import get_session
from models import Book, DailyMetrics, MomentumScore
from models.book import BookFormat

TODAY = date.today()


# ── Demo book definitions ──────────────────────────────────────────────────

BOOKS = [
    dict(asin="B0CX1AAA01", title="The Lake House Keeper", author="Maren Cole",
         publisher="Cole Creative LLC", genre="Romance", kindle_unlimited=True,
         publication_date=date(2026, 6, 3),
         score_history=[21,24,27,29,31,34,37,38,39,42,44,47,51,55,58,61,63,65,67,70,73,76,79,81,83,85,86,87,87,87.4],
         latest_bsr=312, latest_sales=1840, latest_reviews=2341, latest_rating=4.8,
         gr_rating=4.61, gr_reviews=8920, gr_wtr=14200,
         alert=True,
         components=dict(rank_velocity=98,rank_acceleration=91,review_velocity=84,review_acceleration=79,rating_stability=88,sales_growth=92,age_factor=71,kindle_unlimited=100,booktok_velocity=95,reddit_buzz=62,goodreads_want_to_read=87),
         explanation="🔥 Breakout alert: rank surged from #48,200 to #312 in 14 days (+99.4% velocity). Review growth accelerating — 847 new reviews in the last 7 days. BookTok is on fire with 94 mentions and 4.2M views. Want-to-Read count spiking at 14.2K — typically a 3–4 week leading indicator before mainstream breakout."),
    dict(asin="B0DK9BBB02", title="Shadowed Throne", author="J.K. Vayne",
         publisher="Vayne Ink", genre="Fantasy", kindle_unlimited=True,
         publication_date=date(2026, 5, 18),
         score_history=[18,20,22,24,26,28,30,32,33,35,37,40,43,46,49,52,55,58,61,63,65,67,69,71,73,75,77,78,79,79.1],
         latest_bsr=891, latest_sales=1120, latest_reviews=1687, latest_rating=4.7,
         gr_rating=4.53, gr_reviews=5440, gr_wtr=9800,
         alert=True,
         components=dict(rank_velocity=91,rank_acceleration=83,review_velocity=74,review_acceleration=69,rating_stability=85,sales_growth=80,age_factor=78,kindle_unlimited=100,booktok_velocity=51,reddit_buzz=94,goodreads_want_to_read=76),
         explanation="🔥 Alert: strong Reddit word-of-mouth across r/Fantasy and r/RomanceBooks (62 posts, 18.7K upvotes). Rank velocity at 91 — climbed from #22K to #891 in 21 days. Series potential: this is book 1 of a planned trilogy which typically amplifies breakout velocity."),
    dict(asin="B0EF3CCC03", title="One Last Summer", author="Ellie Price",
         publisher="Sunfield Press", genre="Romance", kindle_unlimited=False,
         publication_date=date(2026, 4, 21),
         score_history=[30,32,34,35,37,38,40,42,44,46,48,50,52,54,55,57,58,60,62,64,65,67,68,70,71,72,73,74,74,74.2],
         latest_bsr=1204, latest_sales=890, latest_reviews=3102, latest_rating=4.6,
         gr_rating=4.48, gr_reviews=11200, gr_wtr=6700,
         alert=True,
         components=dict(rank_velocity=82,rank_acceleration=74,review_velocity=90,review_acceleration=86,rating_stability=82,sales_growth=74,age_factor=60,kindle_unlimited=0,booktok_velocity=73,reddit_buzz=38,goodreads_want_to_read=65),
         explanation="🔥 Alert: TikTok-driven spike — 73 BookTok mentions with 2.8M views in 7 days. The 'emotional-healing romance' angle is resonating strongly. Review count (3.1K) is unusually high for a 3-month-old indie title."),
    dict(asin="B0BW7DDD04", title="Iron & Blood", author="Sienna Cross",
         publisher="Cross Worlds Publishing", genre="Dark Romance", kindle_unlimited=True,
         publication_date=date(2026, 6, 29),
         score_history=[15,18,20,22,25,27,29,31,33,35,37,39,41,43,45,47,50,52,54,56,58,60,62,63,65,66,67,68,69,68.9],
         latest_bsr=2870, latest_sales=620, latest_reviews=987, latest_rating=4.5,
         gr_rating=4.42, gr_reviews=3210, gr_wtr=5100,
         alert=False,
         components=dict(rank_velocity=78,rank_acceleration=71,review_velocity=66,review_acceleration=60,rating_stability=80,sales_growth=72,age_factor=85,kindle_unlimited=100,booktok_velocity=42,reddit_buzz=57,goodreads_want_to_read=59),
         explanation="Strong upward trajectory across all channels. Dark romance is the fastest-growing KU subcategory. BookTok audience in r/DarkRomance is actively rec-listing this one. Watch for review acceleration."),
    dict(asin="B0CV5EEE05", title="The Paper Wives", author="Charlotte Reed",
         publisher="Reed & Rowe Books", genre="Thriller", kindle_unlimited=False,
         publication_date=date(2026, 5, 2),
         score_history=[28,30,31,33,34,35,37,38,39,41,42,44,45,46,48,49,50,52,53,54,56,57,58,59,61,62,62,63,64,63.7],
         latest_bsr=3940, latest_sales=480, latest_reviews=1543, latest_rating=4.4,
         gr_rating=4.31, gr_reviews=4870, gr_wtr=3800,
         alert=False,
         components=dict(rank_velocity=71,rank_acceleration=62,review_velocity=70,review_acceleration=65,rating_stability=78,sales_growth=64,age_factor=55,kindle_unlimited=0,booktok_velocity=19,reddit_buzz=71,goodreads_want_to_read=52),
         explanation="Steady climber with strong Reddit presence in r/books and r/Mystery. Rank has improved from #28K to #3.9K over 90 days — a slower but sustained trajectory that often correlates with durable breakouts."),
    dict(asin="B0DA8FFF06", title="Throne of Ash", author="Maya Delacroix",
         publisher="Delacroix Fiction", genre="Fantasy", kindle_unlimited=True,
         publication_date=date(2026, 7, 1),
         score_history=[None]*20 + [22,26,30,34,37,41,45,50,55,58.3],
         latest_bsr=6200, latest_sales=340, latest_reviews=782, latest_rating=4.6,
         gr_rating=4.55, gr_reviews=2340, gr_wtr=4200,
         alert=False,
         components=dict(rank_velocity=65,rank_acceleration=58,review_velocity=58,review_acceleration=52,rating_stability=91,sales_growth=61,age_factor=92,kindle_unlimited=100,booktok_velocity=28,reddit_buzz=36,goodreads_want_to_read=48),
         explanation="Promising recent release with exceptional rating (4.6★). Too early to confirm breakout trajectory but early signals are positive. Only 34 days old; age factor will improve significantly if current velocity holds."),
    dict(asin="B0BL2GGG07", title="Lost in the Static", author="T.J. Marsh",
         publisher="Marsh Writes", genre="Mystery", kindle_unlimited=False,
         publication_date=date(2026, 2, 14),
         score_history=[22,23,24,25,26,27,28,29,30,31,32,33,34,35,36,37,38,39,40,42,44,46,47,49,50,51,52,53,54,54.1],
         latest_bsr=8900, latest_sales=280, latest_reviews=2108, latest_rating=4.3,
         gr_rating=4.22, gr_reviews=7610, gr_wtr=2900,
         alert=False,
         components=dict(rank_velocity=60,rank_acceleration=54,review_velocity=64,review_acceleration=58,rating_stability=74,sales_growth=55,age_factor=38,kindle_unlimited=0,booktok_velocity=11,reddit_buzz=60,goodreads_want_to_read=39),
         explanation="Slow-burn breakout: 170 days tracked, consistent rank improvement, strong review base (2.1K). Review acceleration has picked up in the last 14 days (+6.2/day vs +2.1/day prior period)."),
    dict(asin="B0EJ4HHH08", title="Her Final Chapter", author="Nora Blake",
         publisher="Blake House Books", genre="Thriller", kindle_unlimited=True,
         publication_date=date(2026, 7, 10),
         score_history=[None]*25 + [28,34,40,47,50.8],
         latest_bsr=11400, latest_sales=220, latest_reviews=441, latest_rating=4.5,
         gr_rating=4.39, gr_reviews=1180, gr_wtr=3300,
         alert=False,
         components=dict(rank_velocity=59,rank_acceleration=52,review_velocity=71,review_acceleration=68,rating_stability=82,sales_growth=58,age_factor=95,kindle_unlimited=100,booktok_velocity=22,reddit_buzz=20,goodreads_want_to_read=43),
         explanation="Very new (25 days) with strong early signals. 441 reviews in 25 days is above average for an indie thriller. KU page reads trending up. Monitor closely."),
    dict(asin="B0CF6III09", title="The Gilded Cage", author="Isabelle Fox",
         publisher="Fox & Feather Press", genre="Dark Romance", kindle_unlimited=True,
         publication_date=date(2026, 4, 8),
         score_history=[32,33,34,35,36,37,38,39,40,41,42,43,44,44,45,45,46,46,46,47,47,47,46,46,46,46,46,46,46,46.2],
         latest_bsr=15600, latest_sales=170, latest_reviews=1234, latest_rating=4.4,
         gr_rating=4.35, gr_reviews=3890, gr_wtr=2100,
         alert=False,
         components=dict(rank_velocity=51,rank_acceleration=43,review_velocity=55,review_acceleration=48,rating_stability=77,sales_growth=46,age_factor=47,kindle_unlimited=100,booktok_velocity=16,reddit_buzz=34,goodreads_want_to_read=31),
         explanation="Mid-tier performer with stable trajectory. Rank has plateaued around #15K–18K for the past 3 weeks — may need a promotional push or social catalyst to break through."),
    dict(asin="B0AK8JJJ10", title="Starfall Academy", author="Jade Rivers",
         publisher="Rivers Publishing Co", genre="YA Fantasy", kindle_unlimited=True,
         publication_date=date(2026, 3, 15),
         score_history=[20,21,22,23,24,25,26,27,27,28,29,30,31,31,32,33,33,34,35,35,36,37,38,39,40,41,41,42,43,42.7],
         latest_bsr=19800, latest_sales=140, latest_reviews=889, latest_rating=4.7,
         gr_rating=4.61, gr_reviews=2780, gr_wtr=5800,
         alert=False,
         components=dict(rank_velocity=46,rank_acceleration=39,review_velocity=51,review_acceleration=46,rating_stability=93,sales_growth=41,age_factor=42,kindle_unlimited=100,booktok_velocity=31,reddit_buzz=18,goodreads_want_to_read=62),
         explanation="Underperforming given its social metrics — 5.8K Goodreads WTR and 31 BookTok mentions are strong signals for a YA title, but Amazon rank hasn't caught up yet. This lag pattern often resolves in a sudden rank jump."),
    dict(asin="B0DM1KKK11", title="Sweet Chaos", author="Lily Chambers",
         publisher="Chambers & Lily LLC", genre="Romance", kindle_unlimited=True,
         publication_date=date(2026, 6, 12),
         score_history=[None]*17 + [18,20,22,24,26,28,29,31,33,35,36,38,39.4],
         latest_bsr=24200, latest_sales=110, latest_reviews=567, latest_rating=4.5,
         gr_rating=4.41, gr_reviews=1760, gr_wtr=1600,
         alert=False,
         components=dict(rank_velocity=44,rank_acceleration=38,review_velocity=48,review_acceleration=43,rating_stability=80,sales_growth=40,age_factor=82,kindle_unlimited=100,booktok_velocity=14,reddit_buzz=14,goodreads_want_to_read=22),
         explanation="Consistent early-stage growth pattern. 53 days in with steady rank improvement. Worth monitoring — the trajectory mirrors early-stage patterns of several breakouts in this dataset."),
    dict(asin="B0BG4LLL12", title="Hollow Bones", author="Rae Winters",
         publisher="Winters Dark LLC", genre="Thriller", kindle_unlimited=False,
         publication_date=date(2026, 5, 25),
         score_history=[18,19,20,21,22,23,24,25,26,27,28,28,29,30,30,31,32,32,33,33,34,34,35,35,35,36,36,36,36,36.1],
         latest_bsr=29700, latest_sales=88, latest_reviews=423, latest_rating=4.3,
         gr_rating=4.20, gr_reviews=1290, gr_wtr=980,
         alert=False,
         components=dict(rank_velocity=40,rank_acceleration=35,review_velocity=44,review_acceleration=39,rating_stability=71,sales_growth=37,age_factor=65,kindle_unlimited=0,booktok_velocity=7,reddit_buzz=26,goodreads_want_to_read=14),
         explanation="Stable trajectory with Reddit as the primary discovery channel. Rank improving gradually from #62K at discovery 71 days ago to #29.7K today."),
    dict(asin="B0CE9MMM13", title="The Raven's Bargain", author="Victor Ash",
         publisher="Ashwood Reads", genre="Fantasy", kindle_unlimited=True,
         publication_date=date(2026, 6, 19),
         score_history=[None]*24 + [14,18,22,26,30,32.8],
         latest_bsr=36500, latest_sales=67, latest_reviews=312, latest_rating=4.6,
         gr_rating=4.51, gr_reviews=890, gr_wtr=2200,
         alert=False,
         components=dict(rank_velocity=37,rank_acceleration=31,review_velocity=38,review_acceleration=34,rating_stability=89,sales_growth=33,age_factor=84,kindle_unlimited=100,booktok_velocity=9,reddit_buzz=12,goodreads_want_to_read=30),
         explanation="Promising fundamentals — 4.6★ rating and 2.2K Goodreads WTR are solid for a 46-day-old title. Expect review velocity to accelerate in the next 2–4 weeks."),
    dict(asin="B0BN3NNN14", title="Sins of Silver", author="Derek Stone",
         publisher="Stone Cold Publishing", genre="Mystery", kindle_unlimited=False,
         publication_date=date(2026, 7, 14),
         score_history=[None]*28 + [25,29.3],
         latest_bsr=44100, latest_sales=52, latest_reviews=198, latest_rating=4.4,
         gr_rating=4.28, gr_reviews=620, gr_wtr=740,
         alert=False,
         components=dict(rank_velocity=33,rank_acceleration=27,review_velocity=35,review_acceleration=30,rating_stability=76,sales_growth=29,age_factor=96,kindle_unlimited=0,booktok_velocity=4,reddit_buzz=9,goodreads_want_to_read=10),
         explanation="Early-stage tracker — 21 days in, limited data for confident scoring. Initial signals are neutral. Will need more data points to assess trajectory."),
    dict(asin="B0AJ7OOO15", title="Midnight in Monterey", author="Sophie Crane",
         publisher="Crane Bay Books", genre="Romance", kindle_unlimited=True,
         publication_date=date(2025, 11, 1),
         score_history=[38,37,36,35,34,33,32,31,30,30,29,29,28,28,27,27,27,26,26,26,26,26,25,25,25,25,26,26,25,25.6],
         latest_bsr=58300, latest_sales=38, latest_reviews=3840, latest_rating=4.2,
         gr_rating=4.18, gr_reviews=12800, gr_wtr=890,
         alert=False,
         components=dict(rank_velocity=28,rank_acceleration=21,review_velocity=30,review_acceleration=24,rating_stability=66,sales_growth=24,age_factor=14,kindle_unlimited=100,booktok_velocity=3,reddit_buzz=7,goodreads_want_to_read=12),
         explanation="Legacy tracked title (277 days). High review count (3.8K) reflects a long tail readership but rank has stabilized. No current momentum signals. Keeping in monitor for any sudden reactivation."),
]


# ── Helpers ────────────────────────────────────────────────────────────────

def _bsr_for_day(latest_bsr: int, score_history: list, day_index: int) -> int:
    """Interpolate a plausible historical BSR from score history."""
    valid = [s for s in score_history if s is not None]
    if not valid:
        return latest_bsr
    latest_score = valid[-1]
    day_score = score_history[day_index]
    if day_score is None:
        return None
    # Higher score → lower (better) BSR; scale linearly
    ratio = latest_score / max(day_score, 0.1)
    return max(100, int(latest_bsr * ratio))


def _reviews_for_day(latest_reviews: int, score_history: list, day_index: int) -> int:
    valid = [s for s in score_history if s is not None]
    if not valid or score_history[day_index] is None:
        return None
    ratio = score_history[day_index] / max(valid[-1], 0.1)
    return max(1, int(latest_reviews * ratio))


# ── Main seed function ─────────────────────────────────────────────────────

def seed():
    inserted_books = 0
    inserted_metrics = 0
    inserted_scores = 0

    with get_session() as session:
        for b in BOOKS:
            # Skip if already exists
            from sqlalchemy import select
            existing = session.scalar(
                select(Book).where(Book.asin == b["asin"])
            )
            if existing:
                logger.info("Skipping existing book: {}", b["title"])
                book = existing
            else:
                book = Book(
                    asin=b["asin"],
                    title=b["title"],
                    author=b["author"],
                    publisher=b["publisher"],
                    genre=b["genre"],
                    kindle_unlimited=b["kindle_unlimited"],
                    publication_date=b["publication_date"],
                    format=BookFormat.KINDLE,
                    is_indie=True,
                    language="en",
                )
                session.add(book)
                session.flush()  # get book.id
                inserted_books += 1
                logger.info("Inserted book: {}", b["title"])

            # Insert 30 days of daily metrics
            history = b["score_history"]
            for i, score in enumerate(history):
                day = TODAY - timedelta(days=29 - i)
                if score is None:
                    continue

                # Skip if metrics row already exists
                from models import DailyMetrics as DM
                existing_m = session.scalar(
                    select(DM).where(DM.book_id == book.id, DM.date == day)
                )
                if existing_m:
                    continue

                bsr = _bsr_for_day(b["latest_bsr"], history, i)
                reviews = _reviews_for_day(b["latest_reviews"], history, i)
                sales = max(1, int(b["latest_sales"] * score / max(history[-1], 0.1)))

                metrics = DailyMetrics(
                    book_id=book.id,
                    date=day,
                    amazon_best_seller_rank=bsr,
                    estimated_daily_sales=sales,
                    star_rating=b["latest_rating"],
                    review_count=reviews,
                    price=4.99,
                    goodreads_rating=b["gr_rating"],
                    goodreads_reviews=b["gr_reviews"],
                    goodreads_want_to_read=b["gr_wtr"],
                )
                session.add(metrics)
                inserted_metrics += 1

            # Insert today's momentum score
            from models import MomentumScore as MS
            existing_s = session.scalar(
                select(MS).where(MS.book_id == book.id, MS.date == TODAY)
            )
            if not existing_s:
                final_score = [s for s in history if s is not None][-1]
                ms = MomentumScore(
                    book_id=book.id,
                    date=TODAY,
                    momentum_score=final_score,
                    components=b["components"],
                    explanation=b["explanation"],
                    snapshots_used=len([s for s in history if s is not None]),
                    alert_triggered=b["alert"],
                    alert_reasons=["momentum_spike"] if b["alert"] else [],
                )
                session.add(ms)
                inserted_scores += 1

    logger.info(
        "Seed complete — {} books, {} metric rows, {} scores inserted",
        inserted_books, inserted_metrics, inserted_scores,
    )


if __name__ == "__main__":
    import logging
    logger.remove()
    logger.add(sys.stderr, level="INFO", format="{time:HH:mm:ss} | {level} | {message}")
    seed()
