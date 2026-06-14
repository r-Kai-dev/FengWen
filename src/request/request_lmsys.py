"""Fetch LMSYS blog posts from Next.js RSC payload.

Output to feeds/:
  - lmsys_blog.xml
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

ORG_KEY = "lmsys"
BASE_URL = "https://lmsys.org"


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


def parse_date(date_str: str) -> str | None:
    """Parse date strings to ISO format."""
    if not date_str:
        return None
    date_str = date_str.strip()
    # Strip trailing annotations like " (Updated on ...)"
    date_str = re.sub(r"\s*\([^)]*\)", "", date_str)
    for fmt in ("%B %d, %Y", "%b %d, %Y", "%Y-%m-%d"):
        try:
            return (
                datetime.strptime(date_str, fmt)
                .replace(tzinfo=timezone.utc)
                .isoformat()
            )
        except ValueError:
            continue
    return None


def extract_blog_posts(html: str) -> list[dict]:
    """Extract blog posts from RSC payload chunks.

    The LMSYS blog page has a posts array in the RSC payload with:
      slug, title, author, date, excerpt, category, type
    """
    chunks = re.findall(
        r'self\.__next_f\.push\(\[[0-9]+,\s*"(.*?)"\s*\]\)', html, re.DOTALL
    )

    for chunk in chunks:
        decoded = chunk.encode("utf-8").decode("unicode_escape", errors="replace")
        if '"posts"' not in decoded:
            continue

        # Find the posts JSON array
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
            slug = post.get("slug", "")
            excerpt = post.get("excerpt", "")
            date_str = post.get("date", "")
            author = post.get("author", "")
            category = post.get("category", "")
            post_type = post.get("type", "")

            if not title or not slug:
                continue

            url = f"{BASE_URL}/blog/{slug}"
            published_date = parse_date(date_str) or datetime.now(timezone.utc).isoformat()

            # Clean excerpt - remove HTML and truncate
            if excerpt:
                excerpt = re.sub(r'<[^>]+>', '', excerpt)
                excerpt = excerpt[:500]

            categories = []
            if category and category != "general":
                categories.append(category)
            if post_type:
                categories.append(post_type)

            entry_id = hashlib.md5(f"lmsys_blog_{slug}".encode()).hexdigest()

            entries.append(
                compact(
                    {
                        "id": entry_id,
                        "source": "lmsys",
                        "type": "blog",
                        "title": title,
                        "url": url,
                        "summary": excerpt,
                        "published_date": published_date,
                        "categories": categories,
                        "organization": "LMSYS",
                        "feed_author": author,
                    }
                )
            )

        if entries:
            return entries

    logging.warning("No posts array found in RSC payload")
    return []


def main() -> None:
    """Fetch LMSYS blog and write Atom XML feed."""
    config = load_api_config(ORG_KEY)
    blog_config = config["pages"]["blog"]

    url = f"{BASE_URL}{blog_config['endpoint']}"
    logging.info(f"Fetching LMSYS blog from {url}")
    html = fetch_page(url)

    entries = extract_blog_posts(html)
    if not entries:
        logging.error("No blog posts found")
        return

    output_file = PARSED_DIR / blog_config["output_file"]
    write_atom_feed(
        output_file,
        entries,
        feed_title="LMSYS Blog",
        feed_link=f"{BASE_URL}/blog",
        feed_icon=config.get("favicon", f"{BASE_URL}/favicon.ico"),
    )
    logging.info(f"Saved {len(entries)} entries to {output_file}")


if __name__ == "__main__":
    main()
