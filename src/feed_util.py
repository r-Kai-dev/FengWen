"""Shared Atom-feed writing utilities used by both parse and request scripts."""

import logging
from datetime import datetime, timezone
from pathlib import Path
from xml.dom import minidom

import xml.etree.ElementTree as ET

logger = logging.getLogger(__name__)


def compact(d: dict) -> dict:
    """Remove keys with empty/falsy values from a dict.

    Keeps keys whose value is truthy (non-None, non-empty string,
    non-empty list, non-empty dict). Used by parsers to avoid
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
