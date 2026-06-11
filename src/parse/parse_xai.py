"""Parse xAI news page from cached HTML.

Cache file (from fetch_html.py):
  - x-ai_news.html

Output to feeds/:
  - x-ai_news.xml
"""

import hashlib
import json
import logging
import re
from datetime import datetime, timezone
from pathlib import Path

from bs4 import BeautifulSoup
from config_util import compact, load_site_config, write_atom_feed

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)

project_dir = Path(__file__).resolve().parent.parent.parent
html_dir = project_dir / "html_cache"
parsed_dir = project_dir / "feeds"
parsed_dir.mkdir(exist_ok=True)

BASE_URL = "https://x.ai"


def load_config():
    """Load site configuration from html.json"""
    return load_site_config("x-ai")


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
    """Parse date strings like 'Jun 11, 2026' or 'May 29, 2026' to ISO format."""
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


def _extract_featured_cards(soup):
    """Extract posts from the featured/hero card section (first article).

    This is the largest card with a two-column grid layout:
      <a class="group/card block lg:grid ..." href="/news/slug">
        <div class="border-primary/[0.06] ...">[image]</div>
        <div class="mt-4 lg:order-1 lg:mt-0">
          <div class="lg:hidden">
            <div class="text-primary/40 ...">Date</div>
            <h2 class="...">Title</h2>
          </div>
          <div class="hidden lg:block">
            <div class="text-primary/25 text-xs">Date</div>
            <h1 class="...">Title</h1>
            <p class="...">Description</p>
          </div>
        </div>
      </a>
    """
    posts = []

    # Featured card has the class "lg:grid" (only the first article has this)
    cards = soup.select('a[class*="group/card"][class*="lg:grid"]')

    for card in cards:
        try:
            href = card.get("href", "")
            if not href or not href.startswith("/news/"):
                continue

            # Desktop section has the full title, date, and description
            desktop_section = card.select_one('[class*="hidden"][class*="lg:block"]')
            mobile_section = card.select_one('[class*="lg:hidden"]')

            title = None
            date_str = None
            description = None

            if desktop_section:
                # Title is in h1
                title_el = desktop_section.find("h1")
                title = title_el.get_text(strip=True) if title_el else None

                # Date is in a div with text-xs
                date_el = desktop_section.find(
                    "div", class_=lambda c: c and "text-xs" in str(c) if c else False
                )
                date_str = date_el.get_text(strip=True) if date_el else None

                # Description is in a p
                desc_el = desktop_section.find("p")
                description = desc_el.get_text(strip=True) if desc_el else None

            if not title and mobile_section:
                # Mobile section: title in h2
                title_el = mobile_section.find("h2")
                title = title_el.get_text(strip=True) if title_el else None

                if not date_str:
                    date_el = mobile_section.find(
                        "div", class_=lambda c: c and "text-primary" in str(c) if c else False
                    )
                    date_str = date_el.get_text(strip=True) if date_el else None

            if not title:
                continue

            published_date = parse_date(date_str) if date_str else None
            if not published_date:
                published_date = datetime.now(timezone.utc).isoformat()

            url = f"{BASE_URL}{href}"
            item_id = hashlib.md5(f"x-ai_news_{title}_{href}".encode()).hexdigest()

            posts.append(
                compact(
                    {
                        "id": item_id,
                        "source": "x-ai",
                        "type": "news",
                        "title": title,
                        "url": url,
                        "summary": description,
                        "published_date": published_date,
                        "organization": "xAI",
                    }
                )
            )
            logging.info(f"Extracted featured post: {title[:50]}...")

        except Exception as e:
            logging.warning(f"Failed to parse featured card: {e}")
            continue

    return posts


def _extract_image_cards(soup):
    """Extract posts from image cards (medium-sized, with images but no grid layout).

    These have class "group/card block" (without "lg:grid" or "hover:bg-primary"):
      <a class="group/card block" href="/news/slug">
        <div class="border-primary/[0.06] ...">[image]</div>
        <div class="mt-3">
          <div class="text-primary/40 ...">Date</div>
          <h3 class="...">Title</h3>
        </div>
      </a>
    """
    posts = []

    # These cards have class="group/card block" (no lg:grid, no hover:bg-primary)
    # BeautifulSoup calls the lambda with individual class strings, so we first
    # get all group/card elements, then filter by checking the full class list.
    all_cards = soup.find_all(
        "a", class_=lambda c: c and "group/card" in str(c) if c else False
    )
    cards = []
    for card in all_cards:
        cls_attr = card.get("class", [])
        if not isinstance(cls_attr, (list, tuple)):
            continue
        cls_strs = [str(c) for c in cls_attr]
        if "group/card" in cls_strs and "block" in cls_strs:
            has_lg_grid = any("lg:grid" in c for c in cls_strs)
            has_hover = any("hover:bg-primary" in c for c in cls_strs)
            if not has_lg_grid and not has_hover:
                cards.append(card)

    for card in cards:
        try:
            href = card.get("href", "")
            if not href or not href.startswith("/news/"):
                continue

            # Title is in h3
            title_el = card.find("h3")
            if not title_el:
                continue
            title = title_el.get_text(strip=True)
            if not title:
                continue

            # Date is in a div with text-[11px]
            date_el = card.find(
                "div", class_=lambda c: c and "text-[11px]" in str(c) if c else False
            )
            date_str = date_el.get_text(strip=True) if date_el else None
            published_date = parse_date(date_str) if date_str else None
            if not published_date:
                published_date = datetime.now(timezone.utc).isoformat()

            url = f"{BASE_URL}{href}"
            item_id = hashlib.md5(f"x-ai_news_{title}_{href}".encode()).hexdigest()

            posts.append(
                compact(
                    {
                        "id": item_id,
                        "source": "x-ai",
                        "type": "news",
                        "title": title,
                        "url": url,
                        "published_date": published_date,
                        "organization": "xAI",
                    }
                )
            )
            logging.info(f"Extracted image card: {title[:50]}...")

        except Exception as e:
            logging.warning(f"Failed to parse image card: {e}")
            continue

    return posts


