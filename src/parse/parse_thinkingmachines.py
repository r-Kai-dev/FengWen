"""Parse Thinking Machines Lab News from cached Hugo HTML.

Cache file (from fetch_html.py):
  - thinkingmachines_news.html

Output to feeds/:
  - thinkingmachines_news.xml
"""

import hashlib
import logging
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

BASE_URL = "https://thinkingmachines.ai"


def load_config():
    """Load site configuration from html.json"""
    return load_site_config("thinkingmachines")


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
    """Parse date strings like 'May 19, 2026' to ISO format."""
    if not date_str:
        return None
    date_str = date_str.strip()
    for fmt in ("%B %d, %Y", "%b %d, %Y"):
        try:
            return (
                datetime.strptime(date_str, fmt)
                .replace(tzinfo=timezone.utc)
                .isoformat()
            )
        except ValueError:
            continue
    return None


def parse_news_page(soup: BeautifulSoup) -> list[dict]:
    """Extract news items from the Hugo-rendered HTML.

    Each news item is in:
      <li>
        <a class="post-item-link" href="/news/slug/">
          <time class="desktop-time">May 19, 2026</time>
          <div class="post-info">
            <div class="post-title">Title</div>
          </div>
        </a>
      </li>
    """
    if not soup:
        return []

    posts = []
    items = soup.select("li a.post-item-link")
    for item in items:
        try:
            href = item.get("href", "")
            if not href or not href.startswith("/news/"):
                continue

            title_el = item.select_one(".post-title")
            if not title_el:
                continue
            title = title_el.get_text(strip=True)
            if not title:
                continue

            date_el = item.select_one("time.desktop-time")
            date_str = date_el.get_text(strip=True) if date_el else ""
            published_date = parse_date(date_str)
            if not published_date:
                published_date = datetime.now(timezone.utc).isoformat()

            url = f"{BASE_URL}{href}"
            slug = href.strip("/").split("/")[-1]
            entry_id = hashlib.md5(f"thinkingmachines_news_{slug}".encode()).hexdigest()

            posts.append(
                compact(
                    {
                        "id": entry_id,
                        "source": "thinkingmachines",
                        "type": "news",
                        "title": title,
                        "url": url,
                        "published_date": published_date,
                        "organization": "Thinking Machines Lab",
                    }
                )
            )
        except Exception as e:
            logging.warning(f"Failed to parse news item: {e}")
            continue

    return posts


if __name__ == "__main__":
    config = load_config()
    cache_files = config["cache_files"]

    page_type = "news"
    cache_filename = cache_files.get(page_type)
    if not cache_filename:
        logging.error(f"No cache file configured for page type: {page_type}")
    else:
        file_path = html_dir / cache_filename
        if file_path.exists():
            logging.info(f"Processing file: {cache_filename}")
            soup = load_html(cache_filename)
            if soup:
                posts = parse_news_page(soup)
                if posts:
                    favicon = config.get("favicon") or f"{BASE_URL}/images/favicon-32x32.png"
                    output_filename = cache_filename.replace(".html", ".xml")
                    feed_path = parsed_dir / output_filename

                    write_atom_feed(
                        feed_path,
                        posts,
                        feed_title="Thinking Machines Lab News",
                        feed_link=f"{BASE_URL}/news/",
                        feed_icon=favicon,
                    )
                    logging.info(f"Saved {len(posts)} entries to {output_filename}")
                else:
                    logging.error("No posts to save")
            else:
                logging.error(f"Failed to load HTML from {cache_filename}")
        else:
            logging.error(f"Required cache file not found: {cache_filename}")
