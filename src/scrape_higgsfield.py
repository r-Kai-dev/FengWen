"""Scrape Higgsfield blog via JSON-LD in SSR HTML."""

import hashlib
import json
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
ORG_KEY = "higgsfield"


def parse_date(date_str):
    if not date_str:
        return ""
    date_str = re.sub(r"(\d)(st|nd|rd|th)", r"\1", date_str)
    for fmt in (
        "%Y-%m-%dT%H:%M:%S.%f%z", "%Y-%m-%dT%H:%M:%S%z",
        "%Y-%m-%d", "%B %d, %Y", "%b %d, %Y", "%b. %d, %Y",
    ):
        try:
            dt = datetime.strptime(date_str, fmt)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt.isoformat()
        except (ValueError, TypeError):
            continue
    return ""


def extract_posts(soup):
    posts = []
    seen = set()
    for script in soup.select('script[type="application/ld+json"]'):
        try:
            data = json.loads(script.string)
        except (json.JSONDecodeError, TypeError):
            continue
        if isinstance(data, list):
            data = data[0] if data else {}
        if not isinstance(data, dict):
            continue
        headline = (data.get("headline") or "").strip()
        url = data.get("url") or ""
        me = data.get("mainEntityOfPage", {})
        if isinstance(me, dict):
            url = url or me.get("@id", "")
        date_str = data.get("datePublished", "")
        description = data.get("description", "")
        if not headline or not url or not date_str:
            continue
        if url in seen:
            continue
        seen.add(url)
        pub = parse_date(date_str)
        if not pub:
            pub = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
        slug = url.rstrip("/").split("/")[-1]
        item_id = hashlib.md5(f"higgsfield_blog_{slug}".encode()).hexdigest()
        posts.append(compact({
            "id": item_id, "source": "higgsfield", "type": "blog",
            "title": headline, "url": url, "summary": description,
            "published_date": pub, "organization": "Higgsfield",
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
