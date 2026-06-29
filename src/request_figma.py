"""Fetch Figma blog posts from the Next.js RSC endpoint."""

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
ORG_KEY = "figma"

RSC_HEADERS = {
    "RSC": "1",
    "Next-Router-State-Tree": "%5B%22%22%2C%22%2Fblog%22%2C%22page%22%5D",
}


def _extract_plain_text(blocks: list) -> str:
    """Extract plain text from Sanity portable text blocks."""
    parts = []
    for block in blocks:
        if not isinstance(block, dict):
            continue
        children = block.get("children", [])
        for child in children:
            if isinstance(child, dict) and child.get("_type") == "span":
                parts.append(child.get("text", ""))
    return "".join(parts)


def parse_rsc_posts(text: str) -> list[dict]:
    """Parse Next.js streaming RSC response and extract blog posts.

    The response is newline-separated ``hex_key:json_value`` lines.
    We locate ``figmaBlogPostCard`` entries and extract the nested
    ``post`` object via bracket-depth counting.
    """
    posts = []
    seen_slugs = set()
    for match in re.finditer(r'"_type":"figmaBlogPostCard"', text):
        start = match.start()
        # Find the following "post":{...} object
        post_match = re.search(r'"post":\{', text[start:start + 5000])
        if not post_match:
            continue
        post_start = start + post_match.start() + len('"post":')
        # Bracket-depth parse the inner post JSON object
        depth = 0
        end = post_start
        for i in range(post_start, min(post_start + 50000, len(text))):
            if text[i] == "{":
                depth += 1
            elif text[i] == "}":
                depth -= 1
                if depth == 0:
                    end = i + 1
                    break
        if end == post_start:
            continue
        try:
            post = json.loads(text[post_start:end])
        except json.JSONDecodeError:
            continue
        slug = post.get("slug", {}).get("current", "")
        if not slug or slug in seen_slugs:
            continue
        seen_slugs.add(slug)
        posts.append(post)
    return posts


def build_entry(post: dict, base_url: str) -> dict | None:
    """Convert a Figma blog post dict to an Atom entry."""
    slug = post.get("slug", {}).get("current", "")
    title = post.get("title", "")
    if not slug or not title:
        return None

    url = f"{base_url}{slug}"
    entry_id = hashlib.md5(f"{ORG_KEY}_{slug}".encode()).hexdigest()

    # Publication date
    pub_date = post.get("publicationDate", "")

    # Extract category from labels
    labels = post.get("labels", {})
    category = ""
    if isinstance(labels, dict):
        cat_obj = labels.get("category", {})
        if isinstance(cat_obj, dict):
            category = cat_obj.get("name", "")

    # Extract plain text from lede (Sanity portable text)
    lede = post.get("lede", [])
    summary = _extract_plain_text(lede) if isinstance(lede, list) else ""

    # Extract author names
    authors = post.get("authors", [])
    author_names = []
    if isinstance(authors, list):
        for a in authors:
            if isinstance(a, dict):
                name = a.get("name", "")
                if name:
                    author_names.append(name)
    organization = ", ".join(author_names) if author_names else "Figma"

    return compact({
        "title": title,
        "url": url,
        "id": entry_id,
        "published_date": pub_date,
        "summary": summary or None,
        "categories": [category] if category else [],
        "organization": organization,
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
            raw_posts = parse_rsc_posts(response.text)

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
