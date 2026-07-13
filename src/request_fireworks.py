"""Fetch Fireworks AI blog posts from Sanity CDN API."""

import asyncio
import hashlib
import logging
from datetime import datetime, timezone
from urllib.parse import quote, urlencode

from curl_cffi.requests import AsyncSession

from utils import (
    FEEDS_DIR, setup_logging, ensure_output_dir,
    load_feeds_config, fetch_with_retry, write_atom_feed,
)

setup_logging()
ensure_output_dir()
ORG_KEY = "fireworks"

PROJECT_ID = "pv37i0yn"
DATASET = "production"
API_VERSION = "v2022-03-07"
SANITY_CDN = f"https://{PROJECT_ID}.apicdn.sanity.io/{API_VERSION}/data/query/{DATASET}"

QUERY = """*[_type == "blog"] | order(publishedDate desc)[0...50] {
  postTitle,
  publishedDate,
  "excerpt_text": excerpt[0].children[0].text,
  "slug": seo.slug.current,
  "image_url": featuredImage.asset->url
}"""


def _parse_date(date_str):
    """Parse publishedDate which may be YYYY-MM-DD or ISO-8601."""
    if not date_str:
        return datetime.now(timezone.utc).isoformat()
    formats = [
        "%Y-%m-%dT%H:%M:%S.%fZ",
        "%Y-%m-%dT%H:%M:%SZ",
        "%Y-%m-%dT%H:%M:%S",
        "%Y-%m-%d",
    ]
    for fmt in formats:
        try:
            return datetime.strptime(date_str, fmt).replace(
                tzinfo=timezone.utc
            ).isoformat()
        except ValueError:
            continue
    return datetime.now(timezone.utc).isoformat()


def _build_entry(post):
    title = post.get("postTitle", "").strip()
    slug = post.get("slug", "")
    excerpt = post.get("excerpt_text", "")
    image_url = post.get("image_url", "")

    if not title or not slug:
        return None

    url = f"https://fireworks.ai/blog/{slug}"
    item_id = hashlib.md5(f"{ORG_KEY}_{slug}_{title}".encode()).hexdigest()
    published_date = _parse_date(post.get("publishedDate", ""))

    content_parts = []
    if image_url:
        content_parts.append(f'<img src="{image_url}" alt="{title}" />')
    if excerpt:
        content_parts.append(f"<p>{excerpt}</p>")
    content = "\n".join(content_parts) if content_parts else ""

    return {
        "id": item_id,
        "title": title,
        "url": url,
        "published_date": published_date,
        "summary": excerpt[:300] if excerpt else title,
        "content": content,
    }


async def main():
    config = load_feeds_config(ORG_KEY)
    favicon = config.get("favicon")

    params = {"query": QUERY}
    api_url = f"{SANITY_CDN}?{urlencode(params, quote_via=quote)}"

    async with AsyncSession() as session:
        for page_key, page in config["pages"].items():
            logging.info("Fetching %s…", page["label"])
            response = await fetch_with_retry(
                session, api_url, impersonate="chrome120", timeout=15
            )
            data = response.json()
            posts = data.get("result", [])

            entries = []
            for post in posts:
                entry = _build_entry(post)
                if entry:
                    entries.append(entry)

            if not entries:
                logging.warning("No entries for %s", page_key)
                continue

            entries.sort(key=lambda x: x.get("published_date", ""), reverse=True)
            feed_link = page.get("feed_link", page["url"])
            write_atom_feed(
                FEEDS_DIR / page["output_file"],
                entries,
                feed_title=page["label"],
                feed_link=feed_link,
                feed_icon=favicon,
            )
            logging.info("Wrote %d entries for %s", len(entries), page_key)


if __name__ == "__main__":
    asyncio.run(main())
