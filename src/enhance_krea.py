"""Enhance Krea's official Atom feed by fixing broken entry URLs and
injecting a favicon.

The upstream feed at https://www.krea.ai/blog/feed/atom.xml has entry
<link href> and <id> elements pointing to /blog/category/slug instead of
/blog/slug.  It also lacks an <icon> element.  This script fixes both.
"""

import logging
import re

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


def fix_krea_feed(xml_text: str, favicon: str | None = None) -> str:
    """Replace broken /blog/category/ paths and inject favicon."""
    xml_text = xml_text.replace("/blog/category/", "/blog/")

    if favicon:
        # Insert <icon> after the feed-level <id> if not already present
        if "<icon>" not in xml_text:
            xml_text = re.sub(
                r"(<id>[^<]+</id>)",
                rf"\1\n  <icon>{favicon}</icon>",
                xml_text,
                count=1,
            )

    return xml_text


def main() -> None:
    config = load_feeds_config(ORG_KEY)
    favicon = config.get("favicon")
    for page_key, page in config["pages"].items():
        logging.info("Enhancing %s: %s", page["label"], page["url"])
        xml_text = fetch_page(page["url"])
        xml_text = fix_krea_feed(xml_text, favicon=favicon)

        output_path = FEEDS_DIR / page["output_file"]
        output_path.write_text(xml_text, encoding="utf-8")
        logging.info("Wrote enhanced Atom feed to %s", output_path)


if __name__ == "__main__":
    main()
