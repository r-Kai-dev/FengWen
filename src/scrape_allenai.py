"""Scrape Ai2 (Allen Institute for AI) news and research from RSC payloads."""

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
ORG_KEY = "allenai"
BASE_URL = "https://allenai.org"


def _parse_month_year(date_str):
    if not date_str:
        return datetime.now(timezone.utc).isoformat()
    for fmt in ("%B %Y", "%b %Y"):
        try:
            return datetime.strptime(date_str.strip(), fmt).replace(tzinfo=timezone.utc).isoformat()
        except ValueError:
            continue
    return datetime.now(timezone.utc).isoformat()


def _parse_full_date(date_str):
    if not date_str:
        return datetime.now(timezone.utc).isoformat()
    for fmt in ("%B %d, %Y", "%b %d, %Y"):
        try:
            return datetime.strptime(date_str.strip(), fmt).replace(tzinfo=timezone.utc).isoformat()
        except ValueError:
            continue
    return datetime.now(timezone.utc).isoformat()


def _rsc_data(html):
    chunks = re.findall(r'self\.__next_f\.push\(\[1,\s*"(.*?)"\s*\]\)', html, re.DOTALL)
    all_data = ""
    for chunk in chunks:
        all_data += chunk.encode("utf-8").decode("unicode_escape", errors="replace")
    return all_data


def extract_news(html):
    all_data = _rsc_data(html)
    title_matches = list(re.finditer(
        r'threeUpCardHeading[^}]*children":\[\[.*?"children":"([^"]+)"\}\]'
        r'.*?\]\],"([^"]+)"\]\}\]', all_data,
    ))
    cards = []
    for m in title_matches:
        cards.append({"date": _parse_month_year(m.group(1)), "title": m.group(2), "slug": "", "excerpt": ""})

    slug_matches = list(re.finditer(r'"href":"(/blog/[a-zA-Z0-9_-]+)"', all_data))
    slugs = list(dict.fromkeys(m.group(1).replace("/blog/", "") for m in slug_matches))

    skip_prefixes = ["We couldn't find", "Questions about our work"]
    excerpt_matches = list(re.finditer(r'"p","p-0",\{"children":"([^"]{10,})"\}\]', all_data))
    excerpts = [m.group(1) for m in excerpt_matches if not any(m.group(1).startswith(p) for p in skip_prefixes)]

    for i, card in enumerate(cards):
        if i < len(slugs):
            card["slug"] = slugs[i]
        if i < len(excerpts):
            card["excerpt"] = excerpts[i]

    entries = []
    seen = set()
    for card in cards:
        slug = card["slug"]
        if not slug or slug in seen:
            continue
        seen.add(slug)
        url = f"{BASE_URL}/blog/{slug}"
        item_id = hashlib.md5(f"allenai_news_{slug}".encode()).hexdigest()
        entries.append(compact({
            "id": item_id, "source": "allenai", "type": "news",
            "title": card["title"], "url": url,
            "summary": card["excerpt"], "published_date": card["date"],
            "organization": "Ai2",
        }))
    return entries


def extract_research(html):
    all_data = _rsc_data(html)
    entries = []
    seen = set()
    for date_match in re.finditer(r'"children":"([A-Z][a-z]+ \d{1,2}, \d{4})"\}\]', all_data):
        published = _parse_full_date(date_match.group(1))
        pos = date_match.end()
        nearby = all_data[pos:pos + 1200]
        link_match = re.search(r'"href":"(/blog/[a-zA-Z0-9_-]+)"', nearby)
        if not link_match:
            continue
        slug = link_match.group(1).replace("/blog/", "")
        if slug in seen:
            continue
        after_link = nearby[link_match.end():]
        title_match = re.search(r'"h2",null,\{"className":"[^"]+","children":"([^"]+)"', after_link)
        if not title_match:
            continue
        title = title_match.group(1)
        seen.add(slug)
        url = f"{BASE_URL}/blog/{slug}"
        item_id = hashlib.md5(f"allenai_research_{slug}".encode()).hexdigest()
        entries.append(compact({
            "id": item_id, "source": "allenai", "type": "research",
            "title": title, "url": url, "published_date": published,
            "organization": "Ai2",
        }))
    return entries


def main():
    config = load_feeds_config(ORG_KEY)
    favicon = config.get("favicon")
    for page_key, page in config["pages"].items():
        logging.info("Fetching %s: %s", page["label"], page["url"])
        html = fetch_page(page["url"])
        entries = extract_news(html) if page_key == "news" else extract_research(html)
        if not entries:
            logging.warning("No entries for %s", page_key)
            continue
        entries.sort(key=lambda x: x.get("published_date", ""), reverse=True)
        write_atom_feed(FEEDS_DIR / page["output_file"], entries,
                        feed_title=page["label"], feed_link=page["url"],
                        feed_icon=favicon)

if __name__ == "__main__":
    main()
