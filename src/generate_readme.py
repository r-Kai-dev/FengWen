#!/usr/bin/env python3
"""Generate README.md from feeds.opml (canonical source of truth).

Reads feeds.opml and replaces the marked section in README.md with
human-friendly markdown tables.

Usage:
    python src/generate_readme.py
"""

import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OPML_PATH = ROOT / "feeds.opml"
README_PATH = ROOT / "README.md"

# Sentinel markers in README.md that bracket the auto-generated tables
MARKER_START = "<!-- FEEDS_TABLE_START -->"
MARKER_END = "<!-- FEEDS_TABLE_END -->"

# OPML namespace
NS = {"fw": "https://codeberg.org/r-Kai/FengWen"}


def parse_opml(path: Path) -> list[dict]:
    """Parse feeds.opml and return a list of category dicts.

    Each category dict:
        {
            "title": "Lab/Company Feeds",
            "feeds": [
                {
                    "text": "Anthropic News",
                    "xmlUrl": "https://...",
                    "htmlUrl": "https://...",
                    "type": "created" | "official",
                },
                ...
            ]
        }
    """
    tree = ET.parse(path)
    root = tree.getroot()
    body = root.find("body")
    if body is None:
        raise ValueError("No <body> found in OPML")

    categories = []
    for cat_elem in body.findall("outline"):
        title = cat_elem.get("text") or cat_elem.get("title", "")
        feeds = []
        for feed_elem in cat_elem.findall("outline"):
            text = feed_elem.get("text") or feed_elem.get("title", "")
            xml_url = feed_elem.get("xmlUrl", "")
            html_url = feed_elem.get("htmlUrl", "")
            fw_type = feed_elem.get("{%s}type" % NS["fw"], "created")
            feeds.append({
                "text": text,
                "xmlUrl": xml_url,
                "htmlUrl": html_url,
                "type": fw_type,
            })
        categories.append({"title": title, "feeds": feeds})
    return categories


def feed_filename(xml_url: str) -> str:
    """Extract the filename part from a feed URL."""
    return xml_url.rstrip("/").rsplit("/", 1)[-1]


def format_feed_label(text: str, xml_url: str, fw_type: str) -> str:
    """Format the feed link label. For created feeds, use the filename.
    For official feeds, use the display text."""
    if fw_type == "created":
        label = feed_filename(xml_url)
    else:
        label = text + " Feed"
    return f"[{label}]({xml_url})"


def build_tables(categories: list[dict]) -> str:
    """Build markdown tables from the parsed OPML data."""
    sections = []

    for cat in categories:
        lines = []
        lines.append(f"## {cat['title']}")
        # Add a To-Do note for Academic Feeds if present
        if cat["title"] == "Academic Feeds":
            lines.append("To-Do: Appending logic with snapshot timestamps")
            lines.append("")
        lines.append("| Original Website | Feed | Type |")
        lines.append("|------------------|------|------|")

        for feed in cat["feeds"]:
            text = feed["text"]
            xml_url = feed["xmlUrl"]
            html_url = feed["htmlUrl"]
            fw_type = feed["type"]

            type_label = "Created" if fw_type == "created" else "Official"
            site_link = f"[{text}]({html_url})"
            feed_label = format_feed_label(text, xml_url, fw_type)

            lines.append(f"| {site_link} | {feed_label} | {type_label} |")

        lines.append("")  # blank line after table
        sections.append("\n".join(lines))

    return "\n\n".join(sections)


def update_readme(categories: list[dict]) -> None:
    """Read README.md, find the marker section, and replace it with
    generated tables."""
    raw = README_PATH.read_text(encoding="utf-8")

    if MARKER_START not in raw or MARKER_END not in raw:
        raise SystemExit(
            f"README.md missing markers: {MARKER_START} ... {MARKER_END}"
        )

    before = raw.split(MARKER_START, 1)[0]
    after = raw.split(MARKER_END, 1)[1]

    tables = build_tables(categories)
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


def main() -> None:
    if not OPML_PATH.exists():
        raise SystemExit(f"OPML file not found: {OPML_PATH}")
    categories = parse_opml(OPML_PATH)
    update_readme(categories)


if __name__ == "__main__":
    main()
