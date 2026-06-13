"""Parse Black Forest Labs blog and research pages from cached HTML.

Cache files (from fetch_html.py):
  - bfl_blog.html
  - bfl_research.html

Output to feeds/:
  - bfl_blog.xml
  - bfl_research.xml
"""

import hashlib
import json
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

BASE_URL = "https://bfl.ai"


def load_config():
    """Load site configuration from html.json"""
    return load_site_config("bfl")


def load_html(filename):
    """Load HTML content from cache file"""
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
    """Parse date strings like 'June 4, 2026' or 'March 3, 2026' to ISO format."""
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


def parse_blog_page(soup) -> list[dict]:
    """Extract blog posts from the blog listing page.

    The page has:
      - A hero/featured post with h3 title, date span, p excerpt, a link
      - Remaining posts as <article> elements with:
        - <time datetime="..."> for date
        - <h2> for title
        - <p class="text-bf-body-2-regular"> for excerpt
        - <a href="/blog/slug"> for link
        - <ul> with category badges
    """
    if not soup:
        return []

    posts = []

    # Extract all article elements (remaining posts)
    articles = soup.find_all("article")
    for article in articles:
        try:
            # Title in h2
            title_el = article.find("h2")
            if not title_el:
                continue
            title = title_el.get_text(strip=True)
            if not title:
                continue

            # Date from <time datetime="...">
            time_el = article.find("time")
            published_date = None
            if time_el:
                dt = time_el.get("datetime", "")
                if dt:
                    published_date = dt
                else:
                    date_str = time_el.get_text(strip=True)
                    published_date = parse_date(date_str)
            if not published_date:
                published_date = datetime.now(timezone.utc).isoformat()

            # Excerpt from description paragraph
            excerpt = None
            desc_el = article.find(
                "p", class_=lambda c: c and "text-bf-body-2-regular" in str(c) if c else False
            )
            if desc_el:
                excerpt = desc_el.get_text(strip=True)

            # Link
            link_el = article.find("a", href=re.compile(r"^/blog/"))
            href = link_el.get("href", "") if link_el else ""
            url = f"{BASE_URL}{href}" if href else BASE_URL

            # Categories
            categories = []
            for cat_el in article.find_all("li"):
                cat_text = cat_el.get_text(strip=True)
                if cat_text and cat_text not in ("Read more",):
                    categories.append(cat_text)

            item_id = hashlib.md5(f"bfl_blog_{title}_{href}".encode()).hexdigest()

            posts.append(
                compact(
                    {
                        "id": item_id,
                        "source": "bfl",
                        "type": "blog",
                        "title": title,
                        "url": url,
                        "summary": excerpt,
                        "published_date": published_date,
                        "categories": categories,
                        "organization": "Black Forest Labs",
                    }
                )
            )

        except Exception as e:
            logging.warning(f"Failed to parse blog article: {e}")
            continue

    return posts


def parse_research_page(soup) -> list[dict]:
    """Extract research articles from the research listing page.

    Each research item is in a div with classes 'py-3.5 lg:py-7':
      - <h3> for title
      - <p> for description/excerpt
      - <div> with date text
      - <a href="/research/slug"> for link
    """
    if not soup:
        return []

    posts = []

    # Research items are in divs with py-3.5 lg:py-7 classes
    items = soup.find_all(
        "div",
        class_=lambda c: c and "py-3" in str(c) and "lg:py-7" in str(c) if c else False,
    )

    for item in items:
        try:
            # Title in h3
            title_el = item.find("h3")
            if not title_el:
                continue
            title = title_el.get_text(strip=True)
            if not title:
                continue

            # Description in a p tag
            desc_el = item.find("p")
            excerpt = desc_el.get_text(strip=True) if desc_el else None

            # Date in a div with tracking-wider class (or similar)
            date_el = item.find(
                "div",
                class_=lambda c: c and "tracking-wider" in str(c) if c else False,
            )
            date_str = date_el.get_text(strip=True) if date_el else None
            published_date = parse_date(date_str) if date_str else None
            if not published_date:
                published_date = datetime.now(timezone.utc).isoformat()

            # Link - could be /research/slug or an external PDF URL
            link_el = item.find("a", href=re.compile(r"^/research/"))
            if not link_el:
                # Fallback: find any link in the item with an href
                link_el = item.find("a", href=True)
            href = link_el.get("href", "") if link_el else ""
            if href.startswith("/"):
                url = f"{BASE_URL}{href}"
            elif href:
                url = href
            else:
                url = BASE_URL

            item_id = hashlib.md5(f"bfl_research_{title}_{href}".encode()).hexdigest()

            posts.append(
                compact(
                    {
                        "id": item_id,
                        "source": "bfl",
                        "type": "research",
                        "title": title,
                        "url": url,
                        "summary": excerpt,
                        "published_date": published_date,
                        "organization": "Black Forest Labs",
                    }
                )
            )

        except Exception as e:
            logging.warning(f"Failed to parse research item: {e}")
            continue

    return posts


def extract_html_data(soup, page_type: str) -> list[dict]:
    """Route to the correct parser based on page type."""
    if page_type == "blog":
        return parse_blog_page(soup)
    elif page_type == "research":
        return parse_research_page(soup)
    else:
        logging.error(f"Unknown page type: {page_type}")
        return []


def save_to_json(posts, filename, page_type: str):
    """Save posts to Atom XML feed file."""
    config = load_config()
    favicon = config.get("favicon") or "https://bfl.ai/favicon.ico"

    output_filename = filename.replace(".html", ".xml")
    feed_path = parsed_dir / output_filename

    titles = {
        "blog": "Black Forest Labs Blog",
        "research": "Black Forest Labs Research",
    }
    links = {
        "blog": f"{BASE_URL}/blog",
        "research": f"{BASE_URL}/research",
    }

    write_atom_feed(
        feed_path,
        posts,
        feed_title=titles.get(page_type, "Black Forest Labs"),
        feed_link=links.get(page_type, BASE_URL),
        feed_icon=favicon,
    )


if __name__ == "__main__":
    config = load_config()
    cache_files = config["cache_files"]

    for page_type, cache_filename in cache_files.items():
        file_path = html_dir / cache_filename
        if file_path.exists():
            logging.info(f"Processing BFL {page_type} file: {cache_filename}")
            soup = load_html(cache_filename)
            if soup:
                posts = extract_html_data(soup, page_type)
                if posts:
                    save_to_json(posts, cache_filename, page_type)
                else:
                    logging.error(f"No posts to save for {page_type}")
            else:
                logging.error(f"Failed to load HTML from {cache_filename}")
        else:
            logging.error(f"Required cache file not found: {cache_filename}")
