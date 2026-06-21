"""Scrape Black Forest Labs blog and research pages."""

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
ORG_KEY = "bfl"
BASE_URL = "https://bfl.ai"


def parse_date(date_str):
    if not date_str:
        return None
    for fmt in ("%B %d, %Y", "%b %d, %Y"):
        try:
            return datetime.strptime(date_str.strip(), fmt).replace(tzinfo=timezone.utc).isoformat()
        except ValueError:
            continue
    return None


def extract_blog(soup):
    posts = []
    for article in soup.find_all("article"):
        title_el = article.find("h2")
        if not title_el:
            continue
        title = title_el.get_text(strip=True)
        if not title:
            continue

        time_el = article.find("time")
        pub = None
        if time_el:
            dt = time_el.get("datetime", "")
            pub = dt if dt else parse_date(time_el.get_text(strip=True))
        if not pub:
            pub = datetime.now(timezone.utc).isoformat()

        excerpt = None
        desc_el = article.find("p", class_=lambda c: c and "text-bf-body-2-regular" in str(c) if c else False)
        if desc_el:
            excerpt = desc_el.get_text(strip=True)

        link_el = article.find("a", href=re.compile(r"^/blog/"))
        href = link_el.get("href", "") if link_el else ""
        url = f"{BASE_URL}{href}" if href else BASE_URL

        categories = [li.get_text(strip=True) for li in article.find_all("li")
                      if li.get_text(strip=True) and li.get_text(strip=True) != "Read more"]

        item_id = hashlib.md5(f"bfl_blog_{title}_{href}".encode()).hexdigest()
        posts.append(compact({
            "id": item_id, "source": "bfl", "type": "blog",
            "title": title, "url": url, "summary": excerpt,
            "published_date": pub, "categories": categories,
            "organization": "Black Forest Labs",
        }))
    return posts


def extract_research(soup):
    posts = []
    for item in soup.find_all("div", class_=lambda c: c and "py-3" in str(c) and "lg:py-7" in str(c) if c else False):
        title_el = item.find("h3")
        if not title_el:
            continue
        title = title_el.get_text(strip=True)
        if not title:
            continue

        desc_el = item.find("p")
        excerpt = desc_el.get_text(strip=True) if desc_el else None

        date_el = item.find("div", class_=lambda c: c and "tracking-wider" in str(c) if c else False)
        pub = parse_date(date_el.get_text(strip=True)) if date_el else None
        if not pub:
            pub = datetime.now(timezone.utc).isoformat()

        link_el = item.find("a", href=re.compile(r"^/research/")) or item.find("a", href=True)
        href = link_el.get("href", "") if link_el else ""
        url = f"{BASE_URL}{href}" if href.startswith("/") else (href or BASE_URL)

        item_id = hashlib.md5(f"bfl_research_{title}_{href}".encode()).hexdigest()
        posts.append(compact({
            "id": item_id, "source": "bfl", "type": "research",
            "title": title, "url": url, "summary": excerpt,
            "published_date": pub, "organization": "Black Forest Labs",
        }))
    return posts


def main():
    config = load_feeds_config(ORG_KEY)
    for page_key, page in config["pages"].items():
        logging.info("Fetching %s: %s", page["label"], page["url"])
        html = fetch_page(page["url"])
        soup = BeautifulSoup(html, "html.parser")
        entries = extract_blog(soup) if page_key == "blog" else extract_research(soup)
        if not entries:
            logging.warning("No entries for %s", page_key)
            continue
        entries.sort(key=lambda x: x.get("published_date", ""), reverse=True)
        write_atom_feed(FEEDS_DIR / page["output_file"], entries,
                        feed_title=page["label"], feed_link=page["url"],
                        feed_icon=config.get("favicon"))

if __name__ == "__main__":
    main()
