"""Launch one headless Chromium instance, run all crawl_*.py scripts sequentially.

Each crawl script exposes ``def run(page: ChromiumPage)``.
Auto-discovered via ``importlib`` — no manual registration needed.
"""

import importlib
import logging
from pathlib import Path

from DrissionPage import ChromiumOptions, ChromiumPage

SRC_DIR = Path(__file__).resolve().parent

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)


def _start_browser():
    co = ChromiumOptions()
    co.set_browser_path("/usr/bin/chromium")
    co.set_argument("--headless=new")
    co.set_argument("--no-sandbox")
    co.set_argument("--disable-gpu")
    co.set_argument("--disable-dev-shm-usage")
    co.set_argument("--window-size=1920,1080")
    co.auto_port()
    co.new_env(on_off=True)
    page = ChromiumPage(addr_or_opts=co)
    page.set.timeouts(page_load=30)
    page.set.window.size(1920, 1080)
    logging.info("Browser launched: %s", page.browser_version)
    return page


def main():
    crawlers = sorted(p for p in SRC_DIR.glob("crawl_*.py") if p.name != "crawl_runner.py")
    if not crawlers:
        logging.info("No crawl scripts found.")
        return

    page = _start_browser()
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
        page.quit()

    logging.info("Crawl complete: %d succeeded, %d failed", succeeded, failed)
    if failed_names:
        logging.error("Failed scripts: %s", ", ".join(failed_names))
    if failed > 0 and succeeded == 0:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
