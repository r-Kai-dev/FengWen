"""Scrape Anthropic news, research, and engineering blog pages.

Fetches HTML pages directly and writes Atom XML feeds — no intermediate caching.
"""

import hashlib
import json
import logging
import re
from datetime import datetime, timedelta, timezone

from bs4 import BeautifulSoup

from utils import (
    FEEDS_DIR,
    setup_logging,
    ensure_output_dir,
    load_feeds_config,
    fetch_page,
    compact,
    write_atom_feed,
)

setup_logging()
ensure_output_dir()

ORG_KEY = "anthropic"
ORGANIZATION = "Anthropic"


# ═══════════════════════════════════════════════════════════════════
#  Extraction
# ═══════════════════════════════════════════════════════════════════

def _create_post_item(
    post, title_element, date_element, base_url, page_type, categories=None
):
    """Create a post item from extracted elements."""
    title = title_element.get_text(strip=True) if title_element else ""
    if not title:
        return None

    href = str(post["href"])
    slug = href.split("/")[-1] if "/" in href else href
    url = str(base_url).rstrip("/") + "/" + slug

    published_date = None
    if date_element:
        date_str = date_element.get_text(strip=True)
        try:
            published_date = (
                datetime.strptime(date_str, "%b %d, %Y")
                .replace(tzinfo=timezone.utc)
                .isoformat()
            )
        except ValueError:
            logging.warning(
                "Could not parse date '%s' for article '%s...'",
                date_str, title[:50],
            )

    if not published_date:
        published_date = datetime.now(timezone.utc).isoformat()

    id_components = [ORG_KEY, title, url]
    item_id = hashlib.md5("_".join(filter(None, id_components)).encode()).hexdigest()

    return compact(
        {
            "id": item_id,
            "source": ORG_KEY,
            "type": page_type,
            "title": title,
            "url": url,
            "published_date": published_date,
            "organization": ORGANIZATION,
            "categories": categories,
        }
    )


def _extract_research(soup, base_url):
    """Extract research publications from PublicationList and FeaturedGrid."""
    post_items = []

    # PublicationList items
    for post in soup.select(
        'a[class*="PublicationList-module-scss-module"][class*="listItem"]'
    ):
        title_el = post.select_one(
            '[class*="PublicationList-module-scss-module"][class*="title"]'
        )
        date_el = post.select_one(
            '[class*="PublicationList-module-scss-module"][class*="date"]'
        )
        cat_el = post.select_one(
            '[class*="PublicationList-module-scss-module"][class*="subject"]'
        )
        categories = [cat_el.get_text(strip=True)] if cat_el else []
        if title_el:
            item = _create_post_item(post, title_el, date_el, base_url, "research", categories)
            if item:
                post_items.append(item)

    # FeaturedGrid items
    for post in soup.select(
        'a[class*="FeaturedGrid-module-scss-module"][class*="sideLink"]'
    ):
        title_el = post.select_one(
            '[class*="FeaturedGrid-module-scss-module"][class*="title"]'
        )
        date_el = post.select_one(
            '[class*="FeaturedGrid-module-scss-module"][class*="date"]'
        )
        cat_el = post.select_one("span.caption.bold")
        categories = [cat_el.get_text(strip=True)] if cat_el else []
        if title_el:
            item = _create_post_item(post, title_el, date_el, base_url, "research", categories)
            if item:
                post_items.append(item)

    return post_items


