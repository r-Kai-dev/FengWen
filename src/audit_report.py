"""Post-processor: inspect generated feeds/*.xml and produce a health report.

Reads config/feeds.json and all feed XML files, then writes
feeds/_audit.json — a single distilled report that the CI commits
alongside the XMLs. The agent skill reads this as a cheap triage
step before deeper manual investigation.

Detects silently from XML alone:
  - Missing output files
  - Zero entries
  - Staleness (newest entry older than threshold)
  - All entries sharing the same date (likely fallback spam)
  - Unparseable XML
"""

import json
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import xml.etree.ElementTree as ET

SRC_DIR = Path(__file__).resolve().parent
PROJECT_DIR = SRC_DIR.parent
FEEDS_DIR = PROJECT_DIR / "feeds"
CONFIG_DIR = PROJECT_DIR / "config"

# Namespaces used in Atom feeds
NS = {"atom": "http://www.w3.org/2005/Atom"}
# Also handle feeds without the explicit namespace (etree auto-assigns ns0)
NS_ALT = {"ns0": "http://www.w3.org/2005/Atom"}


def _load_config() -> dict[str, dict]:
    """Load all created feeds from config, keyed by output_file."""
    with open(CONFIG_DIR / "feeds.json", "r", encoding="utf-8") as f:
        cfg = json.load(f)

    result: dict[str, dict] = {}
    for entry in cfg.get("created", []):
        for page in entry.get("pages", []):
            output_file = page["output_file"]
            result[output_file] = {
                "org_key": entry["org_key"],
                "name": entry["name"],
                "strategy": entry.get("strategy", "unknown"),
                "category": entry.get("category", ""),
                "page_key": page["key"],
                "page_label": page["label"],
                "page_url": page["url"],
                "output_file": output_file,
            }
    return result


def _staleness_threshold(category: str) -> int:
    """Return maximum acceptable age in days for a feed's latest entry.

    More frequent feeds get tighter thresholds.  Default: 30 days.
    """
    cat_lower = category.lower() if category else ""
    if "hourly" in cat_lower:
        return 3
    if "daily" in cat_lower:
        return 7
    if "weekly" in cat_lower:
        return 14
    return 30


def _parse_dates_from_feed(
    xml_path: Path,
) -> tuple[list[datetime], list[str], int]:
    """Parse an Atom XML file and return (dates, all_date_strings, entry_count).

    Only extracts <published> dates.  Returns empty lists on parse error.
    """
    try:
        tree = ET.parse(xml_path)
        root = tree.getroot()
    except ET.ParseError:
        return [], [], -1  # -1 signals parse error
    except Exception:
        return [], [], -1

    entries = root.findall("atom:entry", NS)
    if not entries:
        entries = root.findall("ns0:entry", NS_ALT)
    dates = []
    date_strs = []
    for entry in entries:
        published = entry.find("atom:published", NS)
        if published is None:
            published = entry.find("ns0:published", NS_ALT)
        if published is not None and published.text:
            date_str = published.text.strip()
            date_strs.append(date_str)
            try:
                # Handle both "2026-07-02T00:00:00+00:00" and "+00:00"/"Z"
                ds = date_str.replace("Z", "+00:00")
                dt = datetime.fromisoformat(ds)
                # Normalize to UTC
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)
                dates.append(dt.astimezone(timezone.utc))
            except (ValueError, TypeError):
                pass

    return dates, date_strs, len(entries)


