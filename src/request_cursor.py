"""Fetch Cursor blog posts from the Next.js RSC endpoint."""

import asyncio
import hashlib
import json
import logging
import re

from curl_cffi.requests import AsyncSession

from utils import (
    FEEDS_DIR, setup_logging, ensure_output_dir,
    load_feeds_config, fetch_with_retry, compact, write_atom_feed,
)

setup_logging()
ensure_output_dir()
ORG_KEY = "cursor"

RSC_HEADERS = {
    "RSC": "1",
    "Next-Router-State-Tree": "%5B%22%22%2C%22%2Fblog%22%2C%22page%22%5D",
}


def parse_rsc_response(text: str) -> list[dict]:
    """Parse Next.js streaming RSC response to extract blog posts.

    The format is newline-separated ``hex_key:json_value`` lines.
    We locate the line whose value contains ``"posts":[`` and extract
    the posts array via bracket-depth counting.
    """
    lines = text.strip().split("\n")
    for line in lines:
        if ":" not in line:
            continue
        key, _, val = line.partition(":")
        if not re.match(r"^[0-9a-f]+$", key):
            continue
        if '"posts":[' not in val:
            continue
        # Locate and extract the posts JSON array
        start = val.index('"posts":[') + len('"posts":')
        depth = 0
        end = start
        for i, c in enumerate(val[start:], start):
            if c == "[":
                depth += 1
            elif c == "]":
                depth -= 1
                if depth == 0:
                    end = i + 1
                    break
        return json.loads(val[start:end])

    return []


def build_entry(post: dict, base_url: str) -> dict | None:
    """Convert a Cursor blog post dict to an Atom entry."""
    slug = post.get("slug", "")
    title = post.get("title", "")
    href = post.get("href", "")
    date = post.get("date", "")
    category = post.get("categoryValue", "")
    author = post.get("authorText", "")
    read_time = post.get("readingTimeText", "")
    is_external = post.get("isExternal", False)
    ext_name = post.get("externalPublicationName", "")

    # Resolve URL: external links use their full URL, internal use base_url + path
    if href.startswith("http"):
        url = href
    else:
        url = f"{base_url}{href}"

    entry_id = hashlib.md5(f"{ORG_KEY}_{slug}".encode()).hexdigest()

    summary_parts = []
    if is_external:
        if ext_name:
            summary_parts.append(f"Published on {ext_name}")
        else:
            summary_parts.append("External link")
    else:
        if author:
            summary_parts.append(f"By {author}")
        if read_time:
            summary_parts.append(f"{read_time} read")

    return compact({
        "title": title,
        "url": url,
        "id": entry_id,
        "published_date": date,
        "summary": " · ".join(summary_parts) if summary_parts else None,
        "categories": [category] if category else [],
        "organization": "Cursor",
    })


async def main():
    config = load_feeds_config(ORG_KEY)
    favicon = config.get("favicon")
    base_url = config["base_url"]

    for page_key, page in config["pages"].items():
        logging.info("Fetching %s: %s", page["label"], page["url"])
        async with AsyncSession() as session:
            response = await fetch_with_retry(
                session, page["url"],
                impersonate="chrome120", timeout=30,
                headers=RSC_HEADERS,
            )
            raw_posts = parse_rsc_response(response.text)

        if not raw_posts:
            logging.warning("No posts found for %s", page_key)
            continue

        entries = []
        for post in raw_posts:
            entry = build_entry(post, base_url)
            if entry:
                entries.append(entry)

        logging.info("Parsed %d entries for %s", len(entries), page_key)

        if entries:
            write_atom_feed(FEEDS_DIR / page["output_file"], entries,
                            feed_title=page["label"],
                            feed_link=page.get("feed_link", page["url"]),
                            feed_icon=favicon)


if __name__ == "__main__":
    asyncio.run(main())
