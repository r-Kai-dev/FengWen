"""Crawl Unsloth blog (SPA rendered)."""

import hashlib
import logging
import re
from datetime import datetime, timezone

from bs4 import BeautifulSoup
from DrissionPage import ChromiumPage

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
    for card in soup.select('a.w-inline-block[href^="/blog/"]'):
        href = card.get("href", "")
        if not href or href in seen:
            continue
        seen.add(href)

        title_el = card.select_one("h3")
        if not title_el:
            title_el = card.select_one("h2") or card.select_one("h4")
        if not title_el:
            continue
        title = title_el.get_text(strip=True)
        if not title:
            continue

        date_str = ""
        for div in card.find_all("div"):
            text = div.get_text(strip=True)
            if re.match(r"^(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\s+\d{1,2}", text):
                date_str = text; break

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


def run(page: ChromiumPage):
    config = load_feeds_config(ORG_KEY)
    p = config["pages"]["blog"]
    logging.info("Navigating to %s", p["url"])
    page.get(p["url"])
    page.wait.doc_loaded()
    page.wait(3)
    soup = BeautifulSoup(page.html, "html.parser")
    entries = extract_posts(soup)
    if not entries:
        logging.warning("No entries found")
        return
    entries.sort(key=lambda x: x.get("published_date", ""), reverse=True)
    write_atom_feed(FEEDS_DIR / p["output_file"], entries,
                    feed_title=p["label"], feed_link=p["url"],
                    feed_icon=config.get("favicon"))

if __name__ == "__main__":
    from DrissionPage import ChromiumOptions
    co = ChromiumOptions()
    co.set_browser_path("/usr/bin/chromium")
    co.headless(on_off=True); co.new_env(on_off=True)
    co.set_argument("--no-sandbox"); co.set_argument("--disable-gpu")
    pg = ChromiumPage(addr_or_opts=co)
    try: run(pg)
    finally: pg.quit()
