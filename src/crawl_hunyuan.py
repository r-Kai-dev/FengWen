"""Crawl Tencent Hunyuan research page (unified feed — research + news).

Switches to Chinese to get the full content, then extracts cards from
the React-rendered DOM.  Each card becomes a feed entry with date, title,
description, and authors.
"""

import hashlib
import json
import logging
import time
from datetime import datetime, timezone

from bs4 import BeautifulSoup
from DrissionPage import ChromiumPage

from utils import (
    FEEDS_DIR, setup_logging, ensure_output_dir,
    load_feeds_config, compact, write_atom_feed,
)

setup_logging()
ensure_output_dir()
ORG_KEY = "hunyuan"
BASE_URL = "https://hunyuan.tencent.com"


def parse_date(date_str: str) -> str | None:
    """Parse a date string and return ISO-8601, or None."""
    if not date_str:
        return None
    date_str = date_str.strip()
    for fmt in ("%b %d, %Y", "%B %d, %Y", "%Y-%m-%d", "%Y/%m/%d",
                "%Y年%m月%d日", "%Y.%m.%d"):
        try:
            return datetime.strptime(date_str, fmt).replace(
                tzinfo=timezone.utc
            ).isoformat()
        except ValueError:
            continue
    return None


def _fetch_page(page: ChromiumPage, url: str) -> str:
    """Navigate to the Hunyuan research page, switch to Chinese, wait for render."""
    logging.info("Navigating to %s", url)
    page.get(url)
    page.wait.doc_loaded()

    # Wait for skeleton to hide and cards to appear
    deadline = time.time() + 15
    while time.time() < deadline:
        try:
            skel = page.ele("#app-skeleton", timeout=1)
            skel_cls = (skel.attr("class") or "") if skel else ""
            hidden = "hidden" in skel_cls.split()
        except Exception:
            hidden = True
        cards = page.eles("article.research-mobile-list__card")
        if hidden and len(cards) >= 1:
            logging.info("Content rendered (%d cards)", len(cards))
            break
        page.wait(0.5)
    page.wait(3)

    # Switch to Chinese for full content (English page has fewer posts)
    logging.info("Switching to Chinese…")
    page.run_js("""
        const items = document.querySelectorAll('.header__lang-switch-text-item');
        for (const item of items) {
            if (item.textContent.trim() === '中文') { item.click(); break; }
        }
    """)
    page.wait(4)
    return page.html


def extract_cards(soup: BeautifulSoup) -> list[dict]:
    """Extract entries from article cards in the rendered DOM."""
    entries = []
    seen = set()

    for card in soup.select("article.research-mobile-list__card"):
        date_el = card.select_one(".research-mobile-list__date")
        title_el = card.select_one(".research-mobile-list__title")
        desc_el = card.select_one(".research-mobile-list__desc")
        authors_el = card.select_one(".research-mobile-list__authors")

        title = title_el.get_text(strip=True) if title_el else ""
        if not title or len(title) < 3:
            continue

        # Deduplicate by title (Chinese page may have same item in card + row view)
        key = title.lower().strip()
        if key in seen:
            continue
        seen.add(key)

        date_str = date_el.get_text(strip=True) if date_el else ""
        pub = parse_date(date_str) or datetime.now(timezone.utc).isoformat()

        summary = desc_el.get_text(strip=True) if desc_el else ""
        authors = authors_el.get_text(strip=True) if authors_el else ""

        item_id = hashlib.md5(
            f"hunyuan_{title}_{date_str}".encode()
        ).hexdigest()

        entries.append(compact({
            "id": item_id,
            "source": "hunyuan",
            "type": "research",
            "title": title,
            "url": BASE_URL + "/research",
            "summary": summary[:800] if summary else None,
            "published_date": pub,
            "categories": [authors] if authors else [],
            "organization": "Tencent Hunyuan",
        }))

    return entries


def run(page: ChromiumPage) -> None:
    config = load_feeds_config(ORG_KEY)
    favicon = config.get("favicon")

    for page_key, page_cfg in config["pages"].items():
        html = _fetch_page(page, page_cfg["url"])
        soup = BeautifulSoup(html, "html.parser")
        entries = extract_cards(soup)

        if not entries:
            logging.warning("No entries found for %s", page_key)
            continue

        # Stable sort: date descending, title ascending for ties
        entries.sort(key=lambda x: x.get("title", ""))
        entries.sort(key=lambda x: x.get("published_date", ""), reverse=True)

        write_atom_feed(
            FEEDS_DIR / page_cfg["output_file"],
            entries,
            feed_title=page_cfg["label"],
            feed_link=page_cfg["url"],
            feed_icon=favicon,
        )


if __name__ == "__main__":
    from DrissionPage import ChromiumOptions
    co = ChromiumOptions()
    co.set_browser_path("/usr/bin/chromium")
    co.headless(on_off=True)
    co.new_env(on_off=True)
    co.set_argument("--no-sandbox")
    co.set_argument("--disable-gpu")
    pg = ChromiumPage(addr_or_opts=co)
    try:
        run(pg)
    finally:
        pg.quit()
