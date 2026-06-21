"""Scrape Runway news (RSC) and research publications (RSC)."""

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
ORG_KEY = "runway"
BASE_URL = "https://runwayml.com"


def _parse_date(date_str):
    if not date_str:
        return None
    date_str = date_str.strip()
    if "T" in date_str or "-" in date_str:
        try:
            return datetime.fromisoformat(date_str.replace("Z", "+00:00")).isoformat()
        except (ValueError, TypeError):
            pass
    for fmt in ("%B %d, %Y", "%b %d, %Y"):
        try:
            return datetime.strptime(date_str, fmt).replace(tzinfo=timezone.utc).isoformat()
        except ValueError:
            continue
    return None


def _extract_rsc_posts(html):
    chunks = re.findall(r'self\.__next_f\.push\(\[1,\s*"(.*?)"\s*\]\)', html, re.DOTALL)
    for chunk in chunks:
        decoded = chunk.encode("utf-8").decode("unicode_escape", errors="replace")
        if '"posts"' not in decoded:
            continue
        m = re.search(r'"posts":(\[.*?\])\s*\}', decoded, re.DOTALL)
        if m:
            return json.loads(m.group(1))
    return []


def extract_news():
    html = fetch_page(f"{BASE_URL}/news")
    posts = _extract_rsc_posts(html)
    news_posts = [p for p in posts if p.get("slug", "").startswith("news/")]
    entries = []
    for p in news_posts:
        title = p.get("title", "")
        slug = p.get("slug", "")
        href = p.get("href", "") or f"/{slug}"
        url = f"{BASE_URL}{href}"
        pub = _parse_date(p.get("date", "")) or datetime.now(timezone.utc).isoformat()
        category = p.get("categoryLabel", "") or p.get("category", "")
        summary = (p.get("excerpt") or "")[:300]
        item_id = hashlib.md5(f"runway_news_{slug}".encode()).hexdigest()
        entries.append(compact({
            "id": item_id, "source": "runway", "type": "news",
            "title": title, "url": url, "summary": summary,
            "published_date": pub,
            "categories": [category] if category else [],
            "organization": "Runway",
        }))
    return entries


def extract_research():
    html = fetch_page(f"{BASE_URL}/research/publications")
    chunks = re.findall(r'self\.__next_f\.push\(\[1,\s*"(.*?)"\s*\]\)', html, re.DOTALL)
    publications = []
    for chunk in chunks:
        decoded = chunk.encode("utf-8").decode("unicode_escape", errors="replace")
        date_match = re.search(r'rw-bodycopy3 text-darkGrayAlt mb-3[^}]*"children":"([^"]+)"', decoded)
        if not date_match or not re.match(r"^[A-Z][a-z]+ \d{1,2}, \d{4}$", date_match.group(1)):
            continue
        date_str = date_match.group(1)
        title_match = re.search(r'rw-h5 mb-2[^}]*"children":"([^"]+)"', decoded)
        title = title_match.group(1) if title_match else ""
        authors_match = re.search(r'rw-bodycopy3 text-darkGrayAlt mb-1[^}]*"children":"([^"]+)"', decoded)
        authors = authors_match.group(1) if authors_match else ""
        link = ""
        for hm in re.finditer(r'"href":"(https?://[^"]+)"', decoded):
            if "arxiv.org" in hm.group(1) or "/research/" in hm.group(1):
                link = hm.group(1); break

        pub = _parse_date(date_str) or datetime.now(timezone.utc).isoformat()
        item_id = hashlib.md5(f"runway_research_{title}_{date_str}".encode()).hexdigest()
        publications.append(compact({
            "id": item_id, "source": "runway", "type": "research",
            "title": title, "url": link or f"{BASE_URL}/research/publications",
            "summary": f"Authors: {authors}" if authors else "",
            "published_date": pub, "organization": "Runway",
        }))
    return publications


def main():
    config = load_feeds_config(ORG_KEY)
    favicon = config.get("favicon")
    for page_key, page in config["pages"].items():
        if page_key == "news":
            entries = extract_news()
        elif page_key == "research":
            entries = extract_research()
        else:
            continue
        if not entries:
            logging.warning("No entries for %s", page_key)
            continue
        entries.sort(key=lambda x: x.get("published_date", ""), reverse=True)
        write_atom_feed(FEEDS_DIR / page["output_file"], entries,
                        feed_title=page["label"], feed_link=page["url"],
                        feed_icon=favicon)

if __name__ == "__main__":
    main()
