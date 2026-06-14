"""Parse Udio blog posts from cached Feather blog HTML.

Cache file (from fetch_html.py):
  - udio_blog.html

Output to feeds/:
  - udio_blog.xml
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

BASE_URL = "https://www.udio.com"


def load_config():
    """Load site configuration from html.json"""
    return load_site_config("udio")


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
    """Parse date strings like 'Nov 19, 2025' or '2025-11-19' to ISO format."""
    if not date_str:
        return None
    date_str = date_str.strip()
    for fmt in ("%Y-%m-%d", "%b %d, %Y", "%B %d, %Y"):
        try:
            return (
                datetime.strptime(date_str, fmt)
                .replace(tzinfo=timezone.utc)
                .isoformat()
            )
        except ValueError:
            continue
    return None


def parse_blog_page(soup: BeautifulSoup) -> list[dict]:
    """Extract blog posts from the Feather blog HTML.

    The page has:
      - .saas-featured-article and .saas-article cards
      - h3.article-title for title
      - time element for date
      - a[href^='/blog/'] for link
      - .article-tag span for categories
    """
    if not soup:
        return []

    posts = []
    seen = set()
    cards = soup.select(".saas-featured-article, .saas-article")

    for card in cards:
        try:
            title_el = card.select_one(".article-title")
            if not title_el:
                continue
            title = title_el.get_text(strip=True)
            if not title:
                continue

            link_el = card.select_one("a[href^='/blog/']")
            if not link_el:
                continue
            href = link_el.get("href", "")
            if href in seen:
                continue
            seen.add(href)
            if not href:
                continue
            url = f"{BASE_URL}{href}"

            date_el = card.select_one("time")
            date_str = ""
            if date_el:
                date_str = date_el.get("datetime", "") or date_el.get_text(strip=True)
            published_date = parse_date(date_str) if date_str else datetime.now(timezone.utc).isoformat()

            categories = []
            for tag_el in card.select(".article-tag"):
                tag_text = tag_el.get_text(strip=True)
                if tag_text:
                    categories.append(tag_text)

            slug = href.strip("/").split("/")[-1]
            entry_id = hashlib.md5(f"udio_blog_{slug}".encode()).hexdigest()

            posts.append(
                compact(
                    {
                        "id": entry_id,
                        "source": "udio",
                        "type": "blog",
                        "title": title,
                        "url": url,
                        "published_date": published_date,
                        "categories": categories,
                        "organization": "Udio",
                    }
                )
            )
        except Exception as e:
            logging.warning(f"Failed to parse article: {e}")
            continue

    return posts


if __name__ == "__main__":
    config = load_config()
    cache_files = config["cache_files"]

    page_type = "blog"
    cache_filename = cache_files.get(page_type)
    if not cache_filename:
        logging.error(f"No cache file configured for page type: {page_type}")
    else:
        file_path = html_dir / cache_filename
        if file_path.exists():
            logging.info(f"Processing file: {cache_filename}")
            soup = load_html(cache_filename)
            if soup:
                posts = parse_blog_page(soup)
                if posts:
                    favicon = config.get("favicon") or f"{BASE_URL}/favicon.ico"
                    output_filename = cache_filename.replace(".html", ".xml")
                    feed_path = parsed_dir / output_filename

                    write_atom_feed(
                        feed_path,
                        posts,
                        feed_title="Udio Blog",
                        feed_link=f"{BASE_URL}/blog",
                        feed_icon=favicon,
                    )
                    logging.info(f"Saved {len(posts)} entries to {output_filename}")
                else:
                    logging.error("No posts to save")
            else:
                logging.error(f"Failed to load HTML from {cache_filename}")
        else:
            logging.error(f"Required cache file not found: {cache_filename}")
