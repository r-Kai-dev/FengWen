"""Scrape Thinking Machines Lab news page."""

import hashlib
import logging
from datetime import datetime, timezone

from bs4 import BeautifulSoup

from utils import (
    FEEDS_DIR, setup_logging, ensure_output_dir,
    load_feeds_config, fetch_page, compact, write_atom_feed,
)

setup_logging()
ensure_output_dir()
ORG_KEY = "thinkingmachines"
BASE_URL = "https://thinkingmachines.ai"


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
    for item in soup.select("li a.post-item-link"):
        href = item.get("href", "")
        if not href or not href.startswith("/news/"):
            continue
        title_el = item.select_one(".post-title")
        if not title_el:
            continue
        title = title_el.get_text(strip=True)
        date_el = item.select_one("time.desktop-time")
        pub = parse_date(date_el.get_text(strip=True)) if date_el else None
        if not pub:
            pub = datetime.now(timezone.utc).isoformat()

        url = f"{BASE_URL}{href}"
        slug = href.strip("/").split("/")[-1]
        item_id = hashlib.md5(f"thinkingmachines_news_{slug}".encode()).hexdigest()
        posts.append(compact({
            "id": item_id, "source": "thinkingmachines", "type": "news",
            "title": title, "url": url, "published_date": pub,
            "organization": "Thinking Machines Lab",
        }))
    return posts


def main():
    config = load_feeds_config(ORG_KEY)
    page = config["pages"]["news"]
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
