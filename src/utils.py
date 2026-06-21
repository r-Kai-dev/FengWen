"""Shared utilities for Feng Wen feed scripts.

Consolidates what was previously spread across:
  - feed_util.py   (Atom XML writing)
  - common.py      (logging, output dirs, API config loading, async fetch)
  - config_util.py (site config loading from html.json / js.json)

All scripts in src/ import this as a sibling module:
    from utils import load_feeds_config, write_atom_feed, fetch_page, ...
"""

import asyncio
import json
import logging
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from xml.dom import minidom
import xml.etree.ElementTree as ET

from curl_cffi.requests import AsyncSession, Session as SyncSession

# ── Paths ──────────────────────────────────────────────────────────
SRC_DIR = Path(__file__).resolve().parent
PROJECT_DIR = SRC_DIR.parent
FEEDS_DIR = PROJECT_DIR / "feeds"
CONFIG_DIR = PROJECT_DIR / "config"

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════════
#  Logging & output dirs
# ═══════════════════════════════════════════════════════════════════

def setup_logging() -> None:
    """Configure logging once (idempotent via basicConfig)."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(levelname)s - %(message)s",
    )


def ensure_output_dir() -> None:
    """Create the feeds output directory if it doesn't exist."""
    FEEDS_DIR.mkdir(exist_ok=True)


# ═══════════════════════════════════════════════════════════════════
#  Config loading
# ═══════════════════════════════════════════════════════════════════

def load_feeds_config(org_key: str) -> dict:
    """Load the created-feed entry for *org_key* from config/feeds.json.

    Returns a dict with:
      - org_key, name, strategy, base_url, category
      - favicon (str or None)
      - pages: dict of {page_key: {key, label, url, output_file, ...}}

    Raises ValueError if *org_key* not found.
    """
    config_file = CONFIG_DIR / "feeds.json"
    with open(config_file, "r", encoding="utf-8") as f:
        cfg = json.load(f)

    for entry in cfg.get("created", []):
        if entry.get("org_key") == org_key:
            result = dict(entry)
            result["pages"] = {p["key"]: p for p in entry.get("pages", [])}
            return result

    raise ValueError(
        f"Configuration for org_key '{org_key}' not found in config/feeds.json"
    )


# ═══════════════════════════════════════════════════════════════════
#  Sync fetch helper (curl_cffi) — for scrape/crawl scripts
# ═══════════════════════════════════════════════════════════════════

def fetch_page(
    url: str,
    *,
    impersonate: str = "chrome120",
    timeout: int = 30,
    headers: dict[str, str] | None = None,
) -> str:
    """GET *url* synchronously with browser impersonation, return text."""
    with SyncSession() as s:
        resp = s.get(url, impersonate=impersonate, timeout=timeout, headers=headers)
        resp.raise_for_status()
        return resp.text


# ═══════════════════════════════════════════════════════════════════
#  Async fetch helper (curl_cffi) — for request scripts
# ═══════════════════════════════════════════════════════════════════

async def fetch_with_retry(
    session: AsyncSession,
    url: str,
    *,
    max_retries: int = 3,
    base_delay: float = 1.0,
    **kwargs: Any,
):
    """GET *url* with exponential-backoff retries.

    *kwargs* are forwarded to ``session.get()`` (e.g. ``impersonate``,
    ``timeout``, ``params``).
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
                wait = base_delay * (2 ** attempt)
                logging.warning(
                    "Request to %s failed (attempt %d/%d): %s. Retrying in %.1fs …",
                    url,
                    attempt + 1,
                    max_retries,
                    exc,
                    wait,
                )
                time.sleep(wait)
    raise last_exception  # type: ignore[misc]


# ═══════════════════════════════════════════════════════════════════
#  Atom feed writing
# ═══════════════════════════════════════════════════════════════════

def compact(d: dict) -> dict:
    """Remove keys with empty/falsy values from a dict.

    Keeps keys whose value is truthy (non-None, non-empty string,
    non-empty list, non-empty dict).  Used by parsers to avoid
    emitting fields with no meaningful data.
    """
    return {k: v for k, v in d.items() if v}


def write_atom_feed(
    output_path: Path,
    entries: list[dict],
    feed_title: str,
    feed_link: str,
    feed_author: str | None = None,
    feed_icon: str | None = None,
) -> None:
    """Write a list of entry dicts to an Atom XML feed file.

    Entries are sorted by ``published_date`` descending, then by ``title``
    ascending for ties, to ensure stable ordering across runs.

    Each entry dict may contain:
      - title (str)
      - url / link (str)
      - id (str) — optional, falls back to url
      - published_date (str, ISO-8601)
      - summary (str) — optional, plain text
      - content (str) — optional, HTML for ``<content type="html">``
      - categories (list of str) — optional
      - organization (str) — used as author if feed_author not given

    If *feed_icon* is provided, an ``<icon>`` element is added to the feed.
    """

    # Stable sort: date descending, title ascending for ties.
    entries.sort(key=lambda e: e.get("title", "") or "")
    entries.sort(key=lambda e: e.get("published_date", "") or "", reverse=True)

    feed = ET.Element("feed", xmlns="http://www.w3.org/2005/Atom")

    ET.SubElement(feed, "title").text = feed_title
    if feed_icon:
        ET.SubElement(feed, "icon").text = feed_icon
    ET.SubElement(feed, "link", href=feed_link)
    ET.SubElement(feed, "id").text = feed_link

    # Latest date for <updated>
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

        content = entry.get("content", "")
        if content:
            ET.SubElement(e, "content", type="html").text = content

        for cat in entry.get("categories", []):
            if cat:
                ET.SubElement(e, "category", term=cat)

    rough = ET.tostring(feed, encoding="utf-8")
    dom = minidom.parseString(rough)
    pretty = dom.toprettyxml(indent="  ", encoding="utf-8")
    output_path.write_bytes(pretty)
    logger.info(f"Wrote Atom feed ({len(entries)} entries) to {output_path}")
