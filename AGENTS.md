# Feng Wen (风闻) — Agent Guide

## Overview

Feng Wen scrapes AI/tech sources and converts them to Atom RSS feeds into `feeds/*.xml`. The pipeline orchestrator is `src/run_all.sh`.

**Your job**: add new feed sources by following established patterns.

## Pipeline

Three phases — see `src/run_all.sh` for orchestration order:

| Phase | Directory | Pattern | Output |
|-------|-----------|---------|--------|
| Fetch | `src/fetch/` | Download + prune HTML pages → `html_cache/*.html` | Cache |
| Request | `src/request/` | Self-contained fetch+parse (APIs / RSC payloads) | `feeds/*.xml` |
| Parse | `src/parse/` | Read cached HTML → produce feeds | `feeds/*.xml` |

- Phases 1 & 2 are independent. Phase 3 depends on Phase 1.
- Each directory's `run.sh` auto-discovers scripts via glob — no manual registration needed.
- Each script logs to `logs/{script_name}.log`.

## Adding a New Source

### 1. Determine the pattern

Check the target page's view-source:

- **Data in visible DOM elements** → HTML pattern (`fetch_html.py` + `parse_*.py`). Add to `config/html.json`.
- **Data only appears after JavaScript execution** → JS pattern (`fetch_js.py` + `parse_*.py`). Add to `config/js.json`.
- **Data in `self.__next_f.push()` RSC payloads** → RSC pattern (`request_*.py`). Add to `config/api.json`.
- **Data served via a JSON API** → API pattern (`request_*.py`). Add to `config/api.json`.

The `request/` pipeline is now the catch-all for self-contained fetch+parse (any source that doesn't fit the separate-fetch-then-parse model).

### 2. Create the script

Use the existing scripts in the relevant directory as reference. Keep `org_key` consistent between the config entry and the filename (`request_{org_key}.py` or `parse_{org_key}.py`).

### 3. Use the shared utilities

| Utility | Module | Purpose |
|---------|--------|---------|
| `load_site_config(org_key, config_name)` | `src/parse/config_util.py` | Read HTML/JS config, get cache & output filenames |
| `load_api_config(org_key)` | `src/request/common.py` | Read API config |
| `write_atom_feed(path, entries, title, link, icon)` | `src/feed_util.py` | Write Atom XML |
| `compact(dict)` | `src/feed_util.py` | Strip falsy values from entry dict |

Read those files for exact signatures and the expected entry dict schema.

### 4. Update `README.md`

Add the new feed row(s) to the appropriate table. Follow the existing row format: `| [Name](URL) | [filename.xml](feed URL) | Created |`

### 5. Test

```bash
cd /workspace/src && bash run_all.sh
```

Check `feeds/` for the output file and verify it contains valid XML with entries.

## Config File Reference

The canonical schemas live in the config files themselves:
- `config/html.json` — sites for `fetch_html.py`
- `config/js.json` — sites for `fetch_js.py`
- `config/api.json` — sites for `request_*.py`

Read the relevant file to understand the required fields before editing.

## Edge Cases

- **RSC extraction**: decode chunks with `chunk.encode("utf-8").decode("unicode_escape", errors="replace")`. Use bracket-depth matching for JSON arrays if the data is embedded.
- **`fetch_html.py` prunes `<script>` and `<style>` tags**. If content depends on those (e.g., RSC payloads or JSON-LD), use the request pattern instead.
- **All `run.sh` scripts use `shopt -s nullglob`** — no need to register new scripts manually.
