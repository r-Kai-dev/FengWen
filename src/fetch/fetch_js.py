"""Fetch JS-rendered pages using DrissionPage + headless Chromium.

Reads config/js.json and processes each site:
  - bytedance, qwen: navigate, wait for JS render, save pruned HTML.
  - deepseek:      navigate to /, click the "News" sidebar dropdown to expand
                   the news list, then save the rendered HTML (including all
                   sidebar news links).

Saved to html_cache/ following the same naming convention as fetch_html.py.
"""

import json
import logging
import re
from datetime import datetime, timezone
from pathlib import Path

from bs4 import BeautifulSoup, Comment
from DrissionPage import ChromiumOptions, ChromiumPage

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)

script_dir = Path(__file__).resolve().parent
project_dir = script_dir.parent.parent
html_cache_dir = project_dir / "html_cache"
logs_dir = project_dir / "logs"

html_cache_dir.mkdir(parents=True, exist_ok=True)
logs_dir.mkdir(parents=True, exist_ok=True)

# Tags stripped from saved HTML (mirrors fetch_html.py)
_REMOVE_TAGS = {
    "script", "style", "noscript", "template",
    "img", "picture", "video", "audio",
    "source", "track", "canvas", "svg",
    "iframe", "embed", "object",
}


def prune_html(html: str) -> str:
    """Remove non-text boilerplate from raw HTML (same as fetch_html.py)."""
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup.find_all(_REMOVE_TAGS):
        tag.decompose()
    for comment in soup.find_all(string=lambda s: isinstance(s, Comment)):
        comment.extract()
    return str(soup)


def make_cache_filename(org_key: str, page: str) -> str:
    """Derive a safe cache filename from org_key and page path."""
    page_slug = re.sub(r"[^\w]", "-", page.strip("/")) or "index"
    return f"{org_key}_{page_slug}.html"


def save_html(org_key: str, page: str, html: str) -> str:
    """Prune and write HTML to cache, return the filename."""
    pruned = prune_html(html)
    filename = make_cache_filename(org_key, page)
    (html_cache_dir / filename).write_text(pruned, encoding="utf-8")
    logging.info(f"Saved {filename}  ({len(pruned)} chars)")
    return filename


def _start_browser() -> ChromiumPage:
    """Launch or connect to a headless Chromium instance via DrissionPage."""
    co = ChromiumOptions()
    co.set_browser_path("/usr/bin/chromium")
    co.set_argument("--headless=new")
    co.set_argument("--no-sandbox")
    co.set_argument("--disable-gpu")
    co.set_argument("--disable-dev-shm-usage")
    co.set_argument("--window-size", "1920,1080")
    # Use a fresh temp profile so no cookies interfere
    co.new_env(on_off=True)
    co.headless(on_off=True)
    page = ChromiumPage(addr_or_opts=co)
    page.set.timeouts(page_load=30)
    page.set.window.size(1920, 1080)
    logging.info(f"Browser launched: {page.browser_version}")
    return page


def _fetch_straightforward(page: ChromiumPage, url: str) -> str:
    """Navigate and return the fully-rendered HTML (for SPA sites)."""
    logging.info(f"Navigating to {url}")
    page.get(url)
    page.wait.doc_loaded()
    # Give SPA frameworks extra time to render content
    page.wait(2)
    return page.html


def _fetch_deepseek_news(page: ChromiumPage, base_url: str) -> str:
    """Navigate to DeepSeek docs, expand the News sidebar, return HTML.

    The desktop sidebar in Docusaurus only renders at a wide viewport.
    We navigate to the homepage, find the "News" sidebar category
    (which starts collapsed), and click it to expand so all news
    article links are visible in the DOM.
    """
    logging.info(f"Navigating to {base_url}")
    page.get(base_url)
    page.wait.doc_loaded()
    page.wait(2)

    # Find the "News" sidebar category using DrissionPage text locator
    news_link = page.ele("tx:News", timeout=5)
    if news_link:
        # The collapsible toggle is the parent <div class="menu__list-item-collapsible">
        collapsible = news_link.parent("tag:div")
        if collapsible:
            logging.info("Clicking News sidebar dropdown …")
            collapsible.click()
            page.wait(0.5)
            logging.info("News category expanded")
        else:
            logging.warning("Could not find collapsible wrapper for News")
    else:
        logging.warning("Could not find News sidebar element")

    return page.html


def fetch_all(config_path: Path) -> None:
    """Process every entry in the JS config file."""
    entries = json.loads(config_path.read_text(encoding="utf-8"))
    page = _start_browser()

    results = []

    try:
        for entry in entries:
            org_key = entry["org_key"]
            base_url = entry["url"]
            pages = entry.get("pages", ["/"])

            for page_path in pages:
                try:
                    if org_key == "deepseek" and page_path == "/":
                        html = _fetch_deepseek_news(page, base_url)
                    else:
                        full_url = base_url.rstrip("/") + "/" + page_path.lstrip("/")
                        html = _fetch_straightforward(page, full_url)

                    filename = save_html(org_key, page_path, html)
                    results.append({"url": base_url, "page": page_path, "status": "success", "file": filename})
                except Exception as exc:
                    logging.error(f"Failed {org_key}/{page_path}: {exc}")
                    results.append({"url": base_url, "page": page_path, "status": "error", "error": str(exc)})
    finally:
        page.quit()

    # Summary
    successes = sum(1 for r in results if r["status"] == "success")
    logging.info(f"Done: {successes}/{len(results)} successful")
    for r in results:
        if r["status"] != "success":
            logging.warning(f"  FAILED {r['url']}/{r['page']}: {r.get('error', '')}")

    # Save log
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H")
    log_path = logs_dir / f"fetch_js_log_{timestamp}.json"
    log_path.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")


if __name__ == "__main__":
    config_path = project_dir / "config" / "js.json"
    if not config_path.exists():
        logging.error(f"Config not found: {config_path}")
        exit(1)

    logging.info(f"Loaded config from {config_path}")
    fetch_all(config_path)
