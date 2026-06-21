"""Fetch Groq Blog and Newsroom from Sanity CMS API."""

import hashlib
import json
import logging
import re
import urllib.parse
from datetime import datetime, timezone

from utils import (
    FEEDS_DIR, setup_logging, ensure_output_dir,
    load_feeds_config, fetch_page, compact, write_atom_feed,
)

setup_logging()
ensure_output_dir()

ORG_KEY = "groq"
BASE_URL = "https://groq.com"
SANITY_PROJECT = "chol0sk5"
SANITY_API = f"https://{SANITY_PROJECT}.api.sanity.io/v2021-06-07/data/query/production"


def fetch_json(url: str) -> dict:
    return json.loads(fetch_page(url))


def fetch_blog_posts() -> list[dict]:
    query = '*[_type=="blog"]{title,"slug":slug.current,_createdAt,"excerpt":excerpt[0].children[0].text}|order(_createdAt desc)'
    data = fetch_json(f"{SANITY_API}?query={urllib.parse.quote(query)}")
    posts = data.get("result", [])
    entries = []
    for p in posts:
        slug = p.get("slug", "")
        title = p.get("title", "")
        date_str = p.get("_createdAt", "")
        excerpt = p.get("excerpt", "")
        if not title or not slug:
            continue
        try:
            pub = datetime.fromisoformat(date_str.replace("Z", "+00:00")).isoformat()
        except (ValueError, TypeError):
            pub = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
        url = f"{BASE_URL}/blog/{slug}"
        item_id = hashlib.md5(f"groq_blog_{slug}".encode()).hexdigest()
        entries.append(compact({
            "id": item_id, "source": "groq", "type": "blog",
            "title": title, "url": url, "summary": excerpt,
            "published_date": pub, "organization": "Groq",
        }))
    return entries


def fetch_newsroom_items() -> list[dict]:
    page_html = fetch_page(f"{BASE_URL}/newsroom")
    chunks = re.findall(r'self\.__next_f\.push\(\[[0-9]+,\s*"(.*?)"\s*\]\)', page_html, re.DOTALL)
    seen_slugs = set()
    for chunk in chunks:
        decoded = chunk.encode("utf-8").decode("unicode_escape", errors="replace")
        for s in re.findall(r'/newsroom/([a-z][a-z0-9-]+)"', decoded):
            if s != "newsroom":
                seen_slugs.add(s)

    if not seen_slugs:
        return []

    slug_list = '","'.join(seen_slugs)
    query = f'*[slug.current in ["{slug_list}"]]{{title,"slug":slug.current,_createdAt}}'
    data = fetch_json(f"{SANITY_API}?query={urllib.parse.quote(query)}")
    post_map = {p["slug"]: p for p in data.get("result", []) if p.get("slug")}

    entries = []
    for slug in seen_slugs:
        p = post_map.get(slug)
        if not p:
            continue
        title = p.get("title", "")
        date_str = p.get("_createdAt", "")
        if not title:
            continue
        try:
            pub = datetime.fromisoformat(date_str.replace("Z", "+00:00")).isoformat()
        except (ValueError, TypeError):
            pub = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
        url = f"{BASE_URL}/newsroom/{slug}"
        item_id = hashlib.md5(f"groq_newsroom_{slug}".encode()).hexdigest()
        entries.append(compact({
            "id": item_id, "source": "groq", "type": "news",
            "title": title, "url": url, "published_date": pub,
            "organization": "Groq",
        }))
    return entries


def main():
    config = load_feeds_config(ORG_KEY)
    favicon = config.get("favicon")
    for page_key, page in config["pages"].items():
        if page_key == "blog":
            entries = fetch_blog_posts()
        elif page_key == "newsroom":
            entries = fetch_newsroom_items()
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
