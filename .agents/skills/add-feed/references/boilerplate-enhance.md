# Enhance script boilerplate

Copy this template, replace `ORG_KEY`, and apply fixes to the upstream XML.
If the upstream feed is missing a favicon, inject the `<icon>` element
from `config.get("favicon")` — see `enhance_krea.py` for the pattern.

```python
import logging
import re
from utils import (
    FEEDS_DIR, setup_logging, ensure_output_dir,
    load_feeds_config, fetch_page,
)

setup_logging()
ensure_output_dir()
ORG_KEY = "example"

def main():
    config = load_feeds_config(ORG_KEY)
    favicon = config.get("favicon")
    for page_key, page in config["pages"].items():
        logging.info("Enhancing %s: %s", page["label"], page["url"])
        xml_text = fetch_page(page["url"])
        # ← apply fixes here (e.g., xml_text.replace(...) or parse + rebuild)

        # Inject favicon if upstream feed lacks one
        if favicon and "<icon>" not in xml_text:
            xml_text = re.sub(
                r"(<id>[^<]+</id>)",
                rf"\1\n  <icon>{favicon}</icon>",
                xml_text,
                count=1,
            )

        output_path = FEEDS_DIR / page["output_file"]
        output_path.write_text(xml_text, encoding="utf-8")

if __name__ == "__main__":
    main()
```
