"""Persistent log of sent article URLs to prevent duplicate posts."""

import json
import logging
import pathlib
from datetime import date, timedelta

logger = logging.getLogger(__name__)

SEEN_FILE = pathlib.Path(__file__).parent / ".seen_articles.json"
RETENTION_DAYS = 30


def _load() -> dict[str, str]:
    """Return {url: date_str} dict from disk, or empty dict if file missing/corrupt."""
    try:
        return json.loads(SEEN_FILE.read_text())
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def _save(data: dict[str, str]) -> None:
    SEEN_FILE.write_text(json.dumps(data, indent=2))


def _cleanup(data: dict[str, str]) -> dict[str, str]:
    """Remove entries older than RETENTION_DAYS."""
    cutoff = (date.today() - timedelta(days=RETENTION_DAYS)).isoformat()
    cleaned = {url: d for url, d in data.items() if d >= cutoff}
    removed = len(data) - len(cleaned)
    if removed:
        logger.info("Cleaned %d old entries from seen log.", removed)
    return cleaned


def filter_unseen(articles: list[dict]) -> list[dict]:
    """Return only articles whose URL has not been sent before."""
    data = _cleanup(_load())
    _save(data)  # persist the cleanup

    unseen = [a for a in articles if a["link"] not in data]
    skipped = len(articles) - len(unseen)
    if skipped:
        logger.info("Skipped %d already-sent article(s).", skipped)

    return unseen


def mark_sent(articles: list[dict]) -> None:
    """Record article URLs as sent with today's date."""
    data = _load()
    today = date.today().isoformat()
    for article in articles:
        data[article["link"]] = today
    _save(data)
    logger.info("Marked %d article(s) as sent.", len(articles))
