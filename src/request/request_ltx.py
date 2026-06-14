"""Fetch LTX blog and newsroom feeds using DrissionPage (headless Chromium).

Blog: renders the listing page, then visits each article page in the same
browser session to extract the original publication date (the listing page
only shows last-updated dates).

Newsroom: parsed directly from the listing page (dates are correct there).

Output to feeds/:
  - ltx_blog.xml
  - ltx_newsroom.xml
"""

import hashlib
import logging
import re
from datetime import datetime, timezone

from bs4 import BeautifulSoup
from DrissionPage import ChromiumOptions, ChromiumPage

from common import (
    PARSED_DIR,
    ensure_output_dir,
    load_api_config,
    setup_logging,
)
from feed_util import compact, write_atom_feed

setup_logging()
ensure_output_dir()

ORG_KEY = "ltx"
BASE_URL = "https://ltx.io"


def _start_browser():
    co = ChromiumOptions()
    co.set_browser_path("/usr/bin/chromium")
    co.set_argument("--headless=new")
    co.set_argument("--no-sandbox")
    co.set_argument("--disable-gpu")
    co.new_env(on_off=True)
    co.headless(on_off=True)
    return ChromiumPage(addr_or_opts=co)


def parse_date(date_str: str) -> str | None:
    if not date_str:
        return None
    date_str = date_str.strip()
    for fmt in ("%B %d, %Y", "%b %d, %Y"):
        try:
            return (
                datetime.strptime(date_str, fmt)
                .replace(tzinfo=timezone.utc)
                .isoformat()
            )
        except ValueError:
            continue
    return None


def fetch_blog(page: ChromiumPage) -> list[dict]:
    """Load blog listing, extract article links, then visit each article
    page for its original publication date."""
    blog_url = f"{BASE_URL}/blog"
    logging.info(f"Loading listing: {blog_url}")
    page.get(blog_url)
    page.wait.doc_loaded()
    page.wait(5)

    soup = BeautifulSoup(page.html, "html.parser")

    # Collect article metadata from the listing
    articles = []
    seen = set()

    for item in soup.select(".w-dyn-item"):
        title_el = item.select_one("h3.blog-title")
        if not title_el:
            continue
        title = title_el.get_text(strip=True)
        if not title or len(title) < 10:
            continue

        link_el = item.select_one("a.blog-title-wrap")
        href = link_el.get("href", "") if link_el else ""
        if not href or href in seen:
            continue
        seen.add(href)

        cat_el = item.select_one(".blog-category")
        category = cat_el.get_text(strip=True) if cat_el else ""

        excerpt_el = item.select_one(".text-truncate-2")
        excerpt = excerpt_el.get_text(strip=True) if excerpt_el else ""

        author = ""
        author_link = item.select_one("a.post-author-wrap-2 .post-author-new")
        if author_link:
            author = author_link.get_text(strip=True)

        articles.append(
            {
                "title": title,
                "href": href,
                "category": category,
                "excerpt": excerpt,
                "author": author,
            }
        )

    logging.info(f"Found {len(articles)} articles — fetching dates...")

    # Visit each article page in the same browser session
    posts = []
    for i, art in enumerate(articles):
        article_url = f"{BASE_URL}{art['href']}"
        pub_date = None

        try:
            page.get(article_url)
            page.wait.doc_loaded()
            page.wait(1)  # Short wait — article pages are static

            art_soup = BeautifulSoup(page.html, "html.parser")
            for sel in [".date-and-time", ".post-date-wrap .post-author-new"]:
                el = art_soup.select_one(sel)
                if el:
                    text = el.get_text(strip=True)
                    m = re.search(r"([A-Z][a-z]+ \d{1,2}, \d{4})", text)
                    if m:
                        pub_date = parse_date(m.group(1))
                        break
        except Exception as e:
            logging.warning(f"Failed {article_url}: {e}")

        if not pub_date:
            logging.warning(f"No date for {art['title'][:50]}, skipping")
            continue

        slug = art["href"].strip("/").split("/")[-1]
        entry_id = hashlib.md5(f"ltx_blog_{slug}".encode()).hexdigest()

        posts.append(
            compact(
                {
                    "id": entry_id,
                    "source": "ltx",
                    "type": "blog",
                    "title": art["title"],
                    "url": article_url,
                    "summary": art["excerpt"],
                    "published_date": pub_date,
                    "categories": [art["category"]] if art["category"] else [],
                    "feed_author": art["author"],
                    "organization": "LTX",
                }
            )
        )

        if (i + 1) % 10 == 0:
            logging.info(f"  {i + 1}/{len(articles)} done")

    return posts


def fetch_newsroom(page: ChromiumPage) -> list[dict]:
    """Parse newsroom directly from the listing page."""
    news_url = f"{BASE_URL}/newsroom"
    logging.info(f"Loading newsroom: {news_url}")
    page.get(news_url)
    page.wait.doc_loaded()
    page.wait(3)

    soup = BeautifulSoup(page.html, "html.parser")
    posts = []
    seen = set()

    for item in soup.select(".w-dyn-item"):
        main_link = item.select_one("a.news-item-wrap")
        if not main_link:
            main_link = item.select_one('a[href*="/newsroom/"]')
        if not main_link:
            continue
        href = main_link.get("href", "")
        if not href or href in seen:
            continue
        seen.add(href)

        title_el = item.select_one("h3.news-title")
        if not title_el:
            continue
        title = title_el.get_text(strip=True)
        if not title:
            continue

        date_str = ""
        date_wrap = item.select_one(".event1_date-wrapper")
        if date_wrap:
            parts = [
                el.get_text(strip=True)
                for el in date_wrap.find_all(["div", "span"])
                if el.get_text(strip=True)
            ]
            date_str = " ".join(parts)

        excerpt_el = item.select_one("p.text-size-small")
        excerpt = excerpt_el.get_text(strip=True) if excerpt_el else ""

        pub_date = parse_date(date_str) or datetime.now(timezone.utc).isoformat()

        slug = href.strip("/").split("/")[-1]
        url = f"{BASE_URL}{href}"
        entry_id = hashlib.md5(f"ltx_newsroom_{slug}".encode()).hexdigest()

        posts.append(
            compact(
                {
                    "id": entry_id,
                    "source": "ltx",
                    "type": "news",
                    "title": title,
                    "url": url,
                    "summary": excerpt,
                    "published_date": pub_date,
                    "organization": "LTX",
                }
            )
        )

    return posts


def main() -> None:
    config = load_api_config(ORG_KEY)
    page = _start_browser()

    try:
        for page_config in config["pages"]:
            key = page_config["key"]
            if key == "blog":
                entries = fetch_blog(page)
                feed_title = "LTX Blog"
                feed_link = f"{BASE_URL}/blog"
            elif key == "newsroom":
                entries = fetch_newsroom(page)
                feed_title = "LTX News"
                feed_link = f"{BASE_URL}/newsroom"
            else:
                continue

            if not entries:
                logging.error(f"No entries for {key}")
                continue

            output_file = PARSED_DIR / page_config["output_file"]
            write_atom_feed(
                output_file,
                entries,
                feed_title=feed_title,
                feed_link=feed_link,
                feed_icon=config.get("favicon", f"{BASE_URL}/favicon.ico"),
            )
            logging.info(f"Saved {len(entries)} entries to {output_file}")
    finally:
        page.quit()


if __name__ == "__main__":
    main()
