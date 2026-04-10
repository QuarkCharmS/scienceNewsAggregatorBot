"""Science News Bot — main entry point."""

import asyncio
import logging
import os
import pathlib
import sys
from datetime import date

from dotenv import load_dotenv

load_dotenv()

from fetcher import fetch_all_articles, PHYSICS_ASTRONOMY_FEEDS, TECH_AI_FEEDS
from ai import rank_and_summarize, translate_apod
from apod import fetch_apod
from publisher import post_digest, post_apod
from seen import filter_unseen, mark_sent

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)

LAST_RUN_FILE = pathlib.Path(__file__).parent / ".last_run"
LAST_RUN_PHYS_FILE = pathlib.Path(__file__).parent / ".last_run_phys"
LAST_RUN_TECH_FILE = pathlib.Path(__file__).parent / ".last_run_tech"
LAST_RUN_APOD_FILE = pathlib.Path(__file__).parent / ".last_run_apod"


def _require_env(name: str) -> str:
    value = os.getenv(name)
    if not value:
        logger.error("Missing required environment variable: %s", name)
        sys.exit(1)
    return value


BOT_TOKEN = _require_env("TELEGRAM_BOT_TOKEN")
CHANNEL_ID = _require_env("TELEGRAM_CHANNEL_ID")


def _get_last_run(f: pathlib.Path) -> date | None:
    try:
        return date.fromisoformat(f.read_text().strip())
    except (FileNotFoundError, ValueError):
        return None


def _set_last_run(f: pathlib.Path) -> None:
    f.write_text(date.today().isoformat())


def run_digest(top_n: int | None = None) -> None:
    """Fetch, rank, and post the daily science digest."""
    logger.info("Starting daily digest run...")

    # 1. Fetch and deduplicate
    articles = filter_unseen(fetch_all_articles())
    if not articles:
        logger.warning("No new articles after deduplication — skipping digest.")
        return

    # 2. Ask Claude to pick and explain the top 5
    try:
        top_articles = rank_and_summarize(articles, top_n=top_n or 5)
    except Exception as exc:
        logger.error("Claude processing failed: %s — skipping digest.", exc)
        return

    # 3. Post digest to Telegram
    try:
        asyncio.run(post_digest(BOT_TOKEN, CHANNEL_ID, top_articles))
    except Exception as exc:
        logger.error("Failed to post digest to Telegram: %s", exc)
        return

    mark_sent(top_articles)
    _set_last_run(LAST_RUN_FILE)
    logger.info("Daily digest completed successfully.")


def run_phys_digest(top_n: int | None = None) -> None:
    """Fetch, rank (top 3), and post the physics & astronomy digest."""
    logger.info("Starting physics & astronomy digest run...")

    articles = filter_unseen(fetch_all_articles(feeds=PHYSICS_ASTRONOMY_FEEDS))
    if not articles:
        logger.warning("No new physics/astronomy articles after deduplication — skipping.")
        return

    try:
        top_articles = rank_and_summarize(articles, top_n=top_n or 3)
    except Exception as exc:
        logger.error("Claude processing failed: %s — skipping.", exc)
        return

    try:
        asyncio.run(post_digest(BOT_TOKEN, CHANNEL_ID, top_articles))
    except Exception as exc:
        logger.error("Failed to post physics digest to Telegram: %s", exc)
        return

    mark_sent(top_articles)
    _set_last_run(LAST_RUN_PHYS_FILE)
    logger.info("Physics & astronomy digest completed successfully.")


def run_tech_digest(top_n: int | None = None) -> None:
    """Fetch, rank (top 4), and post the CS/AI/tech digest."""
    logger.info("Starting CS/AI/tech digest run...")

    articles = filter_unseen(fetch_all_articles(feeds=TECH_AI_FEEDS))
    if not articles:
        logger.warning("No new tech/AI articles after deduplication — skipping.")
        return

    try:
        top_articles = rank_and_summarize(articles, top_n=top_n or 4)
    except Exception as exc:
        logger.error("Claude processing failed: %s — skipping.", exc)
        return

    try:
        asyncio.run(post_digest(BOT_TOKEN, CHANNEL_ID, top_articles))
    except Exception as exc:
        logger.error("Failed to post tech digest to Telegram: %s", exc)
        return

    mark_sent(top_articles)
    _set_last_run(LAST_RUN_TECH_FILE)
    logger.info("CS/AI/tech digest completed successfully.")


def run_apod() -> None:
    """Fetch and post today's APOD."""
    logger.info("Starting APOD run...")
    try:
        apod = fetch_apod()
        translation = translate_apod(apod)
        asyncio.run(post_apod(BOT_TOKEN, CHANNEL_ID, apod, translation))
    except Exception as exc:
        logger.error("Failed to post APOD: %s", exc)
        return

    _set_last_run(LAST_RUN_APOD_FILE)
    logger.info("APOD posted successfully.")


def run_if_missed(run_fn, last_run_file: pathlib.Path, label: str) -> None:
    """Run run_fn if it hasn't run today."""
    last = _get_last_run(last_run_file)
    today = date.today()

    if last == today:
        logger.info("%s already ran today (%s) — nothing to do.", label, today)
        return

    if last is None:
        logger.info("%s has never run — running now.", label)
    else:
        logger.info("%s last ran %s (missed) — running now.", label, last)

    run_fn()


def _parse_count(args: list[str]) -> int | None:
    """Return the value of --count N if present, else None."""
    if "--count" in args:
        i = args.index("--count")
        try:
            value = int(args[i + 1])
            if value < 1:
                raise ValueError
            return value
        except (IndexError, ValueError):
            print("Error: --count requires a positive integer, e.g. --count 3")
            sys.exit(1)
    return None


if __name__ == "__main__":
    args = sys.argv[1:]
    count = _parse_count(args)

    if "--now" in args:
        logger.info("Running science digest immediately (--now).")
        run_digest(top_n=count)

    elif "--check" in args:
        run_if_missed(lambda: run_digest(top_n=count), LAST_RUN_FILE, "Science digest")

    elif "--phys" in args:
        logger.info("Running physics & astronomy digest immediately (--phys).")
        run_phys_digest(top_n=count)

    elif "--phys-check" in args:
        run_if_missed(lambda: run_phys_digest(top_n=count), LAST_RUN_PHYS_FILE, "Physics & astronomy digest")

    elif "--tech" in args:
        logger.info("Running CS/AI/tech digest immediately (--tech).")
        run_tech_digest(top_n=count)

    elif "--tech-check" in args:
        run_if_missed(lambda: run_tech_digest(top_n=count), LAST_RUN_TECH_FILE, "CS/AI/tech digest")

    elif "--apod" in args:
        logger.info("Running APOD immediately (--apod).")
        run_apod()

    elif "--apod-check" in args:
        run_if_missed(run_apod, LAST_RUN_APOD_FILE, "APOD")

    else:
        print("Usage:")
        print("  python bot.py --now          Run science digest immediately (9 PM)")
        print("  python bot.py --check        Catch-up: science digest if not run today")
        print("  python bot.py --phys         Run physics & astronomy digest immediately (5 PM)")
        print("  python bot.py --phys-check   Catch-up: physics digest if not run today")
        print("  python bot.py --tech         Run CS/AI/tech digest immediately (2 PM)")
        print("  python bot.py --tech-check   Catch-up: tech digest if not run today")
        print("  python bot.py --apod         Run APOD immediately (10 PM)")
        print("  python bot.py --apod-check   Catch-up: APOD if not run today")
        print()
        print("  --count N  Override number of articles (e.g. --now --count 3)")
