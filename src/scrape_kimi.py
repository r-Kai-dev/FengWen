"""Scrape Kimi blog page."""

import hashlib
import logging
from datetime import datetime, timezone

from bs4 import BeautifulSoup

from utils import (
    FEEDS_DIR, setup_logging, ensure_output_dir,
    load_feeds_config, fetch_page, compact, write_atom_feed,
)

setup_logging()
ensure_output_dir()
ORG_KEY = "kimi"


def parse_date(date_str):
    if not date_str:
        return None
    try:
        return datetime.strptime(date_str.strip(), "%Y/%m/%d").replace(tzinfo=timezone.utc).isoformat()
    except ValueError:
        return None


def extract_posts(soup):
    posts = []
    for link in soup.find_all("a", class_="menu-card"):
        href = link.get("href", "")
        if not href or not href.startswith("/blog/"):
            continue
        title_el = link.find("h4", class_="card-title")
        if not title_el:
            continue
        title = title_el.get_text(strip=True)
        desc_el = link.find("p", class_="card-desc")
        description = desc_el.get_text(strip=True) if desc_el else ""
        date_el = link.find("p", class_="card-date")
        published_date = parse_date(date_el.get_text(strip=True)) if date_el else None
        if not published_date:
            published_date = datetime.now(timezone.utc).isoformat()

        item_id = hashlib.md5(f"kimi_{title}_https://www.kimi.com{href}".encode()).hexdigest()
        posts.append(compact({
            "id": item_id, "source": "kimi", "type": "blog",
            "title": title, "url": f"https://www.kimi.com{href}",
            "summary": description, "published_date": published_date,
            "categories": ["Research"], "organization": "Kimi",
        }))
    return posts


def main():
    config = load_feeds_config(ORG_KEY)
    page = config["pages"]["blog"]
    logging.info("Fetching %s: %s", page["label"], page["url"])
    html = fetch_page(page["url"])
    soup = BeautifulSoup(html, "html.parser")
    entries = extract_posts(soup)
    if not entries:
        logging.warning("No entries found")
        return
    entries.sort(key=lambda x: x.get("published_date", ""), reverse=True)
    write_atom_feed(FEEDS_DIR / page["output_file"], entries,
                    feed_title=page["label"], feed_link=page["url"],
                    feed_icon=config.get("favicon"))

if __name__ == "__main__":
    main()
