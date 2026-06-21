"""Fetch AI News Radar — Bole Picks daily brief."""

import asyncio
import hashlib
import logging
from datetime import datetime, timezone

from curl_cffi.requests import AsyncSession

from utils import (
    FEEDS_DIR, setup_logging, ensure_output_dir,
    load_feeds_config, fetch_with_retry, compact, write_atom_feed,
)

setup_logging()
ensure_output_dir()
ORG_KEY = "ainewsradar"


def item_to_entry(item):
    story_id = item.get("story_id", "")
    title = item.get("title", "")
    url = item.get("url", item.get("primary_url", ""))
    primary = item.get("primary_item", {}) or {}
    published_str = primary.get("published_at") or item.get("earliest_at") or item.get("latest_at") or ""
    if published_str:
        try:
            published_date = datetime.fromisoformat(published_str.replace("Z", "+00:00")).isoformat()
        except (ValueError, TypeError):
            published_date = datetime.now(timezone.utc).isoformat()
    else:
        published_date = datetime.now(timezone.utc).isoformat()

    categories = []
    il = item.get("importance_label", "")
    if il: categories.append(il)
    reasons = item.get("reasons") or []
    categories.extend(r for r in reasons if r)
    if item.get("category"): categories.append(item["category"])

    summary_parts = []
    score = item.get("score", 0)
    if score: summary_parts.append(f"Score: {score:.3f}")
    sc = item.get("source_count", 0)
    sn = item.get("source_name", "")
    if sc > 0 and sn: summary_parts.append(f"Sources: {sc} ({sn})")
    elif sc > 0: summary_parts.append(f"Sources: {sc}")
    elif sn: summary_parts.append(f"Source: {sn}")
    if il: summary_parts.append(f"Importance: {il}")
    summary = "\\n".join(summary_parts) if summary_parts else (primary.get("title", "") if primary else "")

    return compact({
        "id": hashlib.md5(f"{ORG_KEY}_{story_id}".encode()).hexdigest(),
        "source": ORG_KEY, "type": "bole_pick",
        "title": title, "url": url, "summary": summary,
        "published_date": published_date, "categories": categories,
        "organization": "AI News Radar",
        "metadata": {"score": score, "importance_score": item.get("importance_score", 0),
                     "importance_label": il, "source_count": sc, "source_name": sn,
                     "story_id": story_id},
    })


async def main():
    config = load_feeds_config(ORG_KEY)
    page = config["pages"]["bole_picks"]
    async with AsyncSession() as session:
        response = await fetch_with_retry(session, page["url"], impersonate="chrome120", timeout=15)
        payload = response.json()
    items = payload.get("items", [])
    if not items:
        logging.warning("No items found in daily-brief.json")
        return
    entries = [item_to_entry(item) for item in items]
    entries.sort(key=lambda x: x.get("published_date", ""), reverse=True)
    write_atom_feed(FEEDS_DIR / page["output_file"], entries,
                    feed_title=page["label"], feed_link=page["url"],
                    feed_icon=config.get("favicon"))


if __name__ == "__main__":
    asyncio.run(main())
