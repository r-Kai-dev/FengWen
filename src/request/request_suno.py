"""Fetch Suno blog posts from Next.js RSC payload.

The blog page embeds post data in a self.__next_f.push chunk containing
a JSON object with a "posts" array. Each post has title, slug, excerpt,
publishedAt, author, tags, etc.

Output to feeds/:
  - suno_blog.xml
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

ORG_KEY = "suno"
BASE_URL = "https://suno.com"


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
    """Extract blog posts from RSC payload chunks."""
    chunks = re.findall(
        r'self\.__next_f\.push\(\[[0-9]+,\s*"(.*?)"\s*\]\)', html, re.DOTALL
    )

    for chunk in chunks:
        decoded = chunk.encode("utf-8").decode("unicode_escape", errors="replace")
        if '"posts"' not in decoded:
            continue

        # Find "posts":[...] pattern in the decoded RSC
        m = re.search(r'"posts":\s*(\[.*?\])\s*\}', decoded, re.DOTALL)
        if not m:
            continue
        try:
            posts = json.loads(m.group(1))
        except json.JSONDecodeError as exc:
            logging.warning(f"Failed to decode posts JSON: {exc}")
            continue

        entries = []
        for post in posts:
            title = post.get("title", "")
            slug = post.get("slug", {})
            if isinstance(slug, dict):
                slug = slug.get("current", "")
            excerpt = post.get("excerpt", "")
            date_str = post.get("publishedAt", "")
            author = post.get("author", "")
            tags = post.get("tags", [])

            if not title or not slug:
                continue

            url = f"{BASE_URL}/blog/{slug}"

            published_date = date_str
            if published_date:
                try:
                    dt = datetime.fromisoformat(published_date.replace("Z", "+00:00"))
                    published_date = dt.isoformat()
                except (ValueError, TypeError):
                    pass

            entry_id = hashlib.md5(f"suno_blog_{slug}".encode()).hexdigest()

            entries.append(
                compact(
                    {
                        "id": entry_id,
                        "source": "suno",
                        "type": "blog",
                        "title": title,
                        "url": url,
                        "summary": excerpt,
                        "published_date": published_date,
                        "categories": tags or [],
                        "organization": "Suno",
                        "feed_author": author,
                    }
                )
            )

        return entries

    logging.error("No posts array found in RSC payload")
    return []


def main() -> None:
    """Fetch Suno blog and write Atom XML feed."""
    config = load_api_config(ORG_KEY)
    blog_config = config["pages"]["blog"]

    url = f"{BASE_URL}{blog_config['endpoint']}"
    logging.info(f"Fetching Suno blog from {url}")
    html = fetch_page(url)

    entries = extract_blog_posts(html)
    if not entries:
        logging.error("No blog posts found")
        return

    output_file = PARSED_DIR / blog_config["output_file"]
    write_atom_feed(
        output_file,
        entries,
        feed_title="Suno Blog",
        feed_link=f"{BASE_URL}/blog",
        feed_icon=config.get("favicon", f"{BASE_URL}/favicon.ico"),
    )
    logging.info(f"Saved {len(entries)} entries to {output_file}")


if __name__ == "__main__":
    main()
