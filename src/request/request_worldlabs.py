"""Fetch World Labs blog posts.

Output to feeds/:
  - worldlabs_blog.xml

The World Labs blog page is server-rendered. Article data is in
visible DOM elements: each blog card link contains date, author, title,
description, and "Read More →" all as concatenated text.
"""

import hashlib
import logging
import re
import urllib.request
from datetime import datetime, timezone

from bs4 import BeautifulSoup

from common import (
    PARSED_DIR,
    ensure_output_dir,
    load_api_config,
    setup_logging,
)
from feed_util import compact, write_atom_feed

setup_logging()
ensure_output_dir()

ORG_KEY = "worldlabs"
BASE_URL = "https://www.worldlabs.ai"


def fetch_page(url: str) -> str:
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
    if not date_str:
        return None
    date_str = date_str.strip()
    for fmt in ("%B %d, %Y", "%b %d, %Y"):
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
    """Extract blog posts from the server-rendered HTML body.

    Each article card is an <a> with href="/blog/..." whose text nodes
    contain date, author, title, description, and "Read More →".
    """
    soup = BeautifulSoup(html, "html.parser")
    posts = []
    seen = set()

    date_re = re.compile(r"^([A-Z][a-z]+ \d{1,2}, \d{4})")

    for a in soup.select('a[href*="/blog/"]'):
        href = a.get("href", "")
        if not href or "/blog/" not in href or href in seen:
            continue

        text = a.get_text(separator="|", strip=True)
        if not text or "Read More" not in text:
            continue

        seen.add(href)

        # Split on "|" to separate text nodes
        parts = [p.strip() for p in text.split("|") if p.strip()]
        if len(parts) < 3:
            continue

        # Find date in parts
        date_str = ""
        date_idx = -1
        for i, p in enumerate(parts):
            m = date_re.match(p)
            if m:
                date_str = m.group(1)
                date_idx = i
                break
        if not date_str or date_idx < 0:
            continue

        # Remaining parts after date
        remaining_parts = parts[date_idx + 1:]

        # Find author and title
        author = ""
        title_parts = []
        if remaining_parts and remaining_parts[0] in ("World Labs team", "Dr. Fei-Fei Li"):
            author = remaining_parts[0]
            remaining_parts = remaining_parts[1:]

        # Title + description are before "Read More"
        read_more_idx = -1
        for i, p in enumerate(remaining_parts):
            if "Read More" in p:
                read_more_idx = i
                break
        if read_more_idx == -1:
            continue

        content_parts = remaining_parts[:read_more_idx]
        if not content_parts:
            continue

        title = content_parts[0]
        description = " ".join(content_parts[1:]) if len(content_parts) > 1 else ""

        if not title:
            continue

        slug = href.strip("/").split("/")[-1]
        url = f"{BASE_URL}{href}"
        published_date = parse_date(date_str) or datetime.now(timezone.utc).isoformat()
        entry_id = hashlib.md5(f"worldlabs_blog_{slug}".encode()).hexdigest()

        posts.append(
            compact(
                {
                    "id": entry_id,
                    "source": "worldlabs",
                    "type": "blog",
                    "title": title,
                    "url": url,
                    "summary": description,
                    "published_date": published_date,
                    "feed_author": author,
                    "organization": "World Labs",
                }
            )
        )

    return posts


def main() -> None:
    config = load_api_config(ORG_KEY)
    blog_config = config["pages"]["blog"]

    url = f"{BASE_URL}{blog_config['endpoint']}"
    logging.info(f"Fetching World Labs blog from {url}")
    html = fetch_page(url)

    entries = extract_blog_posts(html)
    if not entries:
        logging.error("No blog posts found")
        return

    output_file = PARSED_DIR / blog_config["output_file"]
    write_atom_feed(
        output_file,
        entries,
        feed_title="World Labs Blog",
        feed_link=f"{BASE_URL}/blog",
        feed_icon=config.get("favicon", f"{BASE_URL}/favicon.ico"),
    )
    logging.info(f"Saved {len(entries)} entries to {output_file}")


if __name__ == "__main__":
    main()
