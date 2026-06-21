"""Scrape xAI news page."""

import hashlib
import json
import logging
from datetime import datetime, timezone

from bs4 import BeautifulSoup

from utils import (
    FEEDS_DIR, setup_logging, ensure_output_dir,
    load_feeds_config, fetch_page, compact, write_atom_feed,
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


def main():
    config = load_feeds_config(ORG_KEY)
    page = config["pages"]["news"]
    logging.info("Fetching %s: %s", page["label"], page["url"])
    html = fetch_page(page["url"])
    soup = BeautifulSoup(html, "html.parser")

    entries = _extract_featured(soup) + _extract_image_cards(soup) + _extract_list_cards(soup)
    entries = [json.loads(s) for s in {json.dumps(d) for d in entries}]
    entries.sort(key=lambda x: x.get("published_date", ""), reverse=True)

    write_atom_feed(FEEDS_DIR / page["output_file"], entries,
                    feed_title=page["label"], feed_link=page["url"],
                    feed_icon=config.get("favicon"))

if __name__ == "__main__":
    main()
