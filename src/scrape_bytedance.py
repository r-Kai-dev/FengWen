"""Scrape ByteDance Seed blog and public papers via embedded SSR JSON.

The page embeds an article_list JSON array in the initial HTML (no JS needed).
We extract it directly instead of using a browser — timestamps are stable Unix
millis, URLs come from the publisher's own TitleKey slugs.
"""

import hashlib
import json
import logging
import re
from datetime import datetime, timezone

from utils import (
    FEEDS_DIR,
    setup_logging,
    ensure_output_dir,
    load_feeds_config,
    fetch_page,
    compact,
    write_atom_feed,
)

setup_logging()
ensure_output_dir()

ORG_KEY = "bytedance"
ORGANIZATION = "ByteDance Seed"


# ═══════════════════════════════════════════════════════════════════
#  JSON extraction
# ═══════════════════════════════════════════════════════════════════

def _extract_article_list(html):
    """Extract the article_list JSON array from the SSR HTML payload."""
    marker = '"article_list":'
    start = html.find(marker)
    if start < 0:
        raise ValueError("article_list not found in HTML")

    pos = start + len(marker)  # points at '['
    depth = 0
    for i in range(pos, len(html)):
        if html[i] == "[":
            depth += 1
        elif html[i] == "]":
            depth -= 1
            if depth == 0:
                return json.loads(html[pos : i + 1])

    raise ValueError("Unterminated article_list JSON")


# ═══════════════════════════════════════════════════════════════════
#  Entry builders
# ═══════════════════════════════════════════════════════════════════

def _build_blog_entry(article, base_url):
    meta = article["ArticleMeta"]
    sub = article.get("ArticleSubContentEn", {})

    title = sub.get("Title", "")
    if not title:
        return None

    slug = sub.get("TitleKey", "") or re.sub(
        r"[^a-z0-9]+", "-", title.lower()
    ).strip("-")
    url = f"{base_url.rstrip('/')}/blog/{slug}"

    ts = meta.get("PublishDate", 0)
    if ts:
        pub_date = datetime.fromtimestamp(ts / 1000, tz=timezone.utc).isoformat()
    else:
        pub_date = datetime.now(timezone.utc).isoformat()

    categories = [
        r["ResearchAreaName"]
        for r in meta.get("ResearchArea", [])
        if r.get("ResearchAreaName")
    ]

    summary = sub.get("Abstract", "")[:500] if sub.get("Abstract") else None

    item_id = hashlib.md5(f"bytedance_blog_{title}".encode()).hexdigest()

    return compact(
        {
            "id": item_id,
            "title": title,
            "url": url,
            "published_date": pub_date,
            "summary": summary,
            "categories": categories,
            "organization": ORGANIZATION,
        }
    )


def _build_paper_entry(article, base_url):
    meta = article["ArticleMeta"]
    sub = article.get("ArticleSubContentEn", {})

    title = sub.get("Title", "")
    if not title:
        return None

    slug = sub.get("TitleKey", "") or re.sub(
        r"[^a-z0-9]+", "-", title.lower()
    ).strip("-")
    url = f"{base_url.rstrip('/')}/public_papers/{slug}"

    ts = meta.get("PublishDate", 0)
    if ts:
        pub_date = datetime.fromtimestamp(ts / 1000, tz=timezone.utc).isoformat()
    else:
        pub_date = datetime.now(timezone.utc).isoformat()

    categories = [
        r["ResearchAreaName"]
        for r in meta.get("ResearchArea", [])
        if r.get("ResearchAreaName")
    ]

    summary = sub.get("Abstract", "")[:500] if sub.get("Abstract") else None

    item_id = hashlib.md5(f"bytedance_papers_{title}".encode()).hexdigest()

    return compact(
        {
            "id": item_id,
            "title": title,
            "url": url,
            "published_date": pub_date,
            "summary": summary,
            "categories": categories,
            "organization": ORGANIZATION,
        }
    )


# ═══════════════════════════════════════════════════════════════════
#  Main
# ═══════════════════════════════════════════════════════════════════

def main():
    config = load_feeds_config(ORG_KEY)
    base_url = config["base_url"]
    favicon = config.get("favicon")

    for page_key, page in config["pages"].items():
        logging.info("Fetching %s: %s", page["label"], page["url"])

        try:
            html = fetch_page(page["url"])
        except Exception as exc:
            logging.error("Failed to fetch %s: %s", page["url"], exc)
            continue

        try:
            articles = _extract_article_list(html)
        except (ValueError, json.JSONDecodeError) as exc:
            logging.error("Failed to extract article_list: %s", exc)
            continue

        if page_key == "blog":
            builder = _build_blog_entry
        elif page_key == "public_papers":
            builder = _build_paper_entry
        else:
            logging.error("Unknown page key: %s", page_key)
            continue

        entries = []
        for article in articles:
            entry = builder(article, base_url)
            if entry:
                entries.append(entry)

        if not entries:
            logging.warning("No entries for %s", page_key)
            continue

        # Deduplicate and sort
        entries = [json.loads(s) for s in {json.dumps(d) for d in entries}]
        entries.sort(key=lambda x: x.get("published_date", ""), reverse=True)

        write_atom_feed(
            FEEDS_DIR / page["output_file"],
            entries,
            feed_title=page["label"],
            feed_link=page["url"],
            feed_icon=favicon,
        )


if __name__ == "__main__":
    main()
