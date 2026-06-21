"""Crawl Tencent AI Studio news/blog page (SPA, inject React fiber IDs)."""

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
ORG_KEY = "hunyuan_news"
BASE_URL = "https://aistudio.tencent.com"


def parse_date(date_str):
    if not date_str:
        return None
    date_str = date_str.strip()
    for fmt in ("%Y-%m-%d", "%Y/%m/%d", "%Y年%m月%d日", "%Y. %m. %d", "%Y.%m.%d", "%b %d, %Y", "%B %d, %Y", "%b. %d, %Y"):
        try:
            return datetime.strptime(date_str.strip(), fmt).replace(tzinfo=timezone.utc).isoformat()
        except ValueError:
            continue
    return None


def _inject_article_ids(page: ChromiumPage):
    return page.run_js("""
        const items = document.querySelectorAll('.blog-list__item');
        let injected = 0;
        let articleUrlMap = {};
        const listWrapper = document.querySelector('.blog-list, .blog-list-wrapper');
        if (listWrapper) {
            for (const key in listWrapper) {
                if (key.startsWith('__reactFiber')) {
                    let f = listWrapper[key]; let depth = 0;
                    while (f && depth < 30) {
                        let state = f.memoizedState;
                        while (state) {
                            if (state.queue && state.queue.lastRenderedState) {
                                const st = state.queue.lastRenderedState;
                                if (Array.isArray(st)) {
                                    for (const item of st) {
                                        if (item && (item.url || item.link)) articleUrlMap[item.id] = item.url || item.link;
                                    }
                                }
                            }
                            state = state.next;
                        }
                        f = f.return; depth++;
                    }
                }
            }
        }
        items.forEach(item => {
            let articleId = null;
            for (const key in item) {
                if (key.startsWith('__reactFiber')) {
                    let f = item[key]; let depth = 0;
                    while (f && depth < 20) {
                        const fid = f.key;
                        if (fid !== null && fid !== undefined && (typeof fid === 'number' || /^\\d+$/.test(String(fid)))) {
                            articleId = String(fid);
                            item.setAttribute('data-article-id', articleId); injected++;
                            if (articleUrlMap[articleId]) item.setAttribute('data-article-url', articleUrlMap[articleId]);
                            break;
                        }
                        const mp = f.memoizedProps || {};
                        if (mp.id && !articleId) { articleId = String(mp.id); item.setAttribute('data-article-id', articleId); injected++; }
                        if (mp.url && !item.getAttribute('data-article-url')) item.setAttribute('data-article-url', String(mp.url));
                        f = f.return; depth++;
                    }
                }
            }
            if (articleId && !item.getAttribute('data-article-url') && articleUrlMap[articleId]) item.setAttribute('data-article-url', articleUrlMap[articleId]);
        });
        return injected;
    """)


def _fetch_aistudio(page: ChromiumPage, url: str):
    logging.info("Navigating to %s", url)
    page.get(url)
    page.wait.doc_loaded()
    deadline = time.time() + 15
    while time.time() < deadline:
        try:
            cards = page.eles(".blog-list__item")
            if len(cards) >= 1:
                logging.info("AI Studio content rendered (%d blog items)", len(cards))
                break
        except Exception:
            pass
        page.wait(0.5)
    page.wait(5)
    _inject_article_ids(page)
    return page.html


def extract_items(soup):
    items = []
    seen = set()
    for card in soup.select("div.blog-list__item"):
        title_el = card.select_one("div.blog-list__item-right-title")
        if not title_el:
            continue
        title = title_el.get_text(strip=True)
        if not title or len(title) < 3 or title.lower().strip() in seen:
            continue
        seen.add(title.lower().strip())
        date_el = card.select_one("div.blog-list__item-left-time")
        pub = parse_date(date_el.get_text(strip=True)) if date_el else None
        desc_el = card.select_one("div.blog-list__item-right-desc")
        summary = desc_el.get_text(strip=True) if desc_el else ""
        cat_el = card.select_one("div.blog-list__item-left-tag")
        eng_cat = cat_el.get_text(strip=True) if cat_el else ""
        tags = [t.get_text(strip=True) for t in card.select("div.blog-list__item-right-tag") if t.get_text(strip=True)]
        cats = [eng_cat] + tags if eng_cat else tags
        article_url = card.get("data-article-url")
        if article_url:
            url = article_url
        else:
            slug = re.sub(r"[^\w\-\u4e00-\u9fff]+", "", re.sub(r"\s+", "-", title).strip("-"))
            url = f"{BASE_URL}/news/blog/{quote(slug, safe='-')}"
        pub = pub or datetime.now(timezone.utc).isoformat()
        item_id = hashlib.md5(f"tencent_hunyuan_news_{title}".encode()).hexdigest()
        items.append(compact({
            "id": item_id, "source": "tencent_hunyuan_news", "type": "news",
            "title": title, "url": url, "summary": summary[:800],
            "published_date": pub, "categories": cats if cats else None,
            "organization": "Tencent Hunyuan",
        }))
    return items


def run(page: ChromiumPage):
    config = load_feeds_config(ORG_KEY)
    p = config["pages"]["news"]
    html = _fetch_aistudio(page, p["url"])
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
