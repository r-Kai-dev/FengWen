"""Scrape Agents' Last Exam blog page."""

import hashlib
import html as html_mod
import logging
from datetime import datetime, timezone

from bs4 import BeautifulSoup

from utils import (
    FEEDS_DIR, setup_logging, ensure_output_dir,
    load_feeds_config, fetch_page, compact, write_atom_feed,
)

setup_logging()
ensure_output_dir()
ORG_KEY = "agentslastexam"
BASE_URL = "https://agents-last-exam.org"


MONTH_MAP = {
    "January": "01", "February": "02", "March": "03", "April": "04",
    "May": "05", "June": "06", "July": "07", "August": "08",
    "September": "09", "October": "10", "November": "11", "December": "12",
}


def parse_date(date_str):
    """Parse 'June 14, 2026' date string."""
    if not date_str:
        return None
    try:
        dt = datetime.strptime(date_str.strip(), "%B %d, %Y")
        return dt.replace(tzinfo=timezone.utc).isoformat()
    except ValueError:
        return None


def extract_posts(soup):
    posts = []
    base_date_el = None

    for a in soup.find_all("a", class_="surface-card"):
        href = a.get("href", "")
        if not href or not href.startswith("/blogs/"):
            continue
        full_url = f"{BASE_URL}{href}"

        # Category chip
        chip = a.find("span", class_="chip")
        cat = chip.get_text(strip=True) if chip else None

        # Date — first text-slate-400 span
        date_els = a.find_all("span", class_="text-slate-400")
        date_str = date_els[0].get_text(strip=True) if date_els else None
        pub = parse_date(date_str) or datetime.now(timezone.utc).isoformat()

        # Title
        title_el = a.find("h2")
        title = html_mod.unescape(title_el.get_text(strip=True)) if title_el else None
        if not title:
            continue

        # Summary
        summary_el = a.find("p", class_=lambda c: c and "text-slate-500" in c)
        summary = html_mod.unescape(summary_el.get_text(strip=True)) if summary_el else None

        item_id = hashlib.md5(f"ale_blog_{title}_{href}".encode()).hexdigest()
        posts.append(compact({
            "id": item_id,
            "title": title,
            "url": full_url,
            "published_date": pub,
            "summary": summary,
            "categories": [cat] if cat else [],
            "organization": "Agents' Last Exam",
        }))

    return posts


def main():
    config = load_feeds_config(ORG_KEY)
    favicon = config.get("favicon")

    for page_key, page in config["pages"].items():
        logging.info("Fetching %s: %s", page["label"], page["url"])
        html = fetch_page(page["url"])
        soup = BeautifulSoup(html, "html.parser")

        entries = extract_posts(soup)
        if not entries:
            logging.warning("No entries for %s", page_key)
            continue

        entries.sort(key=lambda x: x.get("published_date", ""), reverse=True)
        write_atom_feed(FEEDS_DIR / page["output_file"], entries,
                        feed_title=page["label"], feed_link=page["url"],
                        feed_icon=favicon)


if __name__ == "__main__":
    main()
