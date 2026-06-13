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
    "script",
    "style",
    "noscript",
    "template",
    "img",
    "picture",
    "video",
    "audio",
    "source",
    "track",
    "canvas",
    "svg",
    "iframe",
    "embed",
    "object",
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


def _wait_for_render(page: ChromiumPage, org_key: str, timeout: int = 15) -> None:
    """Wait for SPA content to finish rendering, with org_key-specific logic.

    Some SPAs initially show a skeleton loader, then render real content
    after the JS bundles execute and API calls resolve.  This helper waits
    for site-specific signals that the *real* content is in the DOM.
    """
    import time

    if org_key == "tencent_hunyuan":
        # Hunyuan research: wait for blog-item cards to appear AND
        # the skeleton loader to gain class "hidden"
        deadline = time.time() + timeout
        while time.time() < deadline:
            # Check if skeleton is hidden
            try:
                skel = page.ele("#app-skeleton", timeout=1)
                skel_cls = (skel.attr("class") or "") if skel else ""
                skeleton_hidden = "hidden" in skel_cls.split()
            except Exception:
                skeleton_hidden = True

            # Check if any blog cards are rendered
            try:
                cards = page.eles(".blog-item")
                has_content = len(cards) >= 1
            except Exception:
                has_content = False

            if skeleton_hidden and has_content:
                logging.info(f"  Hunyuan content rendered ({len(cards)} blog items)")
                return
            page.wait(0.5)

        # Fallback: just wait a few more seconds
        logging.warning("  Hunyuan render signal not detected, waiting extra …")
        page.wait(5)

    elif org_key == "tencent_aistudio":
        # AI Studio: wait for blog-list__item cards to appear
        deadline = time.time() + timeout
        while time.time() < deadline:
            try:
                cards = page.eles(".blog-list__item")
                if len(cards) >= 1:
                    logging.info(f"  AI Studio content rendered ({len(cards)} blog items)")
                    return
            except Exception:
                pass
            page.wait(0.5)

        logging.warning("  AI Studio render signal not detected, waiting extra …")
        page.wait(5)

    else:
        # Generic wait for other SPAs
        page.wait(3)


def _fetch_straightforward(page: ChromiumPage, url: str, org_key: str = "") -> str:
    """Navigate and return the fully-rendered HTML (for SPA sites).

    Uses org_key-specific wait logic when provided.
    """
    logging.info(f"Navigating to {url}")
    page.get(url)
    page.wait.doc_loaded()
    _wait_for_render(page, org_key)
    return page.html


def _inject_article_ids(page: ChromiumPage, selector: str) -> int:
    """Extract article IDs from React fiber tree and inject as DOM attributes.

    Both the Hunyuan research and AI Studio news/blog pages render their
    article listings via React components.  The article detail URLs use
    numeric IDs stored in the React fiber tree (as fiber.key), not in
    static DOM attributes.  This helper walks each element matching
    *selector*, finds the React fiber internals, and writes
    ``data-article-id`` onto the element so parsers can read it from the
    cached HTML.

    For AI Studio, it also extracts the actual article URL (WeChat article
    links) from the parent component's state and writes it as
    ``data-article-url``.

    Returns the number of elements that received an ID.
    """
    count = page.run_js(f"""
        const items = document.querySelectorAll('{selector}');
        let injected = 0;

        // First pass: find article URLs from the blog-list parent fiber tree
        let articleUrlMap = {{}};
        const listWrapper = document.querySelector('.blog-list, .blog-list-wrapper');
        if (listWrapper) {{
            for (const key in listWrapper) {{
                if (key.startsWith('__reactFiber')) {{
                    let f = listWrapper[key];
                    let depth = 0;
                    while (f && depth < 30) {{
                        let state = f.memoizedState;
                        while (state) {{
                            if (state.queue && state.queue.lastRenderedState) {{
                                const st = state.queue.lastRenderedState;
                                if (Array.isArray(st)) {{
                                    for (const item of st) {{
                                        if (item && (item.url || item.link)) {{
                                            articleUrlMap[item.id] = item.url || item.link;
                                        }}
                                    }}
                                }}
                            }}
                            state = state.next;
                        }}
                        f = f.return;
                        depth++;
                    }}
                }}
            }}
        }}

        // Second pass: inject IDs and URLs onto each item
        items.forEach(item => {{
            let articleId = null;
            for (const key in item) {{
                if (key.startsWith('__reactFiber')) {{
                    let f = item[key];
                    let depth = 0;
                    while (f && depth < 20) {{
                        const fid = f.key;
                        if (fid !== null && fid !== undefined &&
                            (typeof fid === 'number' || /^\\d+$/.test(String(fid)))) {{
                            articleId = String(fid);
                            item.setAttribute('data-article-id', articleId);
                            injected++;
                            // Look up the URL from the parent state map
                            if (articleUrlMap[articleId]) {{
                                item.setAttribute('data-article-url', articleUrlMap[articleId]);
                            }}
                            break;
                        }}
                        // Also check memoizedProps for id or customUrl
                        const mp = f.memoizedProps || {{}};
                        if (mp.id && !articleId) {{
                            articleId = String(mp.id);
                            item.setAttribute('data-article-id', articleId);
                            injected++;
                        }}
                        if (mp.url && !item.getAttribute('data-article-url')) {{
                            item.setAttribute('data-article-url', String(mp.url));
                        }}
                        if (mp.customUrl && !item.getAttribute('data-custom-url')) {{
                            item.setAttribute('data-custom-url', String(mp.customUrl));
                        }}
                        f = f.return;
                        depth++;
                    }}
                }}
            }}
            // Final fallback: if we have an ID but no URL, use the map
            if (articleId && !item.getAttribute('data-article-url') && articleUrlMap[articleId]) {{
                item.setAttribute('data-article-url', articleUrlMap[articleId]);
            }}
        }});
        return injected;
    """)
    return int(count) if count else 0


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


