"""Shared utilities for API-based request scripts."""

import json
import logging
import time
from datetime import datetime, timezone
from pathlib import Path
from xml.dom import minidom

# ── Paths ────────────────────────────────────────────────
PROJECT_DIR = Path(__file__).resolve().parent.parent.parent
PARSED_DIR = PROJECT_DIR / "feeds"
CONFIG_DIR = PROJECT_DIR / "config"


def setup_logging() -> None:
    """Configure logging once (idempotent via basicConfig)."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(levelname)s - %(message)s",
    )


def ensure_output_dir() -> None:
    """Create the output directory if it doesn't exist."""
    PARSED_DIR.mkdir(exist_ok=True)


def load_api_config(org_key: str) -> dict:
    """Load and return the site config matching *org_key* from *config/api.json*.

    Returns a dict with ``base_url`` (str), ``pages`` (dict keyed by page key),
    and ``favicon`` (str or None).
    """
    config_file = CONFIG_DIR / "api.json"
    with open(config_file, "r", encoding="utf-8") as f:
        api_config = json.load(f)

    for site in api_config.get("sites", []):
        if site.get("org_key") == org_key:
            pages = {p["key"]: p for p in site.get("pages", [])}
            return {
                "base_url": site["base_url"],
                "pages": pages,
                "favicon": site.get("favicon"),
            }

    raise ValueError(f"Configuration for '{org_key}' not found in config/api.json")


async def fetch_with_retry(
    session,
    url: str,
    *,
    max_retries: int = 3,
    base_delay: float = 1.0,
    **kwargs,
):
    """GET *url* with exponential-backoff retries.

    *kwargs* are forwarded to ``session.get()`` (e.g. ``impersonate``, ``timeout``,
    ``params``).
    """
    last_exception = None
    for attempt in range(max_retries):
        try:
            response = await session.get(url, **kwargs)
            response.raise_for_status()
            return response
        except Exception as exc:
            last_exception = exc
            if attempt < max_retries - 1:
                wait = base_delay * (2**attempt)
                logging.warning(
                    "Request to %s failed (attempt %d/%d): %s. Retrying in %.1fs …",
                    url,
                    attempt + 1,
                    max_retries,
                    exc,
                    wait,
                )
                time.sleep(wait)  # blocking sleep is fine for sequential scrapes
    raise last_exception  # type: ignore[misc]


def write_atom_feed(
    output_path: Path,
    entries: list[dict],
    feed_title: str,
    feed_link: str,
    feed_author: str | None = None,
    feed_icon: str | None = None,
) -> None:
    """Write a list of entry dicts to an Atom XML feed file.

    Each entry dict may contain:
      - title (str)
      - url / link (str)
      - id (str) — optional, falls back to url
      - published_date (str, ISO-8601)
      - summary (str) — optional, plain text
      - categories (list of str) — optional
      - organization (str) — used as author if feed_author not given

    If *feed_icon* is provided, an ``<icon>`` element is added to the feed.
    """
    import xml.etree.ElementTree as ET

    feed = ET.Element("feed", xmlns="http://www.w3.org/2005/Atom")

    ET.SubElement(feed, "title").text = feed_title
    if feed_icon:
        ET.SubElement(feed, "icon").text = feed_icon
    ET.SubElement(feed, "link", href=feed_link)
    ET.SubElement(feed, "id").text = feed_link

    dates = [e.get("published_date", "") for e in entries if e.get("published_date")]
    dates.sort(reverse=True)
    updated = dates[0] if dates else datetime.now(timezone.utc).isoformat()
    ET.SubElement(feed, "updated").text = updated

    author_name = feed_author or (entries[0].get("organization") if entries else None)
    if author_name:
        author = ET.SubElement(feed, "author")
        ET.SubElement(author, "name").text = author_name

    for entry in entries:
        e = ET.SubElement(feed, "entry")
        ET.SubElement(e, "title").text = entry.get("title", "")
        ET.SubElement(e, "link", href=entry.get("url", entry.get("link", "")))
        ET.SubElement(e, "id").text = entry.get("id", entry.get("url", ""))

        pub_date = entry.get("published_date", "")
        if pub_date:
            ET.SubElement(e, "published").text = pub_date
            ET.SubElement(e, "updated").text = pub_date

        summary = entry.get("summary", "")
        if summary:
            ET.SubElement(e, "summary", type="text").text = summary

        for cat in entry.get("categories", []):
            if cat:
                ET.SubElement(e, "category", term=cat)

    rough = ET.tostring(feed, encoding="utf-8")
    dom = minidom.parseString(rough)
    pretty = dom.toprettyxml(indent="  ", encoding="utf-8")
    output_path.write_bytes(pretty)
    logging.getLogger(__name__).info(
        f"Wrote Atom feed ({len(entries)} entries) to {output_path}"
    )
