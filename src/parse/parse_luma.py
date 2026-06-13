"""Parse Luma AI news page from cached HTML.

Cache file (from fetch_html.py):
  - luma_news.html

Output to feeds/:
  - luma_news.xml
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

BASE_URL = "https://lumalabs.ai"


def load_config():
    """Load site configuration from html.json"""
    return load_site_config("luma")


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
    """Parse date strings like 'Jun 9, 2026' to ISO format."""
    if not date_str:
        return None
    date_str = date_str.strip()
    for fmt in ("%b %d, %Y", "%B %d, %Y"):
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
    """Extract news articles from the Luma news listing page.

    Each article card is inside a <div style="display:contents"> with structure:
      - <span class="...text-secondary">Category</span>
      - <span class="typo-body-s text-secondary">Date (e.g. "Jun 9, 2026")</span>
      - <h3><a class="card-link" href="/news/slug">Title</a></h3>
    """
    if not soup:
        return []

    posts = []

    # Each article is in a div[style="display:contents"] container
    containers = soup.find_all("div", style="display:contents")
    for container in containers:
        try:
            # Title + URL from h3 > a.card-link
            link_el = container.find("a", class_="card-link")
            if not link_el:
                continue
            title = link_el.get_text(strip=True)
            href = link_el.get("href", "")
            if not title or not href:
                continue

            # Decode HTML entities in title (e.g. &amp; -> &)
            import html as html_mod

            title = html_mod.unescape(title)
            url = f"{BASE_URL}{href}" if href.startswith("/") else href

            # Category and date are in sibling spans
            # Structure: <div class="flex items-center gap-2"> <span>Cat</span> <span class="typo-body-s">Date</span> </div>
            date_str = None
            category = None

            date_el = container.find("span", class_="typo-body-s")
            if date_el:
                date_str = date_el.get_text(strip=True)

            # Category is the span before the date span in the flex container
            flex_div = container.find("div", class_=lambda c: c and "flex items-center gap-2" in str(c) if c else False)
            if not flex_div:
                flex_div = date_el.find_parent("div") if date_el else None
            if flex_div:
                cat_el = flex_div.find("span")
                if cat_el and cat_el != date_el:
                    category = cat_el.get_text(strip=True)

            published_date = parse_date(date_str) if date_str else None
            if not published_date:
                published_date = datetime.now(timezone.utc).isoformat()

            item_id = hashlib.md5(f"luma_news_{title}_{href}".encode()).hexdigest()

            categories = [category] if category else []

            posts.append(
                compact(
                    {
                        "id": item_id,
                        "source": "luma",
                        "type": "news",
                        "title": title,
                        "url": url,
                        "published_date": published_date,
                        "categories": categories,
                        "organization": "Luma AI",
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

    page_type = "news"
    cache_filename = cache_files.get(page_type)
    if not cache_filename:
        logging.error(f"No cache file configured for page type: {page_type}")
    else:
        file_path = html_dir / cache_filename
        if file_path.exists():
            logging.info(f"Processing Luma news file: {cache_filename}")
            soup = load_html(cache_filename)
            if soup:
                posts = parse_news_page(soup)
                if posts:
                    favicon = config.get("favicon") or f"{BASE_URL}/favicon.ico"
                    output_filename = cache_filename.replace(".html", ".xml")
                    feed_path = parsed_dir / output_filename

                    write_atom_feed(
                        feed_path,
                        posts,
                        feed_title="Luma AI News",
                        feed_link="https://lumalabs.ai/news",
                        feed_icon=favicon,
                    )
                    logging.info(f"Saved {len(posts)} entries to {output_filename}")
                else:
                    logging.error("No posts to save")
            else:
                logging.error(f"Failed to load HTML from {cache_filename}")
        else:
            logging.error(f"Required cache file not found: {cache_filename}")
