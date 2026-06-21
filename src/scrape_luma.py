"""Scrape Luma AI news page."""

import hashlib
import html as html_mod
import logging
from datetime import datetime, timezone

from bs4 import BeautifulSoup

from utils import (
    FEEDS_DIR, setup_logging, ensure_output_dir,
    load_feeds_config, fetch_page, compact, write_atom_feed,
)

setup_logging()
ensure_output_dir()
ORG_KEY = "luma"
BASE_URL = "https://lumalabs.ai"


def parse_date(date_str):
    if not date_str:
        return None
    for fmt in ("%b %d, %Y", "%B %d, %Y"):
        try:
            return datetime.strptime(date_str.strip(), fmt).replace(tzinfo=timezone.utc).isoformat()
        except ValueError:
            continue
    return None


def extract_posts(soup):
    posts = []
    for container in soup.find_all("div", style="display:contents"):
        link_el = container.find("a", class_="card-link")
        if not link_el:
            continue
        title = html_mod.unescape(link_el.get_text(strip=True))
        href = link_el.get("href", "")
        if not title or not href:
            continue
        url = f"{BASE_URL}{href}" if href.startswith("/") else href

        date_el = container.find("span", class_="typo-body-s")
        date_str = date_el.get_text(strip=True) if date_el else None
        pub = parse_date(date_str) or datetime.now(timezone.utc).isoformat()

        category = None
        flex_div = container.find("div", class_=lambda c: c and "flex items-center gap-2" in str(c) if c else False)
        if not flex_div:
            flex_div = date_el.find_parent("div") if date_el else None
        if flex_div:
            cat_el = flex_div.find("span")
            if cat_el and cat_el != date_el:
                category = cat_el.get_text(strip=True)

        item_id = hashlib.md5(f"luma_news_{title}_{href}".encode()).hexdigest()
        posts.append(compact({
            "id": item_id, "source": "luma", "type": "news",
            "title": title, "url": url, "published_date": pub,
            "categories": [category] if category else [],
            "organization": "Luma AI",
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
