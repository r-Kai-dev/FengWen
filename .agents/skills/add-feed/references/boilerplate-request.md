# Request script boilerplate

Copy this template, replace `ORG_KEY`, add the extraction logic, and wire up
`fetch_with_retry()` with the actual endpoints.

```python
import asyncio, hashlib, logging
from datetime import datetime, timezone
from curl_cffi.requests import AsyncSession
from utils import (
    FEEDS_DIR, setup_logging, ensure_output_dir,
    load_feeds_config, fetch_with_retry, compact, write_atom_feed,
)

setup_logging()
ensure_output_dir()
ORG_KEY = "example"

async def main():
    config = load_feeds_config(ORG_KEY)
    favicon = config.get("favicon")
    async with AsyncSession() as session:
        for page_key, page in config["pages"].items():
            logging.info("Fetching %s: %s", page["label"], page["url"])
            response = await fetch_with_retry(session, page["url"],
                                              impersonate="chrome120", timeout=15)
            data = response.json()
            entries = []  # ← your extraction logic here
            if not entries:
                logging.warning("No entries for %s", page_key)
                continue
            entries.sort(key=lambda x: x.get("published_date", ""), reverse=True)
            feed_link = page.get("feed_link", page["url"])
            write_atom_feed(FEEDS_DIR / page["output_file"], entries,
                            feed_title=page["label"], feed_link=feed_link,
                            feed_icon=favicon)

if __name__ == "__main__":
    asyncio.run(main())
```
