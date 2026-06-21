"""Fetch Hacker News best stories from Firebase API."""

import asyncio
import hashlib
import logging
from datetime import datetime, timezone

from curl_cffi.requests import AsyncSession

from utils import (
    FEEDS_DIR, setup_logging, ensure_output_dir,
    load_feeds_config, fetch_with_retry, write_atom_feed,
)

setup_logging()
ensure_output_dir()
ORG_KEY = "hackernews"


async def fetch_best_stories(base_url, limit=50):
    async with AsyncSession() as session:
        response = await fetch_with_retry(session, f"{base_url}/beststories.json", impersonate="chrome120", timeout=10)
        story_ids = response.json()[:limit]

        stories = []
        for story_id in story_ids:
            try:
                sr = await fetch_with_retry(session, f"{base_url}/item/{story_id}.json", impersonate="chrome120", timeout=5, max_retries=2)
                story_data = sr.json()
            except Exception as exc:
                logging.warning("Failed to fetch story %s: %s", story_id, exc)
                continue

            if not story_data or story_data.get("type") != "story":
                continue

            discussion_url = f"https://news.ycombinator.com/item?id={story_data['id']}"
            article_url = story_data.get("url")
            pub = datetime.fromtimestamp(story_data.get("time", 0), tz=timezone.utc).isoformat()

            stories.append({
                "id": hashlib.md5(f"hackernews_{story_data['id']}".encode()).hexdigest(),
                "source": ORG_KEY, "type": "story",
                "title": story_data.get("title", ""),
                "url": discussion_url, "external_url": article_url,
                "published_date": pub,
                "organization": "Hacker News",
                "metadata": {
                    "score": story_data.get("score", 0),
                    "author": story_data.get("by", ""),
                    "comments": story_data.get("descendants", 0),
                    "hn_id": story_data["id"],
                },
            })
        return stories


async def main():
    config = load_feeds_config(ORG_KEY)
    page = config["pages"]["best"]
    limit = page.get("limit", 50)
    logging.info("Fetching Hacker News best stories…")
    stories = await fetch_best_stories(config["base_url"], limit=limit)
    if not stories:
        logging.error("No stories were fetched")
        return
    stories.sort(key=lambda x: x.get("published_date", ""), reverse=True)
    write_atom_feed(FEEDS_DIR / page["output_file"], stories,
                    feed_title=page["label"], feed_link=page.get("feed_link", page["url"]),
                    feed_icon=config.get("favicon"))


if __name__ == "__main__":
    asyncio.run(main())
