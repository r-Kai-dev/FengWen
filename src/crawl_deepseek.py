"""Crawl DeepSeek API docs news sidebar (expand News category)."""

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
ORG_KEY = "deepseek"
BASE_URL = "https://api-docs.deepseek.com"


def parse_date(date_str):
    if not date_str:
        return None
    try:
        return datetime.strptime(date_str.strip(), "%Y/%m/%d").replace(tzinfo=timezone.utc).isoformat()
    except ValueError:
        return None


def _fetch_deepseek_news(page: ChromiumPage):
    logging.info("Navigating to %s", BASE_URL)
    page.get(BASE_URL)
    page.wait.doc_loaded()
    page.wait(2)
    news_link = page.ele("tx:News", timeout=5)
    if news_link:
        collapsible = news_link.parent("tag:div")
        if collapsible:
            logging.info("Clicking News sidebar dropdown…")
            collapsible.click()
            page.wait(0.5)
    return page.html


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


def run(page: ChromiumPage):
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
    from DrissionPage import ChromiumOptions
    co = ChromiumOptions()
    co.set_browser_path("/usr/bin/chromium")
    co.headless(on_off=True); co.new_env(on_off=True)
    co.set_argument("--no-sandbox"); co.set_argument("--disable-gpu")
    pg = ChromiumPage(addr_or_opts=co)
    try: run(pg)
    finally: pg.quit()
