"""Parse Qwen Research page from cached HTML.

Cache file (from fetch_js.py):
  - qwen_research.html

Output to data/:
  - qwen_research.json

The Qwen Research page has two sections:
  - "Latest Advancements" — featured recent items
  - "Research Index" — the full paginated list
Both use similar card structures.
"""

import hashlib
import json
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


def load_config():
    return load_site_config("qwen", config_name="js.json")


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
    """Parse date strings like '2026/05/31'."""
    date_str = date_str.strip()
    try:
        return (
            datetime.strptime(date_str, "%Y/%m/%d")
            .replace(tzinfo=timezone.utc)
            .isoformat()
        )
    except ValueError:
        pass
    return None


def _extract_slug(soup_item):
    """Extract the blog slug from the element's id attribute.

    Capability cards have ids like:
      id="capabilities_blog_id_qwen3.7-plus"

    Returns the slug part (e.g. "qwen3.7-plus") or None.
    """
    elem_id = soup_item.get("id", "")
    match = re.search(r"blog_id_(.+)$", elem_id)
    return match.group(1) if match else None


def extract_item(soup_item, base_url, seen_ids):
    """Extract a single research item from a card element.

    Returns a compact dict or None if already seen / invalid.
    """
    # Title
    title_el = soup_item.select_one(
        "[class*='Advancement__Title'], [class*='Capability__Title']"
    )
    if not title_el:
        return None
    title = title_el.get_text(strip=True)
    if not title:
        return None

    # Deduplicate by title
    dedup_key = title.lower().strip()
    if dedup_key in seen_ids:
        return None
    seen_ids.add(dedup_key)

    # Description / summary
    desc_el = soup_item.select_one(
        "[class*='Advancement__Description'], [class*='Capability__Description'] "
    )
    summary = ""
    if desc_el:
        summary = desc_el.get_text(strip=True)

    # Source/category (e.g., "Release", "Open-Source", "Research")
    source_el = soup_item.select_one(
        "[class*='Advancement__Source'], [class*='Capability__Source'] "
    )
    categories = [source_el.get_text(strip=True)] if source_el else []

    # Date
    date_el = soup_item.select_one(
        "[class*='Advancement__Date'], [class*='Capability__Date'] "
    )
    published_date = None
    if date_el:
        published_date = parse_date(date_el.get_text(strip=True))
    if not published_date:
        published_date = datetime.now(timezone.utc).isoformat()

    # Extract the blog slug from the element's id attribute
    # Format: "https://qwen.ai/blog?id={slug}"
    slug = _extract_slug(soup_item)
    if slug:
        url = f"{base_url.rstrip('/')}/blog?id={slug}"
    else:
        # Fallback: construct from title
        slug = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")
        url = f"{base_url.rstrip('/')}/research/{slug}"

    item_id = hashlib.md5(f"qwen_research_{title}".encode()).hexdigest()

    return compact(
        {
            "id": item_id,
            "source": "qwen",
            "type": "research",
            "title": title,
            "url": url,
            "summary": summary[:600] if summary else None,
            "published_date": published_date,
            "organization": "Qwen (Alibaba)",
            "categories": categories,
        }
    )


def extract_research_items(soup, base_url):
    """Extract research items from the Research Index section.

    Only parses the Research Index cards (class*='Capability--dztDuQSg'),
    skipping the duplicate "Latest Advancements" section.
    """
    items = []
    seen_ids = set()

    capability_items = soup.select("[class*='Capability--dztDuQSg']")
    for cap in capability_items:
        item = extract_item(cap, base_url, seen_ids)
        if item:
            items.append(item)

    if not items:
        logging.warning("No research items found — page structure may have changed")
    else:
        logging.info(f"Extracted {len(items)} research items")

    return items


def save_to_json(post_items, filename):
    """Deduplicate, sort, and save to feeds/ as Atom XML"""
    dedup_list = [json.loads(entry) for entry in {json.dumps(d) for d in post_items}]
    dedup_list.sort(
        key=lambda x: x.get("published_date", ""),
        reverse=True,
    )

    config = load_config()
    output_files = config["output_files"]
    favicon = config.get("favicon") or (
        config.get("url", "").rstrip("/") + "/favicon.ico"
    )

    for page_type, cache_name in config["cache_files"].items():
        if cache_name == filename:
            output_name = output_files.get(page_type, f"qwen_{page_type}.xml")
            break
    else:
        output_name = "qwen_research.xml"

    feed_path = parsed_dir / output_name
    write_atom_feed(
        feed_path,
        dedup_list,
        feed_title="Qwen (Alibaba)",
        feed_link="https://qwen.ai/research",
        feed_icon=favicon,
    )


if __name__ == "__main__":
    config = load_config()
    for page_type, cache_filename in config["cache_files"].items():
        file_path = html_dir / cache_filename
        if file_path.exists():
            logging.info(f"Processing qwen {page_type}: {cache_filename}")
            soup = load_html(cache_filename)
            if soup:
                items = extract_research_items(soup, "https://qwen.ai")
                save_to_json(items, cache_filename)
        else:
            logging.warning(f"Cache file not found: {cache_filename}")
