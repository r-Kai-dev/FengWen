"""Fetch Ai2 (Allen Institute for AI) news and research from RSC payloads.

Both pages (https://allenai.org/news and https://allenai.org/research) are
built with Next.js App Router.  Blog post metadata is embedded in
``self.__next_f.push()`` chunks as rendered React components.

- News page: uses threeUpCardHeading components for post cards
- Research page: uses a table-like layout with date + linked h2 titles

We decode all RSC chunks, find the relevant patterns for each page,
and produce two Atom feeds.
"""

import hashlib
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

ORG_KEY = "allenai"
BASE_URL = "https://allenai.org"


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


def _parse_month_year(date_str: str) -> str:
    """Parse a date like 'May 2026' to ISO format (first of month)."""
    if not date_str:
        return datetime.now(timezone.utc).isoformat()
    try:
        dt = datetime.strptime(date_str.strip(), "%B %Y")
        return dt.replace(tzinfo=timezone.utc).isoformat()
    except ValueError:
        try:
            dt = datetime.strptime(date_str.strip(), "%b %Y")
            return dt.replace(tzinfo=timezone.utc).isoformat()
        except ValueError:
            return datetime.now(timezone.utc).isoformat()


def _parse_full_date(date_str: str) -> str:
    """Parse a date like 'April 23, 2026' to ISO format."""
    if not date_str:
        return datetime.now(timezone.utc).isoformat()
    try:
        dt = datetime.strptime(date_str.strip(), "%B %d, %Y")
        return dt.replace(tzinfo=timezone.utc).isoformat()
    except ValueError:
        try:
            dt = datetime.strptime(date_str.strip(), "%b %d, %Y")
            return dt.replace(tzinfo=timezone.utc).isoformat()
        except ValueError:
            return datetime.now(timezone.utc).isoformat()


def _rsc_data(html: str) -> str:
    """Decode and concatenate all RSC payload chunks."""
    chunks = re.findall(
        r'self\.__next_f\.push\(\[1,\s*"(.*?)"\s*\]\)', html, re.DOTALL
    )
    all_data = ""
    for chunk in chunks:
        all_data += chunk.encode("utf-8").decode("unicode_escape", errors="replace")
    return all_data


def extract_news(html: str) -> list[dict]:
    """Extract news blog entries from the news RSC payload."""

    all_data = _rsc_data(html)

    # Extract titles + dates from threeUpCardHeading elements
    title_matches = list(
        re.finditer(
            r'threeUpCardHeading[^}]*children":\[\['
            r'.*?"children":"([^"]+)"\}\]'
            r'.*?\]\],"([^"]+)"\]\}\]',
            all_data,
        )
    )

    cards = []
    for m in title_matches:
        date_raw = m.group(1)
        title = m.group(2)
        cards.append(
            {"date": _parse_month_year(date_raw), "title": title, "slug": "", "excerpt": ""}
        )

    # Extract blog slugs
    slug_matches = list(
        re.finditer(r'"href":"(/blog/[a-zA-Z0-9_-]+)"', all_data)
    )
    slugs = list(dict.fromkeys(m.group(1).replace("/blog/", "") for m in slug_matches))

    # Extract excerpts, skipping known non-content text
    skip_prefixes = ["We couldn't find", "Questions about our work"]
    excerpt_matches = list(
        re.finditer(r'"p","p-0",\{"children":"([^"]{10,})"\}\]', all_data)
    )
    excerpts = [
        m.group(1)
        for m in excerpt_matches
        if not any(m.group(1).startswith(p) for p in skip_prefixes)
    ]

    # Match slugs and excerpts to cards by position
    for i, card in enumerate(cards):
        if i < len(slugs):
            card["slug"] = slugs[i]
        if i < len(excerpts):
            card["excerpt"] = excerpts[i]

    entries = []
    seen_slugs = set()
    for card in cards:
        slug = card["slug"]
        if not slug or slug in seen_slugs:
            continue
        seen_slugs.add(slug)

        url = f"{BASE_URL}/blog/{slug}"
        entry_id = hashlib.md5(f"allenai_news_{slug}".encode()).hexdigest()

        entries.append(
            compact(
                {
                    "id": entry_id,
                    "source": "allenai",
                    "type": "news",
                    "title": card["title"],
                    "url": url,
                    "summary": card["excerpt"],
                    "published_date": card["date"],
                    "categories": [],
                    "organization": "Ai2",
                }
            )
        )

    return entries


def extract_research(html: str) -> list[dict]:
    """Extract research blog entries from the research RSC payload."""

    all_data = _rsc_data(html)

    entries = []
    seen_slugs = set()

    date_pattern = r'"children":"([A-Z][a-z]+ \d{1,2}, \d{4})"\}\]'
    for date_match in re.finditer(date_pattern, all_data):
        date_raw = date_match.group(1)
        published = _parse_full_date(date_raw)
        pos = date_match.end()

        nearby = all_data[pos : pos + 1200]

        link_match = re.search(r'"href":"(/blog/[a-zA-Z0-9_-]+)"', nearby)
        if not link_match:
            continue

        slug = link_match.group(1).replace("/blog/", "")
        if slug in seen_slugs:
            continue

        after_link = nearby[link_match.end() :]
        title_match = re.search(
            r'"h2",null,\{"className":"[^"]+","children":"([^"]+)"',
            after_link,
        )
        if not title_match:
            continue

        title = title_match.group(1)
        seen_slugs.add(slug)

        url = f"{BASE_URL}/blog/{slug}"
        entry_id = hashlib.md5(f"allenai_research_{slug}".encode()).hexdigest()

        entries.append(
            compact(
                {
                    "id": entry_id,
                    "source": "allenai",
                    "type": "research",
                    "title": title,
                    "url": url,
                    "published_date": published,
                    "categories": [],
                    "organization": "Ai2",
                }
            )
        )

    return entries


def main() -> None:
    """Fetch Ai2 news and research, write two Atom XML feeds."""
    config = load_api_config(ORG_KEY)
    favicon = config.get("favicon", f"{BASE_URL}/favicon.svg")

    for page_key in ("news", "research"):
        page_config = config["pages"].get(page_key)
        if not page_config:
            continue

        url = f"{BASE_URL}{page_config['endpoint']}"
        logging.info(f"Fetching Ai2 {page_key} from {url}")
        html = fetch_page(url)

        if page_key == "news":
            entries = extract_news(html)
            feed_title = "Ai2 News"
        else:
            entries = extract_research(html)
            feed_title = "Ai2 Research"

        if not entries:
            logging.error("No entries found for %s", page_key)
            continue

        output_file = PARSED_DIR / page_config["output_file"]
        write_atom_feed(
            output_file,
            entries,
            feed_title=feed_title,
            feed_link=url,
            feed_icon=favicon,
        )
        logging.info("Saved %d entries to %s", len(entries), output_file)


if __name__ == "__main__":
    main()
