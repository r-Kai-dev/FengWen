"""Enhance Krea's official Atom feed by fixing broken entry URLs.

The Krea blog feed at https://www.krea.ai/blog/feed/atom.xml has entry
<link href> and <id> elements pointing to /blog/category/slug instead of
/blog/slug.  This script fetches the raw feed, fixes the URLs, and writes
the corrected XML.
"""

import logging

from utils import (
    FEEDS_DIR,
    setup_logging,
    ensure_output_dir,
    load_feeds_config,
    fetch_page,
)

setup_logging()
ensure_output_dir()
ORG_KEY = "krea"


def fix_krea_feed(xml_text: str) -> str:
    """Replace broken /blog/category/ paths with /blog/ in entry URLs."""
    return xml_text.replace("/blog/category/", "/blog/")


def main() -> None:
    config = load_feeds_config(ORG_KEY)
    for page_key, page in config["pages"].items():
        logging.info("Enhancing %s: %s", page["label"], page["url"])
        xml_text = fetch_page(page["url"])
        xml_text = fix_krea_feed(xml_text)

        output_path = FEEDS_DIR / page["output_file"]
        output_path.write_text(xml_text, encoding="utf-8")
        logging.info("Wrote enhanced Atom feed to %s", output_path)


if __name__ == "__main__":
    main()
