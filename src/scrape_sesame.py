"""Scrape Sesame AI blog from __NEXT_DATA__ JSON."""

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
ORG_KEY = "sesame"
BASE_URL = "https://www.sesame.com"


def extract(html):
    m = re.search(r'<script id="__NEXT_DATA__"[^>]*type="application/json"[^>]*>(.*?)</script>', html, re.DOTALL)
    if not m:
        return []
    data = json.loads(m.group(1))
    posts = data.get("props", {}).get("pageProps", {}).get("pageData", {}).get("posts", [])
    entries = []
    for post in posts:
        slug = post.get("slug", "")
        title = post.get("title", "")
        excerpt = post.get("excerpt", "")
        date_str = post.get("publishedDate", "")
        if not title or not slug:
            continue
        url = f"{BASE_URL}/blog/{slug}"
        pub = date_str
        if pub:
            try:
                pub = datetime.strptime(pub, "%Y-%m-%d").replace(tzinfo=timezone.utc).isoformat()
            except ValueError:
                pass
        item_id = hashlib.md5(f"sesame_blog_{slug}".encode()).hexdigest()
        entries.append(compact({
            "id": item_id, "source": "sesame", "type": "blog",
            "title": title, "url": url, "summary": excerpt,
            "published_date": pub, "organization": "Sesame",
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
