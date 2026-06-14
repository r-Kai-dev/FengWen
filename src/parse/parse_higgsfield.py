"""Parse Higgsfield blog posts from JSON-LD in DrissionPage-rendered HTML."""

import hashlib
import json
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path

# Ensure src/ is on sys.path
_src_dir = str(Path(__file__).resolve().parent.parent)
if _src_dir not in sys.path:
    sys.path.insert(0, _src_dir)

from bs4 import BeautifulSoup

from config_util import load_site_config
from feed_util import compact, write_atom_feed

CONFIG_NAME = "js.json"
ORG_KEY = "higgsfield"
BASE_URL = "https://higgsfield.ai"

project_dir = Path(__file__).resolve().parent.parent.parent
html_dir = project_dir / "html_cache"
parsed_dir = project_dir / "feeds"


def load_html(filename: str) -> BeautifulSoup | None:
    file_path = html_dir / filename
    if not file_path.exists():
        logging.warning(f"Cache file not found: {filename}")
        return None
    with open(file_path, "r", encoding="utf-8") as f:
        return BeautifulSoup(f.read(), "html.parser")


def parse_date(date_str: str) -> str:
    """Parse various date formats to ISO-8601."""
    import re
    # Strip ordinal suffixes: "1st", "2nd", "3rd", "4th", etc.
    date_str = re.sub(r'(\d)(st|nd|rd|th)', r'\1', date_str)
    for fmt in [
        "%Y-%m-%dT%H:%M:%S.%f%z",
        "%Y-%m-%dT%H:%M:%S%z",
        "%Y-%m-%d",
        "%B %d, %Y",
        "%b %d, %Y",
        "%b. %d, %Y",
    ]:
        try:
            dt = datetime.strptime(date_str, fmt)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt.isoformat()
        except (ValueError, TypeError):
            continue
    return ""


def main():
    config = load_site_config(ORG_KEY, config_name=CONFIG_NAME)
    cache_files = config["cache_files"]
    output_files = config["output_files"]
    favicon = config.get("favicon") or f"{BASE_URL}/favicon.ico"

    for page_type, cache_filename in cache_files.items():
        file_path = html_dir / cache_filename
        if not file_path.exists():
            logging.warning(f"Cache file not found: {cache_filename}")
            continue

        logging.info(f"Processing file: {cache_filename}")
        soup = load_html(cache_filename)
        if not soup:
            continue

        posts = []
        seen_urls = set()

        # Extract from JSON-LD
        ld_scripts = soup.select('script[type="application/ld+json"]')
        for script in ld_scripts:
            try:
                data = json.loads(script.string)
            except (json.JSONDecodeError, TypeError):
                continue

            if isinstance(data, list):
                data = data[0] if data else {}
            if not isinstance(data, dict):
                continue

            headline = (data.get("headline") or "").strip()
            url = data.get("url") or ""
            main_entity = data.get("mainEntityOfPage", {})
            if isinstance(main_entity, dict):
                url = url or main_entity.get("@id", "")
            date_str = data.get("datePublished", "")
            description = data.get("description", "")

            if not headline or not url or not date_str:
                continue

            if url in seen_urls:
                continue
            seen_urls.add(url)

            published_date = parse_date(date_str)
            if not published_date:
                published_date = datetime.now(timezone.utc).replace(microsecond=0).isoformat()

            slug = url.rstrip("/").split("/")[-1]
            entry_id = hashlib.md5(f"higgsfield_blog_{slug}".encode()).hexdigest()

            posts.append(
                compact(
                    {
                        "id": entry_id,
                        "source": "higgsfield",
                        "type": "blog",
                        "title": headline,
                        "url": url,
                        "summary": description,
                        "published_date": published_date,
                        "organization": "Higgsfield",
                    }
                )
            )

        if posts:
            output_filename = output_files.get(page_type, cache_filename.replace(".html", ".xml"))
            feed_path = parsed_dir / output_filename

            write_atom_feed(
                feed_path,
                posts,
                feed_title="Higgsfield Blog",
                feed_link=f"{BASE_URL}/blog",
                feed_icon=favicon,
            )
            logging.info(f"Saved {len(posts)} entries to {output_filename}")
        else:
            logging.error("No posts found")


if __name__ == "__main__":
    main()
