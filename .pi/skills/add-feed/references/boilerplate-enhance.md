# Enhance script boilerplate

Copy this template, replace `ORG_KEY`, and apply fixes to the upstream XML.

```python
import logging
from utils import (
    FEEDS_DIR, setup_logging, ensure_output_dir,
    load_feeds_config, fetch_page,
)

setup_logging()
ensure_output_dir()
ORG_KEY = "example"

def main():
    config = load_feeds_config(ORG_KEY)
    for page_key, page in config["pages"].items():
        logging.info("Enhancing %s: %s", page["label"], page["url"])
        xml_text = fetch_page(page["url"])
        # ← apply fixes here (e.g., xml_text.replace(...) or parse + rebuild)
        output_path = FEEDS_DIR / page["output_file"]
        output_path.write_text(xml_text, encoding="utf-8")

if __name__ == "__main__":
    main()
```
