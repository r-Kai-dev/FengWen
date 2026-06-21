"""Crawl Epoch AI /latest page (SPA rendered)."""

import hashlib
import logging
from datetime import datetime, timezone

from bs4 import BeautifulSoup
from DrissionPage import ChromiumPage

from utils import (
    FEEDS_DIR, setup_logging, ensure_output_dir,
    load_feeds_config, compact, write_atom_feed,
)

setup_logging()
ensure_output_dir()
ORG_KEY = "epoch"
BASE_URL = "https://epoch.ai"


def parse_date(date_str):
    if not date_str:
        return None
    for fmt in ("%b. %d, %Y", "%B %d, %Y", "%b %d, %Y"):
        try:
            return datetime.strptime(date_str.strip(), fmt).replace(tzinfo=timezone.utc).isoformat()
        except ValueError:
            continue
    return None


def extract_posts(soup):
    posts = []
    for card in soup.select(".card-article-listing"):
        href = ""
        for a in card.select('a[href]'):
            h = a.get("href", "")
            if h.startswith("/") and not h.startswith("/#"):
                href = h; break
        if not href:
            continue
        text = card.get_text(separator="|", strip=True)
        parts = [p.strip() for p in text.split("|") if p.strip()]
        if len(parts) < 3:
            continue
        article_type = parts[0]
        date_str = parts[1]
        title = parts[2]
        description = ""; author = ""
        for p in parts[3:]:
            if p.startswith("By "): author = p[3:]
            elif not author: description = p

        pub = parse_date(date_str) or datetime.now(timezone.utc).isoformat()
        slug = href.strip("/").split("/")[-1]
        url = f"{BASE_URL}{href}"
        item_id = hashlib.md5(f"epoch_latest_{slug}".encode()).hexdigest()
        posts.append(compact({
            "id": item_id, "source": "epoch", "type": "article",
            "title": title, "url": url, "summary": description,
            "published_date": pub, "categories": [article_type] if article_type else [],
            "organization": "Epoch AI", "feed_author": author,
        }))
    return posts


def run(page: ChromiumPage):
    config = load_feeds_config(ORG_KEY)
    p = config["pages"]["latest"]
    logging.info("Navigating to %s", p["url"])
    page.get(p["url"])
    page.wait.doc_loaded()
    page.wait(8)
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
