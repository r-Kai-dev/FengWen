import hashlib
import json
import logging
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path

from bs4 import BeautifulSoup

from config_util import compact, load_site_config, write_atom_feed

# Configure logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)

# Directory containing the HTML files
project_dir = Path(__file__).resolve().parent.parent.parent
html_dir = project_dir / "html_cache"
parsed_dir = project_dir / "feeds"
# Ensure parsed directory exists
parsed_dir.mkdir(exist_ok=True)


def load_config():
    """Load site configuration from html.json"""
    return load_site_config("aibase")


def load_html(filename):
    """Load HTML content from cache file"""
    file_path = html_dir / filename
    try:
        with open(file_path, "r", encoding="utf-8") as file:
            html_content = file.read()
    except FileNotFoundError:
        logging.error(f"File not found: {file_path}")
        return None, None
    except Exception as e:
        logging.error(f"Error reading file {file_path}: {e}")
        return None, None

    soup = BeautifulSoup(html_content, "html.parser")
    return soup, html_content


def parse_relative_time(time_str):
    """Parse relative time strings like '8 小时前' or '2 天前' into ISO format"""
    if not time_str:
        return None

    time_str = time_str.strip()

    # Handle "刚刚" (just now)
    if "刚刚" in time_str:
        return datetime.now(timezone.utc).isoformat()

    # Handle "X 分钟前" (X minutes ago)
    minutes_match = re.search(r"(\d+)\s*分钟前", time_str)
    if minutes_match:
        minutes = int(minutes_match.group(1))
        dt = datetime.now(timezone.utc) - timedelta(minutes=minutes)
        return dt.isoformat()

    # Handle "X 小时前" (X hours ago)
    hours_match = re.search(r"(\d+)\s*小时前", time_str)
    if hours_match:
        hours = int(hours_match.group(1))
        dt = datetime.now(timezone.utc) - timedelta(hours=hours)
        return dt.isoformat()

    # Handle "X 天前" (X days ago)
    days_match = re.search(r"(\d+)\s*天前", time_str)
    if days_match:
        days = int(days_match.group(1))
        dt = datetime.now(timezone.utc) - timedelta(days=days)
        return dt.isoformat()

    # Handle "前天" (day before yesterday)
    if "前天" in time_str:
        dt = datetime.now(timezone.utc) - timedelta(days=2)
        return dt.isoformat()

    # Handle "昨天" (yesterday)
    if "昨天" in time_str:
        dt = datetime.now(timezone.utc) - timedelta(days=1)
        return dt.isoformat()

    # Handle date format like "02-13"
    short_date_match = re.match(r"(\d{2})-(\d{2})", time_str)
    if short_date_match:
        month = int(short_date_match.group(1))
        day = int(short_date_match.group(2))
        year = datetime.now().year
        try:
            dt = datetime(year, month, day, tzinfo=timezone.utc)
            return dt.isoformat()
        except ValueError:
            pass

    # Try standard date format YYYY-MM-DD HH:MM:SS
    try:
        dt = datetime.strptime(time_str, "%Y-%m-%d %H:%M:%S")
        return dt.replace(tzinfo=timezone.utc).isoformat()
    except ValueError:
        pass

    return None


