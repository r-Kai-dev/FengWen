"""Parse LTX blog and newsroom from cached Webflow HTML.

Cache files (from fetch_html.py):
  - ltx_blog.html
  - ltx_newsroom.html

Output to feeds/:
  - ltx_blog.xml
  - ltx_newsroom.xml

Blog page structure: .w-dyn-item cards containing:
  h3.blog-title (inside a.blog-title-wrap) → title + href
  .text-truncate-2 → excerpt
  .author-date-wrap → last .post-author-new = date
  a.post-author-wrap-2 .post-author-new → author (optional)

Newsroom page structure:
  .w-dyn-item > a.news-item-wrap
    h3.news-title → title
    a.news-item-wrap → href
    .event1_date-wrapper → join children text = "Mar 5 2026"
    p.text-size-small → excerpt
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

BASE_URL = "https://ltx.io"


def load_config():
    return load_site_config("ltx", config_name="js.json")


def load_html(filename: str) -> BeautifulSoup | None:
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
    if not date_str:
        return None
    date_str = date_str.strip()
    for fmt in ("%B %d, %Y", "%b %d, %Y", "%b %d %Y"):
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
    """Extract blog posts from the LTX blog listing page.

    There are two card structures:
      - Featured card: .blog7_featured-item-content
      - Regular cards: .blog-item-dynamic (inside .w-dyn-item)

    Approach: find all .w-dyn-item that contain h3.blog-title, extract from each.
    """
    if not soup:
        return []

    posts = []
    seen = {}  # href → index in posts list

    for item in soup.select(".w-dyn-item"):
        try:
            title_el = item.select_one("h3.blog-title")
            if not title_el:
                continue
            title = title_el.get_text(strip=True)
            if not title or len(title) < 10:
                continue

            link_el = item.select_one("a.blog-title-wrap")
            if not link_el:
                link_el = title_el.find_parent("a")
            href = link_el.get("href", "") if link_el else ""
            if not href:
                continue
            href_rel = href
            if href_rel.startswith(BASE_URL):
                href_rel = href_rel[len(BASE_URL):]

            # Category, excerpt, author, date
            category_el = item.select_one(".blog-category")
            category = category_el.get_text(strip=True) if category_el else ""
            excerpt_el = item.select_one(".text-truncate-2")
            excerpt = excerpt_el.get_text(strip=True) if excerpt_el else ""
            author = ""
            author_link = item.select_one("a.post-author-wrap-2 .post-author-new")
            if author_link:
                author = author_link.get_text(strip=True)
            date_str = ""
            author_wrap = item.select_one(".author-date-wrap")
            if author_wrap:
                date_els = author_wrap.select(".post-author-new")
                if date_els:
                    date_str = date_els[-1].get_text(strip=True)
            published_date = parse_date(date_str) or datetime.now(timezone.utc).isoformat()

            slug = href_rel.strip("/").split("/")[-1]
            url = href if href.startswith("http") else f"{BASE_URL}{href}"
            entry_id = hashlib.md5(f"ltx_blog_{slug}".encode()).hexdigest()

            entry = compact(
                {
                    "id": entry_id,
                    "source": "ltx",
                    "type": "blog",
                    "title": title,
                    "url": url,
                    "summary": excerpt,
                    "published_date": published_date,
                    "categories": [category] if category else [],
                    "feed_author": author,
                    "organization": "LTX",
                }
            )

            if href_rel in seen:
                # Keep the entry with the older (original publication) date
                prev_idx = seen[href_rel]
                prev_date = posts[prev_idx].get("published_date", "")
                if published_date < prev_date:
                    posts[prev_idx] = entry
                continue

            seen[href_rel] = len(posts)
            posts.append(entry)

        except Exception as e:
            logging.warning(f"Failed to parse blog card: {e}")
            continue

    return posts


def parse_newsroom_page(soup: BeautifulSoup) -> list[dict]:
    """Extract news items from the LTX newsroom.

    Card structure: .w-dyn-item > a.news-item-wrap
      h3.news-title → title
      a.news-item-wrap → href
      .event1_date-wrapper → join children text = "Mar 5 2026"
      p.text-size-small → excerpt
    """
    if not soup:
        return []

    posts = []
    seen = set()

    for item in soup.select(".w-dyn-item"):
        try:
            # The main link wraps the whole card
            main_link = item.select_one("a.news-item-wrap")
            if not main_link:
                # Try any link inside the item that goes to /newsroom/
                main_link = item.select_one('a[href*="/newsroom/"]')
            if not main_link:
                continue
            href = main_link.get("href", "")
            if not href or href in seen:
                continue
            seen.add(href)

            # Title
            title_el = item.select_one("h3.news-title")
            if not title_el:
                continue
            title = title_el.get_text(strip=True)
            if not title or len(title) < 5:
                continue

            # Date — join the date wrapper children
            date_str = ""
            date_wrap = item.select_one(".event1_date-wrapper")
            if date_wrap:
                date_parts = [
                    el.get_text(strip=True)
                    for el in date_wrap.find_all(["div", "span"])
                    if el.get_text(strip=True)
                ]
                date_str = " ".join(date_parts)

            # Excerpt
            excerpt_el = item.select_one("p.text-size-small")
            excerpt = excerpt_el.get_text(strip=True) if excerpt_el else ""

            published_date = parse_date(date_str) or datetime.now(timezone.utc).isoformat()

            slug = href.strip("/").split("/")[-1]
            url = href if href.startswith("http") else f"{BASE_URL}{href}"
            entry_id = hashlib.md5(f"ltx_newsroom_{slug}".encode()).hexdigest()

            posts.append(
                compact(
                    {
                        "id": entry_id,
                        "source": "ltx",
                        "type": "news",
                        "title": title,
                        "url": url,
                        "summary": excerpt,
                        "published_date": published_date,
                        "organization": "LTX",
                    }
                )
            )
        except Exception as e:
            logging.warning(f"Failed to parse newsroom card: {e}")
            continue

    return posts


if __name__ == "__main__":
    config = load_config()
    cache_files = config["cache_files"]
    output_files = config["output_files"]

    for page_type, cache_filename in cache_files.items():
        file_path = html_dir / cache_filename
        if not file_path.exists():
            logging.warning(f"Cache file not found: {cache_filename}")
            continue

        logging.info(f"Processing file: {cache_filename}")
        soup = load_html(cache_filename)

        if not soup:
            continue

        if page_type == "blog":
            posts = parse_blog_page(soup)
            title_text = "LTX Blog"
            link_text = f"{BASE_URL}/blog"
        elif page_type == "newsroom":
            posts = parse_newsroom_page(soup)
            title_text = "LTX News"
            link_text = f"{BASE_URL}/newsroom"
        else:
            continue

        if posts:
            favicon = config.get("favicon") or f"{BASE_URL}/favicon.ico"
            output_filename = output_files.get(page_type, cache_filename.replace(".html", ".xml"))
            feed_path = parsed_dir / output_filename

            write_atom_feed(
                feed_path,
                posts,
                feed_title=title_text,
                feed_link=link_text,
                feed_icon=favicon,
            )
            logging.info(f"Saved {len(posts)} entries to {output_filename}")
        else:
            logging.error(f"No posts to save for {page_type}")
