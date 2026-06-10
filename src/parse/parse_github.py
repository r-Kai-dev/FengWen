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
    return load_site_config("github")


def load_html(filename):
    file_path = html_dir / filename
    # Read the HTML file
    try:
        with open(file_path, "r", encoding="utf-8") as file:
            html_content = file.read()
    except FileNotFoundError:
        logging.error(f"File not found: {file_path}")
        return None
    except Exception as e:
        logging.error(f"Error reading file {file_path}: {e}")
        return None

    # Parse the HTML content
    soup = BeautifulSoup(html_content, "html.parser")
    return soup


def extract_trending_data(soup, timeframe="monthly"):
    """Extract trending repositories from GitHub trending page"""
    repositories = []
    base_url = "https://github.com"

    # Find repository articles
    repo_articles = soup.find_all("article", class_="Box-row")

    for article in repo_articles:
        try:
            # Extract repository name and URL
            title_element = article.find("h2", class_="h3 lh-condensed")
            if not title_element:
                continue

            repo_link = title_element.find("a")
            if not repo_link:
                continue

            repo_name = repo_link.get_text(strip=True)
            repo_url = base_url + repo_link.get("href", "")

            # Extract org/repo path for deduplication
            repo_path = repo_link.get("href", "").strip("/")

            # Format title with proper spacing around forward slash
            if "/" in repo_path:
                formatted_title = repo_path.replace("/", " / ")
            else:
                formatted_title = repo_name

            # Extract description
            description_element = article.find(
                "p", class_="col-9 color-fg-muted my-1 tmp-pr-4"
            )
            description = (
                description_element.get_text(strip=True) if description_element else ""
            )

            # Extract programming language
            language_element = article.find("span", itemprop="programmingLanguage")
            language = language_element.get_text(strip=True) if language_element else ""

            # Extract stars count
            stars_element = article.find("a", href=re.compile(r"/stargazers$"))
            stars_text = stars_element.get_text(strip=True) if stars_element else "0"
            # Clean stars text (remove commas and convert k to thousands)
            stars_clean = stars_text.replace(",", "")
            if "k" in stars_clean.lower():
                stars_clean = stars_clean.lower().replace("k", "")
                try:
                    stars_count = int(float(stars_clean) * 1000)
                except:
                    stars_count = 0
            else:
                try:
                    stars_count = int(stars_clean)
                except:
                    stars_count = 0

            # Extract forks count
            forks_element = article.find("a", href=re.compile(r"/forks$"))
            forks_text = forks_element.get_text(strip=True) if forks_element else "0"
            # Clean forks text
            forks_clean = forks_text.replace(",", "")
            if "k" in forks_clean.lower():
                forks_clean = forks_clean.lower().replace("k", "")
                try:
                    forks_count = int(float(forks_clean) * 1000)
                except:
                    forks_count = 0
            else:
                try:
                    forks_count = int(forks_clean)
                except:
                    forks_count = 0

            # Extract stars today (trending metric)
            stars_today_element = article.find(
                "span", class_="d-inline-block float-sm-right"
            )
            stars_today_text = (
                stars_today_element.get_text(strip=True)
                if stars_today_element
                else "0 stars today"
            )
            # Extract number from "X stars today" text
            stars_today_match = re.search(r"(\d+(?:,\d+)*)", stars_today_text)
            stars_today = (
                int(stars_today_match.group(1).replace(",", ""))
                if stars_today_match
                else 0
            )

            # Generate unique ID based on repository path (stable across updates)
            item_id = hashlib.md5(f"github_trending_{repo_path}".encode()).hexdigest()

            repository = compact(
                {
                    "id": item_id,
                    "source": "github",
                    "type": "trending_repository",
                    "title": formatted_title,
                    "description": description,
                    "url": repo_url,
                    "published_date": datetime.now(timezone.utc).isoformat(),
                    "categories": [language] if language else [],
                    "metadata": {
                        "stars": stars_count,
                        "forks": forks_count,
                        "stars_today": stars_today,
                        "language": language,
                        "timeframe": timeframe,
                        "repo_path": repo_path,
                    },
                }
            )

            repositories.append(repository)

        except Exception as e:
            logging.warning(f"Failed to parse repository: {e}")
            continue

    return repositories


def deduplicate_repositories(all_repositories):
    """Deduplicate repositories by repo_path, keeping the one with highest stars_today"""
    repo_dict = {}

    for repo in all_repositories:
        repo_path = repo["metadata"]["repo_path"]

        # If this repo path hasn't been seen or has higher stars_today, keep it
        if (
            repo_path not in repo_dict
            or repo["metadata"]["stars_today"]
            > repo_dict[repo_path]["metadata"]["stars_today"]
        ):
            repo_dict[repo_path] = repo

    return list(repo_dict.values())


