"""Parse AMI Labs updates from cached Webflow HTML.

Cache file (from fetch_html.py):
  - ami_updates.html

Output to feeds/:
  - ami_updates.xml
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

BASE_URL = "https://amilabs.xyz"


def load_config():
    """Load site configuration from html.json"""
    return load_site_config("ami")


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
    """Parse date strings like 'March 10, 2026' to ISO format."""
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


def parse_updates_page(soup: BeautifulSoup) -> list[dict]:
    """Extract updates from the Webflow HTML.

    Each update is in a div with class 'div-content-other' containing
    paragraphs with dates and content.
    """
    if not soup:
        return []

    posts = []
    for div in soup.select(".div-content-other"):
        try:
            headings = div.find_all("p", class_=lambda c: c and "bold" in (c or ""))
            full_text = div.get_text(separator=" ", strip=True)

            # Try to find date and title from the first bold paragraph
            title = None
            date_str = None
            for p in headings:
                text = p.get_text(strip=True)
                date_match = re.search(r"([A-Z][a-z]+ \d{1,2}, \d{4})", text)
                if date_match:
                    date_str = date_match.group(1)
                    # Title is the text after the date
                    title = text
                    break

            if not title:
                # Fallback: use first paragraph
                first_p = div.find("p")
                if first_p:
                    title = first_p.get_text(strip=True)[:100]
                    date_match = re.search(r"([A-Z][a-z]+ \d{1,2}, \d{4})", title)
                    if date_match:
                        date_str = date_match.group(1)

            if not title:
                continue

            published_date = parse_date(date_str) if date_str else datetime.now(timezone.utc).isoformat()

            # Clean title
            title = re.sub(r'<[^>]+>', '', title).strip()
            title = re.sub(r'^\*+|\*+$', '', title).strip()
            # Extract meaningful title after date prefix
            if " - " in title:
                title = title.split(" - ", 1)[1].strip()
            elif date_str and date_str in title:
                title = title.replace(date_str, "").strip(" -")

            summary = full_text[:500] if full_text else None

            slug = date_str.lower().replace(",", "").replace(" ", "-") if date_str else "update"
            entry_id = hashlib.md5(f"ami_updates_{date_str}_{title}".encode()).hexdigest()

            posts.append(
                compact(
                    {
                        "id": entry_id,
                        "source": "ami",
                        "type": "updates",
                        "title": title,
                        "url": f"{BASE_URL}/updates",
                        "summary": summary,
                        "published_date": published_date,
                        "organization": "AMI Labs",
                    }
                )
            )
        except Exception as e:
            logging.warning(f"Failed to parse update: {e}")
            continue

    return posts


if __name__ == "__main__":
    config = load_config()
    cache_files = config["cache_files"]

    page_type = "updates"
    cache_filename = cache_files.get(page_type)
    if not cache_filename:
        logging.error(f"No cache file configured for page type: {page_type}")
    else:
        file_path = html_dir / cache_filename
        if file_path.exists():
            logging.info(f"Processing file: {cache_filename}")
            soup = load_html(cache_filename)
            if soup:
                posts = parse_updates_page(soup)
                if posts:
                    favicon = config.get("favicon") or f"{BASE_URL}/favicon.ico"
                    output_filename = cache_filename.replace(".html", ".xml")
                    feed_path = parsed_dir / output_filename

                    write_atom_feed(
                        feed_path,
                        posts,
                        feed_title="AMI Labs Updates",
                        feed_link=f"{BASE_URL}/updates",
                        feed_icon=favicon,
                    )
                    logging.info(f"Saved {len(posts)} entries to {output_filename}")
                else:
                    logging.error("No posts to save")
            else:
                logging.error(f"Failed to load HTML from {cache_filename}")
        else:
            logging.error(f"Required cache file not found: {cache_filename}")
