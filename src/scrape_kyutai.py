"""Scrape Kyutai blog (__NEXT_DATA__) and papers (JS chunk)."""

import hashlib
import json
import logging
import re
from datetime import datetime, timezone

from utils import (
    FEEDS_DIR, setup_logging, ensure_output_dir,
    load_feeds_config, fetch_page, compact, write_atom_feed,
)

setup_logging()
ensure_output_dir()
ORG_KEY = "kyutai"
BASE_URL = "https://kyutai.org"


def extract_blog():
    html = fetch_page(f"{BASE_URL}/blog")
    m = re.search(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', html, re.DOTALL)
    if not m:
        return []
    data = json.loads(m.group(1))
    posts = data.get("props", {}).get("pageProps", {}).get("allPostsData", [])
    entries = []
    for p in posts:
        slug = p.get("slug", "")
        meta = p.get("metadata", {})
        title = meta.get("title", "")
        date_str = meta.get("date", "")
        description = meta.get("description", "")
        if not title or not slug:
            continue
        try:
            pub = datetime.strptime(date_str, "%Y-%m-%d").replace(tzinfo=timezone.utc).isoformat()
        except (ValueError, TypeError):
            pub = datetime.now(timezone.utc).isoformat()
        url = f"{BASE_URL}/blog/{slug}"
        item_id = hashlib.md5(f"kyutai_blog_{slug}".encode()).hexdigest()
        entries.append(compact({
            "id": item_id, "source": "kyutai", "type": "blog",
            "title": title, "url": url, "summary": description,
            "published_date": pub, "organization": "Kyutai",
        }))
    return entries


def extract_papers():
    html = fetch_page(f"{BASE_URL}/papers")
    m = re.search(r"/_next/static/chunks/pages/papers-([a-f0-9]+)\.js", html)
    if not m:
        return []
    chunk_url = f"{BASE_URL}/_next/static/chunks/pages/papers-{m.group(1)}.js"
    js = fetch_page(chunk_url)
    start = js.find('[{"id"')
    if start < 0:
        return []
    depth, end = 0, start
    for i in range(start, len(js)):
        if js[i] == "[": depth += 1
        elif js[i] == "]":
            depth -= 1
            if depth == 0: end = i + 1; break
    fixed = re.sub(r"\\x([0-9a-fA-F]{2})", lambda m: chr(int(m.group(1), 16)), js[start:end].encode().decode("unicode_escape"))
    papers = json.loads(fixed)

    entries = []
    for p in papers:
        arxiv_id = p.get("id", "")
        title = p.get("title", "")
        authors = p.get("authors", [])
        abstract = p.get("abstract", "")
        date_str = p.get("published", "")
        if not title or not arxiv_id:
            continue
        try:
            pub = datetime.fromisoformat(date_str.replace("Z", "+00:00")).isoformat()
        except (ValueError, TypeError):
            pub = datetime.now(timezone.utc).isoformat()
        url = f"https://arxiv.org/abs/{arxiv_id}"
        item_id = hashlib.md5(f"kyutai_papers_{arxiv_id}".encode()).hexdigest()
        author_str = ", ".join(authors[:3]) + (" et al." if len(authors) > 3 else "")
        entries.append(compact({
            "id": item_id, "source": "kyutai", "type": "paper",
            "title": title, "url": url, "summary": abstract,
            "published_date": pub, "feed_author": author_str,
            "organization": "Kyutai",
        }))
    return entries


def main():
    config = load_feeds_config(ORG_KEY)
    favicon = config.get("favicon")
    for page_key, page in config["pages"].items():
        if page_key == "blog":
            entries = extract_blog()
        elif page_key == "papers":
            entries = extract_papers()
        else:
            continue
        if not entries:
            logging.warning("No entries for %s", page_key)
            continue
        entries.sort(key=lambda x: x.get("published_date", ""), reverse=True)
        write_atom_feed(FEEDS_DIR / page["output_file"], entries,
                        feed_title=page["label"], feed_link=page["url"],
                        feed_icon=favicon)

if __name__ == "__main__":
    main()
