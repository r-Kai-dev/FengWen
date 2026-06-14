"""Parse Unsloth blog posts from cached JS-rendered HTML.

Cache file (from fetch_js.py):
  - unsloth_blog.html

Output to feeds/:
  - unsloth_blog.xml
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

BASE_URL = "https://unsloth.ai"


def load_config():
    """Load site configuration from js.json"""
    return load_site_config("unsloth", config_name="js.json")


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
    """Parse date strings like 'May 11, 2026' to ISO format."""
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


def parse_blog_page(soup: BeautifulSoup) -> list[dict]:
    """Extract blog posts from the Unsloth Remix-rendered HTML.

    Each blog post link (a[href^='/blog/']) is followed by a text node
    containing the date (e.g. "May 11, 2026"). We traverse next_sibling
    to find the associated date.
    """
    if not soup:
        return []

    posts = []
    seen = set()
    date_re = re.compile(r"^([A-Z][a-z]{2}\s+\d{1,2},\s+\d{4})")

    # Select blog links (handle both absolute and relative URLs)
    candidates = []
    for a in soup.find_all('a', href=True):
        href = a.get('href', '')
        if '/blog/' in href and 'unsloth.ai' in href:
            candidates.append(a)
        elif href.startswith('/blog/'):
            candidates.append(a)
    # Also look for non-/blog/ docs links that appear in the blog listing
    for a in soup.find_all('a', href=True):
        href = a.get('href', '')
        if '/docs/' not in href:
            continue
        if 'unsloth.ai' not in href and not href.startswith('/'):
            continue
        title = a.get_text(strip=True)
        # Only include if it has a date nearby (it's a blog-card-style entry)
        if title and len(title) >= 10:
            node = a
            for _ in range(20):
                if node.next_sibling:
                    node = node.next_sibling
                    if hasattr(node, 'string') and node.string:
                        if date_re.match(node.string.strip()):
                            candidates.append(a)
                            break
                    elif hasattr(node, 'get_text'):
                        if date_re.match(node.get_text(strip=True)):
                            candidates.append(a)
                            break
                else:
                    if node.parent:
                        node = node.parent
                    else:
                        break

    for a in candidates:
        href = a.get("href", "")
        title = a.get_text(strip=True)
        if not title or len(title) < 10:
            continue
        if href in seen:
            continue
        seen.add(href)

        # Find date by walking next_sibling from the link and its ancestors
        date_str = ""
        node = a
        for _ in range(30):
            if node.next_sibling:
                node = node.next_sibling
                # Check text node siblings
                if hasattr(node, 'string') and node.string:
                    text = node.string.strip()
                    m = date_re.match(text)
                    if m:
                        date_str = m.group(1)
                        break
                # Check element siblings (e.g. <span>Jun 11, 2026</span>)
                elif hasattr(node, 'get_text'):
                    text = node.get_text(strip=True)
                    m = date_re.match(text)
                    if m:
                        date_str = m.group(1)
                        break
            else:
                if node.parent:
                    node = node.parent
                else:
                    break

        published_date = parse_date(date_str) if date_str else datetime.now(timezone.utc).isoformat()

        url = href if href.startswith("http") else f"{BASE_URL}{href}"
        slug = href.rstrip("/").split("/")[-1]
        entry_id = hashlib.md5(f"unsloth_blog_{slug}".encode()).hexdigest()

        posts.append(
            compact(
                {
                    "id": entry_id,
                    "source": "unsloth",
                    "type": "blog",
                    "title": title,
                    "url": url,
                    "published_date": published_date,
                    "organization": "Unsloth",
                }
            )
        )

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
                        feed_title="Unsloth Blog",
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