def _fetch_hunyuan_research(page: ChromiumPage, url: str) -> str:
    """Navigate to Hunyuan research page and switch to Chinese (中文).

    The Hunyuan research page shows different articles depending on the
    selected language.  The Chinese version includes more articles (e.g. 5
    vs 4 in English).  We navigate, wait for the initial render, then
    click the Chinese language toggle to switch content, and wait for
    the re-render before capturing the HTML.

    Article URLs use numeric IDs (e.g. /research/100041) that live in
    React fiber internals, not in DOM attributes.  Before saving, we
    inject them as data-article-id attributes onto each .blog-item div
    so the parser can construct correct article URLs.
    """
    logging.info(f"Navigating to {url}")
    page.get(url)
    page.wait.doc_loaded()
    _wait_for_render(page, "tencent_hunyuan")

    # Switch to Chinese for more articles
    logging.info("Switching to Chinese (中文) …")
    page.run_js("""
        const items = document.querySelectorAll('.header__lang-switch-text-item');
        for (const item of items) {
            if (item.textContent.trim() === '中文') {
                item.click();
                break;
            }
        }
    """)
    page.wait(5)

    # Inject article IDs from React fiber tree into DOM
    injected = _inject_article_ids(page, ".blog-item")

    try:
        cards = page.eles(".blog-item")
        logging.info(f"  Chinese version rendered ({len(cards)} blog items, "
                      f"{injected} with article IDs)")
    except Exception:
        logging.warning("  Could not count blog items after language switch")

    return page.html


def _fetch_aistudio_news(page: ChromiumPage, url: str) -> str:
    """Navigate to AI Studio news/blog page, wait for render, and inject
    article IDs from React fiber internals into the DOM before saving.

    Article URLs use numeric IDs (e.g. /news/blog/241) stored in the
    React fiber tree as fiber.key, not in static DOM attributes.
    """
    logging.info(f"Navigating to {url}")
    page.get(url)
    page.wait.doc_loaded()
    _wait_for_render(page, "tencent_aistudio")

    injected = _inject_article_ids(page, ".blog-list__item")

    try:
        cards = page.eles(".blog-list__item")
        logging.info(f"  AI Studio content rendered ({len(cards)} blog items, "
                      f"{injected} with article IDs)")
    except Exception:
        logging.warning("  Could not count blog items")

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
                    elif org_key == "tencent_hunyuan":
                        full_url = base_url.rstrip("/") + "/" + page_path.lstrip("/")
                        html = _fetch_hunyuan_research(page, full_url)
                    elif org_key == "tencent_aistudio":
                        full_url = base_url.rstrip("/") + "/" + page_path.lstrip("/")
                        html = _fetch_aistudio_news(page, full_url)
                    else:
                        full_url = base_url.rstrip("/") + "/" + page_path.lstrip("/")
                        html = _fetch_straightforward(page, full_url, org_key=org_key)

                    filename = save_html(org_key, page_path, html)
                    results.append(
                        {
                            "url": base_url,
                            "page": page_path,
                            "status": "success",
                            "file": filename,
                        }
                    )
                except Exception as exc:
                    logging.error(f"Failed {org_key}/{page_path}: {exc}")
                    results.append(
                        {
                            "url": base_url,
                            "page": page_path,
                            "status": "error",
                            "error": str(exc),
                        }
                    )
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
    log_path.write_text(
        json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8"
    )


if __name__ == "__main__":
    config_path = project_dir / "config" / "js.json"
    if not config_path.exists():
        logging.error(f"Config not found: {config_path}")
        exit(1)

    logging.info(f"Loaded config from {config_path}")
    fetch_all(config_path)
