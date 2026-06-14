"""Parse alphaXiv explore page for top hot papers from cached JS-rendered HTML.

Cache file (from fetch_js.py):
  - alphaxiv_explore.html

Output to feeds/:
  - alphaxiv_hot_papers.xml

The explore page with sort=Hot&interval=90+Days shows papers ordered by
hotness. We extract the top 5 paper links (a[href^="/abs/"]) with titles.
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

BASE_URL = "https://www.alphaxiv.org"


def load_config():
    """Load site configuration from js.json"""
    return load_site_config("alphaxiv", config_name="js.json")


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
    """Parse date strings like '10 Jun 2026' to ISO format."""
    if not date_str:
        return None
    date_str = date_str.strip()
    for fmt in ("%d %b %Y", "%d %B %Y"):
        try:
            return (
                datetime.strptime(date_str, fmt)
                .replace(tzinfo=timezone.utc)
                .isoformat()
            )
        except ValueError:
            continue
    return None


def parse_explore_page(soup: BeautifulSoup) -> list[dict]:
    """Extract top 5 hot papers from the alphaXiv explore page.

    Each paper card has:
      - a[href^='/abs/'] wrapping .tiptap.html-renderer with title
      - span.text-sm.font-medium.whitespace-nowrap.text-text with date (e.g. "10 Jun 2026")
      - Authors in div[aria-haspopup="dialog"] elements
    """
    if not soup:
        return []

    posts = []
    seen = set()

    # Find all paper cards: .rounded-xl containers that have abs links
    # Only the first card has data-onboarding="first-paper-card"
    for card in soup.select('.rounded-xl'):
        if not card.select_one("a[href^='/abs/']"):
            continue
        try:
            link_el = card.select_one("a[href^='/abs/']")
            if not link_el:
                continue
            href = link_el.get("href", "")
            if href in seen:
                continue
            seen.add(href)

            arxiv_id = href.replace("/abs/", "")

            # Title in .tiptap.html-renderer
            title_el = card.select_one(".tiptap.html-renderer")
            title = title_el.get_text(strip=True) if title_el else ""
            if not title or len(title) < 5:
                continue

            # Date in span.text-sm.font-medium
            date_el = card.select_one("span.text-sm.font-medium")
            if not date_el:
                continue
            date_str = date_el.get_text(strip=True)
            published_date = parse_date(date_str) or datetime.now(timezone.utc).isoformat()

            paper_url = f"https://arxiv.org/abs/{arxiv_id}"
            entry_id = hashlib.md5(f"alphaxiv_hot_{arxiv_id}".encode()).hexdigest()

            posts.append(
                compact(
                    {
                        "id": entry_id,
                        "source": "alphaxiv",
                        "type": "paper",
                        "title": title,
                        "url": paper_url,
                        "published_date": published_date,
                        "categories": ["hot"],
                        "organization": "alphaXiv",
                    }
                )
            )

            if len(posts) >= 5:
                break
        except Exception as e:
            logging.warning(f"Failed to parse paper card: {e}")
            continue

    return posts


if __name__ == "__main__":
    config = load_config()
    cache_files = config["cache_files"]
    output_files = config["output_files"]

    page_type = "hot_papers"
    cache_filename = cache_files.get(page_type)
    if not cache_filename:
        logging.error(f"No cache file configured for page type: {page_type}")
    else:
        file_path = html_dir / cache_filename
        if file_path.exists():
            logging.info(f"Processing file: {cache_filename}")
            soup = load_html(cache_filename)
            if soup:
                posts = parse_explore_page(soup)
                if posts:
                    favicon = config.get("favicon") or f"{BASE_URL}/favicon.ico"
                    output_filename = output_files.get(page_type, cache_filename.replace(".html", ".xml"))
                    feed_path = parsed_dir / output_filename

                    write_atom_feed(
                        feed_path,
                        posts,
                        feed_title="alphaXiv Hot Papers (Top 5)",
                        feed_link=f"{BASE_URL}/?sort=Hot&interval=90+Days",
                        feed_icon=favicon,
                    )
                    logging.info(f"Saved {len(posts)} entries to {output_filename}")
                else:
                    logging.error("No posts to save")
            else:
                logging.error(f"Failed to load HTML from {cache_filename}")
        else:
            logging.error(f"Required cache file not found: {cache_filename}")
