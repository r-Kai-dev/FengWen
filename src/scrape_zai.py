"""Scrape Z.AI release notes page."""

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
ORG_KEY = "zai"


def parse_date(date_str):
    if not date_str:
        return None
    date_str = date_str.strip()
    if re.match(r"^\d{4}-\d{2}-\d{2}$", date_str):
        try:
            return datetime.strptime(date_str, "%Y-%m-%d").replace(tzinfo=timezone.utc).isoformat()
        except ValueError:
            pass
    for old, new in [("Jan.", "Jan"), ("Feb.", "Feb"), ("Mar.", "Mar"),
                     ("Apr.", "Apr"), ("May.", "May"), ("Jun.", "Jun"),
                     ("Jul.", "Jul"), ("Aug.", "Aug"), ("Sept.", "Sep"),
                     ("Sep.", "Sep"), ("Oct.", "Oct"), ("Nov.", "Nov"), ("Dec.", "Dec")]:
        if old in date_str:
            date_str = date_str.replace(old, new)
            break
    for fmt in ("%b %d, %Y", "%B %d, %Y", "%b %d %Y", "%b. %d, %Y"):
        try:
            return datetime.strptime(date_str, fmt).replace(tzinfo=timezone.utc).isoformat()
        except ValueError:
            continue
    return None


def extract_posts(soup):
    posts = []
    for container in soup.find_all("div", class_="update"):
        date_id = container.get("id", "")
        date_label = container.find("div", attrs={"data-component-part": "update-label"})
        date_text = date_label.get_text(strip=True) if date_label else date_id
        pub = parse_date(date_text) or datetime.now(timezone.utc).isoformat()

        desc_el = container.find("div", attrs={"data-component-part": "update-description"})
        model_name = desc_el.get_text(strip=True) if desc_el else ""
        title = model_name or "Z.AI Model Update"

        content_el = container.find("div", attrs={"data-component-part": "update-content"})
        descriptions = []
        if content_el:
            for li in content_el.find_all("li"):
                spans = li.find_all("span", attrs={"data-as": "p"})
                for span in spans:
                    text = " ".join(span.get_text().split())
                    if text:
                        descriptions.append(text)
                if not spans:
                    text = " ".join(li.get_text().split())
                    if text:
                        descriptions.append(text)
        filtered = [d for d in descriptions if "learn more" not in d.lower()]
        description = " ".join(filtered) if filtered else (descriptions[0] if descriptions else "")

        base_url = "https://docs.z.ai/release-notes/new-released"
        item_id = hashlib.md5(f"z-ai_{title}_{date_id}".encode()).hexdigest()
        posts.append(compact({
            "id": item_id, "source": "z-ai", "type": "model_update",
            "title": title, "url": base_url, "summary": description,
            "published_date": pub,
            "categories": ["Release Notes", "Models"], "organization": "Z.AI",
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
