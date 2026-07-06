# Crawl script boilerplate

Copy this template, replace `ORG_KEY`, and add the extraction logic.

Crawl scripts are run by `crawl_runner.py` which passes a shared Playwright
`Page`. They expose `def run(page)` — **not** `main()`.

```python
import hashlib, logging, re
from datetime import datetime, timezone
from bs4 import BeautifulSoup
from utils import (
    FEEDS_DIR, setup_logging, ensure_output_dir,
    load_feeds_config, compact, write_atom_feed,
)

setup_logging()
ensure_output_dir()
ORG_KEY = "example"

def parse_date(date_str):
    """Try multiple formats, return ISO-8601 or None."""
    formats = ["%b %d, %Y", "%B %d, %Y", "%Y-%m-%d", "%Y/%m/%d"]
    for fmt in formats:
        try:
            return datetime.strptime(date_str.strip(), fmt).isoformat()
        except ValueError:
            continue
    return None

def run(page):
    config = load_feeds_config(ORG_KEY)
    favicon = config.get("favicon")
    base_url = config["base_url"]
    for page_key, page_cfg in config["pages"].items():
        logging.info("Crawling %s: %s", page_cfg["label"], page_cfg["url"])
        page.goto(page_cfg["url"])
        page.wait_for_timeout(3000)
        soup = BeautifulSoup(page.content(), "html.parser")
        entries = []  # ← your extraction logic here
        if not entries:
            logging.warning("No entries for %s", page_key)
            continue
        entries.sort(key=lambda x: x.get("published_date", ""), reverse=True)
        write_atom_feed(FEEDS_DIR / page_cfg["output_file"], entries,
                        feed_title=page_cfg["label"], feed_link=page_cfg["url"],
                        feed_icon=favicon)

if __name__ == "__main__":
    # Standalone testing
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        browser = p.chromium.launch()
        pg = browser.new_page()
        run(pg)
        browser.close()
```