def extract_daily_news_from_html(soup, html_content):
    """Extract AI daily news from HTML structure"""
    articles = []

    # Find all news item links - they have href like /zh/daily/25844
    news_links = soup.find_all("a", href=re.compile(r"/zh/daily/\d+"))

    for link in news_links:
        try:
            # Extract URL and oid
            href = link.get("href", "")
            oid_match = re.search(r"/zh/daily/(\d+)", href)
            oid = oid_match.group(1) if oid_match else ""
            url = f"https://news.aibase.com{href}" if href.startswith("/") else href

            # Find the title - it's in a div with font600 and mainColor classes
            title_div = link.find(
                "div", class_=lambda x: x and "font600" in x and "mainColor" in x
            )
            if not title_div:
                # Try alternative selector
                title_div = link.find(
                    "div", class_=re.compile(r"font600.*truncate2|truncate2.*font600")
                )

            if not title_div:
                continue

            title = title_div.get_text(strip=True)
            if not title:
                continue

            # Extract description - it's in a div with tipColor and truncate2 classes
            description = ""
            desc_div = link.find(
                "div", class_=lambda x: x and "tipColor" in x and "truncate2" in x
            )
            if desc_div:
                description = desc_div.get_text(strip=True)

            # Clean up description - remove the boilerplate text
            cleaned_description = description
            if "欢迎来到【AI日报】栏目!" in cleaned_description:
                # Find where the actual content starts after the boilerplate
                parts = cleaned_description.split(
                    "新鲜AI产品点击了解：https://app.aibase.com/zh"
                )
                if len(parts) > 1:
                    cleaned_description = parts[1].strip()

            # Extract date/time info - try to get from JSON data first, then fall back to icon-rili
            published_date = None

            # Method 1: Try to extract createTime from the page's embedded JSON data
            # Look for the oid in the JSON data structure
            if oid:
                # The page contains JSON with createTime for each item
                # Pattern: "oid":26000,"createTime":"2026-03-06 15:47:00"
                json_pattern = f'"oid":{oid}.*?"createTime":"([^"]+)"'
                json_match = re.search(json_pattern, html_content)
                if json_match:
                    create_time_str = json_match.group(1)
                    try:
                        dt = datetime.strptime(create_time_str, "%Y-%m-%d %H:%M:%S")
                        published_date = dt.replace(tzinfo=timezone.utc).isoformat()
                    except ValueError:
                        pass

            # Method 2: Fall back to parsing relative time from the display text
            if not published_date:
                date_icon = link.find("i", class_=lambda x: x and "icon-rili" in str(x))
                if date_icon:
                    date_div = date_icon.find_parent("div")
                    if date_div:
                        date_text = date_div.get_text(strip=True)
                        published_date = parse_relative_time(date_text)

            if not published_date:
                published_date = datetime.now(timezone.utc).isoformat()

            # Generate unique ID - using only stable content (title and url) without dates
            # to ensure the ID remains consistent across fetches even when dates change
            id_components = ["aibase", title, url]
            item_id = hashlib.md5(
                "_".join(filter(None, id_components)).encode()
            ).hexdigest()

            article = compact({
                "id": item_id,
                "source": "aibase",
                "type": "daily_news",
                "title": title,
                "description": cleaned_description,
                "url": url,
                "published_date": published_date,
                "categories": ["AI Daily", "人工智能"],
                "organization": "AIBase",
            })

            articles.append(article)
            logging.info(f"Extracted AIBase daily news: {title[:50]}...")

        except Exception as e:
            logging.warning(f"Failed to parse AIBase item: {e}")
            continue

    return articles


def parse_aibase_html(soup, html_content):
    """Parse the AIBase daily HTML to extract AI daily news"""
    if not soup:
        logging.error("No soup provided")
        return []

    # Extract news from HTML structure
    articles = extract_daily_news_from_html(soup, html_content)

    if not articles:
        logging.warning("No articles found in HTML structure")
        return []

    # Remove duplicates using JSON string deduplication
    dedup_list = [
        json.loads(entry) for entry in list({json.dumps(d) for d in articles})
    ]

    # Sort by published_date in reverse chronological order (newest first)
    def get_date_for_sorting(item):
        date_str = item.get("published_date", "")
        if date_str:
            try:
                return datetime.fromisoformat(date_str.replace("Z", "+00:00"))
            except:
                pass
        return datetime.min.replace(tzinfo=timezone.utc)

    dedup_list.sort(key=get_date_for_sorting, reverse=True)

    logging.info(
        f"Successfully parsed {len(dedup_list)} unique articles from AIBase daily"
    )
    return dedup_list


def save_to_json(articles, filename):
    """Save articles to JSON file"""
    config = load_config()
    favicon = config.get("favicon") or (config.get("url", "").rstrip("/") + "/favicon.ico")
    try:
        # Derive output filename from the cache filename (e.g., aibase_zh-daily.html -> aibase_zh-daily.xml)
        output_filename = filename.replace(".html", ".xml")
        feed_path = parsed_dir / output_filename

        write_atom_feed(feed_path, articles, feed_title="AIbase", feed_link="https://news.aibase.com/zh/daily", feed_icon=favicon)
    except IOError as e:
        logging.error(f"Error writing to file: {e}")


if __name__ == "__main__":
    config = load_config()
    cache_files = config["cache_files"]

    # Process each configured cache file
    for page_type, cache_filename in cache_files.items():
        file_path = html_dir / cache_filename
        if file_path.exists():
            logging.info(f"Processing AIBase {page_type} file: {cache_filename}")
            soup, html_content = load_html(cache_filename)
            if soup:
                articles = parse_aibase_html(soup, html_content)
                if articles:
                    save_to_json(articles, cache_filename)
                else:
                    logging.error("No articles to save")
            else:
                logging.error(f"Failed to load HTML from {cache_filename}")
        else:
            logging.error(f"Required cache file not found: {cache_filename}")
