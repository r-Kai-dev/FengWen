"""Scrape Artificial Analysis articles page."""

import hashlib
import logging
import re
from datetime import datetime, timezone

from bs4 import BeautifulSoup

from utils import (
    FEEDS_DIR, setup_logging, ensure_output_dir,
    load_feeds_config, fetch_page, compact, write_atom_feed,
)

setup_logging()
ensure_output_dir()
ORG_KEY = "artificial_analysis"


def parse_date(date_str):
    if not date_str:
        return None
    try:
        return datetime.strptime(date_str.strip(), "%B %d, %Y").replace(tzinfo=timezone.utc).isoformat()
    except ValueError:
        return None


def extract_articles(soup):
    articles = []
    for link in soup.find_all("a", href=re.compile(r"^/articles/")):
        href = link.get("href", "")
        title_el = link.find("h3")
        if not title_el:
            continue
        title = title_el.get_text(strip=True)
        date_el = link.find("p")
        date_str = date_el.get_text(strip=True) if date_el else ""
        pub = parse_date(date_str) or datetime.now(timezone.utc).isoformat()
        url = f"https://artificialanalysis.ai{href}"
        item_id = hashlib.md5(f"artificial_analysis_{title}_{url}".encode()).hexdigest()
        articles.append(compact({
            "id": item_id, "source": "artificial_analysis", "type": "article",
            "title": title, "url": url, "published_date": pub,
            "organization": "Artificial Analysis",
        }))
    return articles


def main():
    config = load_feeds_config(ORG_KEY)
    page = config["pages"]["articles"]
    logging.info("Fetching %s: %s", page["label"], page["url"])
    html = fetch_page(page["url"])
    soup = BeautifulSoup(html, "html.parser")
    entries = extract_articles(soup)
    if not entries:
        logging.warning("No entries found")
        return
    entries.sort(key=lambda x: x.get("published_date", ""), reverse=True)
    write_atom_feed(FEEDS_DIR / page["output_file"], entries,
                    feed_title=page["label"], feed_link=page["url"],
                    feed_icon=config.get("favicon"))

if __name__ == "__main__":
    main()
