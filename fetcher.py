"""RSS feed fetcher for science news sources."""

import logging
import re
from datetime import datetime, timezone, timedelta

import feedparser

logger = logging.getLogger(__name__)

RSS_FEEDS = {
    "ScienceDaily": "https://www.sciencedaily.com/rss/top/science.xml",
    "ScienceDaily Space": "https://www.sciencedaily.com/rss/space_time.xml",
    "NASA": "https://www.nasa.gov/rss/dyn/breaking_news.rss",
    "arXiv AI": "http://arxiv.org/rss/cs.AI",
    "arXiv Physics": "http://arxiv.org/rss/physics",
    "Nature": "https://www.nature.com/nature.rss",
    "PubMed": "https://pubmed.ncbi.nlm.nih.gov/rss/search/trending/?format=rss",
}

PHYSICS_ASTRONOMY_FEEDS = {
    # Astronomy
    "Sky & Telescope": "https://www.skyandtelescope.com/astronomy-news/feed/",
    "The Planetary Society": "https://planetary.org/rss/articles",
    "EarthSky": "https://earthsky.org/feed/",
    "Astrobites": "https://astrobites.org/feed",
    "Space.com": "https://www.space.com/feeds.xml",
    "Universe Today": "https://www.universetoday.com/feed",
    "ESA Top News": "https://www.esa.int/rssfeed/TopNews",
    # Physics
    "Quanta Magazine": "https://quantamagazine.org/physics/feed",
    "APS Physics": "https://feeds.aps.org/rss/recent/physics.xml",
    "CERN News": "https://home.cern/api/news/feed.rss",
    "arXiv astro-ph.GA": "https://arxiv.org/rss/astro-ph.GA",
    "arXiv astro-ph.HE": "https://arxiv.org/rss/astro-ph.HE",
    "arXiv astro-ph.CO": "https://arxiv.org/rss/astro-ph.CO",
}

TECH_AI_FEEDS = {
    # Technology
    "MIT Technology Review": "https://www.technologyreview.com/feed",
    "IEEE Spectrum": "https://feeds.feedburner.com/IeeeSpectrum",
    "Ars Technica Science": "https://arstechnica.com/science/feed",
    "Ars Technica": "https://feeds.arstechnica.com/arstechnica/index",
    "Wired Science": "https://www.wired.com/feed/category/science/rss",
    "Wired": "https://www.wired.com/feed/rss",
    "The Verge": "https://www.theverge.com/rss/index.xml",
    # AI / Computer Science
    "arXiv cs.AI": "https://arxiv.org/rss/cs.AI",
    "arXiv cs.LG": "https://arxiv.org/rss/cs.LG",
    "DeepMind Blog": "https://deepmind.com/blog/feed/basic/",
    "MIT News AI": "http://news.mit.edu/rss/topic/artificial-intelligence2",
    "VentureBeat AI": "https://venturebeat.com/category/ai/feed/",
}

ANTHROPOLOGY_FEEDS = {
    # General Anthropology
    "Anthropology News": "https://www.rsscatalog.com/Anthropology",
    "Perspectives in Anthropology": "https://perspectivesinanthropology.com/feed/",
    # Human Evolution & Biological Anthropology
    "ScienceDaily Human Evolution": "https://www.sciencedaily.com/rss/fossils_ruins/human_evolution.xml",
    "ScienceDaily Early Humans": "https://www.sciencedaily.com/rss/fossils_ruins/early_humans.xml",
    "ScienceDaily Fossils & Ruins": "https://www.sciencedaily.com/rss/fossils_ruins.xml",
    "The Leakey Foundation": "https://leakeyfoundation.org/feed/",
    "Phys.org Evolution": "https://phys.org/rss-feed/biology-news/evolution/",
    # Archaeology
    "Archaeology Magazine": "https://archaeology.org/feed/",
    "Ancient Origins": "https://feeds.feedburner.com/AncientOrigins",
    "ScienceDaily Archaeology": "https://www.sciencedaily.com/rss/fossils_ruins/archaeology.xml",
    "Biblical Archaeology Society": "https://biblicalarchaeology.org/feed",
}

SOFTWARE_FEEDS = {
    # Software / DevOps
    "The New Stack": "https://thenewstack.io/feed",
    "Hacker News Best": "https://hnrss.org/best",
    "InfoQ DevOps": "https://feed.infoq.com/devops",
    "InfoQ": "https://feed.infoq.com",
    # Cloud
    "GitHub Blog": "https://github.blog/feed",
    "AWS News": "https://aws.amazon.com/blogs/aws/feed",
    "AWS DevOps": "https://aws.amazon.com/blogs/devops/feed",
    "Google Cloud": "https://cloud.google.com/feeds/gcp-news.xml",
    "Azure DevOps": "https://devblogs.microsoft.com/devops/feed",
}

