"""Crawl Unsloth blog (SPA rendered)."""

import hashlib
import logging
import re
from datetime import datetime, timezone

from bs4 import BeautifulSoup

from utils import (
    FEEDS_DIR, setup_logging, ensure_output_dir,
    load_feeds_config, compact, write_atom_feed,
)

setup_logging()
ensure_output_dir()
ORG_KEY = "unsloth"
BASE_URL = "https://unsloth.ai"


def parse_date(date_str):
    if not date_str:
        return None
    for fmt in ("%b %d, %Y", "%B %d, %Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(date_str.strip(), fmt).replace(tzinfo=timezone.utc).isoformat()
        except ValueError:
            continue
    return None


def extract_posts(soup):
    posts = []
    seen = set()
    for card in soup.select('a.w-link[href*="/blog/"]'):
        href = card.get("href", "")
        if not href or href == "/blog" or href in seen:
            continue
        title = card.get_text(strip=True)
        if not title or len(title) < 3:
            continue
        seen.add(href)

        # Find date in a parent container's w-text span
        date_str = ""
        parent = card.find_parent('div')
        for _ in range(5):
            if not parent:
                break
            date_el = parent.select_one('span.w-text')
            if date_el:
                date_str = date_el.get_text(strip=True)
                if re.match(r"^(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\s+\d{1,2}", date_str):
                    break
                date_str = ""
            parent = parent.find_parent('div')

        pub = parse_date(date_str) or datetime.now(timezone.utc).isoformat()
        url = href if href.startswith("http") else f"{BASE_URL}{href}"
        slug = href.strip("/").split("/")[-1]
        item_id = hashlib.md5(f"unsloth_blog_{slug}".encode()).hexdigest()
        posts.append(compact({
            "id": item_id, "source": "unsloth", "type": "blog",
            "title": title, "url": url, "published_date": pub,
            "organization": "Unsloth",
        }))
    return posts


def run(page):
    config = load_feeds_config(ORG_KEY)
    p = config["pages"]["blog"]
    logging.info("Navigating to %s", p["url"])
    page.goto(p["url"])
    page.wait_for_timeout(3000)
    soup = BeautifulSoup(page.content(), "html.parser")
    entries = extract_posts(soup)
    if not entries:
        logging.warning("No entries found")
        return
    entries.sort(key=lambda x: x.get("published_date", ""), reverse=True)
    write_atom_feed(FEEDS_DIR / p["output_file"], entries,
                    feed_title=p["label"], feed_link=p["url"],
                    feed_icon=config.get("favicon"))

if __name__ == "__main__":
    from playwright.sync_api import sync_playwright
    pw = sync_playwright().start()
    browser = pw.chromium.launch(headless=True, args=["--no-sandbox", "--disable-dev-shm-usage"])
    page = browser.new_page()
    try:
        run(page)
    finally:
        browser.close()
        pw.stop()
