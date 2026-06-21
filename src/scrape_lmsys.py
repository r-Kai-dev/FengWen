"""Scrape LMSYS blog from Next.js RSC payload."""

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
ORG_KEY = "lmsys"
BASE_URL = "https://lmsys.org"


def parse_date(date_str):
    if not date_str:
        return None
    date_str = re.sub(r"\s*\([^)]*\)", "", date_str.strip())
    for fmt in ("%B %d, %Y", "%b %d, %Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(date_str, fmt).replace(tzinfo=timezone.utc).isoformat()
        except ValueError:
            continue
    return None


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
            slug = post.get("slug", "")
            excerpt = post.get("excerpt", "")
            date_str = post.get("date", "")
            author = post.get("author", "")
            category = post.get("category", "")
            post_type = post.get("type", "")

            if not title or not slug:
                continue
            url = f"{BASE_URL}/blog/{slug}"
            pub = parse_date(date_str) or datetime.now(timezone.utc).isoformat()
            if excerpt:
                excerpt = re.sub(r'<[^>]+>', '', excerpt)[:500]

            cats = []
            if category and category != "general":
                cats.append(category)
            if post_type:
                cats.append(post_type)

            item_id = hashlib.md5(f"lmsys_blog_{slug}".encode()).hexdigest()
            entries.append(compact({
                "id": item_id, "source": "lmsys", "type": "blog",
                "title": title, "url": url, "summary": excerpt,
                "published_date": pub, "categories": cats,
                "organization": "LMSYS", "feed_author": author,
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
