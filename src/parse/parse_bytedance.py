"""Parse ByteDance Seed Blog and Public Papers pages from cached HTML.

Cache files (from fetch_js.py):
  - bytedance_blog.html
  - bytedance_public_papers.html

Output to data/:
  - bytedance_blog.json
  - bytedance_public_papers.json
"""

import hashlib
import json
import logging
import re
from datetime import datetime, timezone
from pathlib import Path

from bs4 import BeautifulSoup

from config_util import compact, load_site_config

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)

project_dir = Path(__file__).resolve().parent.parent.parent
html_dir = project_dir / "html_cache"
parsed_dir = project_dir / "data"
parsed_dir.mkdir(exist_ok=True)


def load_config():
    return load_site_config("bytedance", config_name="js.json")


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
    """Parse various date formats to ISO 8601."""
    date_str = date_str.strip()
    # "Apr 23, 2026"
    for fmt in ("%b %d, %Y", "%B %d, %Y", "%Y/%m/%d"):
        try:
            return datetime.strptime(date_str, fmt).replace(tzinfo=timezone.utc).isoformat()
        except ValueError:
            continue
    # "2026/05/31"
    try:
        return datetime.strptime(date_str, "%Y/%m/%d").replace(tzinfo=timezone.utc).isoformat()
    except ValueError:
        pass
    return None


def _extract_blog(soup, base_url):
    """Extract blog post cards from the blog listing page."""
    items = []

    # Blog cards are inside a grid container
    # Each card: div.group > div (thumbnail) + div.flex.flex-col (content)
    cards = soup.select("div.grid.grid-cols-3 > div.group")
    if not cards:
        # Fallback: look for any div with cursor-pointer inside the grid
        cards = soup.find_all("div", class_=lambda c: c and "group" in str(c) and "cursor-pointer" in str(c))

    for card in cards:
        # Title — find by font-[500] class or common title pattern
        title_el = card.find(
            "div", class_=lambda c: c and "font-[500]" in str(c) if c else False
        )
        if not title_el:
            # Fallback: any div with line-clamp-3
            title_el = card.find(
                "div", class_=lambda c: c and "line-clamp-3" in str(c) if c else False
            )
        if not title_el:
            continue
        title = title_el.get_text(strip=True)
        if not title:
            continue

        # Date — look for text matching "Mon DD, YYYY" pattern
        date_el = card.find(
            "div", string=lambda t: bool(re.match(r"[A-Z][a-z]+ \d{1,2}, \d{4}", (t or "").strip()))
        )
        published_date = None
        if date_el:
            published_date = parse_date(date_el.get_text(strip=True))

        # Category
        category_el = card.find(
            "div", class_=lambda c: c and "justify-self-end" in str(c) if c else False
        )
        if category_el:
            category_el = category_el.find("div")
        categories = [category_el.get_text(strip=True)] if category_el else []

        # Blog cards are plain divs without href — construct URL from title slug
        slug = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")
        url = f"{base_url.rstrip('/')}/blog/{slug}"

        if not published_date:
            published_date = datetime.now(timezone.utc).isoformat()

        item_id = hashlib.md5(f"bytedance_blog_{title}".encode()).hexdigest()

        items.append(compact({
            "id": item_id,
            "source": "bytedance",
            "type": "blog",
            "title": title,
            "url": url,
            "published_date": published_date,
            "organization": "ByteDance Seed",
            "categories": categories,
        }))

    return items


def _extract_public_papers(soup, base_url):
    """Extract research publication items from the public_papers page."""
    items = []

    # Each paper is in a div with class containing "group relative w-full cursor-pointer"
    papers = soup.find_all("div", class_=lambda c: c and "group relative w-full cursor-pointer" in str(c) if c else False)

    for paper in papers:
        # Date is in a div with whitespace-nowrap text
        date_el = paper.select_one("[class*='whitespace-nowrap']")
        date_str = date_el.get_text(strip=True) if date_el else ""

        # Title is in a div with text-[24px] font-[500]
        title_el = paper.find(
            "div", class_=lambda c: c and "text-[24px]" in str(c) and "font-[500]" in str(c) if c else False
        )
        title = title_el.get_text(strip=True) if title_el else ""
        if not title:
            continue

        # Abstract / description
        abstract_el = paper.select_one(".markdown-Vl1VIB")
        abstract = ""
        if abstract_el:
            abstract = abstract_el.get_text(strip=True)

        # Category (italic text at the bottom)
        category_el = paper.select_one("[class*='italic']")
        categories = [category_el.get_text(strip=True)] if category_el else []

        published_date = parse_date(date_str) if date_str else None
        if not published_date:
            published_date = datetime.now(timezone.utc).isoformat()

        # Build a URL slug from the title
        slug = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")
        url = f"{base_url.rstrip('/')}/publication/{slug}"

        item_id = hashlib.md5(f"bytedance_papers_{title}".encode()).hexdigest()

        items.append(compact({
            "id": item_id,
            "source": "bytedance",
            "type": "public_papers",
            "title": title,
            "url": url,
            "summary": abstract[:500] if abstract else None,
            "published_date": published_date,
            "organization": "ByteDance Seed",
            "categories": categories,
        }))

    return items


def extract_html_data(soup, filename):
    """Route to the appropriate extraction function based on filename."""
    if "blog" in filename:
        return _extract_blog(soup, "https://seed.bytedance.com/en")
    elif "public_papers" in filename or "research" in filename:
        return _extract_public_papers(soup, "https://seed.bytedance.com/en")
    else:
        logging.error(f"Unknown file type: {filename}")
        return []


def save_to_json(post_items, filename):
    """Deduplicate, sort, and save to data/."""
    dedup_list = [
        json.loads(entry) for entry in {json.dumps(d) for d in post_items}
    ]
    dedup_list.sort(
        key=lambda x: x.get("published_date", ""),
        reverse=True,
    )

    config = load_config()
    output_files = config["output_files"]

    # Determine output filename from cache filename
    for page_type, cache_name in config["cache_files"].items():
        if cache_name == filename:
            output_name = output_files.get(page_type, f"bytedance_{page_type}.json")
            break
    else:
        if "blog" in filename:
            output_name = "bytedance_blog.json"
        elif "public_papers" in filename:
            output_name = "bytedance_public_papers.json"
        else:
            output_name = f"bytedance_{filename}"

    json_path = parsed_dir / output_name
    json_path.write_text(json.dumps(dedup_list, indent=4, ensure_ascii=False), encoding="utf-8")
    logging.info(f"Saved {len(dedup_list)} items to {json_path}")


if __name__ == "__main__":
    config = load_config()
    for page_type, cache_filename in config["cache_files"].items():
        file_path = html_dir / cache_filename
        if file_path.exists():
            logging.info(f"Processing bytedance {page_type}: {cache_filename}")
            soup = load_html(cache_filename)
            if soup:
                items = extract_html_data(soup, cache_filename)
                save_to_json(items, cache_filename)
        else:
            logging.warning(f"Cache file not found: {cache_filename}")
