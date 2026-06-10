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
    return load_site_config("minimax")


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


def parse_minimax_html(soup):
    """Parse the MiniMax release notes HTML to extract all model updates"""
    if not soup:
        logging.error("No soup provided")
        return []

    posts = []

    # Find all h4 elements (date headers) and their following card elements
    date_headers = soup.find_all("h4", id=True)

    if not date_headers:
        logging.warning("No date header elements found")
        return []

    for header in date_headers:
        try:
            # Get the date from the id
            date_id = header.get("id", "")

            # Get the date text from the span inside h4
            date_span = header.find("span", class_="cursor-pointer")
            date_text = date_span.get_text(strip=True) if date_span else date_id

            # Parse the date
            published_date = parse_date_from_text(date_text)

            # Find the next sibling card element
            next_elem = header.find_next_sibling()
            while next_elem and not (
                next_elem.name == "div" and "card" in next_elem.get("class", [])
            ):
                next_elem = next_elem.find_next_sibling()

            if (
                not next_elem
                or next_elem.name != "div"
                or "card" not in next_elem.get("class", [])
            ):
                continue

            card = next_elem

            # Extract title
            title_elem = card.find("h2", attrs={"data-component-part": "card-title"})
            title = (
                title_elem.get_text(strip=True)
                if title_elem
                else "MiniMax Model Update"
            )

            # Extract description
            content_elem = card.find(
                "div", attrs={"data-component-part": "card-content"}
            )
            description = ""
            if content_elem:
                # Get all text, clean up whitespace
                description = " ".join(content_elem.get_text().split())

            # Extract URL
            url = card.get("href", "")
            if url and not url.startswith("http"):
                url = f"https://platform.minimax.io{url}"
            elif not url:
                url = "https://platform.minimax.io/docs/release-notes/models"

            # Generate unique ID (url is the same main page for all entries, use date_id to differentiate)
            id_components = ["minimax", title, date_id]
            item_id = hashlib.md5(
                "_".join(filter(None, id_components)).encode()
            ).hexdigest()

            post = compact(
                {
                    "id": item_id,
                    "source": "minimax",
                    "type": "model_update",
                    "title": title,
                    "description": description,
                    "url": url,
                    "published_date": published_date
                    or datetime.now(timezone.utc).isoformat(),
                    "categories": ["Release Notes", "Models"],
                    "organization": "MiniMax",
                }
            )
            posts.append(post)
            logging.info(f"Extracted update: {title[:50]}...")

        except Exception as e:
            logging.warning(f"Failed to parse header/card: {e}")
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
        f"Successfully parsed {len(dedup_list)} unique posts from MiniMax release notes"
    )
    return dedup_list


def parse_date_from_text(date_str):
    """Parse date text like 'Mar. 2026', 'Feb. 2026', 'Jan. 16, 2026' to ISO format"""
    if not date_str:
        return None

    # Clean up
    date_str = date_str.strip()

    # Try different formats
    date_formats = [
        "%b. %Y",  # Mar. 2026
        "%B %Y",  # March 2026
        "%b %d, %Y",  # Jan 16, 2026
        "%B %d, %Y",  # January 16, 2026
        "%b %d %Y",  # Jan 16 2026
        "%Y-%m-%d",  # 2026-02-12
    ]

    for fmt in date_formats:
        try:
            dt = datetime.strptime(date_str, fmt)
            return dt.replace(tzinfo=timezone.utc).isoformat()
        except ValueError:
            continue

    # Handle abbreviated months - Sept is special case
    month_replacements = {
        "Jan.": "Jan",
        "Feb.": "Feb",
        "Mar.": "Mar",
        "Apr.": "Apr",
        "May.": "May",
        "Jun.": "Jun",
        "Jul.": "Jul",
        "Aug.": "Aug",
        "Sept.": "Sep",
        "Sep.": "Sep",
        "Oct.": "Oct",
        "Nov.": "Nov",
        "Dec.": "Dec",
    }

    for old, new in month_replacements.items():
        if old in date_str:
            date_str = date_str.replace(old, new)
            break

    # Try again after replacements
    for fmt in ["%b %d, %Y", "%b %d %Y", "%b. %d, %Y", "%b. %d %Y"]:
        try:
            dt = datetime.strptime(date_str, fmt)
            return dt.replace(tzinfo=timezone.utc).isoformat()
        except ValueError:
            continue

    # Try to extract just the year/month if full date fails
    # Handle formats like "Mar. 2026" -> assume 1st of month
    match = re.match(r"([A-Za-z]+)\.?\s+(\d{4})", date_str)
    if match:
        try:
            month_str = match.group(1)
            year = int(match.group(2))
            month_map = {
                "jan": 1,
                "feb": 2,
                "mar": 3,
                "apr": 4,
                "may": 5,
                "jun": 6,
                "jul": 7,
                "aug": 8,
                "sep": 9,
                "oct": 10,
                "nov": 11,
                "dec": 12,
            }
            month_lower = month_str.lower()[:3]
            if month_lower in month_map:
                dt = datetime(year, month_map[month_lower], 1, tzinfo=timezone.utc)
                return dt.isoformat()
        except:
            pass

    logging.warning(f"Could not parse date: '{date_str}'")
    return None


def save_to_json(posts, filename):
    """Save posts to JSON file"""
    config = load_config()
    favicon = config.get("favicon") or (
        config.get("url", "").rstrip("/") + "/favicon.ico"
    )
    try:
        # Derive output filename from the cache filename (e.g., minimax_docs-release-notes-models.html -> minimax_docs-release-notes-models.xml)
        output_filename = filename.replace(".html", ".xml")
        feed_path = parsed_dir / output_filename

        write_atom_feed(
            feed_path,
            posts,
            feed_title="MiniMax",
            feed_link="https://platform.minimax.io/docs/release-notes/models",
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
            logging.info(f"Processing MiniMax {page_type} file: {cache_filename}")
            soup = load_html(cache_filename)
            if soup:
                posts = parse_minimax_html(soup)
                if posts:
                    save_to_json(posts, cache_filename)
                else:
                    logging.error("No posts to save")
            else:
                logging.error(f"Failed to load HTML from {cache_filename}")
        else:
            logging.error(f"Required cache file not found: {cache_filename}")
