"""Fetch Lovable blog posts from the Next.js page (SSR HTML)."""

import hashlib
import json
import logging
import re

from utils import (
    FEEDS_DIR, setup_logging, ensure_output_dir,
    load_feeds_config, fetch_page, compact, write_atom_feed,
)

setup_logging()
ensure_output_dir()
ORG_KEY = "lovable"


def parse_blog_posts(html: str) -> list[dict]:
    """Extract blog posts from the SSR HTML containing self.__next_f.push chunks."""
    posts = []
    seen_hrefs = set()

    # Extract data from the streaming chunks
    # Combine all push chunks into one string
    all_data = ""
    for chunk in re.findall(r'self\.__next_f\.push\(\[1,"(.*?)"\]\)', html, re.DOTALL):
        all_data += chunk

    # Extract fields with consistent patterns from the component tree
    categories = re.findall(r'text-muted-foreground text-sm\\",\\"children\\":\\"([^\\]+)', all_data)
    titles = re.findall(r'text-2xl leading-tight font-medium\\",\\"children\\":\\"([^\\]+)', all_data)
    hrefs = re.findall(r'\\"href\\":\\"(/blog/[^\\"]+)\\', all_data)
    dates = re.findall(r'\\"dateTime\\":\\"\$D([^\\]+)\\', all_data)
    descriptions = re.findall(r'text-muted-foreground line-clamp-2\\",\\"children\\":\\"([^\\]+)', all_data)

    # Authors are harder to extract cleanly; use the "Organization" field instead
    # They appear as: "span",null,{"children":"AuthorName"}],"$","span",null,{"children":"•"}
    # But the pattern varies. We'll skip authors for simplicity.

    # Zip together, matching by position in the page
    # The blog listing and sidebar both use the same card component
    max_len = min(len(titles), len(hrefs), len(dates))
    cat_idx = 0
    for i in range(max_len):
        href = hrefs[i]
        if href in seen_hrefs:
            continue
        seen_hrefs.add(href)

        title = titles[i] if i < len(titles) else ""
        pub_date = dates[i] if i < len(dates) else ""
        category = categories[cat_idx] if cat_idx < len(categories) else ""
        cat_idx += 1

        # Try to match a description (optional, not all cards have one)
        # Descriptions appear after titles in the card structure
        summary = ""
        for d in descriptions:
            if d not in title and len(d) > 10:
                summary = d
                break

        if not title or not href:
            continue

        entry_id = hashlib.md5(f"{ORG_KEY}_{href}".encode()).hexdigest()

        posts.append(compact({
            "title": title.strip(),
            "url": f"https://lovable.dev{href}",
            "id": entry_id,
            "published_date": pub_date,
            "summary": summary or None,
            "categories": [category] if category else [],
            "organization": "Lovable",
        }))

    return posts


def main():
    config = load_feeds_config(ORG_KEY)
    favicon = config.get("favicon")

    for page_key, page in config["pages"].items():
        logging.info("Fetching %s: %s", page["label"], page["url"])
        html = fetch_page(page["url"])
        raw_posts = parse_blog_posts(html)

        if not raw_posts:
            logging.warning("No posts found for %s", page_key)
            continue

        # Deduplicate by JSON round-trip
        entries = [json.loads(s) for s in {json.dumps(p, sort_keys=True) for p in raw_posts}]
        entries.sort(key=lambda x: x.get("published_date", ""), reverse=True)

        logging.info("Parsed %d entries for %s", len(entries), page_key)

        if entries:
            write_atom_feed(FEEDS_DIR / page["output_file"], entries,
                            feed_title=page["label"],
                            feed_link=page.get("feed_link", page["url"]),
                            feed_icon=favicon)


if __name__ == "__main__":
    main()
