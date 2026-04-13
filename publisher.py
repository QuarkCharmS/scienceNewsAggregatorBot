"""Telegram channel publisher for the science digest."""

import asyncio
import logging
import os
import pathlib
import re
import urllib.request
from datetime import date

import telegram
from telegram.constants import ParseMode

logger = logging.getLogger(__name__)

# Delay between messages to avoid Telegram rate limiting (seconds)
MESSAGE_DELAY = 1.5

CACHE_DIR = pathlib.Path(__file__).parent / "cache"


def _wipe_cache() -> None:
    """Delete all files in the cache directory."""
    if CACHE_DIR.exists():
        for f in CACHE_DIR.iterdir():
            if f.is_file():
                f.unlink()
                logger.info("Cache wiped: %s", f.name)


def _download(url: str) -> pathlib.Path:
    """Wipe cache, download url into cache/, return the local path."""
    _wipe_cache()
    CACHE_DIR.mkdir(exist_ok=True)

    filename = url.split("/")[-1].split("?")[0] or "apod_media"
    dest = CACHE_DIR / filename

    logger.info("Downloading %s ...", url)
    urllib.request.urlretrieve(url, dest)
    logger.info("Saved to %s (%.1f MB)", dest, dest.stat().st_size / 1_048_576)
    return dest


def _fetch_og_image(article_url: str) -> str | None:
    """Try to scrape the og:image meta tag from an article page."""
    try:
        req = urllib.request.Request(
            article_url,
            headers={"User-Agent": "Mozilla/5.0 (compatible; ScienceBot/1.0)"},
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            html = resp.read(65536).decode("utf-8", errors="ignore")  # first 64 KB is enough

        # Handle both attribute orderings
        match = re.search(
            r'<meta[^>]+property=["\']og:image["\'][^>]+content=["\']([^"\']+)["\']', html
        ) or re.search(
            r'<meta[^>]+content=["\']([^"\']+)["\'][^>]+property=["\']og:image["\']', html
        )
        return match.group(1) if match else None
    except Exception as exc:
        logger.debug("og:image scrape failed for %s: %s", article_url, exc)
        return None


async def _send_article(bot, channel_id: str, article: dict, text: str) -> None:
    """Send an article: image (if available) then text. Falls back to text-only."""
    image_url = article.get("image_url")

    # Fall back to og:image scrape if the feed didn't include one
    if not image_url:
        image_url = _fetch_og_image(article["link"])

    if image_url:
        local_file = None
        try:
            local_file = _download(image_url)
            with open(local_file, "rb") as f:
                await bot.send_photo(chat_id=channel_id, photo=f, disable_notification=True)
            await asyncio.sleep(MESSAGE_DELAY)
        except Exception as exc:
            logger.warning("Could not send image for '%s': %s — sending text only.", article.get("title_en", ""), exc)
        finally:
            if local_file and local_file.exists():
                local_file.unlink()

    await bot.send_message(
        chat_id=channel_id,
        text=text,
        parse_mode=ParseMode.MARKDOWN,
        disable_web_page_preview=True,
        disable_notification=True,
    )


def _escape(text: str) -> str:
    """Escape Markdown special characters in plain text fields."""
    return text.replace("*", "\\*").replace("_", "\\_")


_MONTHS_ES = {
    1: "enero", 2: "febrero", 3: "marzo", 4: "abril",
    5: "mayo", 6: "junio", 7: "julio", 8: "agosto",
    9: "septiembre", 10: "octubre", 11: "noviembre", 12: "diciembre",
}


def format_header(digest_date: date) -> str:
    date_str = f"{digest_date.day} de {_MONTHS_ES[digest_date.month]} de {digest_date.year}"
    return f"🔬 *Resumen Científico Diario — {date_str}*"


def format_article(article: dict) -> str:
    """Format a single article as a bilingual Telegram Markdown message."""
    emoji = article.get("emoji", "📰")
    title_es = _escape(article["title_es"])
    title_en = _escape(article["title_en"])
    explanation_es = _escape(article["explanation_es"])
    explanation_en = _escape(article["explanation_en"])
    link = article["link"]
    source = _escape(article["source"])

    return (
        f"{emoji} *{title_es}*\n"
        f"\n"
        f"{explanation_es}\n"
        f"\n"
        f"——\n"
        f"\n"
        f"{emoji} *{title_en}*\n"
        f"\n"
        f"{explanation_en}\n"
        f"\n"
        f"[Leer más / Read more]({link}) · _{source}_"
    )


def format_apod_text(apod: dict, translation: dict) -> str:
    """Format the bilingual APOD text block (sent as a separate message after the media)."""
    title_es = _escape(translation["title_es"])
    title_en = _escape(apod["title"])
    explanation_es = _escape(translation["explanation_es"])
    explanation_en = _escape(apod["explanation"])

    return (
        f"🔭 *{title_es}*\n"
        f"\n"
        f"{explanation_es}\n"
        f"\n"
        f"——\n"
        f"\n"
        f"🔭 *{title_en}*\n"
        f"\n"
        f"{explanation_en}\n"
        f"\n"
        f"_📸 NASA Astronomy Picture of the Day_"
    )


async def post_digest(
    bot_token: str,
    channel_id: str,
    articles: list[dict],
    digest_date: date | None = None,
) -> None:
    """Post one message per article."""
    if digest_date is None:
        digest_date = date.today()

    bot = telegram.Bot(token=bot_token)

    for i, article in enumerate(articles):
        await asyncio.sleep(MESSAGE_DELAY)
        await _send_article(bot, channel_id, article, format_article(article))
        logger.info("Posted article %d/%d to '%s'", i + 1, len(articles), channel_id)

    logger.info("Digest complete — %d messages posted to '%s'", len(articles), channel_id)


async def post_apod(
    bot_token: str,
    channel_id: str,
    apod: dict,
    translation: dict,
) -> None:
    """Post the APOD: media first, then the bilingual text as a separate message."""
    bot = telegram.Bot(token=bot_token)

    media_url = apod.get("hdurl") or apod.get("url", "")
    local_file = None
    try:
        local_file = _download(media_url)

        if apod.get("media_type") == "image":
            with open(local_file, "rb") as f:
                await bot.send_photo(chat_id=channel_id, photo=f, disable_notification=True)
        else:
            with open(local_file, "rb") as f:
                await bot.send_video(chat_id=channel_id, video=f, disable_notification=True)
    finally:
        if local_file and local_file.exists():
            local_file.unlink()
            logger.info("Deleted cached file: %s", local_file.name)

    await asyncio.sleep(MESSAGE_DELAY)
    await bot.send_message(
        chat_id=channel_id,
        text=format_apod_text(apod, translation),
        parse_mode=ParseMode.MARKDOWN,
        disable_web_page_preview=True,
        disable_notification=True,
    )
    logger.info("APOD posted to '%s'", channel_id)
