# Scrape script boilerplate

Copy this template and replace `ORG_KEY` + the extraction logic.

```python
import hashlib, logging
from datetime import datetime, timezone
from bs4 import BeautifulSoup
from utils import (
    FEEDS_DIR, setup_logging, ensure_output_dir,
    load_feeds_config, fetch_page, compact, write_atom_feed,
)

setup_logging()
ensure_output_dir()
ORG_KEY = "example"

def main():
    config = load_feeds_config(ORG_KEY)
    favicon = config.get("favicon")
    for page_key, page in config["pages"].items():
        logging.info("Fetching %s: %s", page["label"], page["url"])
        html = fetch_page(page["url"])
        soup = BeautifulSoup(html, "html.parser")
        entries = []  # ← your extraction logic here
        if not entries:
            logging.warning("No entries for %s", page_key)
            continue
        entries.sort(key=lambda x: x.get("published_date", ""), reverse=True)
        write_atom_feed(FEEDS_DIR / page["output_file"], entries,
                        feed_title=page["label"], feed_link=page["url"],
                        feed_icon=favicon)

if __name__ == "__main__":
    main()
```
