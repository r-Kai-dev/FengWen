"""Crawl DeepLearning.AI The Batch page (Playwright — GitHub Actions compatible)."""

import hashlib
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
ORG_KEY = "deeplearning_ai"


def parse_datetime_attr(dt_str):
    if not dt_str:
        return None
    try:
        return datetime.fromisoformat(dt_str.replace("Z", "+00:00")).isoformat()
    except ValueError:
        return None


def extract_posts(soup):
    posts = []
    cards = []
    for article in soup.find_all("article", attrs={"data-sentry-component": "PostCard"}):
        src = article.get("data-sentry-source-file", "")
        if src in ("PostCardLarge.tsx", "PostCard.tsx"):
            cards.append(article)
    for article in soup.find_all("article", attrs={"data-sentry-component": "PostCardSmall"}):
        cards.append(article)

    for article in cards:
        title_el = article.find("h2")
        if not title_el:
            continue
        title = title_el.get_text(strip=True)

        main_link = article.find("a", href=re.compile(r"^/the-batch/(?!tag/)"))
        if not main_link:
            continue
        url = f"https://www.deeplearning.ai{main_link['href']}"

        desc_el = article.find("div", class_=lambda c: c and "line-clamp-3" in c)
        description = desc_el.get_text(strip=True) if desc_el else ""

        pub = None
        time_el = article.find("time")
        if time_el:
            pub = parse_datetime_attr(time_el.get("datetime", ""))
        if not pub:
            tag_link = article.find("a", href=re.compile(r"^/the-batch/tag/"))
            if tag_link:
                try:
                    pub = datetime.strptime(tag_link.get_text(strip=True), "%b %d, %Y").replace(tzinfo=timezone.utc).isoformat()
                except ValueError:
                    pass
        if not pub:
            pub = datetime.now(timezone.utc).isoformat()

        item_id = hashlib.md5(f"deeplearning_ai_{title}_{url}".encode()).hexdigest()
        posts.append(compact({
            "id": item_id, "source": "deeplearning_ai", "type": "newsletter",
            "title": title, "url": url, "summary": description,
            "published_date": pub, "organization": "DeepLearning.AI",
        }))
    return posts


def run(page):
    config = load_feeds_config(ORG_KEY)
    p = config["pages"]["the_batch"]
    logging.info("Crawling %s: %s", p["label"], p["url"])
    page.goto(p["url"])
    page.wait_for_timeout(3000)
    soup = BeautifulSoup(page.content(), "html.parser")
    entries = extract_posts(soup)
    if not entries:
        logging.warning("No entries found")
        return
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