def _extract_list_cards(soup):
    """Extract posts from the list-style cards (remaining articles without images).

    These cards are simpler:
      <a class="group/card hover:bg-primary/[0.02] ..." href="/news/slug">
        <div class="flex-1">
          <h3 class="...">Title</h3>
          <p class="...">Description</p>
        </div>
        <div class="text-primary/40 ...">Date</div>
      </a>
    """
    posts = []

    # List cards have "group/card" but NOT "lg:grid" — they use the flex layout
    cards = soup.select(
        'a[class*="group/card"][class*="hover:bg-primary"]'
    )

    for card in cards:
        try:
            href = card.get("href", "")
            if not href or not href.startswith("/news/"):
                continue

            # Title is in h3 inside flex-1 div
            flex_div = card.find("div", class_=lambda c: c and "flex-1" in str(c) if c else False)
            if not flex_div:
                continue

            title_el = flex_div.find("h3")
            if not title_el:
                continue
            title = title_el.get_text(strip=True)
            if not title:
                continue

            # Description (optional) is the p inside flex-1
            desc_el = flex_div.find("p")
            description = desc_el.get_text(strip=True) if desc_el else None

            # Date is in a standalone div outside flex-1
            date_el = card.find(
                "div",
                class_=lambda c: (
                    c and "text-primary" in str(c) and "shrink-0" in str(c) if c else False
                ),
            )
            date_str = date_el.get_text(strip=True) if date_el else None
            published_date = parse_date(date_str) if date_str else None
            if not published_date:
                published_date = datetime.now(timezone.utc).isoformat()

            url = f"{BASE_URL}{href}"
            item_id = hashlib.md5(f"x-ai_news_{title}_{href}".encode()).hexdigest()

            posts.append(
                compact(
                    {
                        "id": item_id,
                        "source": "x-ai",
                        "type": "news",
                        "title": title,
                        "url": url,
                        "summary": description,
                        "published_date": published_date,
                        "organization": "xAI",
                    }
                )
            )
            logging.info(f"Extracted list post: {title[:50]}...")

        except Exception as e:
            logging.warning(f"Failed to parse list card: {e}")
            continue

    return posts


def extract_html_data(soup):
    """Extract all news posts from the xAI news page."""
    if not soup:
        logging.error("No soup provided")
        return []

    all_posts = []

    # Extract featured cards
    featured = _extract_featured_cards(soup)
    all_posts.extend(featured)

    # Extract intermediate image cards (group/card block without lg:grid)
    image_cards = _extract_image_cards(soup)
    all_posts.extend(image_cards)

    # Extract list cards
    list_posts = _extract_list_cards(soup)
    all_posts.extend(list_posts)

    # Deduplicate by JSON serialization
    dedup_list = [
        json.loads(entry) for entry in list({json.dumps(d) for d in all_posts})
    ]

    # Sort by published_date descending (newest first)
    dedup_list.sort(
        key=lambda x: x.get("published_date", ""),
        reverse=True,
    )

    logging.info(
        f"Successfully parsed {len(dedup_list)} unique posts from xAI news"
    )
    return dedup_list


def save_to_json(posts, filename):
    """Save posts to Atom XML feed file."""
    config = load_config()
    favicon = config.get("favicon") or (
        config.get("url", "").rstrip("/") + "/favicon.ico"
    )

    # Derive output filename from cache filename (e.g., x-ai_news.html -> x-ai_news.xml)
    output_filename = filename.replace(".html", ".xml")
    feed_path = parsed_dir / output_filename

    write_atom_feed(
        feed_path,
        posts,
        feed_title="xAI News",
        feed_link=f"{BASE_URL}/news",
        feed_icon=favicon,
    )


if __name__ == "__main__":
    config = load_config()
    cache_files = config["cache_files"]

    for page_type, cache_filename in cache_files.items():
        file_path = html_dir / cache_filename
        if file_path.exists():
            logging.info(f"Processing xAI {page_type} file: {cache_filename}")
            soup = load_html(cache_filename)
            if soup:
                posts = extract_html_data(soup)
                if posts:
                    save_to_json(posts, cache_filename)
                else:
                    logging.error("No posts to save")
            else:
                logging.error(f"Failed to load HTML from {cache_filename}")
        else:
            logging.error(f"Required cache file not found: {cache_filename}")
