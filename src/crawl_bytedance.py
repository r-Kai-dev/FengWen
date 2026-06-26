"""Crawl ByteDance Seed blog and public papers (SPA rendered)."""

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
ORG_KEY = "bytedance"


def parse_date(date_str):
    if not date_str:
        return None
    for fmt in ("%b %d, %Y", "%B %d, %Y", "%Y/%m/%d"):
        try:
            return datetime.strptime(date_str.strip(), fmt).replace(tzinfo=timezone.utc).isoformat()
        except ValueError:
            continue
    return None


def _navigate(page: ChromiumPage, url: str):
    logging.info("Navigating to %s", url)
    page.get(url)
    page.wait.doc_loaded()
    page.wait(3)


def extract_blog(soup, base_url):
    items = []
    cards = soup.select("div.grid.grid-cols-3 > div.group")
    if not cards:
        cards = soup.find_all("div", class_=lambda c: c and "group" in str(c) and "cursor-pointer" in str(c) if c else False)
    for card in cards:
        title_el = card.find("div", class_=lambda c: c and "font-[500]" in str(c) if c else False)
        if not title_el:
            title_el = card.find("div", class_=lambda c: c and "line-clamp-3" in str(c) if c else False)
        if not title_el:
            continue
        title = title_el.get_text(strip=True)
        date_el = card.find("div", string=lambda t: bool(re.match(r"[A-Z][a-z]+ \d{1,2}, \d{4}", (t or "").strip())))
        pub = parse_date(date_el.get_text(strip=True)) if date_el else None
        cat_el = card.find("div", class_=lambda c: c and "justify-self-end" in str(c) if c else False)
        if cat_el: cat_el = cat_el.find("div")
        cats = [cat_el.get_text(strip=True)] if cat_el else []
        slug = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")
        url = f"{base_url.rstrip('/')}/blog/{slug}"
        if not pub: pub = datetime.now(timezone.utc).isoformat()
        item_id = hashlib.md5(f"bytedance_blog_{title}".encode()).hexdigest()
        items.append(compact({
            "id": item_id, "source": "bytedance", "type": "blog",
            "title": title, "url": url, "published_date": pub,
            "categories": cats, "organization": "ByteDance Seed",
        }))
    return items


def extract_papers(soup, base_url):
    items = []
    papers = soup.find_all("div", class_=lambda c: c and "group relative w-full cursor-pointer" in str(c) if c else False)
    for paper in papers:
        date_el = paper.select_one("[class*='whitespace-nowrap']")
        date_str = date_el.get_text(strip=True) if date_el else ""
        title_el = paper.find("div", class_=lambda c: c and "text-[24px]" in str(c) and "font-[500]" in str(c) if c else False)
        if not title_el: continue
        title = title_el.get_text(strip=True)
        abstract_el = paper.select_one(".markdown-Vl1VIB")
        abstract = abstract_el.get_text(strip=True) if abstract_el else ""
        cat_el = paper.select_one("[class*='italic']")
        cats = [cat_el.get_text(strip=True)] if cat_el else []
        pub = parse_date(date_str) or datetime.now(timezone.utc).isoformat()
        slug = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")
        url = f"{base_url.rstrip('/')}/public_papers/{slug}"
        item_id = hashlib.md5(f"bytedance_papers_{title}".encode()).hexdigest()
        items.append(compact({
            "id": item_id, "source": "bytedance", "type": "public_papers",
            "title": title, "url": url, "summary": abstract[:500],
            "published_date": pub, "categories": cats,
            "organization": "ByteDance Seed",
        }))
    return items


def run(page: ChromiumPage):
    config = load_feeds_config(ORG_KEY)
    base = config["base_url"]
    for page_key, p in config["pages"].items():
        _navigate(page, p["url"])
        soup = BeautifulSoup(page.html, "html.parser")
        entries = extract_blog(soup, base) if page_key == "blog" else extract_papers(soup, base)
        if not entries:
            logging.warning("No entries for %s", page_key)
            continue
        entries = [json.loads(s) for s in {json.dumps(d) for d in entries}]
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
