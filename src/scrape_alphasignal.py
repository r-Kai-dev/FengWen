"""Scrape AlphaSignal news from Next.js RSC payload."""

import hashlib
import json
import logging
import re
from datetime import datetime, timezone

from utils import (
    FEEDS_DIR, setup_logging, ensure_output_dir,
    load_feeds_config, fetch_page, compact, write_atom_feed,
)

setup_logging()
ensure_output_dir()
ORG_KEY = "alphasignal"
BASE_URL = "https://alphasignal.ai"


def extract(html):
    chunks = re.findall(r'self\.__next_f\.push\(\[[0-9]+,\s*"(.*?)"\s*\]\)', html, re.DOTALL)
    for chunk in chunks:
        decoded = chunk.encode("utf-8").decode("unicode_escape", errors="replace")
        if "initialNews" not in decoded:
            continue
        idx = decoded.find("initialNews")
        json_start = decoded.find("[", idx)
        if json_start < 0:
            continue
        depth, end = 0, json_start
        for i in range(json_start, len(decoded)):
            if decoded[i] == "[": depth += 1
            elif decoded[i] == "]":
                depth -= 1
                if depth == 0: end = i + 1; break
        items = json.loads(decoded[json_start:end])
        entries = []
        for item in items:
            title = item.get("title", "")
            url = item.get("url", "")
            subtitle = item.get("subtitle", "")
            date_str = item.get("publish_time", "")
            categories = item.get("regular_categories", [])
            source_name = item.get("name", "")
            if not title or not url:
                continue
            pub = date_str
            if pub:
                try:
                    pub = datetime.fromisoformat(pub.replace("Z", "+00:00")).isoformat()
                except (ValueError, TypeError):
                    pass
            item_id = hashlib.md5(f"alphasignal_news_{url}".encode()).hexdigest()
            entries.append(compact({
                "id": item_id, "source": "alphasignal", "type": "news",
                "title": title, "url": url, "summary": subtitle,
                "published_date": pub, "categories": categories,
                "organization": source_name or "AlphaSignal",
            }))
        return entries
    return []


def main():
    config = load_feeds_config(ORG_KEY)
    page = config["pages"]["news"]
    logging.info("Fetching %s: %s", page["label"], page["url"])
    html = fetch_page(page["url"])
    entries = extract(html)
    if not entries:
        logging.warning("No entries found")
        return
    entries.sort(key=lambda x: x.get("published_date", ""), reverse=True)
    write_atom_feed(FEEDS_DIR / page["output_file"], entries,
                    feed_title=page["label"], feed_link=page["url"],
                    feed_author="AlphaSignal",
                    feed_icon=config.get("favicon"))

if __name__ == "__main__":
    main()
