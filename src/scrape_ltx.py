"""Scrape LTX blog and newsroom from SSR HTML (Webflow site)."""

import hashlib
import logging
from datetime import datetime, timezone

from bs4 import BeautifulSoup

from utils import (
    FEEDS_DIR, setup_logging, ensure_output_dir,
    load_feeds_config, fetch_page, compact, write_atom_feed,
)

setup_logging()
ensure_output_dir()
ORG_KEY = "ltx"
BASE_URL = "https://ltx.io"


def parse_date(date_str):
    if not date_str:
        return None
    for fmt in ("%B %d, %Y", "%b %d, %Y", "%b %d %Y"):
        try:
            return datetime.strptime(date_str.strip(), fmt).replace(tzinfo=timezone.utc).isoformat()
        except ValueError:
            continue
    return None


def _excerpt(item):
    """Extract excerpt from a blog item, trying both SSR class variants."""
    for cls in ("text-truncate-2", "text-truncate-3"):
        el = item.select_one(f".{cls}")
        if el:
            text = el.get_text(strip=True)
            if text:
                return text
    return ""


def _category(item):
    """Extract category — the SSR uses different wrappers for featured vs grid items."""
    el = item.select_one(".blog-category")
    if el:
        return el.get_text(strip=True)
    # Some items store category as a data attribute on the wrapper
    wrapper = item.find(attrs={"r-blog-item-category": True})
    if wrapper:
        return wrapper.get("r-blog-item-category", "").strip()
    return ""


def extract_blog(soup):
    posts = []
    seen = {}
    for item in soup.select(".w-dyn-item"):
        title_el = item.select_one("h3.blog-title")
        if not title_el:
            continue
        title = title_el.get_text(strip=True)
        if not title or len(title) < 10:
            continue
        link_el = item.select_one("a.blog-title-wrap") or title_el.find_parent("a")
        href = link_el.get("href", "") if link_el else ""
        if not href:
            continue

        # Normalise href for dedup
        href_rel = href[len(BASE_URL):] if href.startswith(BASE_URL) else href
        slug = href_rel.strip("/").split("/")[-1]
        url = href if href.startswith("http") else f"{BASE_URL}{href}"

        category = _category(item)
        excerpt = _excerpt(item)

        author = ""
        al = item.select_one("a.post-author-wrap-2 .post-author-new")
        if al:
            author = al.get_text(strip=True)

        date_str = ""
        aw = item.select_one(".author-date-wrap")
        if aw:
            de = aw.select(".post-author-new")
            if de:
                date_str = de[-1].get_text(strip=True)
        pub = parse_date(date_str) or datetime.now(timezone.utc).isoformat()

        entry_id = hashlib.md5(f"ltx_blog_{slug}".encode()).hexdigest()
        entry = compact({
            "id": entry_id, "source": "ltx", "type": "blog",
            "title": title, "url": url, "summary": excerpt,
            "published_date": pub,
            "categories": [category] if category else [],
            "feed_author": author, "organization": "LTX",
        })

        if href_rel in seen:
            prev = posts[seen[href_rel]]
            if pub < prev.get("published_date", ""):
                posts[seen[href_rel]] = entry
            continue
        seen[href_rel] = len(posts)
        posts.append(entry)
    return posts


def extract_newsroom(soup):
    posts = []
    seen = set()
    for item in soup.select(".w-dyn-item"):
        main_link = item.select_one("a.news-item-wrap") or item.select_one('a[href*="/newsroom/"]')
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
        if not title or len(title) < 5:
            continue

        date_str = ""
        dw = item.select_one(".event1_date-wrapper")
        if dw:
            parts = [el.get_text(strip=True) for el in dw.find_all(["div", "span"]) if el.get_text(strip=True)]
            date_str = " ".join(parts)
        excerpt_el = item.select_one("p.text-size-small")
        excerpt = excerpt_el.get_text(strip=True) if excerpt_el else ""
        pub = parse_date(date_str) or datetime.now(timezone.utc).isoformat()

        slug = href.strip("/").split("/")[-1]
        url = href if href.startswith("http") else f"{BASE_URL}{href}"
        entry_id = hashlib.md5(f"ltx_newsroom_{slug}".encode()).hexdigest()
        posts.append(compact({
            "id": entry_id, "source": "ltx", "type": "news",
            "title": title, "url": url, "summary": excerpt,
            "published_date": pub, "organization": "LTX",
        }))
    return posts


def main():
    config = load_feeds_config(ORG_KEY)
    for page_key, page in config["pages"].items():
        logging.info("Fetching %s: %s", page["label"], page["url"])
        html = fetch_page(page["url"])
        soup = BeautifulSoup(html, "html.parser")
        entries = extract_blog(soup) if page_key == "blog" else extract_newsroom(soup)
        if not entries:
            logging.warning("No entries for %s", page_key)
            continue
        entries.sort(key=lambda x: x.get("published_date", ""), reverse=True)
        write_atom_feed(FEEDS_DIR / page["output_file"], entries,
                        feed_title=page["label"], feed_link=page["url"],
                        feed_icon=config.get("favicon"))


if __name__ == "__main__":
    main()
