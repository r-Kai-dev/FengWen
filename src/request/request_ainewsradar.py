"""Fetch AI News Radar — Bole Picks 伯乐精选 (daily brief) and save as Atom XML feed.

Data source: https://learnprompt.github.io/ai-news-radar/data/daily-brief.json

This endpoint returns a curated list ("Bole Picks") of the most important AI/tech
stories from the past 24 hours, each with a score, importance label, source
count, reasons, and links to the primary article.
"""

import hashlib
import logging
from datetime import datetime, timezone

from curl_cffi.requests import AsyncSession

from common import (
    PARSED_DIR,
    ensure_output_dir,
    fetch_with_retry,
    load_api_config,
    setup_logging,
)
from feed_util import compact, write_atom_feed

setup_logging()
ensure_output_dir()

ORG_KEY = "ainewsradar"


def _importance_to_category(importance_label: str | None) -> list[str]:
    """Map the importance label to Atom categories."""
    if not importance_label:
        return []
    return [importance_label]


def _reasons_to_categories(reasons: list[str] | None) -> list[str]:
    """Map the reasons array to Atom categories."""
    if not reasons:
        return []
    return [r for r in reasons if r]


def _build_summary(item: dict) -> str:
    """Build a plain-text summary string with score, sources, and reasons."""
    parts = []

    score = item.get("score", 0)
    if score:
        parts.append(f"Score: {score:.3f}")

    source_count = item.get("source_count", 0)
    source_name = item.get("source_name", "")
    if source_count > 0 and source_name:
        parts.append(f"Sources: {source_count} ({source_name})")
    elif source_count > 0:
        parts.append(f"Sources: {source_count}")
    elif source_name:
        parts.append(f"Source: {source_name}")

    importance_label = item.get("importance_label", "")
    if importance_label:
        parts.append(f"Importance: {importance_label}")

    return "\n".join(parts) if parts else ""


def item_to_entry(item: dict) -> dict:
    """Convert a daily-brief story item to an Atom entry dict."""
    story_id = item.get("story_id", "")
    title = item.get("title", "")
    url = item.get("url", item.get("primary_url", ""))

    primary = item.get("primary_item", {}) or {}
    published_str = primary.get("published_at") or item.get("earliest_at") or item.get("latest_at") or ""
    if published_str:
        try:
            # Ensure ISO format with timezone
            dt = datetime.fromisoformat(published_str.replace("Z", "+00:00"))
            published_date = dt.isoformat()
        except (ValueError, TypeError):
            published_date = datetime.now(timezone.utc).isoformat()
    else:
        published_date = datetime.now(timezone.utc).isoformat()

    categories = []
    categories.extend(_importance_to_category(item.get("importance_label")))
    categories.extend(_reasons_to_categories(item.get("reasons")))
    if item.get("category"):
        categories.append(item["category"])

    summary = _build_summary(item)
    if not summary and primary:
        summary = primary.get("title", "")

    entry_id = hashlib.md5(f"{ORG_KEY}_{story_id}".encode()).hexdigest()

    return compact(
        {
            "id": entry_id,
            "source": ORG_KEY,
            "type": "bole_pick",
            "title": title,
            "url": url,
            "summary": summary,
            "published_date": published_date,
            "categories": categories,
            "organization": "AI News Radar",
            "metadata": {
                "score": item.get("score", 0),
                "importance_score": item.get("importance_score", 0),
                "importance_label": item.get("importance_label", ""),
                "source_count": item.get("source_count", 0),
                "source_name": item.get("source_name", ""),
                "story_id": story_id,
            },
        }
    )


async def fetch_and_parse(base_url: str, page_config: dict) -> list[dict]:
    """Fetch the daily-brief.json endpoint and convert to entries."""
    endpoint = page_config.get("endpoint", "/data/daily-brief.json")
    url = f"{base_url.rstrip('/')}{endpoint}"

    async with AsyncSession() as session:
        try:
            response = await fetch_with_retry(
                session,
                url,
                impersonate="chrome120",
                timeout=15,
            )
            payload = response.json()
        except Exception as exc:
            logging.error("Failed to fetch daily-brief.json: %s", exc)
            return []

    items = payload.get("items", [])
    if not items:
        logging.warning("No items found in daily-brief.json")
        return []

    entries = [item_to_entry(item) for item in items]
    logging.info(
        "Fetched %d bole picks from AI News Radar (generated %s)",
        len(entries),
        payload.get("generated_at", "unknown"),
    )
    return entries


async def main() -> None:
    """Fetch AI News Radar bole picks and write the Atom feed."""
    config = load_api_config(ORG_KEY)
    page_config = config["pages"]["bole_picks"]

    entries = await fetch_and_parse(config["base_url"], page_config)

    if not entries:
        logging.error("No entries to save")
        return

    favicon = config.get("favicon") or "https://learnprompt.github.io/ai-news-radar/assets/logo.svg"

    output_file = PARSED_DIR / page_config["output_file"]
    write_atom_feed(
        output_file,
        entries,
        feed_title="AI News Radar — Bole Picks 伯乐精选",
        feed_link="https://learnprompt.github.io/ai-news-radar/",
        feed_icon=favicon,
    )


if __name__ == "__main__":
    import asyncio

    asyncio.run(main())
