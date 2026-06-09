import hashlib
import json
import logging
import re
from datetime import datetime, timezone
from pathlib import Path

from bs4 import BeautifulSoup

from config_util import compact, load_site_config

# Configure logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)

# Directory containing the HTML files
project_dir = Path(__file__).resolve().parent.parent.parent
html_dir = project_dir / "html_cache"
parsed_dir = project_dir / "data"
# Ensure parsed directory exists
parsed_dir.mkdir(exist_ok=True)


def load_config():
    """Load site configuration from html.json"""
    return load_site_config("z-ai")


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


def parse_date_from_text(date_str):
    """Parse date text like 'Feb. 12, 2026', '2026-02-12' to ISO format"""
    if not date_str:
        return None

    # Clean up
    date_str = date_str.strip()

    # Try to parse as YYYY-MM-DD first
    if re.match(r"^\d{4}-\d{2}-\d{2}$", date_str):
        try:
            dt = datetime.strptime(date_str, "%Y-%m-%d")
            return dt.replace(tzinfo=timezone.utc).isoformat()
        except:
            pass

    # Handle abbreviated months
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

    # Try different formats
    date_formats = [
        "%b %d, %Y",  # Jan 12, 2026
        "%B %d, %Y",  # January 12, 2026
        "%b %d %Y",  # Jan 12 2026
        "%b. %d, %Y",  # Jan. 12, 2026
    ]

    for fmt in date_formats:
        try:
            dt = datetime.strptime(date_str, fmt)
            return dt.replace(tzinfo=timezone.utc).isoformat()
        except ValueError:
            continue

    logging.warning(f"Could not parse date: '{date_str}'")
    return None


def parse_z_ai_html(soup):
    """Parse the Z-AI release notes HTML to extract all model updates"""
    if not soup:
        logging.error("No soup provided")
        return []

    posts = []

    # Find all update containers - these are divs with class "update"
    update_containers = soup.find_all("div", class_="update")

    if not update_containers:
        logging.warning("No update elements found")
        return []

    for container in update_containers:
        try:
            # Get the date from the id (like "2026-02-12")
            date_id = container.get("id", "")

            # Find the date label element
            date_label = container.find(
                "div", attrs={"data-component-part": "update-label"}
            )
            date_text = date_label.get_text(strip=True) if date_label else date_id

            # Parse the date
            published_date = parse_date_from_text(date_text)

            # Find the description (model name)
            model_name = ""
            desc_elem = container.find(
                "div", attrs={"data-component-part": "update-description"}
            )
            if desc_elem:
                model_name = desc_elem.get_text(strip=True)

            # Extract title
            title = model_name if model_name else "Z-AI Model Update"

            # Find the content (all text sections)
            content_elem = container.find(
                "div", attrs={"data-component-part": "update-content"}
            )
            descriptions = []
            if content_elem:
                # Find all li elements
                list_items = content_elem.find_all("li")
                for li in list_items:
                    # Get text from span with data-as="p"
                    text_spans = li.find_all("span", attrs={"data-as": "p"})
                    for span in text_spans:
                        text = " ".join(span.get_text().split())
                        if text:
                            descriptions.append(text)

                    # If no spans, get direct text
                    if not text_spans:
                        text = " ".join(li.get_text().split())
                        if text:
                            descriptions.append(text)

            # Combine descriptions - filter out "Learn more in our documentation" phrases
            filtered = [d for d in descriptions if "learn more" not in d.lower()]
            description = (
                " ".join(filtered)
                if filtered
                else (descriptions[0] if descriptions else "")
            )

            # Generate URL
            base_url = "https://docs.z.ai/release-notes/new-released"

            # Generate unique ID (url is the same main page for all entries, use date_id to differentiate)
            id_components = ["z-ai", title, date_id]
            item_id = hashlib.md5(
                "_".join(filter(None, id_components)).encode()
            ).hexdigest()

            post = compact({
                "id": item_id,
                "source": "z-ai",
                "type": "model_update",
                "title": title,
                "description": description,
                "url": base_url,
                "published_date": published_date
                or datetime.now(timezone.utc).isoformat(),
                "categories": ["Release Notes", "Models"],
                "organization": "Z-AI",
            })
            posts.append(post)
            logging.info(f"Extracted update: {title[:50]}...")

        except Exception as e:
            logging.warning(f"Failed to parse update container: {e}")
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
        f"Successfully parsed {len(dedup_list)} unique posts from Z-AI release notes"
    )
    return dedup_list


def save_to_json(posts, filename):
    """Save posts to JSON file"""
    try:
        # Derive output filename from the cache filename (e.g., z-ai_release-notes-new-released.html -> z-ai_release-notes-new-released.json)
        output_filename = filename.replace(".html", ".json")
        json_path = parsed_dir / output_filename

        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(posts, f, indent=4, ensure_ascii=False)
            logging.info(f"Parsed data successfully written to '{json_path}'")
    except IOError as e:
        logging.error(f"Error writing to file: {e}")


if __name__ == "__main__":
    config = load_config()
    cache_files = config["cache_files"]

    # Process each configured cache file
    for page_type, cache_filename in cache_files.items():
        file_path = html_dir / cache_filename
        if file_path.exists():
            logging.info(f"Processing Z-AI {page_type} file: {cache_filename}")
            soup = load_html(cache_filename)
            if soup:
                posts = parse_z_ai_html(soup)
                if posts:
                    save_to_json(posts, cache_filename)
                else:
                    logging.error("No posts to save")
            else:
                logging.error(f"Failed to load HTML from {cache_filename}")
        else:
            logging.error(f"Required cache file not found: {cache_filename}")
