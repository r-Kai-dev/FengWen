"""Scrape Suno blog from Next.js RSC payload."""

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
ORG_KEY = "suno"
BASE_URL = "https://suno.com"


def extract(html):
    chunks = re.findall(r'self\.__next_f\.push\(\[[0-9]+,\s*"(.*?)"\s*\]\)', html, re.DOTALL)
    for chunk in chunks:
        decoded = chunk.encode("utf-8").decode("unicode_escape", errors="replace")
        if '"posts"' not in decoded:
            continue
        m = re.search(r'"posts":\s*(\[.*?\])\s*\}', decoded, re.DOTALL)
        if not m:
            continue
        posts = json.loads(m.group(1))
        entries = []
        for post in posts:
            title = post.get("title", "")
            slug_obj = post.get("slug", {})
            slug = slug_obj.get("current", "") if isinstance(slug_obj, dict) else str(slug_obj or "")
            excerpt = post.get("excerpt", "")
            date_str = post.get("publishedAt", "")
            tags = post.get("tags", [])
            if not title or not slug:
                continue
            url = f"{BASE_URL}/blog/{slug}"
            pub = date_str
            if pub:
                try:
                    pub = datetime.fromisoformat(pub.replace("Z", "+00:00")).isoformat()
                except (ValueError, TypeError):
                    pass
            item_id = hashlib.md5(f"suno_blog_{slug}".encode()).hexdigest()
            entries.append(compact({
                "id": item_id, "source": "suno", "type": "blog",
                "title": title, "url": url, "summary": excerpt,
                "published_date": pub, "categories": tags or [],
                "organization": "Suno",
            }))
        return entries
    return []


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
