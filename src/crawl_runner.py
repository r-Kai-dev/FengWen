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
    )
    page = context.new_page()
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
