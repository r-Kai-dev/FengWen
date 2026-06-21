"""Scrape GitHub trending repositories (daily, weekly, monthly + combined feed)."""

import hashlib
import json
import logging
import re
from datetime import datetime, timezone

from bs4 import BeautifulSoup

from utils import (
    FEEDS_DIR, setup_logging, ensure_output_dir,
    load_feeds_config, fetch_page, compact, write_atom_feed,
)

setup_logging()
ensure_output_dir()
ORG_KEY = "github"
BASE_URL = "https://github.com"


def _format_count(num):
    if num >= 1000:
        return f"{num / 1000:.1f}k".rstrip("0").rstrip(".")
    return str(num)


def extract_repos(soup, timeframe):
    repos = []
    for article in soup.find_all("article", class_="Box-row"):
        title_el = article.find("h2", class_="h3 lh-condensed")
        if not title_el:
            continue
        repo_link = title_el.find("a")
        if not repo_link:
            continue

        repo_path = repo_link.get("href", "").strip("/")
        formatted_title = repo_path.replace("/", " / ") if "/" in repo_path else repo_link.get_text(strip=True)
        repo_url = BASE_URL + repo_link.get("href", "")

        desc_el = article.find("p", class_="col-9 color-fg-muted my-1 tmp-pr-4")
        description = desc_el.get_text(strip=True) if desc_el else ""

        lang_el = article.find("span", itemprop="programmingLanguage")
        language = lang_el.get_text(strip=True) if lang_el else ""

        stars_el = article.find("a", href=re.compile(r"/stargazers$"))
        stars_text = stars_el.get_text(strip=True).replace(",", "") if stars_el else "0"
        stars_count = int(float(stars_text.lower().replace("k", "")) * 1000) if "k" in stars_text.lower() else (int(stars_text) if stars_text.isdigit() else 0)

        forks_el = article.find("a", href=re.compile(r"/forks$"))
        forks_text = forks_el.get_text(strip=True).replace(",", "") if forks_el else "0"
        forks_count = int(float(forks_text.lower().replace("k", "")) * 1000) if "k" in forks_text.lower() else (int(forks_text) if forks_text.isdigit() else 0)

        stars_today_el = article.find("span", class_="d-inline-block float-sm-right")
        stars_today_text = stars_today_el.get_text(strip=True) if stars_today_el else "0 stars today"
        stars_today_match = re.search(r"(\d+(?:,\d+)*)", stars_today_text)
        stars_today = int(stars_today_match.group(1).replace(",", "")) if stars_today_match else 0

        item_id = hashlib.md5(f"github_trending_{repo_path}".encode()).hexdigest()

        content_parts = []
        if description:
            content_parts.append(f"<p>{description}</p>")
        meta = []
        meta.append(f"\u2b50 <strong>{_format_count(stars_count)}</strong> stars")
        meta.append(f"\U0001f374 <strong>{_format_count(forks_count)}</strong> forks")
        meta.append(f"\U0001f525 <strong>{_format_count(stars_today)}</strong> stars today")
        if language:
            meta.append(f"\U0001f4bb <strong>{language}</strong>")
        content_parts.append(f"<p>{' &middot; '.join(meta)}</p>")

        repos.append(compact({
            "id": item_id, "source": "github", "type": "trending_repository",
            "title": formatted_title, "url": repo_url,
            "summary": description, "content": "\n".join(content_parts),
            "published_date": datetime.now(timezone.utc).isoformat(),
            "categories": [language] if language else [],
            "metadata": {"stars": stars_count, "forks": forks_count,
                         "stars_today": stars_today, "language": language,
                         "timeframe": timeframe, "repo_path": repo_path},
        }))
    return repos


def deduplicate(repos):
    by_path = {}
    for r in repos:
        rp = r["metadata"]["repo_path"]
        if rp not in by_path or r["metadata"]["stars_today"] > by_path[rp]["metadata"]["stars_today"]:
            by_path[rp] = r
    return list(by_path.values())


def write_feed(repos, output_file, feed_title, feed_link, favicon):
    repos.sort(key=lambda x: x["metadata"].get("stars_today", 0), reverse=True)
    write_atom_feed(FEEDS_DIR / output_file, repos,
                    feed_title=feed_title, feed_link=feed_link, feed_icon=favicon)


def main():
    config = load_feeds_config(ORG_KEY)
    favicon = config.get("favicon") or (config.get("base_url", "").rstrip("/") + "/favicon.ico")

    timeframes = [
        ("trending_daily", "daily", "https://github.com/trending?since=daily"),
        ("trending_weekly", "weekly", "https://github.com/trending?since=weekly"),
        ("trending_monthly", "monthly", "https://github.com/trending?since=monthly"),
    ]

    all_repos = []
    for page_key, tf, url in timeframes:
        page = config["pages"].get(page_key)
        if not page:
            continue
        logging.info("Fetching %s: %s", page["label"], url)
        html = fetch_page(url)
        soup = BeautifulSoup(html, "html.parser")
        repos = extract_repos(soup, tf)
        all_repos.extend(repos)
        write_feed(repos, page["output_file"], page["label"], url, favicon)

    # Combined feed
    combined_page = config["pages"].get("trending_combined")
    if combined_page and all_repos:
        deduped = deduplicate(all_repos)
        deduped.sort(key=lambda x: x["metadata"].get("stars_today", 0), reverse=True)
        write_feed(deduped, combined_page["output_file"],
                   combined_page["label"], combined_page["url"], favicon)


if __name__ == "__main__":
    main()
