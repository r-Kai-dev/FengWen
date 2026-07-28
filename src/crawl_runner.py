"""Launch one headless Chromium instance via Playwright, run all crawl_*.py scripts sequentially.

Each crawl script exposes ``def run(page)`` where page is a Playwright Page.
Auto-discovered via ``importlib`` — no manual registration needed.
"""

import importlib
import logging
from pathlib import Path

from playwright.sync_api import sync_playwright

SRC_DIR = Path(__file__).resolve().parent

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)


def _start_browser():
    pw = sync_playwright().start()
    browser = pw.chromium.launch(
        headless=True,
        args=[
            "--disable-blink-features=AutomationControlled",
            "--no-sandbox",
            "--disable-dev-shm-usage",
            "--disable-gpu",
        ],
    )
    context = browser.new_context(
        viewport={"width": 1920, "height": 1080},
        user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
        extra_http_headers={
            "Accept-Language": "en-US,en;q=0.9",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
            "Sec-CH-UA": '"Chromium";v="131", "Google Chrome";v="131", "Not?A_Brand";v="99"',
            "Sec-CH-UA-Platform": '"Windows"',
            "Sec-CH-UA-Mobile": "?0",
            "Upgrade-Insecure-Requests": "1",
            "Cache-Control": "no-cache",
        },
    )
    page = context.new_page()
    # Evade headless detection (Cloudflare, etc.)
    page.add_init_script("""
        Object.defineProperty(navigator, 'webdriver', { get: () => false });
        Object.defineProperty(navigator, 'plugins', { get: () => [1, 2, 3, 4, 5] });
        Object.defineProperty(navigator, 'languages', { get: () => ['en-US', 'en'] });
        window.chrome = { runtime: {} };
        const originalQuery = window.navigator.permissions.query;
        window.navigator.permissions.query = (parameters) => (
            parameters.name === 'notifications' ?
                Promise.resolve({ state: 'denied' }) :
                originalQuery(parameters)
        );
    """)
    logging.info("Browser launched: %s", browser.version)
    return pw, page


def main():
    crawlers = sorted(p for p in SRC_DIR.glob("crawl_*.py") if p.name != "crawl_runner.py")
    if not crawlers:
        logging.info("No crawl scripts found.")
        return

    pw, page = _start_browser()
    succeeded = 0
    failed = 0
    failed_names = []

    try:
        for crawler_path in crawlers:
            name = crawler_path.stem
            try:
                mod = importlib.import_module(name)
                mod.run(page)
                succeeded += 1
                logging.info("[OK] %s", name)
            except Exception as exc:
                failed += 1
                failed_names.append(name)
                logging.error("[FAIL] %s: %s", name, exc)
                import traceback
                traceback.print_exc()
    finally:
        page.context.browser.close()
        pw.stop()

    logging.info("Crawl complete: %d succeeded, %d failed", succeeded, failed)
    if failed_names:
        logging.error("Failed scripts: %s", ", ".join(failed_names))
    if failed > 0 and succeeded == 0:
        logging.warning("No crawl scripts succeeded — pipeline will continue but no crawl feeds were updated")


if __name__ == "__main__":
    main()
