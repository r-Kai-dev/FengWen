"""Shared utility to load site configuration from html.json/js.json.

Derives cache/output filenames from org_key + pages.
"""

import json
import logging
import re
import sys
from pathlib import Path

# Ensure src/ is on sys.path so feed_util is importable from any invocation context
_src_dir = str(Path(__file__).resolve().parent.parent)
if _src_dir not in sys.path:
    sys.path.insert(0, _src_dir)

from feed_util import compact, write_atom_feed  # noqa: F401

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
      - output_files: {page_name: output_xml_filename, ...}
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


def _build_file_mapping(site: dict) -> dict:
    """Build output_files and cache_files mappings from a site config entry."""
    org_key = site["org_key"]
    pages = site.get("pages", [])

    output_files = {}
    cache_files = {}

    for page in pages:
        safe_name = _sanitize(page)
        cache_files[page] = f"{org_key}_{safe_name}.html"
        output_files[page] = f"{org_key}_{safe_name}.xml"

    # Include any extra_outputs (e.g., github's trending_combined)
    extra = site.get("extra_outputs", {})
    if extra:
        output_files.update(extra)

    return {
        "output_files": output_files,
        "cache_files": cache_files,
        "favicon": site.get("favicon"),
        "url": site.get("url", ""),
    }
