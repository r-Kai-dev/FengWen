# Failure Pattern Catalog

Known ways feed generators silently break, their signatures, and how to
diagnose them.

## Zero Entries (P1)

**Signature:** `"zero_entries"` in `_audit.json`.  Script runs, produces
valid XML, but zero `<entry>` elements.

**Common causes:**

| Cause | Diagnosis | Fix |
|-------|-----------|-----|
| CSS selectors broke | Fetch page, run script's selectors — they return nothing.  Site was redesigned. | Update selectors in the script to match new DOM structure |
| Content moved to new URL | Script fetches old URL, gets 200 but different page (landing page, redirect, blank) | Update `url` in `config/feeds.json` |
| Content switched to JS rendering | Page now requires JavaScript.  `view-source:` shows empty shell. | Switch from `scrape` to `crawl` strategy |
| Bot protection | `fetch_page()` returns captcha/403 page instead of content | Try different impersonation, or switch to crawl |
| API endpoint changed | Request script gets 404 or different JSON structure | Update endpoint URL or response parsing |

**Investigation steps:**
1. Fetch the page with `fetch_page()` and dump to file
2. Run the script's selectors manually: `soup.select("the.selector")`
3. Check `view-source:URL` in browser vs rendered page
4. Check browser DevTools Network tab for new API endpoints

## All Same Date (P1)

**Signature:** `"all_same_date"` in `_audit.json`.  Every entry has today's
date (age_days == 0).

**Common causes:**

| Cause | Diagnosis | Fix |
|-------|-----------|------|
| Date parsing failed | All entries fell back to `datetime.now()`.  Script's `strptime` format no longer matches page dates. | Update date format in script |
| Date element missing | Page no longer shows dates, or dates are in a new location | Update selector for date elements |
| Dates in JS, not HTML | Dates are injected by JavaScript, invisible to BeautifulSoup | Switch to crawl strategy or extract from JS payloads |

**Investigation steps:**
1. Check the page for actual date strings — have they changed format?
2. Look at the script's date parsing logic — what `strptime` format does it use?
3. If dates are in Next.js `__NEXT_DATA__` or similar payloads, extract from there

## Staleness (P2)

**Signature:** `"stale_Nd"` in `_audit.json`.  Newest entry is N days old.
May be legitimate (site is dormant) or a bug.

**Thresholds by category:**
- Hourly feeds: > 3 days is stale
- Daily feeds: > 7 days is stale
- Weekly feeds: > 14 days is stale
- Everything else: > 30 days is stale

**When staleness is legitimate:**
- The site simply hasn't published — check their blog/news page manually
- Academic paper feeds — papers are published in batches
- Release notes — only updated with new releases

**When staleness indicates a bug:**
- Page shows NEW articles that the feed doesn't have → selector broken for new content
- Feed has old articles but page has new ones → pagination/lazy-loading changed
- Multiple feeds from same site all went stale simultaneously → site restructured

**Investigation steps:**
1. Browse the live page — are there newer articles than the feed's newest?
2. If yes: check if new articles use different markup (A/B test, section redesign)
3. If no: mark as "legitimate dormancy" in the report

## XML Missing (P0)

**Signature:** `"xml_missing"` in `_audit.json`.  Expected output file not
found in `feeds/`.

**Common causes:**
- Script crashed with an unhandled exception (check CI logs)
- Script was deleted but config entry remains
- Output file path changed in config but old file still expected

**Investigation:** Run the script directly and observe the error.

## XML Parse Error (P0)

**Signature:** `"xml_parse_error"` in `_audit.json`.  File exists but isn't
valid XML.

**Common causes:**
- Script wrote error HTML/traceback instead of XML (e.g., a 502 error page)
- XML namespace issues
- Encoding problems

**Investigation:** Read the file directly — it likely contains a stack trace
or error page rather than XML.

## URL Migration (Silent)

**Signature:** No entries, or stale entries, but the script returns 200.
The old URL serves a redirect page, empty page, or unrelated content.

**Investigation:**
1. `curl -I OLD_URL` — check for 301/302 redirect
2. Browse the old URL in a browser — is there a "we've moved" notice?
3. Search for the organization's new blog URL

**Fix:** Update `url` in `config/feeds.json`, update selectors if the new
site has different markup.

## Bot Protection Escalation (Silent)

**Signature:** Feed has entries but they're wrong/empty/garbled, or entry
count suddenly dropped to near-zero when it was previously healthy.

**Investigation:**
1. `fetch_page(url)` and inspect the returned HTML — is it a captcha?
2. Try different `impersonate` values (chrome120, chrome110, edge101)
3. Check if the site now uses Cloudflare Turnstile or similar

**Fix:** Escalate to `crawl` strategy (DrissionPage uses real Chromium).

## Partial Extraction (Low Signal)

**Signature:** Feed has entries but they lack summaries, content, or dates.
Only detectable by examining the XML directly — `_audit.json` doesn't flag
this yet.

**Investigation:** Manually read a few entries from the XML.  Are summaries
empty?  Dates missing?  This suggests the page structure partially changed.
