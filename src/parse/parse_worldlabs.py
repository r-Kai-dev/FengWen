"""Parse World Labs blog posts from cached server-rendered HTML.

World Labs blog (https://www.worldlabs.ai/blog) is a Next.js App Router page.
The initial HTML payload includes fully server-rendered blog cards as visible
DOM elements — no RSC extraction needed.

Cache file (from fetch_html.py):
  - worldlabs_blog.html

Output to feeds/:
  - worldlabs_blog.xml

Card structure: each blog card is an <a> with href="/blog/..." whose text
nodes contain date, author, title, description, and "Read More →".
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

BASE_URL = "https://www.worldlabs.ai"
ORG_KEY = "worldlabs"


def load_config():
    return load_site_config(ORG_KEY, config_name="html.json")


def load_html(filename: str) -> BeautifulSoup | None:
    file_path = html_dir / filename
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            return BeautifulSoup(f.read(), "html.parser")
    except FileNotFoundError:
        logging.error(f"File not found: {file_path}")
        return None
    except Exception as e:
        logging.error(f"Error reading {file_path}: {e}")
        return None


def parse_date(date_str: str) -> str | None:
    """Parse dates like 'June 3, 2026' to ISO format."""
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
    """Extract blog posts from the server-rendered HTML.

    Each article card is an <a> with href="/blog/..." whose text nodes
    contain date, author, title, description, and "Read More →".
    """
    if not soup:
        return []

    posts = []
    seen = set()
    date_re = re.compile(r"^([A-Z][a-z]+ \d{1,2}, \d{4})")

    for a in soup.select('a[href*="/blog/"]'):
        href = a.get("href", "")
        if not href or "/blog/" not in href or href in seen:
            continue

        text = a.get_text(separator="|", strip=True)
        if not text or "Read More" not in text:
            continue

        seen.add(href)

        parts = [p.strip() for p in text.split("|") if p.strip()]
        if len(parts) < 3:
            continue

        # Find date in parts
        date_str = ""
        date_idx = -1
        for i, p in enumerate(parts):
            m = date_re.match(p)
            if m:
                date_str = m.group(1)
                date_idx = i
                break
        if not date_str or date_idx < 0:
            continue

        remaining_parts = parts[date_idx + 1 :]

        # Author (optional, between date and title)
        author = ""
        if remaining_parts and remaining_parts[0] in (
            "World Labs team",
            "Dr. Fei-Fei Li",
            "Fei‑Fei Li",
            "Christoph Lassner",
        ):
            author = remaining_parts[0]
            remaining_parts = remaining_parts[1:]

        # Find "Read More" boundary
        read_more_idx = -1
        for i, p in enumerate(remaining_parts):
            if "Read More" in p:
                read_more_idx = i
                break
        if read_more_idx == -1:
            continue

        content_parts = remaining_parts[:read_more_idx]
        if not content_parts:
            continue

        title = content_parts[0]
        description = " ".join(content_parts[1:]) if len(content_parts) > 1 else ""

        if not title:
            continue

        # Normalize the slug — handle edge case of /blog/blog/slug
        slug = href.strip("/")
        if slug.startswith("blog/"):
            slug = slug[5:]
        # Also handle external links like substack
        if slug.startswith("blog/"):
            slug = slug[5:]

        url = href if href.startswith("http") else f"{BASE_URL}{href}"
        published_date = parse_date(date_str) or datetime.now(timezone.utc).isoformat()
        entry_id = hashlib.md5(f"worldlabs_blog_{slug}".encode()).hexdigest()

        posts.append(
            compact(
                {
                    "id": entry_id,
                    "source": ORG_KEY,
                    "type": "blog",
                    "title": title,
                    "url": url,
                    "summary": description,
                    "published_date": published_date,
                    "feed_author": author,
                    "organization": "World Labs",
                }
            )
        )

    return posts


if __name__ == "__main__":
    config = load_config()
    cache_files = config["cache_files"]

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
            title_text = "World Labs AI Blog"
            link_text = f"{BASE_URL}/blog"
        else:
            continue

        if posts:
            favicon = config.get("favicon") or f"{BASE_URL}/favicon.ico"
            output_filename = config["output_files"].get(
                page_type, cache_filename.replace(".html", ".xml")
            )
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