MAX_ARTICLES_PER_FEED = 5
LOOKBACK_HOURS = 24


def _parse_published(entry) -> datetime | None:
    """Return a timezone-aware datetime for an entry, or None if unparseable."""
    # feedparser normalises published_parsed / updated_parsed to UTC time.struct_time
    for attr in ("published_parsed", "updated_parsed"):
        t = getattr(entry, attr, None)
        if t is not None:
            try:
                return datetime(*t[:6], tzinfo=timezone.utc)
            except (TypeError, ValueError):
                continue
    return None


def _is_recent(entry, cutoff: datetime) -> bool:
    """Return True if the entry was published at or after *cutoff*, or if its
    publish date is missing (include rather than silently drop undated entries)."""
    published = _parse_published(entry)
    if published is None:
        return True  # can't tell — include it
    return published >= cutoff


def _extract_image_url(entry) -> str | None:
    """Try to pull an image URL out of a feedparser entry."""
    # media:content (most common in modern feeds)
    for media in getattr(entry, "media_content", []):
        url = media.get("url", "")
        if url and media.get("medium") == "image":
            return url
        if url and media.get("type", "").startswith("image/"):
            return url

    # <enclosure type="image/...">
    for enc in getattr(entry, "enclosures", []):
        if enc.get("type", "").startswith("image/") and enc.get("url"):
            return enc["url"]

    # media:thumbnail
    for thumb in getattr(entry, "media_thumbnail", []):
        if thumb.get("url"):
            return thumb["url"]

    # <link rel="..." type="image/...">
    for link in getattr(entry, "links", []):
        if link.get("type", "").startswith("image/") and link.get("href"):
            return link["href"]

    return None


def strip_html(text: str) -> str:
    """Remove HTML tags and decode common entities from a string."""
    if not text:
        return ""
    text = re.sub(r"<[^>]+>", "", text)
    text = (
        text.replace("&amp;", "&")
        .replace("&lt;", "<")
        .replace("&gt;", ">")
        .replace("&quot;", '"')
        .replace("&#39;", "'")
        .replace("&nbsp;", " ")
    )
    return re.sub(r"\s+", " ", text).strip()


def fetch_feed(name: str, url: str, cutoff: datetime) -> list[dict]:
    """Fetch and parse a single RSS feed, keeping only articles newer than *cutoff*."""
    try:
        feed = feedparser.parse(url)
        if feed.bozo and feed.bozo_exception:
            logger.warning("Feed '%s' is malformed: %s", name, feed.bozo_exception)

        articles = []
        for entry in feed.entries:
            if not _is_recent(entry, cutoff):
                continue

            title = strip_html(getattr(entry, "title", ""))
            summary = strip_html(
                getattr(entry, "summary", "") or getattr(entry, "description", "")
            )
            link = getattr(entry, "link", "")

            if not title or not link:
                continue

            articles.append(
                {
                    "title": title,
                    "summary": summary[:600],  # cap to avoid huge prompts
                    "link": link,
                    "source": name,
                    "published": _parse_published(entry).isoformat()
                    if _parse_published(entry)
                    else None,
                    "image_url": _extract_image_url(entry),
                }
            )

            if len(articles) >= MAX_ARTICLES_PER_FEED:
                break

        logger.info("Fetched %d recent articles from '%s'", len(articles), name)
        return articles

    except Exception as exc:
        logger.warning("Failed to fetch feed '%s' (%s): %s", name, url, exc)
        return []


def fetch_all_articles(feeds: dict[str, str] | None = None) -> list[dict]:
    """Fetch articles published in the last 24 hours from the given feed dict.

    Defaults to RSS_FEEDS (the general science digest).
    Pass PHYSICS_ASTRONOMY_FEEDS for the physics & astronomy digest.
    """
    if feeds is None:
        feeds = RSS_FEEDS

    cutoff = datetime.now(tz=timezone.utc) - timedelta(hours=LOOKBACK_HOURS)
    logger.info("Fetching articles published after %s UTC", cutoff.strftime("%Y-%m-%d %H:%M"))

    all_articles = []
    for name, url in feeds.items():
        all_articles.extend(fetch_feed(name, url, cutoff))

    logger.info("Total recent articles fetched: %d", len(all_articles))
    return all_articles
