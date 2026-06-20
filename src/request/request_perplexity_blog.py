"""Fetch Perplexity Hub Blog posts from Framer handoverData.

The page at https://www.perplexity.ai/hub/blog is built with Framer and
protected by Cloudflare.  We use curl_cffi with browser impersonation to
bypass the protection.

Blog post metadata is embedded in ``__framer__handoverData`` — a JSON array
that uses index-based referencing.  Field names are Framer-internal hashes
that vary between collections, so we identify fields by their resolved
value types (date strings, slug-format strings, etc.).
"""

import asyncio
import hashlib
import json
import logging
import re
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

ORG_KEY = "perplexity_blog"
PAGE_URL = "https://www.perplexity.ai/hub/blog"
BLOG_BASE = "https://www.perplexity.ai/hub/blog"


async def fetch_page(url: str) -> str:
    """Fetch a page using curl_cffi with Chrome impersonation and retry."""
    async with AsyncSession() as session:
        resp = await fetch_with_retry(
            session, url, impersonate="chrome120", timeout=30
        )
        return resp.text


def _is_date(value: str) -> bool:
    """Check if a string looks like an ISO datetime."""
    return bool(re.match(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}", value))


def _is_slug(value: str) -> bool:
    """Check if a string looks like a URL slug (kebab-case, no spaces)."""
    return bool(re.match(r"^[a-z0-9]+(-[a-z0-9]+)+$", value))


def _resolve_value(arr: list, idx: int):
    """Resolve a value through the Framer type-wrapper indirection.

    arr[idx] → {"type": N, "value": M} → arr[M] → actual value
    """
    if idx >= len(arr):
        return None
    wrapper = arr[idx]
    if isinstance(wrapper, dict) and "value" in wrapper:
        value_idx = wrapper["value"]
        if isinstance(value_idx, int) and value_idx < len(arr):
            return arr[value_idx]
        return value_idx
    return wrapper


def extract_entries(html: str) -> list[dict]:
    """Extract blog entries from the Framer handoverData.

    Entry maps are identified as dicts with ≥3 integer values that
    resolve through typed wrappers to strings.  We classify each
    resolved value as date, slug, title, or summary.
    """

    m = re.search(
        r'id="__framer__handoverData">(.*?)</script>',
        html,
        re.DOTALL,
    )
    if not m:
        logging.error("Could not find __framer__handoverData")
        return []

    try:
        arr = json.loads(m.group(1))
    except json.JSONDecodeError as exc:
        logging.error("Failed to parse handoverData JSON: %s", exc)
        return []

    entries = []
    seen_slugs = set()

    for idx, item in enumerate(arr):
        if not isinstance(item, dict):
            continue
        # Entry maps have integer values pointing to typed wrappers
        int_fields = {k: v for k, v in item.items() if isinstance(v, int)}
        if len(int_fields) < 3:
            continue

        # Resolve each field
        resolved: dict[str, object] = {}
        for field_name, value_idx in int_fields.items():
            val = _resolve_value(arr, value_idx)
            if isinstance(val, str) and val.strip():
                resolved[field_name] = val

        if len(resolved) < 2:
            continue

        # Classify string values
        date_val = ""
        slug_val = ""
        title_val = ""
        summary_val = ""

        for val in resolved.values():
            if not isinstance(val, str):
                continue
            val = val.strip()
            if not val:
                continue

            if _is_date(val):
                date_val = val
            elif _is_slug(val):
                slug_val = val
            elif len(val) > 80:
                summary_val = val
            elif len(val) < 10 and " " not in val:
                # short single word — likely a category, skip
                pass
            else:
                # Likely a title (medium length, has spaces)
                if not title_val or len(val) > len(title_val):
                    title_val = val

        if not slug_val or not title_val:
            continue
        if slug_val in seen_slugs:
            continue
        seen_slugs.add(slug_val)

        url = f"{BLOG_BASE}/{slug_val}"
        entry_id = hashlib.md5(f"perplexity_blog_{slug_val}".encode()).hexdigest()

        entries.append(
            compact(
                {
                    "id": entry_id,
                    "source": "perplexity",
                    "type": "blog",
                    "title": title_val,
                    "url": url,
                    "summary": summary_val,
                    "published_date": date_val or None,
                    "categories": [],
                    "organization": "Perplexity AI",
                }
            )
        )

    return entries


async def main() -> None:
    """Fetch Perplexity Hub Blog and write Atom XML feed."""
    config = load_api_config(ORG_KEY)
    page_config = config["pages"]["blog"]

    logging.info("Fetching Perplexity Blog from %s", PAGE_URL)
    html = await fetch_page(PAGE_URL)

    entries = extract_entries(html)
    if not entries:
        logging.error("No blog entries found")
        return

    output_file = PARSED_DIR / page_config["output_file"]
    write_atom_feed(
        output_file,
        entries,
        feed_title="Perplexity Hub Blog",
        feed_link=PAGE_URL,
        feed_icon=config.get("favicon", "https://www.perplexity.ai/favicon.ico"),
    )
    logging.info("Saved %d entries to %s", len(entries), output_file)


if __name__ == "__main__":
    asyncio.run(main())
