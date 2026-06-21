#!/usr/bin/env python3
"""Generate README.md from config/feeds.json (canonical source of truth).

Reads config/feeds.json and replaces the marked section in README.md with
human-friendly markdown tables.

Usage:
    python src/generate_readme.py
"""

import json
from pathlib import Path

SRC_DIR = Path(__file__).resolve().parent
PROJECT_DIR = SRC_DIR.parent
CONFIG_PATH = PROJECT_DIR / "config" / "feeds.json"
README_PATH = PROJECT_DIR / "README.md"

MARKER_START = "<!-- FEEDS_TABLE_START -->"
MARKER_END = "<!-- FEEDS_TABLE_END -->"
CODEBERG_BASE = "https://codeberg.org/r-Kai/FengWen/raw/branch/main/feeds"


def feed_filename(xml_url: str) -> str:
    return xml_url.rstrip("/").rsplit("/", 1)[-1]


def format_feed_label(text: str, xml_url: str, fw_type: str) -> str:
    if fw_type == "created":
        label = feed_filename(xml_url)
    else:
        label = text + " Feed"
    return f"[{label}]({xml_url})"


def build_tables(config):
    # Gather feeds by category
    category_feeds: dict[str, list[dict]] = {}

    for entry in config.get("created", []):
        cat_key = entry.get("category", "Uncategorized")
        for page in entry.get("pages", []):
            xml_url = f"{CODEBERG_BASE}/{page['output_file']}"
            category_feeds.setdefault(cat_key, []).append({
                "text": page["label"],
                "xmlUrl": xml_url,
                "htmlUrl": page["url"],
                "type": "created",
            })

    for entry in config.get("official", []):
        cat_key = entry.get("category", "Uncategorized")
        category_feeds.setdefault(cat_key, []).append({
            "text": entry["name"],
            "xmlUrl": entry["xmlUrl"],
            "htmlUrl": entry["htmlUrl"],
            "type": "official",
        })

    sections = []
    for cat_key in sorted(category_feeds.keys()):
        feeds = category_feeds[cat_key]
        if not feeds:
            continue
        lines = [f"## {cat_key}"]
        lines.append("| Original Website | Feed | Type |")
        lines.append("|------------------|------|------|")

        for feed in feeds:
            type_label = "Created" if feed["type"] == "created" else "Official"
            site_link = f"[{feed['text']}]({feed['htmlUrl']})"
            feed_label = format_feed_label(feed["text"], feed["xmlUrl"], feed["type"])
            lines.append(f"| {site_link} | {feed_label} | {type_label} |")

        lines.append("")
        sections.append("\n".join(lines))

    return "\n\n".join(sections)


def update_readme(config):
    raw = README_PATH.read_text(encoding="utf-8")
    if MARKER_START not in raw or MARKER_END not in raw:
        raise SystemExit(f"README.md missing markers: {MARKER_START} ... {MARKER_END}")

    before = raw.split(MARKER_START, 1)[0]
    after = raw.split(MARKER_END, 1)[1]

    tables = build_tables(config)
    new_readme = (
        before.rstrip()
        + "\n\n"
        + MARKER_START
        + "\n\n"
        + tables
        + "\n"
        + MARKER_END
        + after
    )
    README_PATH.write_text(new_readme, encoding="utf-8")
    print(f"Updated {README_PATH}")


def main():
    if not CONFIG_PATH.exists():
        raise SystemExit(f"Config not found: {CONFIG_PATH}")
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        config = json.load(f)
    update_readme(config)


if __name__ == "__main__":
    main()
