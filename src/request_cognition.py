"""Fetch Cognition blog posts from the Next.js RSC endpoint."""

import asyncio
import hashlib
import json
import logging
import re
from datetime import datetime, timezone

from curl_cffi.requests import AsyncSession

from utils import (
    FEEDS_DIR, setup_logging, ensure_output_dir,
    load_feeds_config, fetch_with_retry, compact, write_atom_feed,
)

setup_logging()
ensure_output_dir()
ORG_KEY = "cognition"

RSC_HEADERS = {
    "RSC": "1",
    "Next-Router-State-Tree": "%5B%22%22%2C%22%2Fblog%22%2C%22page%22%5D",
}


def _parse_date(date_str: str) -> str:
    """Convert MM.DD.YY to ISO-8601 date string."""
    try:
        dt = datetime.strptime(date_str.strip(), "%m.%d.%y")
        return dt.replace(tzinfo=timezone.utc).isoformat()
    except ValueError:
        return date_str


def _extract_quoted_strings(json_obj, key: str) -> list[str]:
    """Recursively find all string values for a given key in a nested JSON object."""
    results = []
    if isinstance(json_obj, dict):
        for k, v in json_obj.items():
            if k == key and isinstance(v, str):
                results.append(v)
            results.extend(_extract_quoted_strings(v, key))
    elif isinstance(json_obj, list):
        for item in json_obj:
            results.extend(_extract_quoted_strings(item, key))
    return results


def _parse_li_block(block) -> dict | None:
    """Parse a parsed JSON ``["$","li",key,{props}]`` block into a post dict."""
    if not isinstance(block, list) or len(block) < 4:
        return None
    if block[0] != "$" or block[1] != "li":
        return None

    props = block[3] if isinstance(block[3], dict) else {}
    if not isinstance(props, dict):
        return None

    hrefs = _extract_quoted_strings(props, "href")
    href = next((h for h in hrefs if h.startswith("/blog/") and h != "/blog/"), None)
    if not href:
        return None

    children_values = _extract_quoted_strings(props, "children")
    content_values = [v for v in children_values
                      if v not in ("h2", "span", "p", "li", "h1",
                                   "div", "ul", "a", "section", "main",
                                   "01", "02", "03", "04", "05",
                                   "$undefined")]

    if len(content_values) < 2:
        return None

    # Find date-like value (MM.DD.YY) to anchor title/summary
    date_str = ""
    date_idx = -1
    for i, v in enumerate(content_values):
        if re.match(r'^\d{2}\.\d{2}\.\d{2}$', v):
            date_str = v
            date_idx = i
            break

    if date_idx < 0:
        return None

    title = content_values[date_idx - 1] if date_idx > 0 else ""
    summary = content_values[date_idx + 1] if date_idx + 1 < len(content_values) else ""

    if not title:
        return None

    url = f"https://cognition.com{href}"
    entry_id = hashlib.md5(f"{ORG_KEY}_{href}".encode()).hexdigest()
    published = _parse_date(date_str)

    return {
        "title": title,
        "url": url,
        "id": entry_id,
        "published_date": published,
        "summary": summary,
        "organization": "Cognition",
    }


def parse_rsc_posts(text: str) -> list[dict]:
    """Parse Next.js streaming RSC response for blog posts.

    Handles two formats:
    1. Inline ``["$","li",...]`` blocks anywhere in the text
    2. Top-level ``XX:["$","li",...]`` component definitions
    """
    seen_urls = set()
    posts = []

    # Find all ["$","li",... blocks via bracket-depth counting
    marker = '["$","li","'
    idx = 0
    while True:
        idx = text.find(marker, idx)
        if idx == -1:
            break
        # Bracket-count to find the end of the JSON array
        depth = 0
        end = idx
        for i in range(idx, min(idx + 15000, len(text))):
            if text[i] == "[":
                depth += 1
            elif text[i] == "]":
                depth -= 1
                if depth == 0:
                    end = i + 1
                    break
        if end == idx:
            idx += len(marker)
            continue

        try:
            block = json.loads(text[idx:end])
        except json.JSONDecodeError:
            idx += len(marker)
            continue

        entry = _parse_li_block(block)
        if entry and entry["url"] not in seen_urls:
            seen_urls.add(entry["url"])
            posts.append(entry)

        idx = end

    return posts


async def main():
    config = load_feeds_config(ORG_KEY)
    favicon = config.get("favicon")
    base_url = config["base_url"]

    for page_key, page in config["pages"].items():
        logging.info("Fetching %s: %s", page["label"], page["url"])
        async with AsyncSession() as session:
            response = await fetch_with_retry(
                session, page["url"],
                impersonate="chrome120", timeout=30,
                headers=RSC_HEADERS,
            )
            raw_posts = parse_rsc_posts(response.text)

        if not raw_posts:
            logging.warning("No posts found for %s", page_key)
            continue

        logging.info("Parsed %d entries for %s", len(raw_posts), page_key)

        write_atom_feed(FEEDS_DIR / page["output_file"], raw_posts,
                        feed_title=page["label"],
                        feed_link=page.get("feed_link", page["url"]),
                        feed_icon=favicon)


if __name__ == "__main__":
    asyncio.run(main())
