"""Crawl alphaXiv hot papers explorer (SPA rendered)."""

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
ORG_KEY = "alphaxiv"
BASE_URL = "https://www.alphaxiv.org"


def parse_date(date_str):
    if not date_str:
        return None
    for fmt in ("%d %b %Y", "%d %B %Y"):
        try:
            return datetime.strptime(date_str.strip(), fmt).replace(tzinfo=timezone.utc).isoformat()
        except ValueError:
            continue
    return None


def extract_papers(soup):
    posts = []
    seen = set()
    for card in soup.select('.rounded-xl'):
        if not card.select_one("a[href^='/abs/']"):
            continue
        link_el = card.select_one("a[href^='/abs/']")
        href = link_el.get("href", "")
        if href in seen:
            continue
        seen.add(href)
        arxiv_id = href.replace("/abs/", "")
        title_el = card.select_one(".tiptap.html-renderer")
        title = title_el.get_text(strip=True) if title_el else ""
        if not title or len(title) < 5:
            continue
        date_el = card.select_one("span.text-sm.font-medium")
        if not date_el:
            continue
        pub = parse_date(date_el.get_text(strip=True)) or datetime.now(timezone.utc).isoformat()
        paper_url = f"https://arxiv.org/abs/{arxiv_id}"
        item_id = hashlib.md5(f"alphaxiv_hot_{arxiv_id}".encode()).hexdigest()
        posts.append(compact({
            "id": item_id, "source": "alphaxiv", "type": "paper",
            "title": title, "url": paper_url, "published_date": pub,
            "categories": ["hot"], "organization": "alphaXiv",
        }))
        if len(posts) >= 5:
            break
    return posts


def run(page: ChromiumPage):
    config = load_feeds_config(ORG_KEY)
    p = config["pages"]["hot_papers"]
    logging.info("Navigating to %s", p["url"])
    page.get(p["url"])
    page.wait.doc_loaded()
    page.wait(8)
    soup = BeautifulSoup(page.html, "html.parser")
    entries = extract_papers(soup)
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
