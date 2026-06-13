"""Fetch Runway news and research publications from Next.js RSC payloads.

For the news page (https://runwayml.com/news):
  The posts data is embedded as a JSON array inside a self.__next_f.push RSC
  payload chunk.  We extract the "posts" array, filter to entries whose slug
  starts with "news/" (excluding customer stories, research, etc.), and
  produce an Atom feed.

For the research page (https://runwayml.com/research/publications):
  Each publication is rendered across individual RSC chunks with a consistent
  structure: date (mb-3), title (rw-h5 mb-2), authors (mb-1), and an arXiv
  or /research/ link.
"""

import hashlib
import json
import logging
import re
import urllib.request
from datetime import datetime, timezone

from common import (
    PARSED_DIR,
    ensure_output_dir,
    load_api_config,
    setup_logging,
)
from feed_util import compact, write_atom_feed

setup_logging()
ensure_output_dir()

ORG_KEY = "runway"
BASE_URL = "https://runwayml.com"

MONTHS = {
    "January": 1, "February": 2, "March": 3, "April": 4,
    "May": 5, "June": 6, "July": 7, "August": 8,
    "September": 9, "October": 10, "November": 11, "December": 12,
}


def fetch_page(url: str) -> str:
    """Fetch an HTML page and return the raw text."""
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": (
                "Mozilla/5.0 (X11; Linux x86_64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            ),
        },
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        return resp.read().decode("utf-8")


def _parse_rsc_date(date_str: str) -> str | None:
    """Parse a date from the RSC payload to ISO format.

    Handles:
      - ISO format with TZ: "2026-06-11T10:10:10.110Z"
      - Date only:           "2026-05-29"
      - Long form:           "March 31, 2025"
    """
    if not date_str:
        return None

    date_str = date_str.strip()

    # ISO format
    if "T" in date_str or "-" in date_str:
        try:
            # Handle "2026-06-11T10:10:10.110Z"
            dt = datetime.fromisoformat(date_str.replace("Z", "+00:00"))
            return dt.isoformat()
        except (ValueError, TypeError):
            pass

    # Long form: "March 31, 2025"
    for fmt in ("%B %d, %Y", "%b %d, %Y"):
        try:
            dt = datetime.strptime(date_str, fmt)
            return dt.replace(tzinfo=timezone.utc).isoformat()
        except ValueError:
            continue

    return None


def extract_posts_from_rsc(html: str) -> list[dict]:
    """Extract the 'posts' JSON array from a Next.js RSC payload.

    Returns the list of post dicts, or an empty list.
    """
    # Find all RSC chunks
    chunks = re.findall(r'self\.__next_f\.push\(\[1,\s*"(.*?)"\s*\]\)', html, re.DOTALL)

    for chunk in chunks:
        decoded = chunk.encode("utf-8").decode("unicode_escape", errors="replace")
        if '"posts"' not in decoded:
            continue

        # Extract the posts JSON array
        m = re.search(r'"posts":(\[.*?\])\s*\}', decoded, re.DOTALL)
        if m:
            try:
                return json.loads(m.group(1))
            except json.JSONDecodeError as exc:
                logging.warning("Failed to decode posts JSON: %s", exc)
                return []

    logging.warning("No posts array found in RSC payload")
    return []


def extract_publications_from_rsc(html: str) -> list[dict]:
    """Extract research publications from RSC chunks.

    Each publication has:
      - A date string in mb-3: "March 31, 2025"
      - A title in rw-h5 mb-2: "StochasticSplats: ..."
      - Authors in mb-1: "Shakiba Kheradmand, ..."
      - An arXiv or runwayml.com/research/ link
    """
    chunks = re.findall(r'self\.__next_f\.push\(\[1,\s*"(.*?)"\s*\]\)', html, re.DOTALL)

    publications = []

    for chunk in chunks:
        decoded = chunk.encode("utf-8").decode("unicode_escape", errors="replace")

        # Split on publication separator (py-7 border-t pattern)
        # Actually, each RSC chunk may contain one publication entry
        # Find date in mb-3
        date_match = re.search(
            r'rw-bodycopy3 text-darkGrayAlt mb-3[^}]*"children":"([^"]+)"',
            decoded,
        )
        if not date_match:
            continue
        date_str = date_match.group(1)
        if not re.match(r"^[A-Z][a-z]+ \d{1,2}, \d{4}$", date_str):
            continue

        # Title in rw-h5 mb-2
        title_match = re.search(
            r'rw-h5 mb-2[^}]*"children":"([^"]+)"', decoded
        )
        title = title_match.group(1) if title_match else ""

        # Authors in mb-1
        authors_match = re.search(
            r'rw-bodycopy3 text-darkGrayAlt mb-1[^}]*"children":"([^"]+)"',
            decoded,
        )
        authors = authors_match.group(1) if authors_match else ""

        # Link - arXiv or /research/ URL
        link = ""
        for href_match in re.finditer(r'"href":"(https?://[^"]+)"', decoded):
            href = href_match.group(1)
            if "arxiv.org" in href or "/research/" in href:
                link = href
                break

        publications.append(
            {
                "date": date_str,
                "title": title,
                "authors": authors,
                "link": link,
            }
        )

    return publications


