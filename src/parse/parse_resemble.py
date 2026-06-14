"""Parse Resemble AI resources from cached Webflow HTML.

Cache file (from fetch_html.py):
  - resemble_resources.html

Output to feeds/:
  - resemble_resources.xml

Page structure: .w-dyn-item cards with link text like:
  "Blog•Jun 10, 2026Chatterbox Multilingual v3: TTS..."
  "•Jun 12, 2026The Deepfake Watchlist: Week of..."

When split by "|": [Type|•|Date|Title|Description]
Or without type: [•|Date|Title|Description]
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

BASE_URL = "https://www.resemble.ai"


def load_config():
    return load_site_config("resemble")


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


def parse_resources_page(soup: BeautifulSoup) -> list[dict]:
    """Extract resource/blog posts from Resemble AI resources page.

    Each .w-dyn-item card contains a link whose text embeds type, date, title, and description.
    The link text when split by separator "|" yields:
      - With type prefix: [Type, "•", Date, Title, Description]
      - Without type:     ["•", Date, Title, Description]
    """
    if not soup:
        return []

    posts = []
    seen = set()

    date_re = re.compile(r"([A-Z][a-z]+ \d{1,2}, \d{4})")

    for card in soup.select(".w-dyn-item"):
        try:
            link_el = card.select_one("a")
            if not link_el:
                continue

            href = link_el.get("href", "")
            link_text = link_el.get_text(separator="|", strip=True)

            # Only process links that contain a date AND are resource paths
            if not date_re.search(link_text):
                continue
            if not href or not href.startswith("/resources/"):
                continue
            if href in seen:
                continue
            seen.add(href)

            parts = [p.strip() for p in link_text.split("|") if p.strip()]
            if len(parts) < 4:
                continue

            # Determine structure based on first part
            if parts[0] == "•":
                # Format: [•, Date, Title, Description]
                date_str = parts[1]
                title = parts[2]
                description = parts[3] if len(parts) > 3 else ""
                article_type = ""
            else:
                # Format: [Type, •, Date, Title, Description]
                article_type = parts[0]
                date_str = parts[2] if len(parts) > 2 else ""
                title = parts[3] if len(parts) > 3 else ""
                description = parts[4] if len(parts) > 4 else ""

            if not title:
                continue

            if not date_str:
                continue

            published_date = parse_date(date_str) or datetime.now(timezone.utc).isoformat()

            slug = href.strip("/").split("/")[-1]
            url = f"{BASE_URL}{href}"
            entry_id = hashlib.md5(f"resemble_resources_{slug}".encode()).hexdigest()

            categories = [article_type] if article_type else []

            posts.append(
                compact(
                    {
                        "id": entry_id,
                        "source": "resemble",
                        "type": "resource",
                        "title": title,
                        "url": url,
                        "summary": description,
                        "published_date": published_date,
                        "categories": categories,
                        "organization": "Resemble AI",
                    }
                )
            )
        except Exception as e:
            logging.warning(f"Failed to parse resource card: {e}")
            continue

    return posts


if __name__ == "__main__":
    config = load_config()
    cache_files = config["cache_files"]
    output_files = config["output_files"]

    page_type = "resources"
    cache_filename = cache_files.get(page_type)

    if not cache_filename:
        logging.error(f"No cache file configured for page type: {page_type}")
    else:
        file_path = html_dir / cache_filename
        if file_path.exists():
            logging.info(f"Processing file: {cache_filename}")
            soup = load_html(cache_filename)
            if soup:
                posts = parse_resources_page(soup)
                if posts:
                    favicon = config.get("favicon") or f"{BASE_URL}/favicon.ico"
                    output_filename = output_files.get(page_type, cache_filename.replace(".html", ".xml"))
                    feed_path = parsed_dir / output_filename

                    write_atom_feed(
                        feed_path,
                        posts,
                        feed_title="Resemble AI Resources",
                        feed_link=f"{BASE_URL}/resources",
                        feed_icon=favicon,
                    )
                    logging.info(f"Saved {len(posts)} entries to {output_filename}")
                else:
                    logging.error("No posts to save")
            else:
                logging.error(f"Failed to load HTML from {cache_filename}")
        else:
            logging.error(f"Required cache file not found: {cache_filename}")
