"""Crawl xAI news page (Playwright — GitHub Actions compatible)."""

import hashlib
import json
import logging
from datetime import datetime, timezone

from bs4 import BeautifulSoup

from utils import (
    FEEDS_DIR, setup_logging, ensure_output_dir,
    load_feeds_config, compact, write_atom_feed,
)

setup_logging()
ensure_output_dir()
ORG_KEY = "xai"
BASE_URL = "https://x.ai"


def parse_date(date_str):
    if not date_str:
        return None
    for fmt in ("%b %d, %Y", "%B %d, %Y"):
        try:
            return datetime.strptime(date_str.strip(), fmt).replace(tzinfo=timezone.utc).isoformat()
        except ValueError:
            continue
    return None


def _extract_featured(soup):
    posts = []
    for card in soup.select('a[class*="group/card"][class*="lg:grid"]'):
        href = card.get("href", "")
        if not href or not href.startswith("/news/"):
            continue
        desktop = card.select_one('[class*="hidden"][class*="lg:block"]')
        mobile = card.select_one('[class*="lg:hidden"]')

        title = None; date_str = None; description = None
        if desktop:
            h1 = desktop.find("h1")
            if h1: title = h1.get_text(strip=True)
            date_el = desktop.find("div", class_=lambda c: c and "text-xs" in str(c) if c else False)
            if date_el: date_str = date_el.get_text(strip=True)
            p_el = desktop.find("p")
            if p_el: description = p_el.get_text(strip=True)
        if not title and mobile:
            h2 = mobile.find("h2")
            if h2: title = h2.get_text(strip=True)
            if not date_str:
                d = mobile.find("div", class_=lambda c: c and "text-primary" in str(c) if c else False)
                if d: date_str = d.get_text(strip=True)
        if not title:
            continue

        pub = parse_date(date_str) or datetime.now(timezone.utc).isoformat()
        url = f"{BASE_URL}{href}"
        item_id = hashlib.md5(f"x-ai_news_{title}_{href}".encode()).hexdigest()
        posts.append(compact({
            "id": item_id, "source": "x-ai", "type": "news",
            "title": title, "url": url, "summary": description,
            "published_date": pub, "organization": "xAI",
        }))
    return posts


def _extract_image_cards(soup):
    posts = []
    all_cards = soup.find_all("a", class_=lambda c: c and "group/card" in str(c) if c else False)
    for card in all_cards:
        cls_attr = card.get("class", [])
        if not isinstance(cls_attr, (list, tuple)):
            continue
        cls_strs = [str(c) for c in cls_attr]
        if "group/card" not in cls_strs or "block" not in cls_strs:
            continue
        if any("lg:grid" in c for c in cls_strs) or any("hover:bg-primary" in c for c in cls_strs):
            continue

        href = card.get("href", "")
        if not href or not href.startswith("/news/"):
            continue
        title_el = card.find("h3")
        if not title_el:
            continue
        title = title_el.get_text(strip=True)
        date_el = card.find("div", class_=lambda c: c and "text-[11px]" in str(c) if c else False)
        pub = parse_date(date_el.get_text(strip=True)) if date_el else None
        if not pub:
            pub = datetime.now(timezone.utc).isoformat()

        url = f"{BASE_URL}{href}"
        item_id = hashlib.md5(f"x-ai_news_{title}_{href}".encode()).hexdigest()
        posts.append(compact({
            "id": item_id, "source": "x-ai", "type": "news",
            "title": title, "url": url, "published_date": pub,
            "organization": "xAI",
        }))
    return posts


def _extract_list_cards(soup):
    posts = []
    for card in soup.select('a[class*="group/card"][class*="hover:bg-primary"]'):
        href = card.get("href", "")
        if not href or not href.startswith("/news/"):
            continue
        flex_div = card.find("div", class_=lambda c: c and "flex-1" in str(c) if c else False)
        if not flex_div:
            continue
        title_el = flex_div.find("h3")
        if not title_el:
            continue
        title = title_el.get_text(strip=True)
        desc_el = flex_div.find("p")
        description = desc_el.get_text(strip=True) if desc_el else None
        date_el = card.find("div", class_=lambda c: c and "text-primary" in str(c) and "shrink-0" in str(c) if c else False)
        pub = parse_date(date_el.get_text(strip=True)) if date_el else None
        if not pub:
            pub = datetime.now(timezone.utc).isoformat()

        url = f"{BASE_URL}{href}"
        item_id = hashlib.md5(f"x-ai_news_{title}_{href}".encode()).hexdigest()
        posts.append(compact({
            "id": item_id, "source": "x-ai", "type": "news",
            "title": title, "url": url, "summary": description,
            "published_date": pub, "organization": "xAI",
        }))
    return posts


def run(page):
    config = load_feeds_config(ORG_KEY)
    p = config["pages"]["news"]
    logging.info("Crawling %s: %s", p["label"], p["url"])
    page.goto(p["url"])
    page.wait_for_timeout(3000)
    soup = BeautifulSoup(page.content(), "html.parser")

    entries = _extract_featured(soup) + _extract_image_cards(soup) + _extract_list_cards(soup)
    entries = [json.loads(s) for s in {json.dumps(d) for d in entries}]
    entries.sort(key=lambda x: x.get("published_date", ""), reverse=True)

    write_atom_feed(FEEDS_DIR / p["output_file"], entries,
                    feed_title=p["label"], feed_link=p["url"],
                    feed_icon=config.get("favicon"))


if __name__ == "__main__":
    from playwright.sync_api import sync_playwright
    pw = sync_playwright().start()
    browser = pw.chromium.launch(
        headless=True,
        args=[
            "--disable-blink-features=AutomationControlled",
            "--no-sandbox",
            "--disable-dev-shm-usage",
        ],
    )
    context = browser.new_context(
        viewport={"width": 1920, "height": 1080},
        user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    )
    page = context.new_page()
    page.add_init_script("""
        Object.defineProperty(navigator, 'webdriver', { get: () => false });
        Object.defineProperty(navigator, 'plugins', { get: () => [1, 2, 3, 4, 5] });
        Object.defineProperty(navigator, 'languages', { get: () => ['en-US', 'en'] });
        window.chrome = { runtime: {} };
        const oq = window.navigator.permissions.query;
        window.navigator.permissions.query = (p) => (
            p.name === 'notifications' ? Promise.resolve({ state: 'denied' }) : oq(p)
        );
    """)
    try:
        run(page)
    finally:
        browser.close()
        pw.stop()
