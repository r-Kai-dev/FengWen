"""Scrape AMI Lab updates page."""

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
ORG_KEY = "ami"
BASE_URL = "https://amilabs.xyz"


def parse_date(date_str):
    if not date_str:
        return None
    for fmt in ("%B %d, %Y", "%b %d, %Y"):
        try:
            return datetime.strptime(date_str.strip(), fmt).replace(tzinfo=timezone.utc).isoformat()
        except ValueError:
            continue
    return None


def extract_posts(soup):
    posts = []
    for div in soup.select(".div-content-other"):
        headings = div.find_all("p", class_=lambda c: c and "bold" in (c or ""))
        full_text = div.get_text(separator=" ", strip=True)

        title = None; date_str = None
        for p in headings:
            text = p.get_text(strip=True)
            m = re.search(r"([A-Z][a-z]+ \d{1,2}, \d{4})", text)
            if m:
                date_str = m.group(1)
                title = text
                break
        if not title:
            first_p = div.find("p")
            if first_p:
                title = first_p.get_text(strip=True)[:100]
                m = re.search(r"([A-Z][a-z]+ \d{1,2}, \d{4})", title)
                if m:
                    date_str = m.group(1)
        if not title:
            continue

        pub = parse_date(date_str) or datetime.now(timezone.utc).isoformat()

        title = re.sub(r'<[^>]+>', '', title).strip()
        title = re.sub(r'^\*+|\*+$', '', title).strip()
        if " - " in title:
            title = title.split(" - ", 1)[1].strip()
        elif date_str and date_str in title:
            title = title.replace(date_str, "").strip(" -")

        summary = full_text[:500] if full_text else None

        slug = date_str.lower().replace(",", "").replace(" ", "-") if date_str else "update"
        item_id = hashlib.md5(f"ami_updates_{date_str}_{title}".encode()).hexdigest()
        posts.append(compact({
            "id": item_id, "source": "ami", "type": "updates",
            "title": title, "url": f"{BASE_URL}/updates",
            "summary": summary, "published_date": pub,
            "organization": "AMI Labs",
        }))
    return posts


def main():
    config = load_feeds_config(ORG_KEY)
    page = config["pages"]["updates"]
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
