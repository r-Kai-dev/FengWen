"""Scrape DeepLearning.AI The Batch page."""

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
ORG_KEY = "deeplearning_ai"


def parse_datetime_attr(dt_str):
    if not dt_str:
        return None
    try:
        return datetime.fromisoformat(dt_str.replace("Z", "+00:00")).isoformat()
    except ValueError:
        return None


def extract_posts(soup):
    posts = []
    cards = []
    for article in soup.find_all("article", attrs={"data-sentry-component": "PostCard"}):
        src = article.get("data-sentry-source-file", "")
        if src in ("PostCardLarge.tsx", "PostCard.tsx"):
            cards.append(article)
    for article in soup.find_all("article", attrs={"data-sentry-component": "PostCardSmall"}):
        cards.append(article)

    for article in cards:
        title_el = article.find("h2")
        if not title_el:
            continue
        title = title_el.get_text(strip=True)

        main_link = article.find("a", href=re.compile(r"^/the-batch/(?!tag/)"))
        if not main_link:
            continue
        url = f"https://www.deeplearning.ai{main_link['href']}"

        desc_el = article.find("div", class_=lambda c: c and "line-clamp-3" in c)
        description = desc_el.get_text(strip=True) if desc_el else ""

        pub = None
        time_el = article.find("time")
        if time_el:
            pub = parse_datetime_attr(time_el.get("datetime", ""))
        if not pub:
            tag_link = article.find("a", href=re.compile(r"^/the-batch/tag/"))
            if tag_link:
                try:
                    pub = datetime.strptime(tag_link.get_text(strip=True), "%b %d, %Y").replace(tzinfo=timezone.utc).isoformat()
                except ValueError:
                    pass
        if not pub:
            pub = datetime.now(timezone.utc).isoformat()

        item_id = hashlib.md5(f"deeplearning_ai_{title}_{url}".encode()).hexdigest()
        posts.append(compact({
            "id": item_id, "source": "deeplearning_ai", "type": "newsletter",
            "title": title, "url": url, "summary": description,
            "published_date": pub, "organization": "DeepLearning.AI",
        }))
    return posts


def main():
    config = load_feeds_config(ORG_KEY)
    page = config["pages"]["the_batch"]
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
