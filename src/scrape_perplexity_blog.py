"""Scrape Perplexity Hub Blog from Framer handoverData (async — Cloudflare bypass)."""

import asyncio
import hashlib
import json
import logging
import random
import re
from datetime import datetime, timezone

from curl_cffi.requests import AsyncSession

from utils import (
    FEEDS_DIR, setup_logging, ensure_output_dir,
    load_feeds_config, fetch_with_retry, compact, write_atom_feed,
)

HEADERS = {
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Cache-Control": "no-cache",
    "Sec-Ch-Ua": '"Chromium";v="146", "Google Chrome";v="146", "Not?A_Brand";v="99"',
    "Sec-Ch-Ua-Mobile": "?0",
    "Sec-Ch-Ua-Platform": '"Linux"',
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Site": "none",
    "Sec-Fetch-User": "?1",
    "Upgrade-Insecure-Requests": "1",
}

setup_logging()
ensure_output_dir()
ORG_KEY = "perplexity_blog"
PAGE_URL = "https://www.perplexity.ai/hub/blog"
BLOG_BASE = "https://www.perplexity.ai/hub/blog"


def _is_date(v): return bool(re.match(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}", v))
def _is_slug(v): return bool(re.match(r"^[a-z0-9]+(-[a-z0-9]+)+$", v))


def _resolve(arr, idx):
    if idx >= len(arr):
        return None
    wrapper = arr[idx]
    if isinstance(wrapper, dict) and "value" in wrapper:
        vi = wrapper["value"]
        return arr[vi] if isinstance(vi, int) and vi < len(arr) else vi
    return wrapper


def extract(html):
    m = re.search(r'id="__framer__handoverData">(.*?)</script>', html, re.DOTALL)
    if not m:
        return []
    arr = json.loads(m.group(1))
    entries = []
    seen = set()
    for item in arr:
        if not isinstance(item, dict):
            continue
        int_fields = {k: v for k, v in item.items() if isinstance(v, int)}
        if len(int_fields) < 3:
            continue
        resolved = {}
        for fn, vi in int_fields.items():
            val = _resolve(arr, vi)
            if isinstance(val, str) and val.strip():
                resolved[fn] = val
        if len(resolved) < 2:
            continue

        date_val = slug_val = title_val = summary_val = ""
        for val in resolved.values():
            if not isinstance(val, str):
                continue
            val = val.strip()
            if _is_date(val): date_val = val
            elif _is_slug(val): slug_val = val
            elif len(val) > 80: summary_val = val
            elif len(val) < 10 and " " not in val: pass
            elif not title_val or len(val) > len(title_val): title_val = val

        if not slug_val or not title_val or slug_val in seen:
            continue
        seen.add(slug_val)

        url = f"{BLOG_BASE}/{slug_val}"
        item_id = hashlib.md5(f"perplexity_blog_{slug_val}".encode()).hexdigest()
        entries.append(compact({
            "id": item_id, "source": "perplexity", "type": "blog",
            "title": title_val, "url": url, "summary": summary_val,
            "published_date": date_val or None,
            "organization": "Perplexity AI",
        }))
    return entries


async def main():
    config = load_feeds_config(ORG_KEY)
    page = config["pages"]["blog"]
    logging.info("Fetching %s: %s", page["label"], PAGE_URL)

    async with AsyncSession() as session:
        resp = await fetch_with_retry(session, PAGE_URL,
                                      impersonate="chrome146", timeout=30,
                                      headers=HEADERS, base_delay=random.uniform(1.5, 3.0))

    entries = extract(resp.text)
    if not entries:
        logging.warning("No entries found")
        return
    entries.sort(key=lambda x: x.get("published_date", ""), reverse=True)
    write_atom_feed(FEEDS_DIR / page["output_file"], entries,
                    feed_title=page["label"], feed_link=PAGE_URL,
                    feed_icon=config.get("favicon"))


if __name__ == "__main__":
    asyncio.run(main())
