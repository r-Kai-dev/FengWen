"""Crawl Tencent Hunyuan research page (switch to Chinese, inject React fiber IDs)."""

import hashlib
import json
import logging
import re
import time
from datetime import datetime, timezone
from urllib.parse import quote

from bs4 import BeautifulSoup
from DrissionPage import ChromiumPage

from utils import (
    FEEDS_DIR, setup_logging, ensure_output_dir,
    load_feeds_config, compact, write_atom_feed,
)

setup_logging()
ensure_output_dir()
ORG_KEY = "hunyuan_research"
BASE_URL = "https://hunyuan.tencent.com"


def parse_date(date_str):
    if not date_str:
        return None
    date_str = date_str.strip()
    for fmt in ("%b %d, %Y", "%B %d, %Y", "%Y/%m/%d", "%Y-%m-%d", "%Y年%m月%d日", "%Y.%m.%d"):
        try:
            return datetime.strptime(date_str.strip(), fmt).replace(tzinfo=timezone.utc).isoformat()
        except ValueError:
            continue
    return None


def _inject_article_ids(page: ChromiumPage):
    return page.run_js("""
        const items = document.querySelectorAll('.blog-item');
        let injected = 0;
        items.forEach(item => {
            for (const key in item) {
                if (key.startsWith('__reactFiber')) {
                    let f = item[key]; let depth = 0;
                    while (f && depth < 20) {
                        const fid = f.key;
                        if (fid !== null && fid !== undefined && (typeof fid === 'number' || /^\\d+$/.test(String(fid)))) {
                            item.setAttribute('data-article-id', String(fid)); injected++; break;
                        }
                        f = f.return; depth++;
                    }
                }
            }
        });
        return injected;
    """)


def _fetch_hunyuan(page: ChromiumPage, url: str):
    logging.info("Navigating to %s", url)
    page.get(url)
    page.wait.doc_loaded()
    deadline = time.time() + 15
    while time.time() < deadline:
        try:
            skel = page.ele("#app-skeleton", timeout=1)
            skel_cls = (skel.attr("class") or "") if skel else ""
            hidden = "hidden" in skel_cls.split()
        except Exception:
            hidden = True
        try:
            cards = page.eles(".blog-item")
            has_content = len(cards) >= 1
        except Exception:
            has_content = False
        if hidden and has_content:
            logging.info("Hunyuan content rendered (%d blog items)", len(cards))
            break
        page.wait(0.5)
    page.wait(3)

    logging.info("Switching to Chinese…")
    page.run_js("""
        const items = document.querySelectorAll('.header__lang-switch-text-item');
        for (const item of items) { if (item.textContent.trim() === '\\u4e2d\\u6587') { item.click(); break; } }
    """)
    page.wait(5)
    _inject_article_ids(page)
    return page.html


def extract_items(soup):
    items = []
    seen = set()
    for card in soup.select("div.blog-item"):
        title_el = card.select_one("h2.blog-title")
        if not title_el:
            continue
        title = title_el.get_text(strip=True)
        if not title or len(title) < 3 or title.lower().strip() in seen:
            continue
        seen.add(title.lower().strip())
        date_el = card.select_one("span.blog-item-date")
        pub = parse_date(date_el.get_text(strip=True)) if date_el else None
        desc_el = card.select_one("p.blog-desc")
        summary = desc_el.get_text(strip=True) if desc_el else ""
        authors = [a.get_text(strip=True) for a in card.select("span.blog-item-author-item") if a.get_text(strip=True)]
        article_id = card.get("data-article-id")
        if article_id:
            url = f"{BASE_URL}/research/{article_id}"
        else:
            slug = re.sub(r"[^\w\-\u4e00-\u9fff]+", "", re.sub(r"\s+", "-", title).strip("-"))
            url = f"{BASE_URL}/research/{quote(slug, safe='-')}"
        pub = pub or datetime.now(timezone.utc).isoformat()
        item_id = hashlib.md5(f"tencent_hunyuan_research_{title}".encode()).hexdigest()
        items.append(compact({
            "id": item_id, "source": "tencent_hunyuan_research", "type": "research",
            "title": title, "url": url, "summary": summary[:800],
            "published_date": pub, "categories": authors if authors else None,
            "organization": "Tencent Hunyuan",
        }))
    return items


def run(page: ChromiumPage):
    config = load_feeds_config(ORG_KEY)
    p = config["pages"]["research"]
    html = _fetch_hunyuan(page, p["url"])
    soup = BeautifulSoup(html, "html.parser")
    entries = extract_items(soup)
    if not entries:
        logging.warning("No entries found")
        return
    entries = [json.loads(s) for s in {json.dumps(d) for d in entries}]
    entries.sort(key=lambda x: x.get("published_date", ""), reverse=True)
    write_atom_feed(FEEDS_DIR / p["output_file"], entries,
                    feed_title=p["label"], feed_link=p["url"],
                    feed_icon=config.get("favicon"))

if __name__ == "__main__":
    from DrissionPage import ChromiumOptions
    co = ChromiumOptions()
    co.set_browser_path("/usr/bin/chromium")
    co.headless(on_off=True); co.new_env(on_off=True)
    co.set_argument("--no-sandbox"); co.set_argument("--disable-gpu")
    pg = ChromiumPage(addr_or_opts=co)
    try: run(pg)
    finally: pg.quit()
