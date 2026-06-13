"""Fetch Hume AI blog posts from Next.js RSC payload.

The page at https://www.hume.ai/blog is built with Next.js React Server
Components.  All blog post metadata (title, slug, date, category, excerpt)
is embedded inside a JSON ``"posts":[...]`` array in one of the RSC payload
chunks (``self.__next_f.push([1,"..."])``).

We decode all chunks, locate the ``"posts"`` array with bracket matching,
parse it as JSON, then generate a single Atom feed for all blog posts.
"""

import hashlib
import json
import logging
import re
import urllib.request

from common import (
    PARSED_DIR,
    ensure_output_dir,
    load_api_config,
    setup_logging,
)
from feed_util import compact, write_atom_feed

setup_logging()
ensure_output_dir()

ORG_KEY = "hume"
BASE_URL = "https://www.hume.ai"
BLOG_URL = f"{BASE_URL}/blog"


def fetch_page(url: str) -> str:
    """Fetch an HTML page and return the raw text."""
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


def _parse_date(iso_str: str) -> str:
    """Parse ISO date string to Atom-compatible ISO format."""
    from datetime import datetime, timezone

    if not iso_str:
        return datetime.now(timezone.utc).isoformat()
    try:
        dt = datetime.fromisoformat(iso_str.replace("Z", "+00:00"))
        return dt.isoformat()
    except (ValueError, TypeError):
        return datetime.now(timezone.utc).isoformat()


def _extract_posts_array(html: str) -> list[dict]:
    """Extract and parse the ``"posts"`` JSON array from RSC payload chunks.

    Returns a list of post dicts (each with keys like ``_id``, ``title``,
    ``category``, ``publishedAt``, ``slug``, ``excerpt``).
    """
    # Collect all RSC payload chunks
    chunks = re.findall(
        r'self\.__next_f\.push\(\[1,\s*"(.*?)"\s*\]\)', html, re.DOTALL
    )

    # Decode and concatenate all chunks
    all_data = ""
    for chunk in chunks:
        decoded = chunk.encode("utf-8").decode("unicode_escape", errors="replace")
        all_data += decoded

    # Locate the "posts" array
    idx = all_data.find('"posts":[')
    if idx == -1:
        logging.error('Could not find "posts":[] in RSC payload')
        return []

    array_start = idx + 8  # skip past '"posts":'

    # Match the outer-most array bracket
    depth = 0
    in_str = False
    escaped = False
    array_end = -1
    for i, ch in enumerate(all_data[array_start:], array_start):
        if escaped:
            escaped = False
            continue
        if ch == "\\" and in_str:
            escaped = True
            continue
        if ch == '"':
            in_str = not in_str
            continue
        if in_str:
            continue
        if ch == "[":
            depth += 1
        elif ch == "]":
            depth -= 1
            if depth == 0:
                array_end = i
                break

    if array_end == -1:
        logging.error("Could not find closing bracket for posts array")
        return []

    try:
        posts = json.loads(all_data[array_start : array_end + 1])
    except json.JSONDecodeError as e:
        logging.error("Failed to parse posts JSON array: %s", e)
        return []

    if not isinstance(posts, list):
        logging.error("posts is not a JSON array")
        return []

    return posts


def post_to_entry(post: dict) -> dict | None:
    """Convert a JSON post dict to an Atom entry dict.

    Returns ``None`` if the post is missing essential fields.
    """
    # Extract slug for URL construction
    slug_obj = post.get("slug", {})
    if isinstance(slug_obj, dict):
        slug = slug_obj.get("current", "")
    else:
        slug = str(slug_obj) if slug_obj else ""

    if not slug:
        return None

    url = f"{BASE_URL}/blog/{slug}"
    entry_id = hashlib.md5(f"hume_{slug}".encode()).hexdigest()

    title = post.get("title", slug)
    category = post.get("category", "")
    published_at = _parse_date(post.get("publishedAt", ""))
    excerpt = post.get("excerpt", "")

    return compact(
        {
            "id": entry_id,
            "source": "hume",
            "type": "blog",
            "title": title,
            "url": url,
            "published_date": published_at,
            "summary": excerpt,
            "categories": [category] if category else [],
            "organization": "Hume AI",
        }
    )


def main() -> None:
    """Fetch Hume AI blog and write the Atom feed."""
    config = load_api_config(ORG_KEY)
    page_config = config["pages"]["blog"]

    html = fetch_page(BLOG_URL)
    posts = _extract_posts_array(html)

    if not posts:
        logging.error("No posts extracted from Hume AI blog")
        return

    # Filter out posts that lack a slug (shouldn't happen, but be safe)
    entries = [post_to_entry(p) for p in posts if p.get("slug")]

    if not entries:
        logging.error("No valid entries after filtering")
        return

    favicon = config.get("favicon", f"{BASE_URL}/favicon.ico")
    output_file = PARSED_DIR / page_config["output_file"]

    write_atom_feed(
        output_file,
        entries,
        feed_title="Hume AI Blog",
        feed_link=BLOG_URL,
        feed_icon=favicon,
    )

    logging.info("Fetched %d blog posts from Hume AI", len(entries))


if __name__ == "__main__":
    main()
