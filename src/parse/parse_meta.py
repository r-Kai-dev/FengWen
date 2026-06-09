import hashlib
import json
import logging
import re
from datetime import datetime, timezone
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
    return load_site_config("meta")


def load_html(filename):
    """Load HTML content from cache file"""
    file_path = html_dir / filename
    try:
        with open(file_path, "r", encoding="utf-8") as file:
            html_content = file.read()
    except FileNotFoundError:
        logging.error(f"File not found: {file_path}")
        return None
    except Exception as e:
        logging.error(f"Error reading file {file_path}: {e}")
        return None

    soup = BeautifulSoup(html_content, "html.parser")
    return soup


def parse_date(date_str):
    """Parse date string to ISO format"""
    if not date_str:
        return None

    # Clean up the date string
    date_str = date_str.strip()

    # Try different date formats
    date_formats = [
        "%B %d, %Y",  # December 16, 2025
        "%b %d, %Y",  # Dec 16, 2025
        "%B %d %Y",  # December 16 2025
        "%b %d %Y",  # Dec 16 2025
        "%Y-%m-%d",  # 2025-12-16
    ]

    for fmt in date_formats:
        try:
            dt = datetime.strptime(date_str, fmt)
            return dt.replace(tzinfo=timezone.utc).isoformat()
        except ValueError:
            continue

    # Try to extract date from format like "Feb 9, 2026"
    try:
        # Remove extra spaces and normalize
        date_str = re.sub(r"\s+", " ", date_str)
        dt = datetime.strptime(date_str, "%b %d, %Y")
        return dt.replace(tzinfo=timezone.utc).isoformat()
    except ValueError:
        pass

    logging.warning(f"Could not parse date: '{date_str}'")
    return None


def extract_featured_post(soup):
    """Extract the featured post from the hero section"""
    posts = []

    featured_container = soup.find(
        "div", class_="_metaAIFeaturedBlogHero__heroContainer"
    )
    if not featured_container:
        logging.debug("No featured container found")
        return posts

    title_elem = featured_container.find("div", class_="_amd1")
    if not title_elem:
        return posts

    link_elem = title_elem.find("a", class_="_amd2")
    if not link_elem:
        return posts

    title = link_elem.get_text(strip=True)
    url = link_elem.get("href", "")
    if not url:
        return posts

    # Extract date
    date_elem = featured_container.find("div", class_="_amun")
    date_str = date_elem.get_text(strip=True) if date_elem else None
    published_date = parse_date(date_str)
    if not published_date:
        published_date = datetime.now(timezone.utc).isoformat()

    # Stable ID (without date)
    id_components = ["meta_ai", title, url]
    item_id = hashlib.md5("_".join(filter(None, id_components)).encode()).hexdigest()

    post = compact({
        "id": item_id,
        "source": "meta_ai",
        "type": "blog",
        "title": title,
        "url": url if url.startswith("http") else f"https://ai.meta.com{url}",
        "published_date": published_date,
        "organization": "Meta AI",
    })
    posts.append(post)
    logging.info(f"Extracted featured post: {title[:50]}...")

    return posts


def extract_latest_news(soup):
    """Extract posts from the Latest News section"""
    posts = []

    news_cards = soup.find_all("div", class_="_amda")

    for card in news_cards:
        try:
            title_elem = card.find("div", class_="_amde")
            if not title_elem:
                continue

            link_elem = title_elem.find("a", class_="_amdf")
            if not link_elem:
                continue

            title = link_elem.get_text(strip=True)
            url = link_elem.get("href", "")
            if not title or not url:
                continue

            # Extract category (first _amdj div)
            category_elem = card.find("div", class_="_amdj")
            categories = [category_elem.get_text(strip=True)] if category_elem else []

            # Extract date (second _amdj div)
            date_divs = card.find_all("div", class_="_amdj")
            date_str = None
            for div in date_divs:
                text = div.get_text(strip=True)
                if re.match(
                    r"^(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)", text
                ):
                    date_str = text
                    break

            published_date = parse_date(date_str)
            if not published_date:
                published_date = datetime.now(timezone.utc).isoformat()

            # Stable ID (without date)
            id_components = ["meta_ai", title, url]
            item_id = hashlib.md5("_".join(filter(None, id_components)).encode()).hexdigest()

            post = compact({
                "id": item_id,
                "source": "meta_ai",
                "type": "blog",
                "title": title,
                "url": url if url.startswith("http") else f"https://ai.meta.com{url}",
                "published_date": published_date,
                "categories": categories,
                "organization": "Meta AI",
            })
            posts.append(post)
            logging.info(f"Extracted news post: {title[:50]}...")

        except Exception as e:
            logging.warning(f"Failed to parse news card: {e}")
            continue

    return posts





def parse_meta_ai_html(soup):
    """Parse the Meta AI blog HTML to extract all blog posts"""
    if not soup:
        logging.error("No soup provided")
        return []

    all_posts = []

    # Extract featured post
    featured_posts = extract_featured_post(soup)
    all_posts.extend(featured_posts)

    # Extract latest news posts
    latest_posts = extract_latest_news(soup)
    all_posts.extend(latest_posts)

    # Remove duplicates using JSON string deduplication
    dedup_list = [
        json.loads(entry) for entry in list({json.dumps(d) for d in all_posts})
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
        f"Successfully parsed {len(dedup_list)} unique posts from Meta AI blog"
    )
    return dedup_list


def save_to_json(posts, filename):
    """Save posts to JSON file"""
    config = load_config()
    favicon = config.get("favicon") or (config.get("url", "").rstrip("/") + "/favicon.ico")
    try:
        # Derive output filename from the cache filename (e.g., meta_blog.html -> meta_blog.xml)
        output_filename = filename.replace(".html", ".xml")
        feed_path = parsed_dir / output_filename

        write_atom_feed(feed_path, posts, feed_title="Meta AI", feed_link="https://ai.meta.com/blog", feed_icon=favicon)
    except IOError as e:
        logging.error(f"Error writing to file: {e}")


if __name__ == "__main__":
    config = load_config()
    cache_files = config["cache_files"]

    # Process each configured cache file
    for page_type, cache_filename in cache_files.items():
        file_path = html_dir / cache_filename
        if file_path.exists():
            logging.info(f"Processing Meta AI {page_type} file: {cache_filename}")
            soup = load_html(cache_filename)
            if soup:
                posts = parse_meta_ai_html(soup)
                if posts:
                    save_to_json(posts, cache_filename)
                else:
                    logging.error("No posts to save")
            else:
                logging.error(f"Failed to load HTML from {cache_filename}")
        else:
            logging.error(f"Required cache file not found: {cache_filename}")
