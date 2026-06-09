"""Shared utility to load site configuration from config/html.json.

Replaces the old per-parser load_config() that looked for sites_config.json.
Derives cache/output filenames from org_key + pages.
"""

import json
import logging
import re
from pathlib import Path

logger = logging.getLogger(__name__)

project_dir = Path(__file__).resolve().parent.parent.parent
config_dir = project_dir / "config"


def _sanitize(name: str) -> str:
    """Derive a safe filename slug from a page path.

    Must match the logic in fetch_js.py's make_cache_filename:
    - strip leading/trailing slashes
    - replace non-word chars with hyphens
    - use "index" for empty slugs (e.g. page = "/")
    """
    slug = re.sub(r"[^\w]", "-", name.strip("/"))
    return slug if slug else "index"


def load_site_config(org_key: str, config_name: str = "html.json") -> dict:
    """Load site configuration for the given org_key.

    Args:
        org_key:    The org_key to look up.
        config_name: Config file name (e.g. 'html.json' or 'js.json').
                     Defaults to 'html.json'.

    Returns a dict with:
      - cache_files:  {page_name: cache_html_filename, ...}
      - output_files: {page_name: output_json_filename, ...}
      - (optional) extra outputs like 'trending_combined' for github

    Each page_name is the raw value from the config file's 'pages' array.
    """
    config_file = config_dir / config_name
    with open(config_file, "r", encoding="utf-8") as f:
        sites_config = json.load(f)

    for site in sites_config:
        if site.get("org_key") == org_key:
            return _build_file_mapping(site)

    raise ValueError(
        f"Configuration for org_key '{org_key}' not found in config/{config_name}"
    )


def compact(d: dict) -> dict:
    """Remove keys with empty/falsy values from a dict.

    Keeps keys whose value is truthy (non-None, non-empty string,
    non-empty list, non-empty dict). Used by parsers to avoid
    emitting fields with no meaningful data.
    """
    return {k: v for k, v in d.items() if v}


def _build_file_mapping(site: dict) -> dict:
    """Build output_files and cache_files mappings from a site config entry."""
    org_key = site["org_key"]
    pages = site.get("pages", [])

    output_files = {}
    cache_files = {}

    for page in pages:
        safe_name = _sanitize(page)
        cache_files[page] = f"{org_key}_{safe_name}.html"
        output_files[page] = f"{org_key}_{safe_name}.json"

    # Include any extra_outputs (e.g., github's trending_combined)
    extra = site.get("extra_outputs", {})
    if extra:
        output_files.update(extra)

    return {
        "output_files": output_files,
        "cache_files": cache_files,
    }
