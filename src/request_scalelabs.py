"""Fetch Scale Labs blog and papers from Next.js RSC payloads in initial HTML."""

import hashlib
import json
import logging
import re
from datetime import datetime, timezone

from utils import (
    FEEDS_DIR, setup_logging, ensure_output_dir,
    load_feeds_config, fetch_page, compact, write_atom_feed,
)

setup_logging()
ensure_output_dir()
ORG_KEY = "scalelabs"


def _parse_date(date_str: str) -> str:
    """Convert a date string to ISO-8601. Handles ISO dates and M/D/YYYY."""
    if not date_str:
        return datetime.now(timezone.utc).isoformat()
    # Already ISO
    if "T" in date_str or "-" in date_str:
        return date_str
    # M/D/YYYY format
    try:
        dt = datetime.strptime(date_str.strip(), "%m/%d/%Y")
        return dt.replace(tzinfo=timezone.utc).isoformat()
    except ValueError:
        return datetime.now(timezone.utc).isoformat()


def _extract_json_array(text: str, key: str) -> list[dict]:
    """Extract a JSON array from a string given a key like ``"posts":[``.

    Uses bracket-depth counting to find the matching ``]``.
    """
    prefix = f'"{key}":['
    idx = text.find(prefix)
    if idx == -1:
        return []

    start = idx + len(prefix) - 1  # point at the opening '['
    depth = 0
    end = start
    for i, c in enumerate(text[start:], start):
        if c == "[":
            depth += 1
        elif c == "]":
            depth -= 1
            if depth == 0:
                end = i + 1
                break

    if end == start:
        return []

    try:
        return json.loads(text[start:end])
    except json.JSONDecodeError:
        logging.warning("Failed to parse %s JSON array", key)
        return []


def _fetch_items(page_url: str, array_key: str) -> list[dict]:
    """Fetch a Scale Labs page and extract items from the RSC payload."""
    html = fetch_page(page_url, impersonate="chrome120", timeout=30)

    # Extract all self.__next_f.push chunks
    chunks = re.findall(
        r'self\.__next_f\.push\(\[1,\s*"(.*?)"\s*\]\)',
        html, re.DOTALL,
    )
    if not chunks:
        logging.warning("No __next_f chunks found for %s", page_url)
        return []

    for chunk in chunks:
        decoded = chunk.encode("utf-8").decode("unicode_escape", errors="replace")
        if f'"{array_key}":[' in decoded:
            return _extract_json_array(decoded, array_key)

    logging.warning("No '%s' array found in chunks for %s", array_key, page_url)
    return []


def _build_blog_entry(post: dict, base_url: str) -> dict | None:
    """Convert a blog post dict to an Atom entry."""
    slug_obj = post.get("slug", {})
    slug = slug_obj.get("current", "") if isinstance(slug_obj, dict) else ""
    title = post.get("title", "")
    if not title or not slug:
        return None

    url = f"{base_url}/blog/{slug}"
    entry_id = hashlib.md5(f"{ORG_KEY}_{slug}".encode()).hexdigest()
    date = post.get("date", "")
    intro = post.get("intro", "")
    categories = post.get("categories", [])
    authors = post.get("authorNames", [])

    summary = intro if intro else None
    if authors:
        author_text = ", ".join(authors)
        summary = f"{summary} — By {author_text}" if summary else f"By {author_text}"

    return compact({
        "title": title,
        "url": url,
        "id": entry_id,
        "published_date": _parse_date(date),
        "summary": summary,
        "categories": categories if categories else [],
        "organization": "Scale Labs",
    })


def _build_paper_entry(paper: dict, base_url: str) -> dict | None:
    """Convert a paper dict to an Atom entry."""
    title = paper.get("title", "")
    slug = paper.get("slug", "")
    link = paper.get("link", "")
    external_url = paper.get("externalUrl", "")
    if not title:
        return None

    # Prefer the internal link, fall back to external
    if link:
        url = f"{base_url}{link}"
    elif external_url:
        url = external_url
    else:
        url = f"{base_url}/papers/{slug}"

    entry_id = hashlib.md5(f"{ORG_KEY}_{slug}_{title}".encode()).hexdigest()
    date_sort = paper.get("dateSort", "") or paper.get("date", "")
    categories = paper.get("categories", [])
    authors_str = paper.get("authors", "")

    summary = None
    if authors_str:
        summary = f"By {authors_str}"

    return compact({
        "title": title,
        "url": url,
        "id": entry_id,
        "published_date": _parse_date(date_sort),
        "summary": summary,
        "categories": categories if categories else [],
        "organization": "Scale Labs",
    })


def main():
    config = load_feeds_config(ORG_KEY)
    favicon = config.get("favicon")
    base_url = config["base_url"]

    for page_key, page in config["pages"].items():
        logging.info("Fetching %s: %s", page["label"], page["url"])

        if page_key == "blog":
            raw_items = _fetch_items(page["url"], "posts")
            builder = _build_blog_entry
        elif page_key == "papers":
            raw_items = _fetch_items(page["url"], "papers")
            builder = _build_paper_entry
        else:
            logging.warning("Unknown page key: %s", page_key)
            continue

        if not raw_items:
            logging.warning("No items found for %s", page_key)
            continue

        entries = []
        for item in raw_items:
            entry = builder(item, base_url)
            if entry:
                entries.append(entry)

        logging.info("Parsed %d entries for %s", len(entries), page_key)

        if entries:
            write_atom_feed(FEEDS_DIR / page["output_file"], entries,
                            feed_title=page["label"],
                            feed_link=page.get("feed_link", page["url"]),
                            feed_icon=favicon)


if __name__ == "__main__":
    main()
