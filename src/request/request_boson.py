"""Fetch Boson AI blog posts from Next.js RSC payload.

The blog page renders article cards via RSC chunks embedded in
self.__next_f.push(). We extract article hrefs, dates, and titles.

Output to feeds/:
  - boson_blog.xml
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

ORG_KEY = "boson"
BASE_URL = "https://www.boson.ai"


def fetch_page(url: str) -> str:
    """Fetch an HTML page."""
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


def parse_date(date_str: str) -> str | None:
    """Parse dates like 'Jun. 4, 2026' to ISO format."""
    if not date_str:
        return None
    date_str = date_str.strip()
    for fmt in ("%b. %d, %Y", "%B %d, %Y", "%b %d, %Y"):
        try:
            return (
                datetime.strptime(date_str, fmt)
                .replace(tzinfo=timezone.utc)
                .isoformat()
            )
        except ValueError:
            continue
    return None


def extract_blog_posts(html: str) -> list[dict]:
    """Extract blog posts from RSC payload chunks.

    Boson AI blog renders article cards in RSC. Each article:
      - href="/blog/slug"
      - A date div with text like "Jun. 4, 2026"
      - A title div
      - An excerpt paragraph
    """
    chunks = re.findall(
        r'self\.__next_f\.push\(\[[0-9]+,\s*"(.*?)"\s*\]\)', html, re.DOTALL
    )

    all_hrefs = []
    all_dates = []
    all_titles = []
    all_excerpts = []

    for chunk in chunks:
        decoded = chunk.encode("utf-8").decode("unicode_escape", errors="replace")

        # Find article hrefs for blog posts
        hrefs = re.findall(r'"href":"/blog/([^"]+)"', decoded)
        all_hrefs.extend(hrefs)

        # Find dates like "Jun. 4, 2026"
        dates = re.findall(
            r'"children":"([A-Z][a-z]{2}\.\s*\d{1,2},\s*\d{4})"', decoded
        )
        all_dates.extend(dates)

        # Find titles by looking at children text nodes that look like blog titles
        for m in re.finditer(r'"children":"([^"]{15,150}?)"', decoded):
            text = m.group(1)
            if (
                not text.startswith(("http", "\\u00a9", "$"))
                and "className" not in text
                and "Read More" not in text
                and "text-boson" not in text
                and not re.match(r'^[a-f0-9]{20,}$', text)
                and not text.startswith("Product updates")
            ):
                all_titles.append(text)

    # Match articles by position (RSC renders them in order)
    posts = []
    for i, slug in enumerate(all_hrefs):
        if not slug:
            continue

        url = f"{BASE_URL}/blog/{slug}"

        date_str = all_dates[i] if i < len(all_dates) else None
        published_date = parse_date(date_str) if date_str else datetime.now(timezone.utc).isoformat()

        title = all_titles[i] if i < len(all_titles) else slug.replace("-", " ").title()

        entry_id = hashlib.md5(f"boson_blog_{slug}".encode()).hexdigest()

        posts.append(
            compact(
                {
                    "id": entry_id,
                    "source": "boson",
                    "type": "blog",
                    "title": title,
                    "url": url,
                    "published_date": published_date,
                    "organization": "Boson AI",
                }
            )
        )

    return posts


def main() -> None:
    """Fetch Boson AI blog and write Atom XML feed."""
    config = load_api_config(ORG_KEY)
    blog_config = config["pages"]["blog"]

    url = f"{BASE_URL}{blog_config['endpoint']}"
    logging.info(f"Fetching Boson AI blog from {url}")
    html = fetch_page(url)

    entries = extract_blog_posts(html)
    if not entries:
        logging.error("No blog posts found")
        return

    output_file = PARSED_DIR / blog_config["output_file"]
    write_atom_feed(
        output_file,
        entries,
        feed_title="Boson AI Blog",
        feed_link=f"{BASE_URL}/blog",
        feed_icon=config.get("favicon", f"{BASE_URL}/favicon.ico"),
    )
    logging.info(f"Saved {len(entries)} entries to {output_file}")


if __name__ == "__main__":
    main()
