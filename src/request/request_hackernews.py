"""Fetch Hacker News best stories and save as structured JSON."""

import asyncio
import hashlib
import json
import logging
from datetime import datetime, timezone

from curl_cffi.requests import AsyncSession

from common import (
    PARSED_DIR,
    fetch_with_retry,
    load_api_config,
    setup_logging,
    ensure_output_dir,
    write_atom_feed,
)

setup_logging()
ensure_output_dir()

ORG_KEY = "hackernews"


async def fetch_best_stories(base_url: str, limit: int = 50) -> list[dict]:
    """Fetch best stories from Hacker News API.

    Steps:
    1. Get the list of best story IDs.
    2. Fetch individual story details (up to *limit*).
    """
    async with AsyncSession() as session:
        try:
            # ── Step 1: list of best story IDs ──────────────────────
            response = await fetch_with_retry(
                session,
                f"{base_url}/beststories.json",
                impersonate="chrome120",
                timeout=10,
            )
            story_ids = response.json()[:limit]

            # ── Step 2: individual story details ────────────────────
            stories: list[dict] = []
            for story_id in story_ids:
                try:
                    story_response = await fetch_with_retry(
                        session,
                        f"{base_url}/item/{story_id}.json",
                        impersonate="chrome120",
                        timeout=5,
                        max_retries=2,
                    )
                    story_data = story_response.json()
                except Exception as exc:
                    logging.warning("Failed to fetch story %s: %s", story_id, exc)
                    continue

                if not story_data or story_data.get("type") != "story":
                    continue

                article_url = story_data.get("url")
                discussion_url = (
                    f"https://news.ycombinator.com/item?id={story_data['id']}"
                )

                story = {
                    "id": hashlib.md5(
                        f"hackernews_{story_data['id']}".encode()
                    ).hexdigest(),
                    "source": ORG_KEY,
                    "type": "story",
                    "title": story_data.get("title", ""),
                    "description": "",
                    "url": discussion_url,
                    "external_url": article_url if article_url else None,
                    "published_date": datetime.fromtimestamp(
                        story_data.get("time", 0), tz=timezone.utc
                    ).isoformat(),
                    "categories": [],
                    "organization": "Hacker News",
                    "metadata": {
                        "score": story_data.get("score", 0),
                        "author": story_data.get("by", ""),
                        "comments": story_data.get("descendants", 0),
                        "hn_id": story_data["id"],
                    },
                    "objects": [],
                }
                stories.append(story)

            return stories

        except Exception as exc:
            logging.error("Failed to fetch best stories: %s", exc)
            return []


async def main() -> None:
    """Fetch Hacker News best stories and write to the configured output file."""
    config = load_api_config(ORG_KEY)
    page_config = config["pages"]["best"]

    # Client-side limit on how many stories to return
    limit = page_config.get("limit", 50)

    logging.info("Fetching Hacker News best stories…")
    stories = await fetch_best_stories(config["base_url"], limit=limit)

    if not stories:
        logging.error("No stories were fetched")
        return

    # Favicon: use config value or fall back to {base_url}/favicon.ico
    favicon = config.get("favicon") or (config.get("base_url", "").rstrip("/") + "/favicon.ico")

    output_file = PARSED_DIR / page_config["output_file"]
    write_atom_feed(
        output_file, stories,
        feed_title="Hacker News Best",
        feed_link="https://news.ycombinator.com/best",
        feed_icon=favicon,
    )


if __name__ == "__main__":
    asyncio.run(main())
