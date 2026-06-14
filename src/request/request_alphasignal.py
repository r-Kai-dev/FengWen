"""Fetch AlphaSignal news from Next.js RSC payload.

The page has an `initialNews` array in the RSC with news items containing
title, subtitle, publish_time, url, categories, and source name.

Output to feeds/:
  - alphasignal_news.xml
"""

import hashlib
import json
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

ORG_KEY = "alphasignal"
BASE_URL = "https://alphasignal.ai"


def fetch_page(url: str) -> str:
    """Fetch an HTML page."""
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


def extract_news(html: str) -> list[dict]:
    """Extract news items from the initialNews RSC array."""
    chunks = re.findall(
        r'self\.__next_f\.push\(\[[0-9]+,\s*"(.*?)"\s*\]\)', html, re.DOTALL
    )

    for chunk in chunks:
        decoded = chunk.encode("utf-8").decode("unicode_escape", errors="replace")
        if "initialNews" not in decoded:
            continue

        # Find the JSON array after "initialNews"
        idx = decoded.find("initialNews")
        json_start = decoded.find("[", idx)
        if json_start < 0:
            continue

        depth = 0
        end = json_start
        for i in range(json_start, len(decoded)):
            if decoded[i] == "[":
                depth += 1
            elif decoded[i] == "]":
                depth -= 1
                if depth == 0:
                    end = i + 1
                    break

        try:
            news_items = json.loads(decoded[json_start:end])
        except json.JSONDecodeError as exc:
            logging.warning(f"Failed to decode news JSON: {exc}")
            continue

        entries = []
        for item in news_items:
            title = item.get("title", "")
            subtitle = item.get("subtitle", "")
            url = item.get("url", "")
            date_str = item.get("publish_time", "")
            categories = item.get("regular_categories", [])
            source_name = item.get("name", "")

            if not title or not url:
                continue

            published_date = date_str
            if published_date:
                try:
                    dt = datetime.fromisoformat(published_date.replace("Z", "+00:00"))
                    published_date = dt.isoformat()
                except (ValueError, TypeError):
                    pass

            entry_id = hashlib.md5(f"alphasignal_news_{url}".encode()).hexdigest()

            entries.append(
                compact(
                    {
                        "id": entry_id,
                        "source": "alphasignal",
                        "type": "news",
                        "title": title,
                        "url": url,
                        "summary": subtitle,
                        "published_date": published_date,
                        "categories": categories,
                        "organization": source_name or "AlphaSignal",
                    }
                )
            )

        return entries

    logging.error("No initialNews found in RSC payload")
    return []


def main() -> None:
    """Fetch AlphaSignal news and write Atom XML feed."""
    config = load_api_config(ORG_KEY)
    pages = config["pages"]

    url = f"{BASE_URL}/"
    logging.info(f"Fetching AlphaSignal news from {url}")
    html = fetch_page(url)

    entries = extract_news(html)
    if not entries:
        logging.error("No news items found")
        return

    output_file = PARSED_DIR / pages["news"]["output_file"]
    write_atom_feed(
        output_file,
        entries,
        feed_title="AlphaSignal AI News",
        feed_link=BASE_URL,
        feed_icon=config.get("favicon", f"{BASE_URL}/favicon.ico"),
    )
    logging.info(f"Saved {len(entries)} entries to {output_file}")


if __name__ == "__main__":
    main()
