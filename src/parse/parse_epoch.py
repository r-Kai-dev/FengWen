"""Parse Epoch AI Latest page from cached JS-rendered HTML.

Cache file (from fetch_js.py):
  - epoch_latest.html

Output to feeds/:
  - epoch_latest.xml
"""

import hashlib
import logging
import re
from datetime import datetime, timezone
from pathlib import Path

from bs4 import BeautifulSoup
from config_util import load_site_config
from feed_util import compact, write_atom_feed

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)

project_dir = Path(__file__).resolve().parent.parent.parent
html_dir = project_dir / "html_cache"
parsed_dir = project_dir / "feeds"
parsed_dir.mkdir(exist_ok=True)

BASE_URL = "https://epoch.ai"


def load_config():
    """Load site configuration from js.json"""
    return load_site_config("epoch", config_name="js.json")


def load_html(filename: str) -> BeautifulSoup | None:
    """Load HTML content from cache file."""
    file_path = html_dir / filename
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            return BeautifulSoup(f.read(), "html.parser")
    except FileNotFoundError:
        logging.error(f"File not found: {file_path}")
        return None
    except Exception as e:
        logging.error(f"Error reading file {file_path}: {e}")
        return None


def parse_date(date_str: str) -> str | None:
    """Parse dates like 'Jun. 11, 2026' or 'June 11, 2026'."""
    if not date_str:
        return None
    date_str = date_str.strip()
    for fmt in ("%b. %d, %Y", "%B %d, %Y", "%b %d, %Y"):
        try:
            return (
                datetime.strptime(date_str, fmt)
                .replace(tzinfo=timezone.utc)
                .isoformat()
            )
        except ValueError:
            continue
    return None


def parse_latest_page(soup: BeautifulSoup) -> list[dict]:
    """Extract articles from the Epoch AI /latest page.

    Each article is in a .card-article-listing div with:
      - Type (Data Insight, Newsletter, Report, etc.)
      - Date
      - Title
      - Description/subtitle
      - Author
      - Link
    """
    if not soup:
        return []

    posts = []

    for card in soup.select(".card-article-listing"):
        try:
            # Get the link
            link_el = card.select_one('a[href]')
            if not link_el:
                continue
            href = link_el.get("href", "")
            if not href or href.startswith("http"):
                # Use first meaningful relative link in the card
                for a in card.select('a[href]'):
                    h = a.get("href", "")
                    if h.startswith("/") and not h.startswith("/#"):
                        href = h
                        break
            if not href or href.startswith("http") or href.startswith("/#"):
                continue

            # Get full text
            text = card.get_text(separator="|", strip=True)
            parts = [p.strip() for p in text.split("|") if p.strip()]
            if len(parts) < 3:
                continue

            article_type = parts[0]
            date_str = parts[1]
            title = parts[2]

            # Description (if exists) is the part between title and "By X"
            description = ""
            author = ""
            for p in parts[3:]:
                if p.startswith("By "):
                    author = p[3:]
                elif not author:
                    description = p

            published_date = parse_date(date_str) or datetime.now(timezone.utc).isoformat()

            slug = href.strip("/").split("/")[-1]
            url = f"{BASE_URL}{href}"
            entry_id = hashlib.md5(f"epoch_latest_{slug}".encode()).hexdigest()

            categories = [article_type] if article_type else []

            posts.append(
                compact(
                    {
                        "id": entry_id,
                        "source": "epoch",
                        "type": "article",
                        "title": title,
                        "url": url,
                        "summary": description,
                        "published_date": published_date,
                        "categories": categories,
                        "organization": "Epoch AI",
                        "feed_author": author,
                    }
                )
            )
        except Exception as e:
            logging.warning(f"Failed to parse article card: {e}")
            continue

    return posts


if __name__ == "__main__":
    config = load_config()
    cache_files = config["cache_files"]
    output_files = config["output_files"]

    page_type = "latest"
    cache_filename = cache_files.get(page_type)
    if not cache_filename:
        logging.error(f"No cache file configured for page type: {page_type}")
    else:
        file_path = html_dir / cache_filename
        if file_path.exists():
            logging.info(f"Processing file: {cache_filename}")
            soup = load_html(cache_filename)
            if soup:
                posts = parse_latest_page(soup)
                if posts:
                    favicon = config.get("favicon") or f"{BASE_URL}/favicon.ico"
                    output_filename = output_files.get(page_type, cache_filename.replace(".html", ".xml"))
                    feed_path = parsed_dir / output_filename

                    write_atom_feed(
                        feed_path,
                        posts,
                        feed_title="Epoch AI Latest",
                        feed_link=f"{BASE_URL}/latest",
                        feed_icon=favicon,
                    )
                    logging.info(f"Saved {len(posts)} entries to {output_filename}")
                else:
                    logging.error("No posts to save")
            else:
                logging.error(f"Failed to load HTML from {cache_filename}")
        else:
            logging.error(f"Required cache file not found: {cache_filename}")
