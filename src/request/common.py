"""Shared utilities for API-based request scripts."""

import json
import logging
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

# Ensure src/ is on sys.path so feed_util is importable from any invocation context
_src_dir = str(Path(__file__).resolve().parent.parent)
if _src_dir not in sys.path:
    sys.path.insert(0, _src_dir)

from feed_util import write_atom_feed  # noqa: F401

# ── Paths ────────────────────────────────────────────────
PROJECT_DIR = Path(__file__).resolve().parent.parent.parent
PARSED_DIR = PROJECT_DIR / "feeds"
CONFIG_DIR = PROJECT_DIR / "config"


def setup_logging() -> None:
    """Configure logging once (idempotent via basicConfig)."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(levelname)s - %(message)s",
    )


def ensure_output_dir() -> None:
    """Create the output directory if it doesn't exist."""
    PARSED_DIR.mkdir(exist_ok=True)


def load_api_config(org_key: str) -> dict:
    """Load and return the site config matching *org_key* from *config/api.json*.

    Returns a dict with ``base_url`` (str), ``pages`` (dict keyed by page key),
    and ``favicon`` (str or None).
    """
    config_file = CONFIG_DIR / "api.json"
    with open(config_file, "r", encoding="utf-8") as f:
        api_config = json.load(f)

    for site in api_config.get("sites", []):
        if site.get("org_key") == org_key:
            pages = {p["key"]: p for p in site.get("pages", [])}
            return {
                "base_url": site["base_url"],
                "pages": pages,
                "favicon": site.get("favicon"),
            }

    raise ValueError(f"Configuration for '{org_key}' not found in config/api.json")


async def fetch_with_retry(
    session,
    url: str,
    *,
    max_retries: int = 3,
    base_delay: float = 1.0,
    **kwargs,
):
    """GET *url* with exponential-backoff retries.

    *kwargs* are forwarded to ``session.get()`` (e.g. ``impersonate``, ``timeout``,
    ``params``).
    """
    last_exception = None
    for attempt in range(max_retries):
        try:
            response = await session.get(url, **kwargs)
            response.raise_for_status()
            return response
        except Exception as exc:
            last_exception = exc
            if attempt < max_retries - 1:
                wait = base_delay * (2**attempt)
                logging.warning(
                    "Request to %s failed (attempt %d/%d): %s. Retrying in %.1fs \u2026",
                    url,
                    attempt + 1,
                    max_retries,
                    exc,
                    wait,
                )
                time.sleep(wait)  # blocking sleep is fine for sequential scrapes
    raise last_exception  # type: ignore[misc]
