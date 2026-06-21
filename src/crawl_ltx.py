"""Crawl LTX blog and newsroom (Webflow SPA)."""

import hashlib
import logging
from datetime import datetime, timezone

from bs4 import BeautifulSoup
from DrissionPage import ChromiumPage

from utils import (
    FEEDS_DIR, setup_logging, ensure_output_dir,
    load_feeds_config, compact, write_atom_feed,
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
        href_rel = href[len(BASE_URL):] if href.startswith(BASE_URL) else href

        cat_el = item.select_one(".blog-category")
        category = cat_el.get_text(strip=True) if cat_el else ""
        excerpt_el = item.select_one(".text-truncate-2")
        excerpt = excerpt_el.get_text(strip=True) if excerpt_el else ""
        author = ""
        al = item.select_one("a.post-author-wrap-2 .post-author-new")
        if al: author = al.get_text(strip=True)
        date_str = ""
        aw = item.select_one(".author-date-wrap")
        if aw:
            de = aw.select(".post-author-new")
            if de: date_str = de[-1].get_text(strip=True)
        pub = parse_date(date_str) or datetime.now(timezone.utc).isoformat()
        slug = href_rel.strip("/").split("/")[-1]
        url = href if href.startswith("http") else f"{BASE_URL}{href}"
        entry_id = hashlib.md5(f"ltx_blog_{slug}".encode()).hexdigest()

        entry = compact({
            "id": entry_id, "source": "ltx", "type": "blog",
            "title": title, "url": url, "summary": excerpt,
            "published_date": pub, "categories": [category] if category else [],
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


def run(page: ChromiumPage):
    config = load_feeds_config(ORG_KEY)
    for page_key, p in config["pages"].items():
        logging.info("Navigating to %s", p["url"])
        page.get(p["url"])
        page.wait.doc_loaded()
        page.wait(3)
        soup = BeautifulSoup(page.html, "html.parser")
        entries = extract_blog(soup) if page_key == "blog" else extract_newsroom(soup)
        if not entries:
            logging.warning("No entries for %s", page_key)
            continue
        entries.sort(key=lambda x: x.get("published_date", ""), reverse=True)
        write_atom_feed(FEEDS_DIR / p["output_file"], entries,
                        feed_title=p["label"], feed_link=p["url"],
                        feed_icon=config.get("favicon"))

if __name__ == "__main__":
    from DrissionPage import ChromiumOptions
    co = ChromiumOptions()
    co.set_browser_path("/usr/bin/chromium")
    co.headless(on_off=True); co.new_env(on_off=True)
    co.set_argument("--no-sandbox"); co.set_argument("--disable-gpu")
    pg = ChromiumPage(addr_or_opts=co)
    try: run(pg)
    finally: pg.quit()