def save_to_json(
    repositories, output_filename, feed_icon=None, feed_title=None, feed_link=None
):
    """Save repositories to JSON file"""
    # Sort by stars_today (trending metric) in descending order
    repositories.sort(key=lambda x: x["metadata"].get("stars_today", 0), reverse=True)

    # Derive feed link and title from output_filename if not provided
    if not feed_title:
        if "daily" in output_filename:
            feed_title = "GitHub Trending (Daily)"
        elif "weekly" in output_filename:
            feed_title = "GitHub Trending (Weekly)"
        elif "monthly" in output_filename:
            feed_title = "GitHub Trending (Monthly)"
        else:
            feed_title = "GitHub Trending"
    if not feed_link:
        if "daily" in output_filename:
            feed_link = "https://github.com/trending?since=daily"
        elif "weekly" in output_filename:
            feed_link = "https://github.com/trending?since=weekly"
        elif "monthly" in output_filename:
            feed_link = "https://github.com/trending?since=monthly"
        else:
            feed_link = "https://github.com/trending"

    feed_path = parsed_dir / output_filename
    write_atom_feed(
        feed_path,
        repositories,
        feed_title=feed_title,
        feed_link=feed_link,
        feed_icon=feed_icon,
    )

    logging.info(
        f"Successfully saved {len(repositories)} trending repositories to {feed_path}"
    )


def merge_with_existing(new_repositories, combined_output, feed_icon=None):
    """Merge newly parsed repos with the existing stateful JSON.

    Repos currently on trending replace their old entry (fresh data + timestamp).
    Repos that have dropped off trending remain in the file unchanged.
    """
    feed_path = parsed_dir / combined_output

    # Load existing entries by id
    existing_by_id = {}
    if feed_path.exists():
        try:
            with open(feed_path, "r", encoding="utf-8") as f:
                existing = json.load(f)
            for repo in existing:
                existing_by_id[repo["id"]] = repo
        except (json.JSONDecodeError, IOError) as e:
            logging.warning(f"Could not load existing {combined_output}: {e}")

    # Build merged list: start with old entries, overlay current ones
    merged_by_id = dict(existing_by_id)
    for repo in new_repositories:
        merged_by_id[repo["id"]] = repo  # replace or add

    merged = list(merged_by_id.values())

    logging.info(
        f"Merge result: {len(existing_by_id)} old + {len(new_repositories)} current = {len(merged)} total "
        f"({len(merged) - len(new_repositories)} carried over from previous runs)"
    )

    save_to_json(merged, combined_output, feed_icon=feed_icon)


if __name__ == "__main__":
    config = load_config()
    cache_files = config["cache_files"]
    output_files = config["output_files"]
    favicon = config.get("favicon") or (
        config.get("url", "").rstrip("/") + "/favicon.ico"
    )

    all_repositories = []
    timeframes = ["daily", "weekly", "monthly"]

    # Process each timeframe
    for timeframe in timeframes:
        cache_key = f"trending?since={timeframe}"
        cache_filename = cache_files.get(cache_key)
        individual_output = output_files.get(cache_key)

        if not cache_filename:
            logging.warning(f"No cache file configured for {cache_key}")
            continue

        file_path = html_dir / cache_filename
        if file_path.exists():
            logging.info(f"Processing GitHub trending file: {cache_filename}")
            soup = load_html(cache_filename)
            if soup:
                repositories = extract_trending_data(soup, timeframe)
                all_repositories.extend(repositories)

                # Save individual timeframe file
                if individual_output:
                    save_to_json(repositories, individual_output, feed_icon=favicon)
            else:
                logging.error(f"Failed to load HTML content for {cache_filename}")
        else:
            logging.warning(f"Cache file not found: {cache_filename}")

    # Deduplicate and merge combined results
    if all_repositories:
        logging.info(
            f"Found {len(all_repositories)} total repositories before deduplication"
        )
        deduplicated_repositories = deduplicate_repositories(all_repositories)
        logging.info(
            f"After deduplication: {len(deduplicated_repositories)} repositories"
        )

        # Merge with existing stateful data (carry over repos from previous runs)
        combined_output = output_files.get("trending_combined", "github_trends.xml")
        merge_with_existing(
            deduplicated_repositories, combined_output, feed_icon=favicon
        )
    else:
        logging.error("No repositories found to process")
