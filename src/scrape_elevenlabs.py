"""Scrape ElevenLabs research blog from Next.js RSC payload."""

import hashlib
import logging
import re
from datetime import datetime, timezone

from utils import (
    FEEDS_DIR, setup_logging, ensure_output_dir,
    load_feeds_config, fetch_page, compact, write_atom_feed,
)

setup_logging()
ensure_output_dir()
ORG_KEY = "elevenlabs"
BASE_URL = "https://elevenlabs.io"


def _parse_date(iso_str):
    try:
        return datetime.fromisoformat(iso_str.replace("Z", "+00:00")).isoformat()
    except (ValueError, TypeError):
        return datetime.now(timezone.utc).isoformat()


def extract(html):
    chunks = re.findall(r'self\.__next_f\.push\(\[1,\s*"(.*?)"\s*\]\)', html, re.DOTALL)
    all_data = ""
    for chunk in chunks:
        all_data += chunk.encode("utf-8").decode("unicode_escape", errors="replace")

    titles = []
    for m in re.finditer(r'children":\[\["\$","span",null,\{[^}]*\}\],"([^"]+)"\]', all_data):
        ctx = all_data[max(0, m.start() - 200):m.start()]
        href_m = re.search(r'href":"(/blog/[^"]+)"', ctx)
        if href_m:
            titles.append({"title": m.group(1), "url": f"{BASE_URL}{href_m.group(1)}"})

    dates = []
    for m in re.finditer(r'"dateTime":"([^"]+)"', all_data):
        after = all_data[m.end():m.end() + 200]
        disp_m = re.search(r'children":"([A-Za-z]+ \d{1,2}, \d{4})"', after)
        if not disp_m:
            continue
        ctx = all_data[max(0, m.start() - 400):m.start() + 200]
        cat_m = re.search(r'children":"Category"[\s\S]*?"children":"([^"]+)"', ctx)
        dates.append({"dateTime": _parse_date(m.group(1)), "category": cat_m.group(1) if cat_m else ""})

    entries = []
    for t, d in zip(titles, dates):
        item_id = hashlib.md5(f"elevenlabs_{t['url']}".encode()).hexdigest()
        entries.append(compact({
            "id": item_id, "source": "elevenlabs", "type": "research",
            "title": t["title"], "url": t["url"],
            "published_date": d["dateTime"],
            "categories": [d["category"]] if d["category"] else [],
            "organization": "ElevenLabs",
        }))
    return entries


def main():
    config = load_feeds_config(ORG_KEY)
    page = config["pages"]["research"]
    logging.info("Fetching %s: %s", page["label"], page["url"])
    html = fetch_page(page["url"])
    entries = extract(html)
    if not entries:
        logging.warning("No entries found")
        return
    entries.sort(key=lambda x: x.get("published_date", ""), reverse=True)
    write_atom_feed(FEEDS_DIR / page["output_file"], entries,
                    feed_title=page["label"], feed_link=page["url"],
                    feed_icon=config.get("favicon"))

if __name__ == "__main__":
    main()
