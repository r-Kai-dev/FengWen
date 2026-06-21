"""Scrape Resemble AI resources page."""

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
ORG_KEY = "resemble"
BASE_URL = "https://www.resemble.ai"


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
    date_re = re.compile(r"([A-Z][a-z]+ \d{1,2}, \d{4})")

    for card in soup.select(".w-dyn-item"):
        link_el = card.select_one("a")
        if not link_el:
            continue
        href = link_el.get("href", "")
        link_text = link_el.get_text(separator="|", strip=True)
        if not date_re.search(link_text) or not href.startswith("/resources/") or href in seen:
            continue
        seen.add(href)

        parts = [p.strip() for p in link_text.split("|") if p.strip()]
        if len(parts) < 4:
            continue

        if parts[0] == "\u2022":  # bullet
            date_str = parts[1]; title = parts[2]
            description = parts[3] if len(parts) > 3 else ""
            article_type = ""
        else:
            article_type = parts[0]; date_str = parts[2] if len(parts) > 2 else ""
            title = parts[3] if len(parts) > 3 else ""
            description = parts[4] if len(parts) > 4 else ""

        if not title or not date_str:
            continue
        pub = parse_date(date_str) or datetime.now(timezone.utc).isoformat()

        slug = href.strip("/").split("/")[-1]
        url = f"{BASE_URL}{href}"
        item_id = hashlib.md5(f"resemble_resources_{slug}".encode()).hexdigest()
        posts.append(compact({
            "id": item_id, "source": "resemble", "type": "resource",
            "title": title, "url": url, "summary": description,
            "published_date": pub,
            "categories": [article_type] if article_type else [],
            "organization": "Resemble AI",
        }))
    return posts


def main():
    config = load_feeds_config(ORG_KEY)
    page = config["pages"]["resources"]
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
