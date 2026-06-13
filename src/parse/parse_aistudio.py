"""Parse Tencent AI Studio News/Blog page from cached JS-rendered HTML.

Cache file (from fetch_js.py):
  - tencent_aistudio_news-blog.html

Output to feeds/:
  - tencent_aistudio_news-blog.xml

The page is a React SPA (TDesign UI).  After JS rendering the DOM contains
blog-list__item cards with the following structure (revealed by live
Chromium test):

  <div class="blog-list__item">
    <div class="blog-list__item-left">
      <div class="blog-list__item-left-name">Model Release</div>
      <div class="blog-list__item-left-cover" style="background-image: ..."></div>
    </div>
    <div class="blog-list__item-right">
      <div class="blog-list__item-right-tags">
        <div class="blog-list__item-right-tag">模型发布</div>
      </div>
      <div class="blog-list__item-right-title">腾讯混元全新翻译模型Hy-MT2开源...</div>
      <div class="blog-list__item-right-desc">Hy-MT2 是支持 33 种语言互译...</div>
      <div class="blog-list__item-right-time">2026-05-20</div>
    </div>
  </div>

No <a> tags wrap the items (navigation is via React Router onClick),
so URLs are derived from the title slug: /news/blog/{slug}
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

_BASE_URL = "https://aistudio.tencent.com"


def load_config():
    return load_site_config("tencent_aistudio", config_name="js.json")


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

    Handles formats seen on AI Studio blog:
      - "2026-05-20" (ISO-like)
      - "2026/05/20"
    """
    date_str = date_str.strip()
    for fmt in ("%Y-%m-%d", "%Y/%m/%d"):
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
    """Extract news/blog items from the rendered DOM.

    Selects on the exact CSS classes observed in rendered HTML:
      div.blog-list__item  →  div.blog-list__item-right-title,
                               div.blog-list__item-right-time,
                               div.blog-list__item-right-desc,
                               div.blog-list__item-right-tag,
                               div.blog-list__item-left-name
    """
    items = []
    seen_titles = set()

    blog_items = soup.select("div.blog-list__item")
    logging.info(f"Found {len(blog_items)} div.blog-list__item elements")

    for card in blog_items:
        # Title
        title_el = card.select_one("div.blog-list__item-right-title")
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
        date_el = card.select_one("div.blog-list__item-right-time")
        published_date = None
        if date_el:
            published_date = parse_date(date_el.get_text(strip=True))

        # Category (English label in left column)
        category_el = card.select_one("div.blog-list__item-left-name")
        eng_category = category_el.get_text(strip=True) if category_el else ""

        # Tags (Chinese labels)
        tags = []
        for tag_el in card.select("div.blog-list__item-right-tag"):
            tag = tag_el.get_text(strip=True)
            if tag:
                tags.append(tag)
        categories = []
        if eng_category:
            categories.append(eng_category)
        categories.extend(tags)

        # Summary / description
        desc_el = card.select_one("div.blog-list__item-right-desc")
        summary = desc_el.get_text(strip=True) if desc_el else ""

        # Use article URL from data-attribute (injected by fetch_js.py from React fiber)
        article_url = card.get("data-article-url")
        if article_url:
            url = article_url
        else:
            # Fallback: derive a slug from the title
            slug = re.sub(r"\s+", "-", title).strip("-")
            slug = re.sub(r"[^\w\-\u4e00-\u9fff]+", "", slug)
            encoded_slug = quote(slug, safe="-")
            url = f"{_BASE_URL}/news/blog/{encoded_slug}"

        item_id = hashlib.md5(f"tencent_aistudio_{title}".encode()).hexdigest()

        items.append(
            compact(
                {
                    "id": item_id,
                    "source": "tencent_aistudio",
                    "type": "news",
                    "title": title,
                    "url": url,
                    "summary": summary[:800] if summary else None,
                    "published_date": published_date
                    or datetime.now(timezone.utc).isoformat(),
                    "organization": "Tencent Hunyuan",
                    "categories": categories if categories else None,
                }
            )
        )

    if not items:
        logging.warning(
            "No blog items extracted via 'div.blog-list__item' selector. "
            "The rendered DOM structure may have changed."
        )
    else:
        logging.info(f"Extracted {len(items)} news items")

    return items


def extract_blog_items(soup: BeautifulSoup, base_url: str) -> list[dict]:
    """Main extraction entry-point for the news/blog listing page."""
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
            output_name = output_files.get(page_type, "tencent_aistudio_news-blog.xml")
            break
    else:
        output_name = "tencent_aistudio_news-blog.xml"

    feed_path = parsed_dir / output_name
    write_atom_feed(
        feed_path,
        dedup_list,
        feed_title="Tencent Hunyuan Blog (AI Studio)",
        feed_link="https://aistudio.tencent.com/news/blog",
        feed_icon=favicon,
    )


if __name__ == "__main__":
    config = load_config()
    for page_type, cache_filename in config["cache_files"].items():
        file_path = html_dir / cache_filename
        if file_path.exists():
            logging.info(f"Processing tencent_aistudio {page_type}: {cache_filename}")
            soup = load_html(cache_filename)
            if soup:
                items = extract_blog_items(soup, _BASE_URL)
                save_to_json(items, cache_filename)
        else:
            logging.warning(f"Cache file not found: {cache_filename}")
