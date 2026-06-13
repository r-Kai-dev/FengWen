"""Fetch ElevenLabs research blog posts from Next.js RSC payload.

The page at https://elevenlabs.io/blog/category/research is built with
Next.js React Server Components.  All blog post data — title, URL, date,
category — is embedded as RSC payload chunks inside:

    self.__next_f.push([1,"..."])

We decode the chunks, extract h2 elements (with title + blog link) and dl
elements (with category + date), then pair them sequentially to produce
an Atom feed.
"""

import hashlib
import logging
import re
import urllib.request
from datetime import datetime, timezone

from common import (
    PARSED_DIR,
    ensure_output_dir,
    load_api_config,
    setup_logging,
)
from feed_util import compact, write_atom_feed

setup_logging()
ensure_output_dir()

ORG_KEY = "elevenlabs"
BASE_URL = "https://elevenlabs.io"
FEED_URL = f"{BASE_URL}/blog/category/research"


def fetch_page(url: str) -> str:
    """Fetch an HTML page and return the raw text."""
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": (
                "Mozilla/5.0 (X11; Linux x86_64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            ),
        },
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        return resp.read().decode("utf-8")


def _parse_date(iso_str: str) -> str:
    """Parse ISO date string to Atom-compatible ISO format."""
    try:
        dt = datetime.fromisoformat(iso_str.replace("Z", "+00:00"))
        return dt.isoformat()
    except (ValueError, TypeError):
        return datetime.now(timezone.utc).isoformat()


def extract_data(html: str) -> list[dict]:
    """Extract blog post data from Next.js RSC payload chunks.

    Returns a list of dicts with keys: title, url, dateTime, displayDate, category.
    """
    # Collect all RSC payload chunks
    chunks = re.findall(
        r'self\.__next_f\.push\(\[1,\s*"(.*?)"\s*\]\)', html, re.DOTALL
    )

    # Decode and concatenate all chunks
    all_data = ""
    for chunk in chunks:
        decoded = chunk.encode("utf-8").decode("unicode_escape", errors="replace")
        all_data += decoded

    # --- Extract titles with blog links ---
    # Pattern: h2 with children [["$","span",null,{...}],"TITLE"]
    titles = []
    for m in re.finditer(
        r'children":\[\["\$","span",null,\{[^}]*\}\],"([^"]+)"\]', all_data
    ):
        title = m.group(1)
        ctx = all_data[max(0, m.start() - 200) : m.start()]
        href_m = re.search(r'href":"(/blog/[^"]+)"', ctx)
        href = href_m.group(1) if href_m else ""
        if href:
            titles.append({"title": title, "url": f"{BASE_URL}{href}"})

    # --- Extract dates with category ---
    # Pattern: look for dateTime values that belong to blog posts
    dates = []
    for m in re.finditer(r'"dateTime":"([^"]+)"', all_data):
        date_time = m.group(1)
        ctx = all_data[max(0, m.start() - 400) : m.start() + 200]

        # Extract display date after the dateTime attribute
        after = all_data[m.end() : m.end() + 200]
        disp_m = re.search(r'children":"([A-Za-z]+ \d{1,2}, \d{4})"', after)
        if not disp_m:
            continue
        display_date = disp_m.group(1)

        # Extract category from before the dateTime
        # Pattern: find the dd after the Category dt
        cat_m = re.search(
            r'children":"Category"[\s\S]*?"children":"([^"]+)"', ctx
        )
        category = cat_m.group(1) if cat_m else ""

        dates.append(
            {
                "dateTime": _parse_date(date_time),
                "displayDate": display_date,
                "category": category,
            }
        )

    # --- Pair titles and dates in order ---
    # Both lists are in page order, so we zip them
    if len(titles) != len(dates):
        logging.warning(
            "Mismatch: %d titles vs %d dates — using minimum",
            len(titles),
            len(dates),
        )

    entries = []
    for t, d in zip(titles, dates):
        entries.append(
            {
                "title": t["title"],
                "url": t["url"],
                "dateTime": d["dateTime"],
                "category": d["category"],
            }
        )

    return entries


def post_to_entry(post: dict) -> dict:
    """Convert an extracted post dict to an Atom entry dict."""
    entry_id = hashlib.md5(
        f"elevenlabs_{post['url']}".encode()
    ).hexdigest()

    return compact(
        {
            "id": entry_id,
            "source": "elevenlabs",
            "type": "research",
            "title": post["title"],
            "url": post["url"],
            "published_date": post["dateTime"],
            "categories": [post["category"]] if post.get("category") else [],
            "organization": "ElevenLabs",
        }
    )


def main() -> None:
    """Fetch ElevenLabs research blog and write the Atom feed."""
    config = load_api_config(ORG_KEY)
    page_config = config["pages"]["research"]

    html = fetch_page(FEED_URL)
    posts = extract_data(html)

    if not posts:
        logging.error("No posts extracted from ElevenLabs research page")
        return

    entries = [post_to_entry(p) for p in posts]

    favicon = config.get("favicon", f"{BASE_URL}/favicon.ico")
    output_file = PARSED_DIR / page_config["output_file"]

    write_atom_feed(
        output_file,
        entries,
        feed_title="ElevenLabs Research Blog",
        feed_link=FEED_URL,
        feed_icon=favicon,
    )

    logging.info(
        "Fetched %d research blog posts from ElevenLabs", len(entries)
    )


if __name__ == "__main__":
    main()
