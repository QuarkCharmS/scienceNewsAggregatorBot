"""NASA Astronomy Picture of the Day fetcher."""

import logging
import os
import urllib.request
import json

logger = logging.getLogger(__name__)

APOD_URL = "https://api.nasa.gov/planetary/apod"


def fetch_apod() -> dict:
    """Fetch today's APOD entry from the NASA API.

    Returns a dict with at least: title, explanation, url, media_type.
    Raises on network or API errors.
    """
    api_key = os.getenv("NASA_API_KEY", "DEMO_KEY")
    full_url = f"{APOD_URL}?api_key={api_key}"

    with urllib.request.urlopen(full_url, timeout=15) as response:
        data = json.loads(response.read().decode())

    logger.info("Fetched APOD: '%s' (media_type=%s)", data.get("title"), data.get("media_type"))
    return data
