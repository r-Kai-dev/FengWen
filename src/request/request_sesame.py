"""Fetch Sesame blog posts from __NEXT_DATA__ JSON embedded in the page.

The blog listing page has __NEXT_DATA__ with:
  pageProps.pageData.posts - array of {slug, title, excerpt, publishedDate, ...}

Output to feeds/:
  - sesame_blog.xml
"""

import hashlib
import json
import logging
import re
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

ORG_KEY = "sesame"
BASE_URL = "https://www.sesame.com"


def fetch_page(url: str) -> str:
    """Fetch an HTML page."""
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


def extract_blog_posts(html: str) -> list[dict]:
    """Extract blog posts from __NEXT_DATA__ JSON."""
    m = re.search(
        r'<script id="__NEXT_DATA__"[^>]*type="application/json"[^>]*>(.*?)</script>',
        html,
        re.DOTALL,
    )
    if not m:
        logging.error("__NEXT_DATA__ script tag not found")
        return []

    try:
        data = json.loads(m.group(1))
    except json.JSONDecodeError as exc:
        logging.error(f"Failed to parse __NEXT_DATA__ JSON: {exc}")
        return []

    posts = data.get("props", {}).get("pageProps", {}).get("pageData", {}).get("posts", [])
    if not posts:
        logging.error("No posts found in page props")
        return []

    entries = []
    for post in posts:
        slug = post.get("slug", "")
        title = post.get("title", "")
        excerpt = post.get("excerpt", "")
        date_str = post.get("publishedDate", "")
        featured = post.get("featured", False)

        if not title or not slug:
            continue

        url = f"{BASE_URL}/blog/{slug}"

        published_date = date_str
        if published_date:
            try:
                dt = datetime.strptime(published_date, "%Y-%m-%d")
                published_date = dt.replace(tzinfo=timezone.utc).isoformat()
            except ValueError:
                pass

        entry_id = hashlib.md5(f"sesame_blog_{slug}".encode()).hexdigest()

        entries.append(
            compact(
                {
                    "id": entry_id,
                    "source": "sesame",
                    "type": "blog",
                    "title": title,
                    "url": url,
                    "summary": excerpt,
                    "published_date": published_date,
                    "organization": "Sesame",
                }
            )
        )

    return entries


def main() -> None:
    """Fetch Sesame blog and write Atom XML feed."""
    config = load_api_config(ORG_KEY)
    blog_config = config["pages"]["blog"]

    url = f"{BASE_URL}{blog_config['endpoint']}"
    logging.info(f"Fetching Sesame blog from {url}")
    html = fetch_page(url)

    entries = extract_blog_posts(html)
    if not entries:
        logging.error("No blog posts found")
        return

    output_file = PARSED_DIR / blog_config["output_file"]
    write_atom_feed(
        output_file,
        entries,
        feed_title="Sesame Blog",
        feed_link=f"{BASE_URL}/blog",
        feed_icon=config.get("favicon", f"{BASE_URL}/favicon.svg"),
    )
    logging.info(f"Saved {len(entries)} entries to {output_file}")


if __name__ == "__main__":
    main()
