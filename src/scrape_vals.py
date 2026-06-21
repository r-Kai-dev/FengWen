"""Scrape Vals AI news page."""

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
ORG_KEY = "vals"
BASE_URL = "https://www.vals.ai"


def parse_date(date_str):
    """Parse MM/DD/YYYY date string."""
    if not date_str:
        return None
    try:
        return datetime.strptime(date_str.strip(), "%m/%d/%Y").replace(tzinfo=timezone.utc).isoformat()
    except ValueError:
        return None


def extract_featured_articles(soup, all_urls_seen):
    """Extract featured articles from the two featured sections."""
    entries = []

    # Find the featured articles container — the div that holds all featured sections
    featured_container = None
    for h4 in soup.find_all("h4"):
        if "Featured Articles" in h4.get_text():
            featured_container = h4.find_parent("div")
            break

    if not featured_container:
        logging.warning("Featured Articles container not found")
        return entries

    # All <a> tags within the featured container that have hrefs
    for section in featured_container.find_all("section"):
        for a in section.find_all("a", href=True):
            href = a.get("href", "")
            full_url = href if href.startswith("http") else f"{BASE_URL}{href}"

            if full_url in all_urls_seen:
                continue

            # Title: either <h3> or <p class="foreground-primary ...">
            title_el = a.find("h3") or a.find("p", class_=lambda c: c and "foreground-primary" in c)
            if not title_el:
                continue
            title = html_mod.unescape(title_el.get_text(strip=True))

            # Category from pill
            pill = a.find("span", class_=lambda c: c and "pill" in c)
            cat = pill.get_text(strip=True) if pill else None

            # Date from the font-mono spans — take the first one (or any with date-like format)
            date_el = a.find("span", class_=lambda c: c and "font-mono" in c)
            date_str = date_el.get_text(strip=True) if date_el else None
            pub = parse_date(date_str) or datetime.now(timezone.utc).isoformat()

            item_id = hashlib.md5(f"vals_feat_{title}_{href}".encode()).hexdigest()
            all_urls_seen.add(full_url)

            entries.append(compact({
                "id": item_id,
                "title": title,
                "url": full_url,
                "published_date": pub,
                "categories": [cat] if cat else [],
                "organization": "Vals AI",
            }))

    return entries


def extract_all_articles(soup, all_urls_seen):
    """Extract articles from the All Articles list section."""
    entries = []

    all_section = None
    for h2 in soup.find_all("h2"):
        if "All Articles" in h2.get_text():
            all_section = h2.find_parent("section")
            break

    if not all_section:
        logging.warning("All Articles section not found")
        return entries

    for a in all_section.find_all("a", href=True):
        href = a.get("href", "")
        full_url = href if href.startswith("http") else f"{BASE_URL}{href}"

        if full_url in all_urls_seen:
            continue

        # Category from pill
        pill = a.find("div", class_=lambda c: c and "pill" in c)
        if not pill:
            continue
        cat = pill.get_text(strip=True)

        # Title
        title_el = a.find("p", class_=lambda c: c and "foreground-primary" in c)
        if not title_el:
            continue
        title = html_mod.unescape(title_el.get_text(strip=True))

        # Author/org badge
        author_el = a.find("span", class_=lambda c: c and "text-nowrap" in c)
        author = author_el.get_text(strip=True) if author_el else "Vals AI"

        # Date — the last font-mono span
        date_els = a.find_all("span", class_=lambda c: c and "font-mono" in c)
        date_str = date_els[-1].get_text(strip=True) if date_els else None
        pub = parse_date(date_str) or datetime.now(timezone.utc).isoformat()

        item_id = hashlib.md5(f"vals_article_{title}_{href}".encode()).hexdigest()
        all_urls_seen.add(full_url)

        entries.append(compact({
            "id": item_id,
            "title": title,
            "url": full_url,
            "published_date": pub,
            "categories": [cat] if cat else [],
            "organization": author,
        }))

    return entries


def main():
    config = load_feeds_config(ORG_KEY)
    favicon = config.get("favicon")
    all_urls_seen = set()

    for page_key, page in config["pages"].items():
        logging.info("Fetching %s: %s", page["label"], page["url"])
        html = fetch_page(page["url"])
        soup = BeautifulSoup(html, "html.parser")

        entries = []
        entries.extend(extract_featured_articles(soup, all_urls_seen))
        entries.extend(extract_all_articles(soup, all_urls_seen))

        if not entries:
            logging.warning("No entries for %s", page_key)
            continue

        entries.sort(key=lambda x: x.get("published_date", ""), reverse=True)
        write_atom_feed(FEEDS_DIR / page["output_file"], entries,
                        feed_title=page["label"], feed_link=page["url"],
                        feed_icon=favicon)


if __name__ == "__main__":
    main()
