import hashlib
import json
import logging
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
    return load_site_config("kimi")


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
    """Parse date string like '2026/04/20' to ISO format"""
    if not date_str:
        return None
    date_str = date_str.strip()
    try:
        dt = datetime.strptime(date_str, "%Y/%m/%d")
        return dt.replace(tzinfo=timezone.utc).isoformat()
    except ValueError:
        pass
    logging.warning(f"Could not parse date: '{date_str}'")
    return None


def extract_posts(soup):
    """Extract blog posts from the Kimi blog HTML.

    The page uses VitePress with card elements:
      <a class="menu-card" href="/blog/slug">
        <div class="card-body">
          <h4 class="card-title">Title</h4>
          <p class="card-desc">Description</p>
          <p class="card-date">2026/04/20</p>
        </div>
      </a>
    """
    posts = []

    # Find all menu-card links
    card_links = soup.find_all("a", class_="menu-card")
    logging.info(f"Found {len(card_links)} blog cards on the page")

    for link in card_links:
        try:
            href = link.get("href", "")
            if not href or not href.startswith("/blog/"):
                continue

            # Title
            title_elem = link.find("h4", class_="card-title")
            if not title_elem:
                continue
            title = title_elem.get_text(strip=True)

            # URL
            url = f"https://www.kimi.com{href}"

            # Description
            desc_elem = link.find("p", class_="card-desc")
            description = desc_elem.get_text(strip=True) if desc_elem else ""

            # Date
            date_elem = link.find("p", class_="card-date")
            date_str = date_elem.get_text(strip=True) if date_elem else None
            published_date = parse_date(date_str)
            if not published_date:
                published_date = datetime.now(timezone.utc).isoformat()

            # Stable ID
            id_components = ["kimi", title, url]
            item_id = hashlib.md5(
                "_".join(filter(None, id_components)).encode()
            ).hexdigest()

            post = compact({
                "id": item_id,
                "source": "kimi",
                "type": "blog",
                "title": title,
                "description": description,
                "url": url,
                "published_date": published_date,
                "categories": ["Research"],
                "organization": "Kimi",
            })
            posts.append(post)
            logging.info(f"Extracted post: {title[:50]}...")

        except Exception as e:
            logging.warning(f"Failed to parse blog card: {e}")
            continue

    return posts


def main():
    """Main function to run the scraper"""
    logging.info("Starting Kimi blog scraper...")

    config = load_config()
    output_filename = config["output_files"].get("blog", "kimi_blog.xml")
    cache_filename = config["cache_files"].get("blog", "kimi_blog.html")
    favicon = config.get("favicon") or (config.get("url", "").rstrip("/") + "/favicon.ico")

    logging.info(f"Output file: {output_filename}")
    logging.info(f"Cache file: {cache_filename}")

    soup = load_html(cache_filename)
    if not soup:
        logging.error("Failed to load HTML")
        return

    posts = extract_posts(soup)

    if not posts:
        logging.warning("No posts found")
        posts = []

    posts.sort(key=lambda x: x.get("published_date", ""), reverse=True)

    feed_path = parsed_dir / output_filename
    write_atom_feed(feed_path, posts, feed_title="Kimi (Moonshot AI)", feed_link="https://www.kimi.com/blog", feed_icon=favicon)


if __name__ == "__main__":
    main()
