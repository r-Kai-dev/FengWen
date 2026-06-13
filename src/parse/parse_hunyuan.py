"""Parse Tencent Hunyuan Research page from cached JS-rendered HTML.

Cache file (from fetch_js.py):
  - tencent_hunyuan_research.html

Output to feeds/:
  - tencent_hunyuan_research.xml

The page is a React SPA (Vite-based).  After JS rendering the DOM contains
blog-item cards with the following structure (revealed by live Chromium test):

  <div class="blog-item">
    <div class="blog-item-header">
      <span class="blog-item-date">Apr 30, 2026</span>
      <span class="blog-item-separator"></span>
      <span class="blog-item-author-item">Author Name</span>
    </div>
    <div class="blog-item-content">
      <h2 class="blog-title">Real life is where context gets hard</h2>
      <p class="blog-desc">Previously, we built CL-Bench to test ...</p>
      <div class="blog-read-more">Read Paper</div>
    </div>
  </div>

Individual article pages are navigated via React Router (no <a> tags),
so URLs are derived from the title slug: /research/{slug}
"""

import hashlib
import json
import logging
import re
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote

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

_BASE_URL = "https://hunyuan.tencent.com"


def load_config():
    return load_site_config("tencent_hunyuan", config_name="js.json")


def load_html(filename):
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
    """Parse date strings to ISO 8601.

    Handles formats seen on Hunyuan research blog:
      - "Apr 30, 2026"
      - "Jun 13, 2026"
      - "2026/05/20"
    """
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
    for fmt in ("%Y/%m/%d", "%Y-%m-%d"):
        try:
            return (
                datetime.strptime(date_str, fmt)
                .replace(tzinfo=timezone.utc)
                .isoformat()
            )
        except ValueError:
            continue
    return None


def _extract_items(soup: BeautifulSoup) -> list[dict]:
    """Extract research blog items from the rendered DOM.

    Selects on the exact CSS classes observed in the rendered HTML:
      div.blog-item  →  h2.blog-title, span.blog-item-date,
                        p.blog-desc, span.blog-item-author-item
    """
    items = []
    seen_titles = set()

    blog_items = soup.select("div.blog-item")
    logging.info(f"Found {len(blog_items)} div.blog-item elements")

    for card in blog_items:
        # Title
        title_el = card.select_one("h2.blog-title")
        if not title_el:
            continue
        title = title_el.get_text(strip=True)
        if not title or len(title) < 3:
            continue

        dedup_key = title.lower().strip()
        if dedup_key in seen_titles:
            continue
        seen_titles.add(dedup_key)

        # Date
        date_el = card.select_one("span.blog-item-date")
        published_date = None
        if date_el:
            published_date = parse_date(date_el.get_text(strip=True))

        # Authors / categories
        authors = []
        for author_el in card.select("span.blog-item-author-item"):
            author = author_el.get_text(strip=True)
            if author:
                authors.append(author)
        categories = authors if authors else None

        # Summary / description
        desc_el = card.select_one("p.blog-desc")
        summary = desc_el.get_text(strip=True) if desc_el else ""

        # Use article ID from data-attribute (injected by fetch_js.py from React fiber)
        article_id = card.get("data-article-id") or card.get("data-custom-url")
        if article_id:
            url = f"{_BASE_URL}/research/{article_id}"
        else:
            # Fallback: derive a slug from the title
            slug = re.sub(r"\s+", "-", title).strip("-")
            slug = re.sub(r"[^\w\-\u4e00-\u9fff]+", "", slug)
            encoded_slug = quote(slug, safe="-")
            url = f"{_BASE_URL}/research/{encoded_slug}"

        item_id = hashlib.md5(f"tencent_hunyuan_{title}".encode()).hexdigest()

        items.append(
            compact(
                {
                    "id": item_id,
                    "source": "tencent_hunyuan",
                    "type": "research",
                    "title": title,
                    "url": url,
                    "summary": summary[:800] if summary else None,
                    "published_date": published_date
                    or datetime.now(timezone.utc).isoformat(),
                    "organization": "Tencent Hunyuan",
                    "categories": categories,
                }
            )
        )

    if not items:
        logging.warning(
            "No blog items extracted via 'div.blog-item' selector. "
            "The rendered DOM structure may have changed."
        )
    else:
        logging.info(f"Extracted {len(items)} research items")

    return items


def extract_research_items(soup: BeautifulSoup, base_url: str) -> list[dict]:
    """Main extraction entry-point for the research listing page."""
    return _extract_items(soup)


def save_to_json(post_items: list[dict], filename: str) -> None:
    """Deduplicate, sort, and save to feeds/ as Atom XML."""
    dedup_list = [json.loads(entry) for entry in {json.dumps(d) for d in post_items}]
    dedup_list.sort(
        key=lambda x: x.get("published_date", ""),
        reverse=True,
    )

    config = load_config()
    output_files = config["output_files"]
    favicon = config.get("favicon") or f"{_BASE_URL}/favicon.ico"

    for page_type, cache_name in config["cache_files"].items():
        if cache_name == filename:
            output_name = output_files.get(page_type, "tencent_hunyuan_research.xml")
            break
    else:
        output_name = "tencent_hunyuan_research.xml"

    feed_path = parsed_dir / output_name
    write_atom_feed(
        feed_path,
        dedup_list,
        feed_title="Tencent Hunyuan Research",
        feed_link="https://hunyuan.tencent.com/research",
        feed_icon=favicon,
    )


if __name__ == "__main__":
    config = load_config()
    for page_type, cache_filename in config["cache_files"].items():
        file_path = html_dir / cache_filename
        if file_path.exists():
            logging.info(f"Processing tencent_hunyuan {page_type}: {cache_filename}")
            soup = load_html(cache_filename)
            if soup:
                items = extract_research_items(soup, _BASE_URL)
                save_to_json(items, cache_filename)
        else:
            logging.warning(f"Cache file not found: {cache_filename}")
