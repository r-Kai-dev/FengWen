"""Crawl Higgsfield blog (SPA with scroll + JSON-LD extraction)."""

import hashlib
import json
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
ORG_KEY = "higgsfield"
BASE_URL = "https://higgsfield.ai"


def parse_date(date_str):
    if not date_str:
        return ""
    date_str = re.sub(r'(\d)(st|nd|rd|th)', r'\1', date_str)
    for fmt in ("%Y-%m-%dT%H:%M:%S.%f%z", "%Y-%m-%dT%H:%M:%S%z", "%Y-%m-%d", "%B %d, %Y", "%b %d, %Y", "%b. %d, %Y"):
        try:
            dt = datetime.strptime(date_str, fmt)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt.isoformat()
        except (ValueError, TypeError):
            continue
    return ""


def extract_posts(soup):
    posts = []
    seen = set()
    for script in soup.select('script[type="application/ld+json"]'):
        try:
            data = json.loads(script.string)
        except (json.JSONDecodeError, TypeError):
            continue
        if isinstance(data, list):
            data = data[0] if data else {}
        if not isinstance(data, dict):
            continue
        headline = (data.get("headline") or "").strip()
        url = data.get("url") or ""
        me = data.get("mainEntityOfPage", {})
        if isinstance(me, dict):
            url = url or me.get("@id", "")
        date_str = data.get("datePublished", "")
        description = data.get("description", "")
        if not headline or not url or not date_str:
            continue
        if url in seen:
            continue
        seen.add(url)
        pub = parse_date(date_str)
        if not pub:
            pub = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
        slug = url.rstrip("/").split("/")[-1]
        item_id = hashlib.md5(f"higgsfield_blog_{slug}".encode()).hexdigest()
        posts.append(compact({
            "id": item_id, "source": "higgsfield", "type": "blog",
            "title": headline, "url": url, "summary": description,
            "published_date": pub, "organization": "Higgsfield",
        }))
    return posts


def run(page: ChromiumPage):
    config = load_feeds_config(ORG_KEY)
    p = config["pages"]["blog"]
    logging.info("Navigating to %s", p["url"])
    page.get(p["url"])
    page.wait.doc_loaded()
    page.wait(3)
    for _ in range(5):
        page.run_js("window.scrollTo(0, document.body.scrollHeight)")
        page.wait(2)
    page.run_js("window.scrollTo(0, 0)")
    page.wait(1)
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
