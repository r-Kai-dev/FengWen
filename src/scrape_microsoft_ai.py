"""Fetch Microsoft AI blog posts from the WordPress listing page."""

import hashlib
import logging
import re

from bs4 import BeautifulSoup

from utils import (
    FEEDS_DIR, setup_logging, ensure_output_dir,
    load_feeds_config, fetch_page, compact, write_atom_feed,
)

setup_logging()
ensure_output_dir()
ORG_KEY = "microsoft_ai"


def _extract_date_from_article(url: str) -> str:
    """Visit an article page and extract datePublished from JSON-LD."""
    try:
        html = fetch_page(url)
        match = re.search(r'"datePublished":"([^"]+)"', html)
        if match:
            return match.group(1)
    except Exception as exc:
        logging.warning("Failed to fetch date from %s: %s", url, exc)
    return ""


def main():
    config = load_feeds_config(ORG_KEY)
    favicon = config.get("favicon")

    for page_key, page in config["pages"].items():
        logging.info("Fetching %s: %s", page["label"], page["url"])
        # The posts are server-rendered in #news-container when ?subject=all is present
        html = fetch_page(page["url"] + "?subject=all")
        soup = BeautifulSoup(html, "html.parser")

        container = soup.find(id="news-container")
        if not container:
            logging.warning("No news-container found for %s", page_key)
            continue

        posts = container.find_all("scroll-object")
        logging.info("Found %d scroll-object elements", len(posts))

        entries = []
        seen = set()
        for post in posts:
            # Find the main heading link
            h2 = post.find("h2")
            link = h2.find("a", href=True) if h2 else None
            if not link:
                # Try the image link (featured post layout)
                link = post.find("a", href=True, title=True)
            if not link:
                continue

            href = link.get("href", "").strip()
            if not href or href in seen:
                continue
            seen.add(href)

            # Title: from h2 link, or fallback to the title attr
            title = ""
            if h2:
                h2_link = h2.find("a", href=True)
                if h2_link:
                    title = h2_link.get_text(strip=True)
            if not title:
                title = link.get("title", "").replace(" Link", "")

            if not title:
                continue

            # Category tag
            tag_span = post.find("span", class_=lambda c: c and "tag" in c if c else False)
            category = tag_span.get_text(strip=True) if tag_span else ""

            # Fetch article page to grab the real publication date
            pub_date = _extract_date_from_article(href)

            entry_id = hashlib.md5(f"{ORG_KEY}_{href}".encode()).hexdigest()

            entries.append(compact({
                "title": title.strip(),
                "url": href,
                "id": entry_id,
                "published_date": pub_date,
                "categories": [category] if category else [],
                "organization": "Microsoft AI",
            }))

        # Interpolate missing dates from adjacent entries
        logging.info("Parsed %d entries for %s", len(entries), page_key)

        if entries:
            write_atom_feed(FEEDS_DIR / page["output_file"], entries,
                            feed_title=page["label"],
                            feed_link=page["url"],
                            feed_icon=favicon)


if __name__ == "__main__":
    main()
