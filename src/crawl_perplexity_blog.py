"""Crawl Perplexity Hub Blog from Framer handoverData (Playwright — GitHub Actions compatible)."""

import hashlib
import json
import logging
import re
from datetime import datetime, timezone

from bs4 import BeautifulSoup

from utils import (
    FEEDS_DIR, setup_logging, ensure_output_dir,
    load_feeds_config, compact, write_atom_feed,
)

setup_logging()
ensure_output_dir()
ORG_KEY = "perplexity_blog"
PAGE_URL = "https://www.perplexity.ai/hub/blog"
BLOG_BASE = "https://www.perplexity.ai/hub/blog"


def _is_date(v): return bool(re.match(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}", v))
def _is_slug(v): return bool(re.match(r"^[a-z0-9]+(-[a-z0-9]+)+$", v))


def _resolve(arr, idx):
    if idx >= len(arr):
        return None
    wrapper = arr[idx]
    if isinstance(wrapper, dict) and "value" in wrapper:
        vi = wrapper["value"]
        return arr[vi] if isinstance(vi, int) and vi < len(arr) else vi
    return wrapper


def extract(html):
    m = re.search(r'id="__framer__handoverData">(.*?)</script>', html, re.DOTALL)
    if not m:
        return []
    arr = json.loads(m.group(1))
    entries = []
    seen = set()
    for item in arr:
        if not isinstance(item, dict):
            continue
        int_fields = {k: v for k, v in item.items() if isinstance(v, int)}
        if len(int_fields) < 3:
            continue
        resolved = {}
        for fn, vi in int_fields.items():
            val = _resolve(arr, vi)
            if isinstance(val, str) and val.strip():
                resolved[fn] = val
        if len(resolved) < 2:
            continue

        date_val = slug_val = title_val = summary_val = ""
        for val in resolved.values():
            if not isinstance(val, str):
                continue
            val = val.strip()
            if _is_date(val): date_val = val
            elif _is_slug(val): slug_val = val
            elif len(val) > 80: summary_val = val
            elif len(val) < 10 and " " not in val: pass
            elif not title_val or len(val) > len(title_val): title_val = val

        if not slug_val or not title_val or slug_val in seen:
            continue
        seen.add(slug_val)

        url = f"{BLOG_BASE}/{slug_val}"
        item_id = hashlib.md5(f"perplexity_blog_{slug_val}".encode()).hexdigest()
        entries.append(compact({
            "id": item_id, "source": "perplexity", "type": "blog",
            "title": title_val, "url": url, "summary": summary_val,
            "published_date": date_val or None,
            "organization": "Perplexity AI",
        }))
    return entries


def run(page):
    config = load_feeds_config(ORG_KEY)
    p = config["pages"]["blog"]
    logging.info("Crawling %s: %s", p["label"], PAGE_URL)
    page.goto(PAGE_URL, wait_until="domcontentloaded")
    # Framer's handoverData appears briefly then is consumed by hydration — grab it fast
    html = page.content()
    for _ in range(10):
        if "__framer__handoverData" in html:
            break
        page.wait_for_timeout(500)
        html = page.content()
    entries = extract(html)
    if not entries:
        logging.warning("No entries found")
        return
    entries.sort(key=lambda x: x.get("published_date", ""), reverse=True)
    write_atom_feed(FEEDS_DIR / p["output_file"], entries,
                    feed_title=p["label"], feed_link=PAGE_URL,
                    feed_icon=config.get("favicon"))


if __name__ == "__main__":
    from playwright.sync_api import sync_playwright
    pw = sync_playwright().start()
    browser = pw.chromium.launch(
        headless=True,
        args=[
            "--disable-blink-features=AutomationControlled",
            "--no-sandbox",
            "--disable-dev-shm-usage",
        ],
    )
    context = browser.new_context(
        viewport={"width": 1920, "height": 1080},
        user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    )
    page = context.new_page()
    page.add_init_script("""
        Object.defineProperty(navigator, 'webdriver', { get: () => false });
        Object.defineProperty(navigator, 'plugins', { get: () => [1, 2, 3, 4, 5] });
        Object.defineProperty(navigator, 'languages', { get: () => ['en-US', 'en'] });
        window.chrome = { runtime: {} };
        const oq = window.navigator.permissions.query;
        window.navigator.permissions.query = (p) => (
            p.name === 'notifications' ? Promise.resolve({ state: 'denied' }) : oq(p)
        );
    """)
    try:
        run(page)
    finally:
        browser.close()
        pw.stop()
