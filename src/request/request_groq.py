"""Fetch Groq Blog and Newsroom from Sanity CMS API.

Groq's blog and newsroom are backed by Sanity CMS. The public query endpoint is open:
  https://chol0sk5.api.sanity.io/v2021-06-07/data/query/production?query=...

Output to feeds/:
  - groq_blog.xml
  - groq_newsroom.xml
"""

import hashlib
import json
import logging
import urllib.parse
import urllib.request
from datetime import datetime, timezone

from common import (
    PARSED_DIR,
    ensure_output_dir,
    load_api_config,
    setup_logging,
)
from feed_util import compact, write_atom_feed

setup_logging()
ensure_output_dir()

ORG_KEY = "groq"
BASE_URL = "https://groq.com"
SANITY_PROJECT = "chol0sk5"
SANITY_API = f"https://{SANITY_PROJECT}.api.sanity.io/v2021-06-07/data/query/production"


def fetch_json(url: str) -> dict:
    """Fetch a JSON endpoint."""
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": (
                "Mozilla/5.0 (X11; Linux x86_64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            ),
        },
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode("utf-8"))


def fetch_blog_posts() -> list[dict]:
    """Fetch all blog posts from Sanity."""
    query = '*[_type=="blog"]{title,"slug":slug.current,_createdAt,"excerpt":excerpt[0].children[0].text}|order(_createdAt desc)'
    url = f"{SANITY_API}?query={urllib.parse.quote(query)}"
    data = fetch_json(url)
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
            dt = datetime.fromisoformat(date_str.replace("Z", "+00:00"))
            published_date = dt.isoformat()
        except (ValueError, TypeError):
            published_date = datetime.now(timezone.utc).replace(microsecond=0).isoformat()

        url = f"{BASE_URL}/blog/{slug}"
        entry_id = hashlib.md5(f"groq_blog_{slug}".encode()).hexdigest()

        entries.append(
            compact(
                {
                    "id": entry_id,
                    "source": "groq",
                    "type": "blog",
                    "title": title,
                    "url": url,
                    "summary": excerpt,
                    "published_date": published_date,
                    "organization": "Groq",
                }
            )
        )

    return entries


def fetch_newsroom_items() -> list[dict]:
    """Fetch newsroom items.

    The newsroom is a curated list of blog posts. The listing page HTML
    contains the slugs in its RSC payload. We scrape those slugs from the
    page and look up their metadata from Sanity.
    """
    # Fetch the newsroom page to extract slugs
    import re
    page_html = fetch_page_html(f"{BASE_URL}/newsroom")

    # RSC chunks contain blog slugs displayed on the newsroom page
    chunks = re.findall(
        r'self\.__next_f\.push\(\[[0-9]+,\s*"(.*?)"\s*\]\)',
        page_html, re.DOTALL,
    )

    seen_slugs = set()
    for chunk in chunks:
        decoded = chunk.encode("utf-8").decode("unicode_escape", errors="replace")
        slugs = re.findall(r'/newsroom/([a-z][a-z0-9-]+)"', decoded)
        for s in slugs:
            if s != "newsroom":
                seen_slugs.add(s)

    if not seen_slugs:
        logging.warning("No newsroom slugs found in RSC")
        return []

    # Bulk query Sanity for these slugs
    slug_list = '","'.join(seen_slugs)
    query = (
        f'*[slug.current in ["{slug_list}"]]'
        '{title,"slug":slug.current,_createdAt}'
    )
    url = f"{SANITY_API}?query={urllib.parse.quote(query)}"
    data = fetch_json(url)
    posts = data.get("result", [])

    # Build a lookup
    post_map = {p["slug"]: p for p in posts if p.get("slug")}

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
            dt = datetime.fromisoformat(date_str.replace("Z", "+00:00"))
            published_date = dt.isoformat()
        except (ValueError, TypeError):
            published_date = datetime.now(timezone.utc).replace(microsecond=0).isoformat()

        url = f"{BASE_URL}/newsroom/{slug}"
        entry_id = hashlib.md5(f"groq_newsroom_{slug}".encode()).hexdigest()

        entries.append(
            compact(
                {
                    "id": entry_id,
                    "source": "groq",
                    "type": "news",
                    "title": title,
                    "url": url,
                    "summary": "",
                    "published_date": published_date,
                    "organization": "Groq",
                }
            )
        )

    return entries


def fetch_page_html(url: str) -> str:
    """Fetch an HTML page as text."""
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": (
                "Mozilla/5.0 (X11; Linux x86_64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            ),
        },
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        return resp.read().decode("utf-8")


def main():
    config = load_api_config(ORG_KEY)
    pages = config["pages"]
    favicon = config.get("favicon") or f"{BASE_URL}/favicon.ico"

    # Blog
    if "blog" in pages:
        entries = fetch_blog_posts()
        if entries:
            write_atom_feed(
                PARSED_DIR / pages["blog"]["output_file"],
                entries,
                feed_title="Groq Blog",
                feed_link=f"{BASE_URL}/blog",
                feed_icon=favicon,
            )
            logging.info(f"Saved {len(entries)} entries to {pages['blog']['output_file']}")

    # Newsroom
    if "newsroom" in pages:
        entries = fetch_newsroom_items()
        if entries:
            write_atom_feed(
                PARSED_DIR / pages["newsroom"]["output_file"],
                entries,
                feed_title="Groq Newsroom",
                feed_link=f"{BASE_URL}/newsroom",
                feed_icon=favicon,
            )
            logging.info(f"Saved {len(entries)} entries to {pages['newsroom']['output_file']}")


if __name__ == "__main__":
    main()
