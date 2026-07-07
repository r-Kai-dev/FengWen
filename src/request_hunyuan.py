"""Fetch Tencent Hunyuan research articles via the public API."""

import asyncio
import hashlib
import logging
from datetime import datetime, timezone

from curl_cffi.requests import AsyncSession

from utils import (
    FEEDS_DIR, setup_logging, ensure_output_dir,
    load_feeds_config, compact, write_atom_feed,
)

setup_logging()
ensure_output_dir()
ORG_KEY = "hunyuan"
BASE_URL = "https://hunyuan.tencent.com"
API_LIST = "https://api.hunyuan.tencent.com/api/blog/publicList"


def _build_entry(item: dict) -> dict | None:
    """Build a feed entry from an API item."""
    item_id = item.get("id")
    title = item.get("title", "")
    if not item_id or not title:
        return None

    # Article URL: prefer customUrl slug, fall back to numeric id
    custom_url = item.get("customUrl", "")
    slug = custom_url if custom_url else str(item_id)
    url = f"{BASE_URL}/research/{slug}"

    # Use displayPublishTime (Unix timestamp), fall back to publishedAt
    ts = item.get("displayPublishTime") or item.get("publishedAt")
    if ts:
        published_date = datetime.fromtimestamp(ts, tz=timezone.utc).isoformat()
    else:
        published_date = datetime.now(timezone.utc).isoformat()

    desc = item.get("desc", "")
    author = item.get("author", "")

    entry_id = hashlib.md5(
        f"hunyuan_{item_id}_{title}".encode()
    ).hexdigest()

    return compact({
        "id": entry_id,
        "source": "hunyuan",
        "type": "research",
        "title": title,
        "url": url,
        "summary": desc[:800] if desc else None,
        "published_date": published_date,
        "categories": [author] if author else [],
        "organization": "Tencent Hunyuan",
    })


async def main():
    config = load_feeds_config(ORG_KEY)
    favicon = config.get("favicon")

    for page_key, page_cfg in config["pages"].items():
        logging.info("Fetching %s from API…", page_cfg["label"])

        async with AsyncSession() as session:
            # POST to the API (fetch_with_retry only does GETs)
            for attempt in range(3):
                try:
                    response = await session.post(
                        API_LIST, json={},
                        impersonate="chrome120", timeout=15,
                    )
                    response.raise_for_status()
                    break
                except Exception as exc:
                    if attempt == 2:
                        raise
                    wait = 2 ** attempt
                    logging.warning(
                        "API request failed (attempt %d/3): %s. Retrying in %ds…",
                        attempt + 1, exc, wait,
                    )
                    await asyncio.sleep(wait)
        data = response.json()
        if data.get("code") != 0:
            logging.error("API error for %s: %s", page_key, data.get("msg"))
            continue

        items = data.get("data", {}).get("list", [])
        entries = []
        seen = set()
        for item in items:
            entry = _build_entry(item)
            if entry is None:
                continue
            key = entry["title"].lower().strip()
            if key in seen:
                continue
            seen.add(key)
            entries.append(entry)

        if not entries:
            logging.warning("No entries found for %s", page_key)
            continue

        entries.sort(key=lambda x: x.get("title", ""))
        entries.sort(key=lambda x: x.get("published_date", ""), reverse=True)

        write_atom_feed(
            FEEDS_DIR / page_cfg["output_file"],
            entries,
            feed_title=page_cfg["label"],
            feed_link=page_cfg["url"],
            feed_icon=favicon,
        )


if __name__ == "__main__":
    asyncio.run(main())
