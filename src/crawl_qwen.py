"""Crawl Qwen Research page (SPA rendered)."""

import hashlib
import json
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
ORG_KEY = "qwen"
BASE_URL = "https://qwen.ai"


def parse_date(date_str):
    if not date_str:
        return None
    try:
        return datetime.strptime(date_str.strip(), "%Y/%m/%d").replace(tzinfo=timezone.utc).isoformat()
    except ValueError:
        return None


def _extract_slug(item):
    elem_id = item.get("id", "")
    m = re.search(r"blog_id_(.+)$", elem_id)
    return m.group(1) if m else None


def extract_item(item, base_url, seen):
    title_el = item.select_one("[class*='Advancement__Title'], [class*='Capability__Title']")
    if not title_el: return None
    title = title_el.get_text(strip=True)
    if not title or title.lower().strip() in seen: return None
    seen.add(title.lower().strip())

    desc_el = item.select_one("[class*='Advancement__Description'], [class*='Capability__Description']")
    summary = desc_el.get_text(strip=True) if desc_el else ""
    source_el = item.select_one("[class*='Advancement__Source'], [class*='Capability__Source']")
    cats = [source_el.get_text(strip=True)] if source_el else []
    date_el = item.select_one("[class*='Advancement__Date'], [class*='Capability__Date']")
    pub = parse_date(date_el.get_text(strip=True)) if date_el else None
    if not pub: pub = datetime.now(timezone.utc).isoformat()

    slug = _extract_slug(item)
    if slug:
        url = f"{base_url.rstrip('/')}/blog?id={slug}"
    else:
        slug = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")
        url = f"{base_url.rstrip('/')}/research/{slug}"

    item_id = hashlib.md5(f"qwen_research_{title}".encode()).hexdigest()
    return compact({
        "id": item_id, "source": "qwen", "type": "research",
        "title": title, "url": url, "summary": summary[:600],
        "published_date": pub, "categories": cats,
        "organization": "Qwen (Alibaba)",
    })


def extract_items(soup):
    items = []
    seen = set()
    for cap in soup.select("[class*='Capability--dztDuQSg']"):
        entry = extract_item(cap, BASE_URL, seen)
        if entry: items.append(entry)
    return items


def run(page):
    config = load_feeds_config(ORG_KEY)
    p = config["pages"]["research"]
    logging.info("Navigating to %s", p["url"])
    page.goto(p["url"])
    page.wait_for_timeout(3000)
    soup = BeautifulSoup(page.content(), "html.parser")
    entries = extract_items(soup)
    if not entries:
        logging.warning("No entries found")
        return
    entries = [json.loads(s) for s in {json.dumps(d) for d in entries}]
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
