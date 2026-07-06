"""Crawl DeepSeek API docs news sidebar (expand News category)."""

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
ORG_KEY = "deepseek"
BASE_URL = "https://api-docs.deepseek.com"


def parse_date(date_str):
    if not date_str:
        return None
    try:
        return datetime.strptime(date_str.strip(), "%Y/%m/%d").replace(tzinfo=timezone.utc).isoformat()
    except ValueError:
        return None


def _fetch_deepseek_news(page):
    logging.info("Navigating to %s", BASE_URL)
    page.goto(BASE_URL)
    page.wait_for_timeout(2000)
    # Click the News sidebar dropdown via JS to avoid Playwright selector
    # ambiguity between desktop "News" and mobile "Languages" toggle.
    clicked = page.evaluate('''() => {
        const links = document.querySelectorAll('a.menu__link--sublist-caret');
        for (const l of links) {
            if (l.textContent.trim() === 'News') { l.click(); return true; }
        }
        return false;
    }''')
    if clicked:
        logging.info("Clicked News sidebar dropdown")
        page.wait_for_timeout(1000)
    return page.content()


def extract_news(soup):
    items = []
    news_section = soup.find("a", class_=lambda c: c and "menu__link--sublist-caret" in str(c), string=lambda t: t and "News" in t.strip() if t else False)
    if not news_section:
        news_section = soup.find("a", string=lambda t: t and t.strip() == "News" if t else False)
    if not news_section:
        return items
    parent_li = news_section.find_parent("li")
    if not parent_li:
        return items
    news_links = parent_li.select('li a[href^="/news/"]')
    if not news_links:
        news_links = soup.select('a[href^="/news/"]')
    for link in news_links:
        href = link.get("href", "")
        text = link.get_text(strip=True)
        if not text or not href:
            continue
        m = re.search(r"(\d{4}/\d{2}/\d{2})$", text)
        date_str = m.group(1) if m else ""
        title = text[:-len(date_str)].strip() if date_str else text
        pub = parse_date(date_str) or datetime.now(timezone.utc).isoformat()
        url = BASE_URL.rstrip("/") + "/" + href.lstrip("/")
        item_id = hashlib.md5(f"deepseek_news_{title}_{date_str}".encode()).hexdigest()
        items.append(compact({
            "id": item_id, "source": "deepseek", "type": "news",
            "title": title, "url": url, "published_date": pub,
            "organization": "DeepSeek",
        }))
    return items


def run(page):
    config = load_feeds_config(ORG_KEY)
    html = _fetch_deepseek_news(page)
    soup = BeautifulSoup(html, "html.parser")
    entries = extract_news(soup)
    if not entries:
        logging.warning("No entries found")
        return
    entries = [json.loads(s) for s in {json.dumps(d) for d in entries}]
    entries.sort(key=lambda x: x.get("published_date", ""), reverse=True)
    p = config["pages"]["news"]
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
