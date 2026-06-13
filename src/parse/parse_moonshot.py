import hashlib
import json
import logging
from datetime import datetime, timezone
from pathlib import Path

from bs4 import BeautifulSoup
from config_util import load_site_config
from feed_util import compact, write_atom_feed

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
    return load_site_config("moonshot")


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
        "%Y-%m-%d",  # 2025-12-31
        "%Y/%m/%d",  # 2025/12/31
        "%B %d, %Y",  # December 31, 2025
        "%b %d, %Y",  # Dec 31, 2025
    ]

    for fmt in date_formats:
        try:
            dt = datetime.strptime(date_str, fmt)
            return dt.replace(tzinfo=timezone.utc).isoformat()
        except ValueError:
            continue

    logging.warning(f"Could not parse date: '{date_str}'")
    return None


def parse_moonshot_html(soup):
    """Parse the Moonshot blog HTML to extract all blog posts"""
    if not soup:
        logging.error("No soup provided")
        return []

    posts = []

    # Find all post-item divs
    post_items = soup.find_all("div", class_="post-item")

    if not post_items:
        logging.warning("No post-item elements found")
        return []

    for item in post_items:
        try:
            # Extract title and URL from h3 > a
            title_elem = item.find("h3")
            if not title_elem:
                continue

            link_elem = title_elem.find("a")
            if not link_elem:
                continue

            title = link_elem.get_text(strip=True)
            url_path = link_elem.get("href", "")

            # Build full URL
            base_url = "https://platform.moonshot.ai"
            url = url_path if url_path.startswith("http") else f"{base_url}{url_path}"

            # Extract description from p
            desc_elem = item.find("p")
            description = desc_elem.get_text(strip=True) if desc_elem else ""

            # Remove "Read More →" from description if present
            if "Read More" in description:
                description = description.split("Read More")[0].strip()

            # Extract date from time element
            time_elem = item.find("time")
            published_date = None
            if time_elem:
                date_str = time_elem.get("datetime", "")
                if date_str:
                    # Parse ISO format date
                    try:
                        dt = datetime.fromisoformat(date_str.replace("Z", "+00:00"))
                        published_date = dt.isoformat()
                    except:
                        pass

                if not published_date:
                    date_str = time_elem.get_text(strip=True)
                    published_date = parse_date(date_str)

            if not published_date:
                published_date = datetime.now(timezone.utc).isoformat()

            # Generate unique ID
            id_components = ["moonshot", title, url]
            item_id = hashlib.md5(
                "_".join(filter(None, id_components)).encode()
            ).hexdigest()

            post = compact(
                {
                    "id": item_id,
                    "source": "moonshot",
                    "type": "blog",
                    "title": title,
                    "description": description,
                    "summary": description,
                    "url": url,
                    "published_date": published_date,
                    "categories": ["Blog"],
                    "organization": "Moonshot AI",
                }
            )
            posts.append(post)
            logging.info(f"Extracted post: {title[:50]}...")

        except Exception as e:
            logging.warning(f"Failed to parse post item: {e}")
            continue

    # Remove duplicates using JSON string deduplication
    dedup_list = [json.loads(entry) for entry in list({json.dumps(d) for d in posts})]

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
        f"Successfully parsed {len(dedup_list)} unique posts from Moonshot blog"
    )
    return dedup_list


def save_to_json(posts, filename):
    """Save posts to JSON file"""
    try:
        config = load_config()
        output_files = config["output_files"]
        favicon = config.get("favicon") or (
            config.get("url", "").rstrip("/") + "/favicon.ico"
        )

        # Determine the output filename based on the cache filename
        if "blog" in filename:
            page_type = "blog"
        else:
            page_type = "main"

        output_filename = output_files.get(page_type, "moonshot_blog.xml")
        feed_path = parsed_dir / output_filename

        write_atom_feed(
            feed_path,
            posts,
            feed_title="Moonshot AI",
            feed_link="https://platform.moonshot.ai/blog",
            feed_icon=favicon,
        )
    except IOError as e:
        logging.error(f"Error writing to file: {e}")


if __name__ == "__main__":
    config = load_config()
    cache_files = config["cache_files"]

    # Process each configured cache file
    for page_type, cache_filename in cache_files.items():
        file_path = html_dir / cache_filename
        if file_path.exists():
            logging.info(f"Processing Moonshot {page_type} file: {cache_filename}")
            soup = load_html(cache_filename)
            if soup:
                posts = parse_moonshot_html(soup)
                if posts:
                    save_to_json(posts, cache_filename)
                else:
                    logging.error("No posts to save")
            else:
                logging.error(f"Failed to load HTML from {cache_filename}")
        else:
            logging.error(f"Required cache file not found: {cache_filename}")
