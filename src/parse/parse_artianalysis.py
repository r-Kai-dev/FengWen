import hashlib
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
    return load_site_config("artificial_analysis")


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

    date_str = date_str.strip()

    # All dates on the page are "Month Day, Year" format (e.g., "June 4, 2026")
    try:
        dt = datetime.strptime(date_str, "%B %d, %Y")
        return dt.replace(tzinfo=timezone.utc).isoformat()
    except ValueError:
        pass

    logging.warning(f"Could not parse date: '{date_str}'")
    return None


def extract_articles(soup):
    """Extract articles from the HTML"""
    articles = []

    # Find all article links with href starting with /articles/
    article_links = soup.find_all("a", href=re.compile(r"^/articles/"))

    logging.info(f"Found {len(article_links)} article links")

    for link in article_links:
        try:
            # Get the href (slug)
            href = link.get("href", "")

            # Get the title from h3 element
            title_elem = link.find("h3")
            title = title_elem.get_text(strip=True) if title_elem else ""

            # Get the date from p element
            date_elem = link.find("p")
            date_str = date_elem.get_text(strip=True) if date_elem else ""

            if not title:
                logging.warning(f"Skipping article without title: {href}")
                continue

            # Parse the date
            published_date = parse_date(date_str)
            if not published_date:
                published_date = datetime.now(timezone.utc).isoformat()

            # Generate URL
            url = f"https://artificialanalysis.ai{href}"

            # Generate unique ID
            id_components = ["artificial_analysis", title, url]
            item_id = hashlib.md5(
                "_".join(filter(None, id_components)).encode()
            ).hexdigest()

            article = compact(
                {
                    "id": item_id,
                    "source": "artificial_analysis",
                    "type": "article",
                    "title": title,
                    "url": url,
                    "published_date": published_date,
                    "organization": "Artificial Analysis",
                }
            )
            articles.append(article)
            logging.info(f"Extracted article: {title[:50]}...")

        except Exception as e:
            logging.warning(f"Failed to parse article: {e}")
            continue

    return articles


def main():
    """Main function to run the scraper"""
    logging.info("Starting Artificial Analysis scraper...")

    # Load configuration
    config = load_config()
    output_filename = config["output_files"].get("articles", "artificial_analysis.xml")
    cache_filename = config["cache_files"].get("articles", "artificial_analysis.html")
    favicon = config.get("favicon") or (
        config.get("url", "").rstrip("/") + "/favicon.ico"
    )

    logging.info(f"Output file: {output_filename}")
    logging.info(f"Cache file: {cache_filename}")

    # Load HTML
    soup = load_html(cache_filename)
    if not soup:
        logging.error("Failed to load HTML")
        return

    # Extract articles
    articles = extract_articles(soup)

    if not articles:
        logging.warning("No articles found")
        # Save empty array to maintain consistency
        articles = []

    # Sort articles by published_date descending
    articles.sort(key=lambda x: x.get("published_date", ""), reverse=True)

    # Save to JSON
    feed_path = parsed_dir / output_filename
    write_atom_feed(
        feed_path,
        articles,
        feed_title="Artificial Analysis",
        feed_link="https://artificialanalysis.ai/articles",
        feed_icon=favicon,
    )


if __name__ == "__main__":
    main()
