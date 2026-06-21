"""Scrape Boson AI blog from Next.js RSC payload."""

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
ORG_KEY = "boson"
BASE_URL = "https://www.boson.ai"


def parse_date(date_str):
    if not date_str:
        return None
    for fmt in ("%b. %d, %Y", "%B %d, %Y", "%b %d, %Y"):
        try:
            return datetime.strptime(date_str.strip(), fmt).replace(tzinfo=timezone.utc).isoformat()
        except ValueError:
            continue
    return None


def extract(html):
    chunks = re.findall(r'self\.__next_f\.push\(\[[0-9]+,\s*"(.*?)"\s*\]\)', html, re.DOTALL)
    all_hrefs, all_dates, all_titles = [], [], []
    for chunk in chunks:
        decoded = chunk.encode("utf-8").decode("unicode_escape", errors="replace")
        all_hrefs.extend(re.findall(r'"href":"/blog/([^"]+)"', decoded))
        all_dates.extend(re.findall(r'"children":"([A-Z][a-z]{2}\.\s*\d{1,2},\s*\d{4})"', decoded))
        for m in re.finditer(r'"children":"([^"]{15,150}?)"', decoded):
            text = m.group(1)
            if not text.startswith(("http", "\\u00a9", "$")) and "className" not in text and "Read More" not in text and "text-boson" not in text and not re.match(r'^[a-f0-9]{20,}$', text) and not text.startswith("Product updates"):
                all_titles.append(text)

    posts = []
    for i, slug in enumerate(all_hrefs):
        if not slug:
            continue
        url = f"{BASE_URL}/blog/{slug}"
        pub = parse_date(all_dates[i]) if i < len(all_dates) else None
        if not pub:
            pub = datetime.now(timezone.utc).isoformat()
        title = all_titles[i] if i < len(all_titles) else slug.replace("-", " ").title()
        item_id = hashlib.md5(f"boson_blog_{slug}".encode()).hexdigest()
        posts.append(compact({
            "id": item_id, "source": "boson", "type": "blog",
            "title": title, "url": url, "published_date": pub,
            "organization": "Boson AI",
        }))
    return posts


def main():
    config = load_feeds_config(ORG_KEY)
    page = config["pages"]["blog"]
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
