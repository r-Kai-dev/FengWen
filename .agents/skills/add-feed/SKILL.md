---
name: add-feed
description: >
  Adds or removes a feed from the Feng Wen (风闻) project. Covers the full
  decision tree — official feed, enhance, scrape, request, or crawl — plus
  config entry creation, script boilerplate, regeneration, and testing. Use
  when asked to add, remove, or set up a new feed source.
---

# Add Feed

For the Feng Wen (风闻) project at `/workspace`. Walks through adding a new
feed source or removing an existing one.

## Decision Flow

Always work from simplest to most complex:

```
Official feed exists & works?  ──→  Add to "official" array in config
    ↓ no / has issues
Official feed exists but broken?  ──→  enhance_*.py (fix and republish)
    ↓ no
Content in initial HTML?  ──→  scrape_*.py or request_*.py (lightweight HTTP)
    ↓ no (requires JS)
Last resort  ──→  crawl_*.py (Playwright, shared browser)
```

## Adding a Feed

### Step 0 — Check for existing feeds

Before building a pipeline, check whether the site already publishes an RSS or
Atom feed:

- **Feed autodiscovery** `<link>` tags: look for
  `<link rel="alternate" type="application/rss+xml" ...>` or
  `application/atom+xml` in the page source.
- **Common URL patterns**: `/rss.xml`, `/feed.xml`, `/atom.xml`, `/rss`,
  `/feed`, `/news/rss`, `/blog/rss`, `/index.xml`.
- **Platform conventions**: WordPress (`/feed/`), Ghost (`/rss/`),
  Medium (`/feed/`), Substack (`/feed`), Hugo (`/index.xml`).
- **API-based feeds**: Check the Network tab for JSON endpoints that mirror
  feed data.

**If the official feed is correct** (valid URLs, complete dates, reasonable
  summaries), add it to the `"official"` array in `config/feeds.json` — no
  pipeline script needed:

```json
{
  "name": "Site Name",
  "xmlUrl": "https://example.com/feed.xml",
  "htmlUrl": "https://example.com/blog",
  "category": "Blogs"
}
```

**If the official feed has fixable issues** (broken URLs, missing fields, bad
dates), use the `enhance` strategy below.

**If no official feed exists**, proceed to Step 1.

### Step 1 — Determine the strategy

Check the target page in browser DevTools (Network tab), in priority order:

| Priority | Strategy | When to use | Script prefix |
|----------|----------|-------------|---------------|
| 1 (simplest) | `enhance` | Official feed exists but has fixable issues | `enhance_*.py` |
| 2 | `scrape` | Content is in the initial HTML (view-source shows data) | `scrape_*.py` |
| 2 | `request` | Data comes from JSON API / RSC payloads | `request_*.py` |
| 3 (last resort) | `crawl` | Content requires JavaScript execution (SPA, lazy-loaded) | `crawl_*.py` |

### Step 2 — Add the config entry

Add to `config/feeds.json` under `"created"`. Choose `org_key` to match the
script filename you'll create (e.g., `scrape_example.py` → `"example"`):

```json
{
  "org_key": "example",
  "name": "Example Corp",
  "strategy": "scrape",
  "base_url": "https://example.com",
  "favicon": "https://example.com/favicon.ico",
  "category": "Labs",
  "pages": [
    {
      "key": "blog",
      "label": "Example Blog",
      "url": "https://example.com/blog",
      "output_file": "example_blog.xml"
    }
  ]
}
```

**Categories** used in the project — choose the best fit and confirm with the user:

`Labs`, `Platforms`, `Tools`, `Academics`, `Blogs`, `Daily`, `Weekly`,
`Hourly`, `Eval`, `Quantum`

**Multiple pages on the same domain** get multiple entries under one `pages`
array, handled by one script routing on `page_key`. If pages need different
strategies, create separate config entries.

### Step 3 — Create the script

Use an existing script of the same strategy as reference, or copy from the
boilerplate templates in `references/`:

| Strategy | Boilerplate |
|----------|-------------|
| scrape | [boilerplate-scrape.md](references/boilerplate-scrape.md) |
| request | [boilerplate-request.md](references/boilerplate-request.md) |
| enhance | [boilerplate-enhance.md](references/boilerplate-enhance.md) |
| crawl | [boilerplate-crawl.md](references/boilerplate-crawl.md) |

Key rules:
- `ORG_KEY` must match the config `org_key` exactly.
- Use `hashlib.md5(f"{ORG_KEY}_{slug}_{title}".encode()).hexdigest()` for IDs.
- Sort entries by `published_date` descending before writing.
- Crawl scripts expose `def run(page)`, all others use `def main()`.

### Step 4 — Regenerate OPML and README

```bash
cd /workspace && python src/generate_all.py
```

### Step 5 — Test

```bash
cd /workspace/src && bash run_all.sh
```

Verify `feeds/{output_file}` contains valid Atom XML with entries.

## Removing a Feed

1. Remove the entry from `config/feeds.json`
2. Delete the script file in `src/`
3. Delete the output XML in `feeds/` (optional; stale files won't break anything)
4. Run `python src/generate_all.py`
