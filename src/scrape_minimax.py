"""Scrape MiniMax release notes page."""

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
ORG_KEY = "minimax"


def parse_date(date_str):
    if not date_str:
        return None
    date_str = date_str.strip()
    # Handle abbreviated months
    for old, new in [("Jan.", "Jan"), ("Feb.", "Feb"), ("Mar.", "Mar"),
                     ("Apr.", "Apr"), ("May.", "May"), ("Jun.", "Jun"),
                     ("Jul.", "Jul"), ("Aug.", "Aug"), ("Sept.", "Sep"),
                     ("Sep.", "Sep"), ("Oct.", "Oct"), ("Nov.", "Nov"), ("Dec.", "Dec")]:
        if old in date_str:
            date_str = date_str.replace(old, new)
            break
    for fmt in ("%b %d, %Y", "%B %d, %Y", "%b %d %Y", "%b. %d, %Y", "%b. %d %Y", "%b. %Y"):
        try:
            return datetime.strptime(date_str, fmt).replace(tzinfo=timezone.utc).isoformat()
        except ValueError:
            continue
    # "Mar. 2026" fallback
    m = re.match(r"([A-Za-z]+)\.?\s+(\d{4})", date_str)
    if m:
        month_map = {"jan":1,"feb":2,"mar":3,"apr":4,"may":5,"jun":6,
                     "jul":7,"aug":8,"sep":9,"oct":10,"nov":11,"dec":12}
        ml = m.group(1).lower()[:3]
        if ml in month_map:
            return datetime(int(m.group(2)), month_map[ml], 1, tzinfo=timezone.utc).isoformat()
    return None


def extract_posts(soup):
    posts = []
    for header in soup.find_all("h4", id=True):
        date_id = header.get("id", "")
        date_span = header.find("span", class_="cursor-pointer")
        date_text = date_span.get_text(strip=True) if date_span else date_id
        pub = parse_date(date_text) or datetime.now(timezone.utc).isoformat()

        next_elem = header.find_next_sibling()
        while next_elem and not (next_elem.name == "div" and "card" in next_elem.get("class", [])):
            next_elem = next_elem.find_next_sibling()
        if not next_elem or next_elem.name != "div" or "card" not in next_elem.get("class", []):
            continue
        card = next_elem

        title_el = card.find("h2", attrs={"data-component-part": "card-title"})
        title = title_el.get_text(strip=True) if title_el else "MiniMax Model Update"

        content_el = card.find("div", attrs={"data-component-part": "card-content"})
        description = " ".join(content_el.get_text().split()) if content_el else ""

        url = card.get("href", "")
        if url and not url.startswith("http"):
            url = f"https://platform.minimax.io{url}"
        elif not url:
            url = "https://platform.minimax.io/docs/release-notes/models"

        item_id = hashlib.md5(f"minimax_{title}_{date_id}".encode()).hexdigest()
        posts.append(compact({
            "id": item_id, "source": "minimax", "type": "model_update",
            "title": title, "url": url, "summary": description,
            "published_date": pub,
            "categories": ["Release Notes", "Models"], "organization": "MiniMax",
        }))
    return posts


def main():
    config = load_feeds_config(ORG_KEY)
    page = config["pages"]["release_notes"]
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