def _extract_news(soup, base_url):
    """Extract news articles from PublicationList and FeaturedGrid."""
    post_items = []

    # PublicationList items
    for post in soup.select(
        'a[class*="PublicationList-module-scss-module"][class*="listItem"]'
    ):
        title_el = post.select_one(
            '[class*="PublicationList-module-scss-module"][class*="title"]'
        )
        date_el = post.select_one(
            '[class*="PublicationList-module-scss-module"][class*="date"]'
        )
        cat_el = post.select_one(
            '[class*="PublicationList-module-scss-module"][class*="subject"]'
        )
        categories = [cat_el.get_text(strip=True)] if cat_el else []
        if title_el:
            item = _create_post_item(post, title_el, date_el, base_url, "news", categories)
            if item:
                post_items.append(item)

    # FeaturedGrid items
    for post in soup.select(
        'a[class*="FeaturedGrid-module-scss-module"][class*="sideLink"]'
    ):
        title_el = post.select_one(
            '[class*="FeaturedGrid-module-scss-module"][class*="title"]'
        )
        date_el = post.select_one(
            '[class*="FeaturedGrid-module-scss-module"][class*="date"]'
        )
        cat_el = post.select_one("span.caption.bold")
        categories = [cat_el.get_text(strip=True)] if cat_el else []
        if title_el:
            item = _create_post_item(post, title_el, date_el, base_url, "news", categories)
            if item:
                post_items.append(item)

    return post_items


def _parse_rsc_article_dates(html):
    """Extract article publish dates from Next.js RSC payload.

    The engineering page embeds a Sanity CMS articleList inside a
    self.__next_f.push() call.  We extract each engineeringArticle's
    slug.current → publishedOn mapping for date fallback.

    Returns dict mapping slug → "YYYY-MM-DD" date string.
    """
    dates = {}
    push_pattern = r'self\.__next_f\.push\(\[1,"(.*?)"\]\)'
    for match in re.finditer(push_pattern, html, re.DOTALL):
        chunk = match.group(1)
        try:
            decoded = chunk.encode("utf-8").decode("unicode_escape", errors="replace")
        except Exception:
            decoded = chunk

        if "articleList" not in decoded or "engineeringArticle" not in decoded:
            continue

        # Brace-depth match around each engineeringArticle marker
        for m in re.finditer(r'"_type":"engineeringArticle"', decoded):
            marker = m.start()
            # Walk backwards to opening brace
            depth = 0
            obj_start = marker
            for j in range(marker, -1, -1):
                if decoded[j] == "}":
                    depth += 1
                elif decoded[j] == "{":
                    if depth == 0:
                        obj_start = j
                        break
                    depth -= 1
            # Walk forwards to closing brace
            depth = 0
            obj_end = marker
            for j in range(obj_start, len(decoded)):
                if decoded[j] == "{":
                    depth += 1
                elif decoded[j] == "}":
                    depth -= 1
                    if depth == 0:
                        obj_end = j + 1
                        break

            try:
                obj = json.loads(decoded[obj_start:obj_end])
                slug = obj.get("slug", {}).get("current", "")
                pub = obj.get("publishedOn", "")
                if slug and pub:
                    dates[slug] = pub
            except (json.JSONDecodeError, KeyError):
                pass

        break  # only the first matching chunk matters

    return dates


def _extract_engineering(soup, base_url, html):
    """Extract engineering blog articles from ArticleList.

    Falls back to dates from the embedded RSC payload when an article
    card (typically the featured / hero card) omits a visible date.
    """
    post_items = []
    rsc_dates = _parse_rsc_article_dates(html)

    article_items = soup.find_all(
        "article", class_=lambda x: x and "ArticleList-module" in x
    )
    for post in article_items:
        card_link = post.find("a", class_=lambda x: x and "cardLink" in x)
        if not card_link:
            continue

        title_el = post.select_one("h3.headline-4")
        if not title_el:
            title_el = post.select_one("h2.headline-1")

        date_el = post.find("div", class_=lambda x: x and "__date" in str(x))

        if title_el:
            item = _create_post_item(card_link, title_el, date_el, base_url, "engineering")
            if item:
                # If no date was found in the HTML card, try the RSC payload
                if not date_el:
                    href = card_link.get("href", "")
                    slug = href.rstrip("/").split("/")[-1] if href else ""
                    if slug in rsc_dates:
                        try:
                            item["published_date"] = (
                                datetime.strptime(rsc_dates[slug], "%Y-%m-%d")
                                .replace(tzinfo=timezone.utc)
                                .isoformat()
                            )
                            logging.info(
                                "Filled date from RSC for '%s': %s",
                                slug, rsc_dates[slug],
                            )
                        except ValueError:
                            pass
                post_items.append(item)

    return post_items


