"""Scrape Meta AI blog page."""

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
ORG_KEY = "meta"


def parse_date(date_str):
    if not date_str:
        return None
    date_str = re.sub(r"\s+", " ", date_str.strip())
    for fmt in ("%B %d, %Y", "%b %d, %Y", "%B %d %Y", "%b %d %Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(date_str, fmt).replace(tzinfo=timezone.utc).isoformat()
        except ValueError:
            continue
    logging.warning("Could not parse date: '%s'", date_str)
    return None


def extract_posts(soup):
    posts = []

    # Featured post (hero section)
    featured = soup.find("div", class_="_metaAIFeaturedBlogHero__heroContainer")
    if featured:
        title_el = featured.find("div", class_="_amd1")
        if title_el:
            link_el = title_el.find("a", class_="_amd2")
            if link_el:
                title = link_el.get_text(strip=True)
                url = link_el.get("href", "")
                if title and url:
                    date_el = featured.find("div", class_="_amun")
                    pub = parse_date(date_el.get_text(strip=True)) if date_el else None
                    if not pub:
                        pub = datetime.now(timezone.utc).isoformat()
                    item_id = hashlib.md5(f"meta_ai_{title}_{url}".encode()).hexdigest()
                    posts.append(compact({
                        "id": item_id, "source": "meta_ai", "type": "blog",
                        "title": title,
                        "url": url if url.startswith("http") else f"https://ai.meta.com{url}",
                        "published_date": pub, "organization": "Meta AI",
                    }))

    # Latest News cards
    for card in soup.find_all("div", class_="_amda"):
        title_el = card.find("div", class_="_amde")
        if not title_el:
            continue
        link_el = title_el.find("a", class_="_amdf")
        if not link_el:
            continue
        title = link_el.get_text(strip=True)
        url = link_el.get("href", "")
        if not title or not url:
            continue

        cat_el = card.find("div", class_="_amdj")
        categories = [cat_el.get_text(strip=True)] if cat_el else []

        date_str = None
        for div in card.find_all("div", class_="_amdj"):
            text = div.get_text(strip=True)
            if re.match(r"^(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)", text):
                date_str = text
                break
        pub = parse_date(date_str)
        if not pub:
            pub = datetime.now(timezone.utc).isoformat()

        item_id = hashlib.md5(f"meta_ai_{title}_{url}".encode()).hexdigest()
        posts.append(compact({
            "id": item_id, "source": "meta_ai", "type": "blog",
            "title": title,
            "url": url if url.startswith("http") else f"https://ai.meta.com{url}",
            "published_date": pub, "categories": categories,
            "organization": "Meta AI",
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
    entries = [json.loads(s) for s in {json.dumps(d) for d in entries}]
    entries.sort(key=lambda x: x.get("published_date", ""), reverse=True)
    write_atom_feed(FEEDS_DIR / page["output_file"], entries,
                    feed_title=page["label"], feed_link=page["url"],
                    feed_icon=config.get("favicon"))

if __name__ == "__main__":
    main()
