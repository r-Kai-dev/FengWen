# Feng Wen (风闻)

Feng Wen (风闻) is a news aggregator focused on AI and technology. It periodically scrapes official blogs, release notes, trending repositories, and research publications from major AI companies and platforms, then converts them into standard **Atom/RSS XML feeds** so they can be consumed by any feed reader directly.

## How It Works

The project runs a **three-phase data pipeline**:

1. **Fetch** (`src/fetch/`) — Downloads HTML from target sites.
   - `fetch_html.py` — Uses `curl_cffi` (async HTTP with TLS fingerprint impersonation) to fetch plain HTML pages from ~10 sources (Anthropic, Meta, KIMI, Moonshot, etc.). 15–20 URLs total.
   - `fetch_js.py` — Uses **DrissionPage** + headless Chromium to render JavaScript-heavy pages (ByteDance, DeepSeek, Qwen) that require browser execution. 3–4 URLs total.
2. **Request** (`src/request/`) — Fetches data from public REST APIs.
   - `request_hackernews.py` — Fetches Hacker News best stories via Firebase API.
   - `request_huggingface.py` — Fetches Hugging Face trending models, datasets, and daily papers.
3. **Parse** (`src/parse/`) — Reads cached HTML / API responses with BeautifulSoup and produces Atom XML feeds (saved under `feeds/`).

The full pipeline is orchestrated by `src/run_all.sh`, which runs the three phases sequentially. Each script logs to `logs/` for observability.

## Codeberg CI Usage

We plan to use Codeberg CI to automate feed generation so that the raw XML files at `feeds/*.xml` are always up-to-date and linkable from feed readers.

### CI Pipeline

**Pipeline A — HTML + JS scrape feeds** (fetch + parse)
- Triggers: **2 times per day** (e.g., 06:00 and 18:00 UTC)
- Steps:
  1. `python3 src/fetch/fetch_html.py` — async HTTP fetches (~15 URLs, 5 concurrent)
  2. `python3 src/fetch/fetch_js.py` — DrissionPage + headless Chromium (~3 pages)
  3. `python3 src/parse/parse_*.py` — 13 parse scripts, each reads cached HTML and writes an XML feed

**Pipeline B — API-based feeds** (request + parse)
- Triggers: **1 time per day** (e.g., 06:00 UTC)
- Steps:
  1. `python3 src/request/request_hackernews.py` — single HTTP API call
  2. `python3 src/request/request_huggingface.py` — 3 HTTP API calls

After both pipelines complete, the generated `feeds/*.xml` files would be committed back to the repository (or deployed to a static hosting branch).

### Expected Resource Usage

| Resource | Pipeline A (HTML+JS) | Pipeline B (API) |
|----------|----------------------|------------------|
| **RAM**  | ~500–800 MB (peak during DrissionPage Chromium launch) | < 128 MB |
| **CPU**  | 1 (scripts are single-threaded; async I/O is non-blocking) | 1 |
| **Runtime** | ~1–2 minutes total | ~10–30 seconds |
| **Disk (transient)** | ~2 MB cache (text-only pruned HTML) | None |
| **Network** | ~15–20 small HTTP requests (~100 KB–1 MB each) | ~4 small API calls |

The **DrissionPage** browser is the most resource-intensive component, but it runs headless with `--no-sandbox --disable-gpu --disable-dev-shm-usage`, launches only once, navigates 3–4 pages sequentially, and exits. Peak memory is well under 1 GB.

**Overall classification: minimal** (< 1 GB RAM, 1 CPU, < 2 minutes of runtime per run).

### Committed Files

The repository already contains:
- `config/html.json` — site list for plain-HTML fetchers
- `config/js.json` — site list for JS-rendered fetchers
- `config/api.json` — API endpoint configuration
- `src/` — all Python scripts
- `feeds/` — generated XML feeds (stale without CI automation)
- `html_cache/` — cached/pruned HTML (stale without CI automation)

### Dependencies

- Python ≥ 3.12
- `curl_cffi` — async HTTP with TLS fingerprint impersonation
- `beautifulsoup4` — HTML parsing / XML generation
- `DrissionPage` — headless Chromium automation for JS-rendered pages
- Chromium (or Chrome) installed on the CI runner for DrissionPage

All Python dependencies are declared in `pyproject.toml`.