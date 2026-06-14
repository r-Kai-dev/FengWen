"""Fetch Kyutai Lab blog posts and papers.

Blog: __NEXT_DATA__ JSON at /blog.
Papers: embedded JSON array in the page JS chunk at /papers.

Output to feeds/:
  - kyutai_blog.xml
  - kyutai_papers.xml
"""

import hashlib
import json
import logging
import re
import urllib.request
from datetime import datetime, timezone

from common import (
    PARSED_DIR,
    ensure_output_dir,
    load_api_config,
    setup_logging,
)
from feed_util import compact, write_atom_feed

setup_logging()
ensure_output_dir()

ORG_KEY = "kyutai"
BASE_URL = "https://kyutai.org"


def fetch_html(url: str) -> str:
    """Fetch an HTML page."""
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": (
                "Mozilla/5.0 (X11; Linux x86_64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            ),
        },
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        return resp.read().decode("utf-8")


def extract_blog_posts() -> list[dict]:
    """Fetch blog posts from __NEXT_DATA__ on /blog."""
    html = fetch_html(f"{BASE_URL}/blog")

    nd_match = re.search(
        r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', html, re.DOTALL
    )
    if not nd_match:
        logging.error("Could not find __NEXT_DATA__ on blog page")
        return []

    try:
        data = json.loads(nd_match.group(1))
    except json.JSONDecodeError as exc:
        logging.error(f"Failed to parse __NEXT_DATA__: {exc}")
        return []

    posts = data.get("props", {}).get("pageProps", {}).get("allPostsData", [])
    entries = []

    for p in posts:
        slug = p.get("slug", "")
        meta = p.get("metadata", {})
        title = meta.get("title", "")
        date_str = meta.get("date", "")
        description = meta.get("description", "")
        author = meta.get("author", "")

        if not title or not slug:
            continue

        if date_str:
            try:
                dt = datetime.strptime(date_str, "%Y-%m-%d").replace(tzinfo=timezone.utc)
                published_date = dt.isoformat()
            except (ValueError, TypeError):
                published_date = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
        else:
            published_date = datetime.now(timezone.utc).replace(microsecond=0).isoformat()

        url = f"{BASE_URL}/blog/{slug}"
        entry_id = hashlib.md5(f"kyutai_blog_{slug}".encode()).hexdigest()

        entries.append(
            compact(
                {
                    "id": entry_id,
                    "source": "kyutai",
                    "type": "blog",
                    "title": title,
                    "url": url,
                    "summary": description,
                    "published_date": published_date,
                    "feed_author": author,
                    "organization": "Kyutai",
                }
            )
        )

    return entries


def extract_papers() -> list[dict]:
    """Fetch papers from the JS chunk on /papers."""
    html = fetch_html(f"{BASE_URL}/papers")

    # Find the papers page chunk: pages/papers-<hash>.js
    chunk_match = re.search(
        r"/_next/static/chunks/pages/papers-([a-f0-9]+)\.js", html
    )
    if not chunk_match:
        logging.error("Could not find papers JS chunk URL")
        return []

    chunk_hash = chunk_match.group(1)
    chunk_url = f"{BASE_URL}/_next/static/chunks/pages/papers-{chunk_hash}.js"
    js = fetch_html(chunk_url)

    # Find the papers JSON array
    start = js.find('[{"id"')
    if start < 0:
        logging.error("Could not find papers data in JS chunk")
        return []

    depth = 0
    end = start
    for i in range(start, len(js)):
        if js[i] == "[":
            depth += 1
        elif js[i] == "]":
            depth -= 1
            if depth == 0:
                end = i + 1
                break

    papers_json = js[start:end]

    # Fix \xNN escape sequences (JS-style) to proper Unicode
    fixed = re.sub(
        r"\\x([0-9a-fA-F]{2})",
        lambda m: chr(int(m.group(1), 16)),
        papers_json.encode().decode("unicode_escape"),
    )

    try:
        papers = json.loads(fixed)
    except json.JSONDecodeError as exc:
        logging.error(f"Failed to parse papers JSON: {exc}")
        return []

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
            dt = datetime.fromisoformat(date_str.replace("Z", "+00:00"))
            published_date = dt.isoformat()
        except (ValueError, TypeError):
            published_date = datetime.now(timezone.utc).replace(microsecond=0).isoformat()

        url = f"https://arxiv.org/abs/{arxiv_id}"
        entry_id = hashlib.md5(f"kyutai_papers_{arxiv_id}".encode()).hexdigest()
        author_str = ", ".join(authors[:3])
        if len(authors) > 3:
            author_str += " et al."

        entries.append(
            compact(
                {
                    "id": entry_id,
                    "source": "kyutai",
                    "type": "paper",
                    "title": title,
                    "url": url,
                    "summary": abstract,
                    "published_date": published_date,
                    "feed_author": author_str,
                    "organization": "Kyutai",
                }
            )
        )

    return entries


def main():
    config = load_api_config(ORG_KEY)
    pages = config["pages"]
    favicon = config.get("favicon") or f"{BASE_URL}/favicon.ico"

    # Blog
    if "blog" in pages:
        entries = extract_blog_posts()
        if entries:
            write_atom_feed(
                PARSED_DIR / pages["blog"]["output_file"],
                entries,
                feed_title="Kyutai Lab Blog",
                feed_link=f"{BASE_URL}/blog",
                feed_icon=favicon,
            )
            logging.info(f"Saved {len(entries)} entries to {pages['blog']['output_file']}")

    # Papers
    if "papers" in pages:
        entries = extract_papers()
        if entries:
            write_atom_feed(
                PARSED_DIR / pages["papers"]["output_file"],
                entries,
                feed_title="Kyutai Lab Papers",
                feed_link=f"{BASE_URL}/papers",
                feed_icon=favicon,
            )
            logging.info(f"Saved {len(entries)} entries to {pages['papers']['output_file']}")


if __name__ == "__main__":
    main()