def _check_feed(
    output_file: str, config_entry: dict | None
) -> dict[str, Any]:
    """Run health checks on a single feed XML file.

    Returns a result dict with status and issues.
    """
    xml_path = FEEDS_DIR / output_file

    # File missing
    if not xml_path.exists():
        return {
            "output_file": output_file,
            "status": "error",
            "entry_count": 0,
            "newest_date": None,
            "oldest_date": None,
            "age_days": None,
            "issues": ["xml_missing"],
        }

    dates, date_strs, entry_count = _parse_dates_from_feed(xml_path)

    # Parse error
    if entry_count == -1:
        return {
            "output_file": output_file,
            "status": "error",
            "entry_count": 0,
            "newest_date": None,
            "oldest_date": None,
            "age_days": None,
            "issues": ["xml_parse_error"],
        }

    result: dict[str, Any] = {
        "output_file": output_file,
        "entry_count": entry_count,
        "newest_date": None,
        "oldest_date": None,
        "age_days": None,
        "issues": [],
    }

    if dates:
        dates.sort(reverse=True)
        newest = dates[0]
        oldest = dates[-1]
        result["newest_date"] = newest.strftime("%Y-%m-%d")
        result["oldest_date"] = oldest.strftime("%Y-%m-%d")
        now = datetime.now(timezone.utc)
        age_days = (now - newest).days
        result["age_days"] = age_days

        # Staleness check
        category = config_entry.get("category", "") if config_entry else ""
        threshold = _staleness_threshold(category)
        if age_days > threshold:
            result["issues"].append(f"stale_{age_days}d")

        # All same date — only flag when the date is today (age_days == 0),
        # which strongly suggests a datetime.now() fallback with no real dates
        # parsed.  Snapshot feeds (trending, daily digests) naturally have
        # same-date entries but the date is at least yesterday's content.
        unique_dates = {d.strftime("%Y-%m-%d") for d in dates}
        if len(unique_dates) == 1 and entry_count > 1 and age_days == 0:
            result["issues"].append("all_same_date")

    # Zero entries (only flag if file exists and parses OK)
    if entry_count == 0:
        result["issues"].append("zero_entries")

    # Determine status
    if result["issues"]:
        # "error" status for parse errors and missing files (handled above)
        result["status"] = "warning"
    else:
        result["status"] = "healthy"

    return result


def _check_official(config_entry: dict) -> dict[str, Any]:
    """Check an official feed — we can't inspect the XML but we note it exists.

    Official feeds are not generated by us, so there's no filesystem check.
    The agent skill will handle these during manual investigation.
    """
    return {
        "output_file": None,
        "name": config_entry.get("name", ""),
        "xml_url": config_entry.get("xmlUrl", ""),
        "html_url": config_entry.get("htmlUrl", ""),
        "category": config_entry.get("category", ""),
        "status": "unchecked",
        "entry_count": None,
        "newest_date": None,
        "oldest_date": None,
        "age_days": None,
        "issues": ["unchecked_official"],
    }


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

    config = _load_config()
    logging.info("Loaded %d created feeds from config", len(config))

    results: dict[str, dict] = {}
    summary = {"total": 0, "healthy": 0, "warning": 0, "error": 0, "unchecked": 0}

    for output_file, cfg_entry in config.items():
        result = _check_feed(output_file, cfg_entry)
        # Include metadata from config for the agent
        result.update(
            {
                k: cfg_entry.get(k)
                for k in [
                    "name",
                    "strategy",
                    "category",
                    "page_key",
                    "page_label",
                    "page_url",
                    "org_key",
                ]
            }
        )
        results[output_file] = result
        summary["total"] += 1
        summary[result["status"]] += 1

    # Also record official feeds for agent awareness
    with open(CONFIG_DIR / "feeds.json", "r", encoding="utf-8") as f:
        full_cfg = json.load(f)
    for entry in full_cfg.get("official", []):
        name = entry.get("name", entry.get("xmlUrl", "unknown"))
        official = _check_official(entry)
        # Use name as key; handle duplicates by appending url
        key = name
        i = 1
        while key in results:
            key = f"{name}_{i}"
            i += 1
        results[key] = official
        summary["total"] += 1
        summary["unchecked"] += 1

    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "feeds": results,
        "summary": summary,
    }

    audit_path = FEEDS_DIR / "_audit.json"
    audit_path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    logging.info(
        "Audit report written: %d/%d healthy, %d warning, %d error, %d unchecked",
        summary["healthy"],
        summary["total"],
        summary["warning"],
        summary["error"],
        summary["unchecked"],
    )

    # Exit non-zero on errors (but not warnings — those are for the agent)
    if summary["error"] > 0:
        logging.warning("Exiting with code 1 due to %d error(s)", summary["error"])
        sys.exit(1)
    else:
        logging.info("Audit passed.")


if __name__ == "__main__":
    main()
