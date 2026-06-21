"""Scrape Udio blog page."""

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
ORG_KEY = "udio"
BASE_URL = "https://www.udio.com"


def parse_date(date_str):
    if not date_str:
        return None
    for fmt in ("%Y-%m-%d", "%b %d, %Y", "%B %d, %Y"):
        try:
            return datetime.strptime(date_str.strip(), fmt).replace(tzinfo=timezone.utc).isoformat()
        except ValueError:
            continue
    return None


def extract_posts(soup):
    posts = []
    seen = set()
    for card in soup.select(".saas-featured-article, .saas-article"):
        title_el = card.select_one(".article-title")
        if not title_el:
            continue
        title = title_el.get_text(strip=True)
        link_el = card.select_one("a[href^='/blog/']")
        if not link_el:
            continue
        href = link_el.get("href", "")
        if href in seen:
            continue
        seen.add(href)
        url = f"{BASE_URL}{href}"

        date_el = card.select_one("time")
        date_str = ""
        if date_el:
            date_str = date_el.get("datetime", "") or date_el.get_text(strip=True)
        pub = parse_date(date_str) or datetime.now(timezone.utc).isoformat()

        categories = [tag_el.get_text(strip=True) for tag_el in card.select(".article-tag") if tag_el.get_text(strip=True)]

        slug = href.strip("/").split("/")[-1]
        item_id = hashlib.md5(f"udio_blog_{slug}".encode()).hexdigest()
        posts.append(compact({
            "id": item_id, "source": "udio", "type": "blog",
            "title": title, "url": url, "published_date": pub,
            "categories": categories, "organization": "Udio",
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
