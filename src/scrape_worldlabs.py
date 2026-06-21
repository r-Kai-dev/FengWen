"""Scrape World Labs blog page."""

import hashlib
import logging
import re
from datetime import datetime, timezone

from bs4 import BeautifulSoup

from utils import (
    FEEDS_DIR, setup_logging, ensure_output_dir,
    load_feeds_config, fetch_page, compact, write_atom_feed,
)

setup_logging()
ensure_output_dir()
ORG_KEY = "worldlabs"
BASE_URL = "https://www.worldlabs.ai"


def parse_date(date_str):
    if not date_str:
        return None
    for fmt in ("%B %d, %Y", "%b %d, %Y"):
        try:
            return datetime.strptime(date_str.strip(), fmt).replace(tzinfo=timezone.utc).isoformat()
        except ValueError:
            continue
    return None


def extract_posts(soup):
    posts = []
    seen = set()
    date_re = re.compile(r"^([A-Z][a-z]+ \d{1,2}, \d{4})")

    for a in soup.select('a[href*="/blog/"]'):
        href = a.get("href", "")
        if not href or "/blog/" not in href or href in seen:
            continue
        text = a.get_text(separator="|", strip=True)
        if not text or "Read More" not in text:
            continue
        seen.add(href)

        parts = [p.strip() for p in text.split("|") if p.strip()]
        if len(parts) < 3:
            continue

        date_str = ""; date_idx = -1
        for i, p in enumerate(parts):
            if date_re.match(p):
                date_str = date_re.match(p).group(1)
                date_idx = i
                break
        if not date_str:
            continue

        remaining = parts[date_idx + 1:]
        known_authors = ("World Labs team", "Dr. Fei-Fei Li", "Fei\u2011Fei Li", "Christoph Lassner")
        if remaining and remaining[0] in known_authors:
            remaining = remaining[1:]

        read_more_idx = -1
        for i, p in enumerate(remaining):
            if "Read More" in p:
                read_more_idx = i
                break
        if read_more_idx == -1:
            continue

        content_parts = remaining[:read_more_idx]
        if not content_parts:
            continue
        title = content_parts[0]
        description = " ".join(content_parts[1:]) if len(content_parts) > 1 else ""

        slug = href.strip("/")
        if slug.startswith("blog/"):
            slug = slug[5:]
        if slug.startswith("blog/"):
            slug = slug[5:]
        url = href if href.startswith("http") else f"{BASE_URL}{href}"
        pub = parse_date(date_str) or datetime.now(timezone.utc).isoformat()
        item_id = hashlib.md5(f"worldlabs_blog_{slug}".encode()).hexdigest()
        posts.append(compact({
            "id": item_id, "source": "worldlabs", "type": "blog",
            "title": title, "url": url, "summary": description,
            "published_date": pub, "organization": "World Labs",
        }))
    return posts


def main():
    config = load_feeds_config(ORG_KEY)
    page = config["pages"]["blog"]
    logging.info("Fetching %s: %s", page["label"], page["url"])
    html = fetch_page(page["url"])
    soup = BeautifulSoup(html, "html.parser")
    entries = extract_posts(soup)
    if not entries:
        logging.warning("No entries found")
        return
    entries.sort(key=lambda x: x.get("published_date", ""), reverse=True)
    write_atom_feed(FEEDS_DIR / page["output_file"], entries,
                    feed_title=page["label"], feed_link=page["url"],
                    feed_icon=config.get("favicon"))

if __name__ == "__main__":
    main()
