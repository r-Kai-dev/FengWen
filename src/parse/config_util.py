"""Shared utility to load site configuration and write Atom feeds.

Replaces the old per-parser load_config() that looked for sites_config.json.
Derives cache/output filenames from org_key + pages.
"""

import json
import logging
import re
from datetime import datetime, timezone
from pathlib import Path
from xml.dom import minidom

logger = logging.getLogger(__name__)

project_dir = Path(__file__).resolve().parent.parent.parent
config_dir = project_dir / "config"


def _sanitize(name: str) -> str:
    """Derive a safe filename slug from a page path.

    Must match the logic in fetch_js.py's make_cache_filename:
    - strip leading/trailing slashes
    - replace non-word chars with hyphens
    - use "index" for empty slugs (e.g. page = "/")
    """
    slug = re.sub(r"[^\w]", "-", name.strip("/"))
    return slug if slug else "index"


def load_site_config(org_key: str, config_name: str = "html.json") -> dict:
    """Load site configuration for the given org_key.

    Args:
        org_key:    The org_key to look up.
        config_name: Config file name (e.g. 'html.json' or 'js.json').
                     Defaults to 'html.json'.

    Returns a dict with:
      - cache_files:  {page_name: cache_html_filename, ...}
      - output_files: {page_name: output_xml_filename, ...}
      - (optional) extra outputs like 'trending_combined' for github

    Each page_name is the raw value from the config file's 'pages' array.
    """
    config_file = config_dir / config_name
    with open(config_file, "r", encoding="utf-8") as f:
        sites_config = json.load(f)

    for site in sites_config:
        if site.get("org_key") == org_key:
            return _build_file_mapping(site)

    raise ValueError(
        f"Configuration for org_key '{org_key}' not found in config/{config_name}"
    )


def compact(d: dict) -> dict:
    """Remove keys with empty/falsy values from a dict.

    Keeps keys whose value is truthy (non-None, non-empty string,
    non-empty list, non-empty dict). Used by parsers to avoid
    emitting fields with no meaningful data.
    """
    return {k: v for k, v in d.items() if v}


def _build_file_mapping(site: dict) -> dict:
    """Build output_files and cache_files mappings from a site config entry."""
    org_key = site["org_key"]
    pages = site.get("pages", [])

    output_files = {}
    cache_files = {}

    for page in pages:
        safe_name = _sanitize(page)
        cache_files[page] = f"{org_key}_{safe_name}.html"
        output_files[page] = f"{org_key}_{safe_name}.xml"

    # Include any extra_outputs (e.g., github's trending_combined)
    extra = site.get("extra_outputs", {})
    if extra:
        output_files.update(extra)

    return {
        "output_files": output_files,
        "cache_files": cache_files,
        "favicon": site.get("favicon"),
        "url": site.get("url", ""),
    }


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
      - categories (list of str) — optional
      - organization (str) — used as author if feed_author not given

    If *feed_icon* is provided, an ``<icon>`` element is added to the feed.
    """
    import xml.etree.ElementTree as ET

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

        for cat in entry.get("categories", []):
            if cat:
                ET.SubElement(e, "category", term=cat)

    rough = ET.tostring(feed, encoding="utf-8")
    dom = minidom.parseString(rough)
    pretty = dom.toprettyxml(indent="  ", encoding="utf-8")
    output_path.write_bytes(pretty)
    logger.info(f"Wrote Atom feed ({len(entries)} entries) to {output_path}")