def extract_entries(soup, page_key, base_url, html=""):
    """Route to the correct extraction function based on page key."""
    if page_key == "research":
        return _extract_research(soup, base_url)
    elif page_key == "engineering":
        return _extract_engineering(soup, base_url, html)
    elif page_key == "news":
        return _extract_news(soup, base_url)
    else:
        logging.error("Unknown page key: %s", page_key)
        return []


# ═══════════════════════════════════════════════════════════════════
#  Dedup, date fallback, sort, write
# ═══════════════════════════════════════════════════════════════════

def _is_valid_date(item):
    """Check if an item's date was parsed from the page (not a current-time fallback)."""
    date_str = item.get("published_date", "")
    if not date_str:
        return False
    try:
        dt = datetime.fromisoformat(date_str.replace("Z", "+00:00"))
        now = datetime.now(timezone.utc)
        return (now - dt).total_seconds() >= 60
    except (ValueError, TypeError):
        return False


def _get_date(item):
    date_str = item.get("published_date", "")
    if date_str:
        try:
            return datetime.fromisoformat(date_str.replace("Z", "+00:00"))
        except (ValueError, TypeError):
            pass
    return datetime.min.replace(tzinfo=timezone.utc)


def process_and_write(post_items, page, favicon):
    """Deduplicate, apply date fallbacks, sort, and write Atom feed."""
    # Deduplicate by JSON serialization
    dedup = [json.loads(s) for s in {json.dumps(d) for d in post_items}]
    dedup.sort(key=_get_date, reverse=True)

    # Compute fallback date: latest valid date + 1 day
    valid_dates = [_get_date(item) for item in dedup if _is_valid_date(item)]
    if valid_dates:
        latest = max(valid_dates)
        fallback = (latest + timedelta(days=1)).replace(tzinfo=timezone.utc)
        logging.info(
            "Found %d posts with valid dates, latest: %s, fallback: %s",
            len(valid_dates), latest.date(), fallback.date(),
        )
    else:
        fallback = datetime.now(timezone.utc)
        logging.warning("No valid dates found, using current date as fallback")

    # Apply fallback to items without valid dates
    for item in dedup:
        if not _is_valid_date(item):
            item["published_date"] = fallback.isoformat()
            logging.info(
                "Applied fallback date to: %s...", item.get("title", "Unknown")[:50]
            )

    dedup.sort(key=_get_date, reverse=True)

    output_path = FEEDS_DIR / page["output_file"]
    write_atom_feed(
        output_path,
        dedup,
        feed_title=page["label"],
        feed_link=page["url"],
        feed_icon=favicon,
    )


# ═══════════════════════════════════════════════════════════════════
#  Main
# ═══════════════════════════════════════════════════════════════════

def main():
    config = load_feeds_config(ORG_KEY)
    favicon = config.get("favicon") or (
        config.get("base_url", "").rstrip("/") + "/favicon.ico"
    )

    for page_key, page in config["pages"].items():
        logging.info("Fetching %s: %s", page["label"], page["url"])
        try:
            html = fetch_page(page["url"])
        except Exception as exc:
            logging.error("Failed to fetch %s: %s", page["url"], exc)
            continue

        soup = BeautifulSoup(html, "html.parser")
        entries = extract_entries(soup, page_key, page["url"], html)

        if not entries:
            logging.warning("No entries found for %s", page_key)
            continue

        process_and_write(entries, page, favicon)


if __name__ == "__main__":
    main()
