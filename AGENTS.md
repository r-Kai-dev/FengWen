# Feng Wen (风闻) — Agent Guide

## Overview

Feng Wen scrapes AI/tech sources and converts them to Atom RSS feeds into
`feeds/*.xml`. The pipeline orchestrator is `src/run_all.sh`.

For adding or removing a feed, use the **add-feed** skill — it walks through
the decision tree, strategy selection, boilerplate, and testing. This document
covers project architecture, conventions, and reference material.

## Project Structure

```
config/feeds.json   ← Canonical source of truth (all feeds, all metadata)
src/                ← All scripts (flat, no subdirectories)
  utils.py          ← Shared utilities (config loading, fetching, Atom writing)
  run_all.sh        ← Pipeline orchestrator
  crawl_runner.py   ← Single-browser runner for crawl_*.py scripts
  scrape_*.py       ← HTTP scraping with curl_cffi
  request_*.py      ← Async API / JSON / RSC fetching
  enhance_*.py      ← Official feed repair
  crawl_*.py        ← Browser-based crawling with Playwright
  generate_*.py     ← Generate feeds.opml, README.md
feeds/              ← Output Atom XML files + _audit.json health report
logs/               ← Per-script log files
```

## Config File (`config/feeds.json`)

Two top-level arrays: `created` (feeds Feng Wen generates) and `official`
(external RSS/Atom feeds passed through as-is).

### `created` — generated feeds

```json
{
  "org_key": "anthropic",
  "name": "Anthropic",
  "strategy": "scrape",
  "base_url": "https://www.anthropic.com",
  "favicon": "https://www.anthropic.com/favicon.ico",
  "category": "Labs",
  "pages": [
    {
      "key": "news",
      "label": "Anthropic News",
      "url": "https://www.anthropic.com/news",
      "output_file": "anthropic_news.xml"
    }
  ]
}
```

| Field | Description |
|-------|-------------|
| `org_key` | Unique key matching the script filename (`scrape_anthropic.py` → `"anthropic"`) |
| `name` | Display name |
| `strategy` | `"scrape"`, `"request"`, `"enhance"`, or `"crawl"` — determines script prefix |
| `base_url` | Root URL (favicon fallback and URL construction) |
| `favicon` | Favicon URL (optional, falls back to `base_url/favicon.ico`) |
| `category` | Grouping label — used directly, alphabetically ordered in OPML/README |
| `pages[].key` | Internal key used for routing in the script |
| `pages[].label` | Human-readable feed title |
| `pages[].url` | Source page URL |
| `pages[].output_file` | Output XML filename in `feeds/` |

Extra page fields used by some request scripts: `limit`, `feed_link`, `endpoint`,
`item_type`. See existing request scripts for usage.

### `official` — external feeds

```json
{
  "name": "OpenAI News",
  "xmlUrl": "https://openai.com/news/rss.xml",
  "htmlUrl": "https://openai.com/news",
  "category": "Labs"
}
```

Official feeds require no script — they appear directly in OPML and README.

## Script Types

Four strategies, each with a distinct pattern. Existing scripts of each type
are the best reference when modifying or creating feeds.

### `scrape_*.py` — HTTP scraping

For content delivered in the initial HTML response. Sync `main()`, uses
`BeautifulSoup` + `fetch_page()` (curl_cffi with `chrome120` impersonation).

Reference: `scrape_anthropic.py`, `scrape_meta.py`, `scrape_github.py`

### `request_*.py` — Async API / JSON / RSC

For JSON APIs, Next.js RSC payloads, or any async I/O source.
`async def main()` + `asyncio.run(main())`, uses `curl_cffi.requests.AsyncSession`
with `fetch_with_retry()`.

Reference: `request_huggingface.py`, `request_ainewsradar.py`, `request_hackernews.py`

### `enhance_*.py` — Official feed repair

For sites with an official RSS/Atom feed that needs targeted fixes (broken URLs,
missing fields, bad formatting). Sync `main()`, fetches the upstream XML via
`fetch_page()`, applies fixes, writes corrected output.

Reference: `enhance_krea.py`

### `crawl_*.py` — Browser-based crawling

For SPAs requiring JavaScript execution. Exposes `def run(page)` — **not**
`main()`. Receives a Playwright `Page` from `crawl_runner.py`, navigates with
`page.goto()` + `page.wait_for_timeout()`, parses `page.content()` with
BeautifulSoup.

Reference: `crawl_deepseek.py`, `crawl_hunyuan.py`, `crawl_unsloth.py`

**Crawler lifecycle:** `crawl_runner.py` launches one shared Playwright browser
instance and passes a `Page` to each crawl script sequentially. Scripts must
**not** close the browser or page. Clear cookies between runs if needed. Each
script includes an `if __name__ == "__main__":` block for standalone testing
with its own browser.

## Shared Utilities (`src/utils.py`)

All scripts import from `utils`. `run_all.sh` sets `PYTHONPATH="$PWD"` so
everything can do `from utils import ...`.

### Functions

| Function | Signature | Purpose |
|----------|-----------|---------|
| `load_feeds_config(org_key)` | `→ dict` | Load `created` entry by `org_key`. Returns entry with `pages` as dict `{key: page}`. Raises `ValueError` if not found. |
| `fetch_page(url, *, impersonate, timeout)` | `→ str` | Sync GET with browser impersonation via curl_cffi (used by scrape/enhance scripts). |
| `fetch_with_retry(session, url, *, max_retries, base_delay, **kwargs)` | `→ response` | Async GET with exponential backoff (3 retries by default). |
| `write_atom_feed(path, entries, feed_title, feed_link, *, feed_author, feed_icon)` | `→ None` | Write Atom XML to `path`. Sorts by `published_date` desc, then `title` asc. |
| `compact(dict)` | `→ dict` | Strip falsy keys (`None`, `""`, `[]`, `{}`). |
| `setup_logging()` | `→ None` | Configure root logger (idempotent). |
| `ensure_output_dir()` | `→ None` | Create `feeds/` if needed. |

