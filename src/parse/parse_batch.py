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
    return load_site_config("deeplearning_ai")


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


def parse_datetime_attr(dt_str):
    """Parse an ISO datetime string from a time[datetime] attribute."""
    if not dt_str:
        return None
    try:
        dt = datetime.fromisoformat(dt_str.replace("Z", "+00:00"))
        return dt.isoformat()
    except ValueError:
        pass
    return None


def extract_posts(soup):
    """Extract posts from the server-rendered HTML.

    Handles three card types:
      - PostCardLarge (hero/featured article)
      - PostCard (regular grid articles)
      - PostCardSmall (sidebar articles)
    """
    posts = []

    # Collect article cards: PostCardLarge, PostCard (regular), PostCardSmall
    cards = []
    for article in soup.find_all("article", attrs={"data-sentry-component": "PostCard"}):
        src = article.get("data-sentry-source-file", "")
        if src in ("PostCardLarge.tsx", "PostCard.tsx"):
            cards.append(article)
    for article in soup.find_all("article", attrs={"data-sentry-component": "PostCardSmall"}):
        cards.append(article)

    logging.info(f"Found {len(cards)} post cards on the page")

    for article in cards:
        try:
            # Title
            title_elem = article.find("h2")
            if not title_elem:
                continue
            title = title_elem.get_text(strip=True)

            # URL: find <a> linking to /the-batch/... (not /the-batch/tag/...)
            main_link = article.find("a", href=re.compile(r"^/the-batch/(?!tag/)"))
            if not main_link:
                continue
            url = f"https://www.deeplearning.ai{main_link['href']}"

            # Description: div with line-clamp-3
            desc_elem = article.find("div", class_=lambda c: c and "line-clamp-3" in c)
            description = desc_elem.get_text(strip=True) if desc_elem else ""

            # Date from time[datetime] attribute
            published_date = None
            time_elem = article.find("time")
            if time_elem:
                published_date = parse_datetime_attr(time_elem.get("datetime", ""))
            # Fallback: date from tag link text (e.g., "Jun 05, 2026")
            if not published_date:
                tag_link = article.find("a", href=re.compile(r"^/the-batch/tag/"))
                if tag_link:
                    tag_text = tag_link.get_text(strip=True)
                    try:
                        dt = datetime.strptime(tag_text, "%b %d, %Y")
                        published_date = dt.replace(tzinfo=timezone.utc).isoformat()
                    except ValueError:
                        pass
            if not published_date:
                published_date = datetime.now(timezone.utc).isoformat()

            # Stable ID
            id_components = ["deeplearning_ai", title, url]
            item_id = hashlib.md5("_".join(filter(None, id_components)).encode()).hexdigest()

            post = compact({
                "id": item_id,
                "source": "deeplearning_ai",
                "type": "newsletter",
                "title": title,
                "description": description,
                "url": url,
                "published_date": published_date,
                "organization": "DeepLearning.AI",
            })
            posts.append(post)
            logging.info(f"Extracted post: {title[:50]}...")

        except Exception as e:
            logging.warning(f"Failed to parse post card: {e}")
            continue

    return posts


def main():
    """Main function to run the scraper"""
    logging.info("Starting DeepLearning AI The Batch scraper...")

    # Load configuration
    config = load_config()
    output_filename = config["output_files"].get("the-batch", "deeplearning_ai_the-batch.xml")
    cache_filename = config["cache_files"].get("the-batch", "deeplearning_ai_the-batch.html")
    favicon = config.get("favicon") or (config.get("url", "").rstrip("/") + "/favicon.ico")

    logging.info(f"Output file: {output_filename}")
    logging.info(f"Cache file: {cache_filename}")

    # Load HTML
    soup = load_html(cache_filename)
    if not soup:
        logging.error("Failed to load HTML")
        return

    # Extract posts
    posts = extract_posts(soup)

    if not posts:
        logging.warning("No posts found")
        # Save empty array to maintain consistency
        posts = []

    # Sort posts by published_date descending
    posts.sort(key=lambda x: x.get("published_date", ""), reverse=True)

    # Save to JSON
    feed_path = parsed_dir / output_filename
    write_atom_feed(feed_path, posts, feed_title="DeepLearning.AI", feed_link="https://www.deeplearning.ai/the-batch", feed_icon=favicon)


if __name__ == "__main__":
    main()
