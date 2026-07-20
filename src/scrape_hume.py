"""Scrape Hume AI blog from Next.js RSC payload."""

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
ORG_KEY = "hume"
BASE_URL = "https://www.hume.ai"


def _parse_date(date_str):
    if not date_str:
        return datetime.now(timezone.utc).isoformat()
    # ISO format
    try:
        return datetime.fromisoformat(date_str.replace("Z", "+00:00")).isoformat()
    except (ValueError, TypeError):
        pass
    # Human-readable formats
    for fmt in ("%b %d, %Y", "%B %d, %Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(date_str.strip(), fmt).replace(tzinfo=timezone.utc).isoformat()
        except ValueError:
            continue
    return datetime.now(timezone.utc).isoformat()


def _extract_posts_from_rsc(html):
    """Extract blog posts from Next.js RSC flight data.

    The Hume blog renders posts inline as React Server Components.
    We find all $Lf (Link) components pointing to /blog/ slugs by
    searching the decoded RSC payload directly with regex, then
    extract title + date from child text nodes.
    """
    chunks = re.findall(r'self\.__next_f\.push\(\[1,\s*"(.*?)"\s*\]\)', html, re.DOTALL)
    all_data = ""
    for chunk in chunks:
        all_data += chunk.encode("utf-8").decode("unicode_escape", errors="replace")

    posts = []
    seen_slugs = set()

    # Find all $Lf Link components with /blog/ href via regex.
    # Pattern: ["$","$Lf",...,{"href":"/blog/slug",...},...]
    for m in re.finditer(
        r'\["\$","\$Lf",(?:null|"[^"]*"|\d+),'
        r'\{"href":"(/blog/([^"]+))"',
        all_data
    ):
        slug = m.group(2)
        if slug in seen_slugs:
            continue
        seen_slugs.add(slug)

        # Find the full component by brace-matching from the opening [
        start = m.start()
        depth = 0
        end = start
        for i in range(start, min(len(all_data), start + 10000)):
            if all_data[i] == "[":
                depth += 1
            elif all_data[i] == "]":
                depth -= 1
                if depth == 0:
                    end = i + 1
                    break

        try:
            obj_val = json.loads(all_data[start:end])
        except json.JSONDecodeError:
            continue

        # Extract text from the component tree.  We collect ALL
        # strings recursively (including from referenced sub-components)
        # and then filter with heuristics to find the real title.
        def _all_strings(obj):
            strings = []
            if isinstance(obj, str):
                strings.append(obj)
            elif isinstance(obj, list):
                for item in obj:
                    strings.extend(_all_strings(item))
            elif isinstance(obj, dict):
                for v in obj.values():
                    strings.extend(_all_strings(v))
            return strings

        def _looks_like_title(s):
            """Heuristic: real titles look like English, not CSS classes."""
            if not s or len(s) < 10:
                return False
            if s.startswith("http") or s.startswith("/"):
                return False
            # Real titles start with uppercase letter (or quote/digit)
            if not (s[0].isupper() or s[0].isdigit() or s[0] in '"\u201c'):
                return False
            # CSS class strings: contain Tailwind patterns
            if "text-" in s and ("text-lg" in s or "text-xl" in s or "text-xs" in s
                                  or "text-sm" in s or "text-2xl" in s or "text-3xl" in s):
                return False
            # UUID-like
            if s.count("-") == 4 and len(s) < 50:
                return False
            return True

        texts = _all_strings(obj_val)
        title = ""
        date_str = ""
        for t in texts:
            if re.match(
                r"^(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)"
                r"\s+\d{1,2},\s+20\d{2}$", t
            ):
                date_str = t
            elif _looks_like_title(t) and len(t) > len(title):
                title = t
        if title and slug:
            posts.append({
                "slug": {"current": slug},
                "title": title,
                "publishedAt": date_str,
                "excerpt": "",
                "category": "",
            })
    return posts


def extract(html):
    posts = _extract_posts_from_rsc(html)
    entries = []
    for p in posts:
        slug_obj = p.get("slug", {})
        slug = slug_obj.get("current", "") if isinstance(slug_obj, dict) else str(slug_obj or "")
        if not slug:
            continue
        title = p.get("title", slug)
        category = p.get("category", "")
        pub = _parse_date(p.get("publishedAt", ""))
        excerpt = p.get("excerpt", "")
        url = f"{BASE_URL}/blog/{slug}"
        item_id = hashlib.md5(f"hume_{slug}".encode()).hexdigest()
        entries.append(compact({
            "id": item_id, "source": "hume", "type": "blog",
            "title": title, "url": url, "summary": excerpt,
            "published_date": pub,
            "categories": [category] if category else [],
            "organization": "Hume AI",
        }))
    return entries


def main():
    config = load_feeds_config(ORG_KEY)
    page = config["pages"]["blog"]
    logging.info("Fetching %s: %s", page["label"], page["url"])
    html = fetch_page(page["url"])
    entries = extract(html)
    if not entries:
        logging.warning("No entries found")
        return
    entries.sort(key=lambda x: x.get("published_date", ""), reverse=True)
    write_atom_feed(FEEDS_DIR / page["output_file"], entries,
                    feed_title=page["label"], feed_link=page["url"],
                    feed_icon=config.get("favicon"))

if __name__ == "__main__":
    main()
