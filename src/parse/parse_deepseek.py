"""Parse DeepSeek API Docs news sidebar from cached HTML.

Cache file (from fetch_js.py):
  - deepseek_index.html  (with the "News" sidebar category expanded)

Output to data/:
  - deepseek_news.json
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
    return load_site_config("deepseek", config_name="js.json")


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


def parse_news_date(date_str: str) -> str | None:
    """Parse date strings like '2026/04/24' or '2025/12/01'."""
    date_str = date_str.strip()
    # "2026/04/24"
    try:
        return datetime.strptime(date_str, "%Y/%m/%d").replace(tzinfo=timezone.utc).isoformat()
    except ValueError:
        pass
    return None


def extract_news_items(soup, base_url):
    """Extract news items from the Docusaurus sidebar.

    The News category, when expanded, contains <li> items with <a> links
    whose text is in the format "Title 2026/04/24".
    """
    items = []

    # Find the News sidebar category — look for the expanded <ul> under the
    # sidebar category whose parent <a> contains the text "News"
    # Target: a.menu__link--sublist-caret containing "News"
    # Then get the sibling <ul.menu__list> with its <li> children
    news_section = soup.find(
        "a",
        class_=lambda c: c and "menu__link--sublist-caret" in str(c),
        string=lambda t: t and "News" in t.strip() if t else False,
    )
    if not news_section:
        # Fallback: broader search
        news_section = soup.find("a", string=lambda t: t and t.strip() == "News" if t else False)

    if not news_section:
        logging.warning("Could not find News sidebar category in HTML")
        return items

    # The news links are in the sibling <ul> after the parent <li>
    parent_li = news_section.find_parent("li")
    if not parent_li:
        logging.warning("Could not find parent <li> for News category")
        return items

    # Find all <a> links inside this category that point to /news/
    news_links = parent_li.select('li a[href^="/news/"]')
    if not news_links:
        # Fallback: any <a> with href starting with /news/ on the page
        news_links = soup.select('a[href^="/news/"]')

    for link in news_links:
        href = link.get("href", "")
        text = link.get_text(strip=True)
        if not text or not href:
            continue

        # Text format: "DeepSeek-V4 Preview Release 2026/04/24"
        # Try to split off the date at the end
        date_match = re.search(r"(\d{4}/\d{2}/\d{2})$", text)
        date_str = date_match.group(1) if date_match else ""
        title = text[: -len(date_str)].strip() if date_str else text

        published_date = parse_news_date(date_str) if date_str else None
        if not published_date:
            published_date = datetime.now(timezone.utc).isoformat()

        url = str(base_url).rstrip("/") + "/" + href.lstrip("/")

        item_id = hashlib.md5(f"deepseek_news_{title}_{date_str}".encode()).hexdigest()

        items.append(compact({
            "id": item_id,
            "source": "deepseek",
            "type": "news",
            "title": title,
            "url": url,
            "published_date": published_date,
            "organization": "DeepSeek",
        }))

    return items


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

    # Determine output filename
    for page_type, cache_name in config["cache_files"].items():
        if cache_name == filename:
            output_name = output_files.get(page_type, f"deepseek_{page_type}.json")
            break
    else:
        output_name = "deepseek_news.json"

    json_path = parsed_dir / output_name
    json_path.write_text(json.dumps(dedup_list, indent=4, ensure_ascii=False), encoding="utf-8")
    logging.info(f"Saved {len(dedup_list)} items to {json_path}")


if __name__ == "__main__":
    config = load_config()
    for page_type, cache_filename in config["cache_files"].items():
        file_path = html_dir / cache_filename
        if file_path.exists():
            logging.info(f"Processing deepseek {page_type}: {cache_filename}")
            soup = load_html(cache_filename)
            if soup:
                items = extract_news_items(soup, "https://api-docs.deepseek.com")
                save_to_json(items, cache_filename)
        else:
            logging.warning(f"Cache file not found: {cache_filename}")
