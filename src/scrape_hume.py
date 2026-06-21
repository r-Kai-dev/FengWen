"""Scrape Hume AI blog from Next.js RSC payload."""

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
ORG_KEY = "hume"
BASE_URL = "https://www.hume.ai"


def _parse_date(iso_str):
    if not iso_str:
        return datetime.now(timezone.utc).isoformat()
    try:
        return datetime.fromisoformat(iso_str.replace("Z", "+00:00")).isoformat()
    except (ValueError, TypeError):
        return datetime.now(timezone.utc).isoformat()


def _extract_posts_array(html):
    chunks = re.findall(r'self\.__next_f\.push\(\[1,\s*"(.*?)"\s*\]\)', html, re.DOTALL)
    all_data = ""
    for chunk in chunks:
        all_data += chunk.encode("utf-8").decode("unicode_escape", errors="replace")

    idx = all_data.find('"posts":[')
    if idx == -1:
        return []
    array_start = idx + 8
    depth, in_str, escaped = 0, False, False
    array_end = -1
    for i, ch in enumerate(all_data[array_start:], array_start):
        if escaped: escaped = False; continue
        if ch == "\\" and in_str: escaped = True; continue
        if ch == '"': in_str = not in_str; continue
        if in_str: continue
        if ch == "[": depth += 1
        elif ch == "]":
            depth -= 1
            if depth == 0: array_end = i; break
    if array_end == -1:
        return []
    try:
        return json.loads(all_data[array_start:array_end + 1])
    except json.JSONDecodeError:
        return []


def extract(html):
    posts = _extract_posts_array(html)
    entries = []
    for p in posts:
        slug_obj = p.get("slug", {})
        slug = slug_obj.get("current", "") if isinstance(slug_obj, dict) else str(slug_obj or "")
        if not slug:
            continue
        title = p.get("title", slug)
        category = p.get("category", "")
        pub = _parse_date(p.get("publishedAt", ""))
        excerpt = p.get("excerpt", "")
        url = f"{BASE_URL}/blog/{slug}"
        item_id = hashlib.md5(f"hume_{slug}".encode()).hexdigest()
        entries.append(compact({
            "id": item_id, "source": "hume", "type": "blog",
            "title": title, "url": url, "summary": excerpt,
            "published_date": pub,
            "categories": [category] if category else [],
            "organization": "Hume AI",
        }))
    return entries


def main():
    config = load_feeds_config(ORG_KEY)
    page = config["pages"]["blog"]
    logging.info("Fetching %s: %s", page["label"], page["url"])
    html = fetch_page(page["url"])
    entries = extract(html)
    if not entries:
        logging.warning("No entries found")
        return
    entries.sort(key=lambda x: x.get("published_date", ""), reverse=True)
    write_atom_feed(FEEDS_DIR / page["output_file"], entries,
                    feed_title=page["label"], feed_link=page["url"],
                    feed_icon=config.get("favicon"))

if __name__ == "__main__":
    main()