### Entry dict schema

```python
{
    "title": str,           # required
    "url": str,             # required (also accepted as "link")
    "id": str,              # optional, falls back to url
    "published_date": str,  # ISO-8601, used for sort ordering only
    "summary": str,         # optional, plain text
    "content": str,         # optional, HTML for <content type="html">
    "categories": [str],    # optional
    "organization": str,    # used as author if feed_author not given
}
```

Dates are used for sorting only — no filtering. Entries without dates get
`datetime.now(timezone.utc)` as fallback.

## Pipeline (`src/run_all.sh`)

Three phases, all launched from `src/` with `PYTHONPATH="$PWD"`:

| Phase | Scripts | Mode |
|-------|---------|------|
| 1 | `scrape_*.py` + `request_*.py` + `enhance_*.py` | **Parallel** with `&` |
| 2 | `crawl_runner.py` → `crawl_*.py` | **Sequential** (shared browser) |
| 3 | `audit_report.py` | Generates `feeds/_audit.json` |

Scripts are auto-discovered via glob — no manual registration needed. Each
script logs to `logs/{script_name}.log`.

## Generators

After modifying `config/feeds.json`, regenerate derived files:

```bash
python src/generate_all.py
```

This runs:
- `generate_opml.py` — writes `feeds.opml`
- `generate_readme.py` — rewrites the `<!-- FEEDS_TABLE_START --> ... <!-- FEEDS_TABLE_END -->` section of `README.md`

Both derive categories alphabetically from the `category` field.

### `feeds.opml` format

```xml
<opml version="2.0" xmlns:fw="https://codeberg.org/r-Kai/FengWen">
  <body>
    <outline text="CategoryName" title="CategoryName">
      <outline text="Feed Title" type="rss" xmlUrl="..." htmlUrl="..." fw:type="created"/>
      <outline text="Feed Title" type="rss" xmlUrl="..." htmlUrl="..." fw:type="official"/>
    </outline>
  </body>
</opml>
```

- `fw:type="created"` — feeds generated by Feng Wen, hosted on Codeberg
- `fw:type="official"` — external RSS/Atom feeds
- Codeberg base: `https://codeberg.org/r-Kai/FengWen/raw/branch/main/feeds`

## Development Conventions

### Same site, multiple pages

When multiple pages live on the same domain, add multiple entries under the
same `pages` array. Handle them in **one script** that iterates over
`config["pages"]` and routes by `page_key`.

Reference: `scrape_anthropic.py` (news + research + engineering),
`scrape_bfl.py` (blog + research).

If pages require **different strategies** (e.g., one scrape, one crawl), they
**cannot** share a config entry — create separate entries.

### Script naming

`{strategy}_{org_key}.py` — the `org_key` must match the config entry exactly.
No subdirectories; everything is flat in `src/`.

### ID generation

Use MD5 with a namespaced prefix to avoid collisions across feeds:

```python
item_id = hashlib.md5(f"{ORG_KEY}_{slug}_{title}".encode()).hexdigest()
```

### Date parsing

Dates come in many formats. Use a flexible `parse_date()` helper that tries
multiple `strptime` formats. Always fall back to
`datetime.now(timezone.utc).isoformat()` when parsing fails.

Common formats used in the codebase:
`"%b %d, %Y"`, `"%B %d, %Y"`, `"%Y-%m-%d"`, `"%Y/%m/%d"`.

### Deduplication

For scripts that might produce duplicate entries across navigations:

```python
entries = [json.loads(s) for s in {json.dumps(d) for d in entries}]
```

### Feed link for API-based feeds

By default `feed_link` is the page's source URL. For feeds generated from API
endpoints, provide a human-browsable `feed_link` in the page config.

### RSC payload decoding

When extracting from Next.js `self.__next_f.push()` chunks:

```python
chunk.encode("utf-8").decode("unicode_escape", errors="replace")
```

Use bracket-depth matching for embedded JSON arrays.

### Cloudflare / bot protection

If `fetch_page()` returns 403 or a captcha page, try different impersonation
values first (`chrome120`, `chrome110`, `edge101`). If that fails, switch to
the crawl strategy (Playwright with real Chromium).

### Import paths

All scripts are flat in `src/`. `run_all.sh` sets `PYTHONPATH="$PWD"` so
`from utils import ...` works from any script. There are no `request/`,
`scrape/`, or `crawl/` subdirectories.

## CI Compatibility (`.woodpecker.yaml`)

The CI pipeline mirrors `run_all.sh` but runs in isolated steps — each installs
only its own dependencies:

| Step | Deps | Scripts |
|------|------|---------|
| `scrape-request` | `curl_cffi`, `beautifulsoup4` | `scrape_*.py`, `request_*.py`, `enhance_*.py` |
| `crawl` | `beautifulsoup4`, `playwright` | `crawl_runner.py` → `crawl_*.py` |
| `audit` | (stdlib only) | `audit_report.py` |

Key constraints:
- `scrape_*.py`, `request_*.py`, `enhance_*.py` use `curl_cffi` for HTTP — no browser needed.
- `crawl_*.py` use Playwright with **bundled** Chromium — no system chromium needed.
- Scripts are auto-discovered via glob — no CI config changes for new/removed scripts.
- The `update-feeds` step commits only `feeds/*.xml` (not `feeds.opml` or `README.md`), so regenerating those is a local-only task.