def news_post_to_entry(post: dict) -> dict:
    """Convert a news page post dict to an Atom entry."""
    title = post.get("title", "")
    slug = post.get("slug", "")
    href = post.get("href", "") or f"/{slug}"
    url = f"{BASE_URL}{href}"

    published_date = _parse_rsc_date(post.get("date", ""))
    if not published_date:
        published_date = datetime.now(timezone.utc).isoformat()

    # Category: prefer categoryLabel, fall back to category
    category = post.get("categoryLabel", "") or post.get("category", "") or ""

    # Excerpt
    summary = (post.get("excerpt") or "")[:300]

    entry_id = hashlib.md5(f"runway_news_{slug}".encode()).hexdigest()

    return compact(
        {
            "id": entry_id,
            "source": "runway",
            "type": "news",
            "title": title,
            "url": url,
            "summary": summary,
            "published_date": published_date,
            "categories": [category] if category else [],
            "organization": "Runway",
        }
    )


def research_pub_to_entry(pub: dict) -> dict:
    """Convert a research publication dict to an Atom entry."""
    title = pub.get("title", "")
    link = pub.get("link", "")
    date_str = pub.get("date", "")

    published_date = _parse_rsc_date(date_str)
    if not published_date:
        published_date = datetime.now(timezone.utc).isoformat()

    authors = pub.get("authors", "")
    summary = f"Authors: {authors}" if authors else ""

    # Use the arXiv link or construct a Runway page URL
    url = link or f"{BASE_URL}/research/publications"

    entry_id = hashlib.md5(f"runway_research_{title}_{date_str}".encode()).hexdigest()

    return compact(
        {
            "id": entry_id,
            "source": "runway",
            "type": "research",
            "title": title,
            "url": url,
            "summary": summary,
            "published_date": published_date,
            "organization": "Runway",
        }
    )


def process_news_page() -> list[dict]:
    """Fetch the news page and extract filtered entries."""
    url = f"{BASE_URL}/news"
    html = fetch_page(url)

    posts = extract_posts_from_rsc(html)
    if not posts:
        logging.error("No posts found on news page")
        return []

    # Filter to only news posts (slug starts with "news/")
    news_posts = [p for p in posts if p.get("slug", "").startswith("news/")]

    entries = [news_post_to_entry(p) for p in news_posts]

    logging.info("Fetched %d news posts from Runway (filtered from %d total)", len(entries), len(posts))
    return entries


def process_research_page() -> list[dict]:
    """Fetch the research/publications page and extract entries."""
    url = f"{BASE_URL}/research/publications"
    html = fetch_page(url)

    pubs = extract_publications_from_rsc(html)
    if not pubs:
        logging.error("No publications found on research page")
        return []

    entries = [research_pub_to_entry(p) for p in pubs]
    logging.info("Fetched %d research publications from Runway", len(entries))
    return entries


def main() -> None:
    """Fetch Runway news and research feeds and write Atom XML files."""
    config = load_api_config(ORG_KEY)

    # Process news page
    news_entries = process_news_page()
    if news_entries:
        news_config = config["pages"]["news"]
        output_file = PARSED_DIR / news_config["output_file"]
        write_atom_feed(
            output_file,
            news_entries,
            feed_title="Runway News",
            feed_link=f"{BASE_URL}/news",
            feed_icon=config.get("favicon", f"{BASE_URL}/icon.png"),
        )

    # Process research page
    research_entries = process_research_page()
    if research_entries:
        research_config = config["pages"]["research"]
        output_file = PARSED_DIR / research_config["output_file"]
        write_atom_feed(
            output_file,
            research_entries,
            feed_title="Runway Research Publications",
            feed_link=f"{BASE_URL}/research/publications",
            feed_icon=config.get("favicon", f"{BASE_URL}/icon.png"),
        )


if __name__ == "__main__":
    main()
