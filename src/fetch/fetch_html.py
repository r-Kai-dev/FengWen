import asyncio
import json
import logging
import re
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urljoin

import curl_cffi
from bs4 import BeautifulSoup, Comment
from curl_cffi.requests import AsyncSession

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)

script_dir = Path(__file__).resolve().parent
project_dir = script_dir.parent.parent
html_cache_dir = project_dir / "html_cache"
logs_dir = project_dir / "logs"

html_cache_dir.mkdir(parents=True, exist_ok=True)
logs_dir.mkdir(parents=True, exist_ok=True)

# Tags that are never visible text content — safe to remove unconditionally.
_REMOVE_TAGS = {
    "script",
    "style",
    "noscript",
    "template",  # executable / inert
    "img",
    "picture",
    "video",
    "audio",  # binary media
    "source",
    "track",  # media children
    "canvas",
    "svg",  # rendered graphics
    "iframe",
    "embed",
    "object",  # third-party embeds
}


def prune_html(html: str) -> str:
    """
    Conservatively remove non-text nodes from raw HTML.

    Only strips content that can never be article text: scripts, styles,
    media elements, embeds, and HTML comments. All structural and
    class/id-based heuristics are intentionally omitted.
    """
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


async def fetch_and_save(
    session: AsyncSession,
    org_key: str,
    base_url: str,
    page: str,
    semaphore: asyncio.Semaphore,
) -> dict:
    """Fetch a single URL, prune boilerplate, and save HTML to the cache directory."""
    url = urljoin(base_url.rstrip("/") + "/", page.lstrip("/"))

    async with semaphore:
        try:
            response = await session.get(url, impersonate="chrome120", timeout=10)
            response.raise_for_status()
        except curl_cffi.requests.errors.RequestsError as e:
            if e.response is not None:
                code = e.response.status_code
                logging.error(f"HTTP {code} — {url}")
                return {"url": url, "status": "http_error", "status_code": code}
            elif "timeout" in str(e).lower():
                logging.error(f"Timeout — {url}")
                return {"url": url, "status": "timeout", "error": str(e)}
            else:
                logging.error(f"Error — {url}: {e}")
                return {"url": url, "status": "error", "error": str(e)}

        pruned = prune_html(response.text)
        filename = make_cache_filename(org_key, page)
        (html_cache_dir / filename).write_text(pruned, encoding="utf-8")
        logging.info(f"Saved {filename}")
        return {"url": url, "status": "success", "file": filename}


async def fetch_all(entries: list[dict], max_concurrent: int = 5) -> None:
    """Fetch all URLs from the config entries concurrently and log results."""
    semaphore = asyncio.Semaphore(max_concurrent)

    async with AsyncSession() as session:
        tasks = [
            fetch_and_save(session, entry["org_key"], entry["url"], page, semaphore)
            for entry in entries
            for page in entry.get("pages", ["/"])
        ]
        results = await asyncio.gather(*tasks, return_exceptions=True)

    # Save log
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H")
    log_path = logs_dir / f"fetch_logs_{timestamp}.json"
    log_path.write_text(
        json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    # Summary
    successes = sum(
        1 for r in results if isinstance(r, dict) and r.get("status") == "success"
    )
    failures = [
        r for r in results if isinstance(r, dict) and r.get("status") != "success"
    ]

    logging.info(f"Done: {successes}/{len(results)} successful")
    for f in failures:
        code = f.get("status_code", "")
        detail = f" (HTTP {code})" if code else f" ({f.get('status')})"
        logging.warning(f"  FAILED {f['url']}{detail}")


if __name__ == "__main__":
    config_path = project_dir / "config" / "html.json"
    entries = json.loads(config_path.read_text(encoding="utf-8"))

    logging.info(f"Loaded {len(entries)} sites, fetching all pages...")
    asyncio.run(fetch_all(entries, max_concurrent=5))
