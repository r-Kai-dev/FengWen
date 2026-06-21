"""Scrape Moonshot AI blog page."""

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
ORG_KEY = "moonshot"


def parse_date(date_str):
    if not date_str:
        return None
    date_str = date_str.strip()
    for fmt in ("%Y-%m-%d", "%Y/%m/%d", "%B %d, %Y", "%b %d, %Y"):
        try:
            return datetime.strptime(date_str, fmt).replace(tzinfo=timezone.utc).isoformat()
        except ValueError:
            continue
    return None


def extract_posts(soup):
    posts = []
    for item in soup.find_all("div", class_="post-item"):
        title_el = item.find("h3")
        if not title_el:
            continue
        link_el = title_el.find("a")
        if not link_el:
            continue
        title = link_el.get_text(strip=True)
        url_path = link_el.get("href", "")
        url = url_path if url_path.startswith("http") else f"https://platform.moonshot.ai{url_path}"

        desc_el = item.find("p")
        description = desc_el.get_text(strip=True) if desc_el else ""
        if "Read More" in description:
            description = description.split("Read More")[0].strip()

        published_date = None
        time_el = item.find("time")
        if time_el:
            date_str = time_el.get("datetime", "")
            if date_str:
                try:
                    published_date = datetime.fromisoformat(date_str.replace("Z", "+00:00")).isoformat()
                except (ValueError, TypeError):
                    pass
            if not published_date:
                published_date = parse_date(time_el.get_text(strip=True))
        if not published_date:
            published_date = datetime.now(timezone.utc).isoformat()

        item_id = hashlib.md5(f"moonshot_{title}_{url}".encode()).hexdigest()
        posts.append(compact({
            "id": item_id, "source": "moonshot", "type": "blog",
            "title": title, "url": url, "summary": description,
            "published_date": published_date,
            "categories": ["Blog"], "organization": "Moonshot AI",
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
    # Dedup
    entries = [json.loads(s) for s in {json.dumps(d) for d in entries}]
    entries.sort(key=lambda x: x.get("published_date", ""), reverse=True)
    write_atom_feed(FEEDS_DIR / page["output_file"], entries,
                    feed_title=page["label"], feed_link=page["url"],
                    feed_icon=config.get("favicon"))

if __name__ == "__main__":
    main()
