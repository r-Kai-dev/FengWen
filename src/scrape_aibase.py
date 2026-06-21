"""Scrape AIbase daily news page."""

import hashlib
import json
import logging
import re
from datetime import datetime, timedelta, timezone

from bs4 import BeautifulSoup

from utils import (
    FEEDS_DIR, setup_logging, ensure_output_dir,
    load_feeds_config, fetch_page, compact, write_atom_feed,
)

setup_logging()
ensure_output_dir()
ORG_KEY = "aibase"


def parse_relative_time(time_str):
    if not time_str:
        return None
    time_str = time_str.strip()
    if "刚刚" in time_str:
        return datetime.now(timezone.utc).isoformat()
    m = re.search(r"(\d+)\s*分钟前", time_str)
    if m:
        return (datetime.now(timezone.utc) - timedelta(minutes=int(m.group(1)))).isoformat()
    m = re.search(r"(\d+)\s*小时前", time_str)
    if m:
        return (datetime.now(timezone.utc) - timedelta(hours=int(m.group(1)))).isoformat()
    m = re.search(r"(\d+)\s*天前", time_str)
    if m:
        return (datetime.now(timezone.utc) - timedelta(days=int(m.group(1)))).isoformat()
    if "前天" in time_str:
        return (datetime.now(timezone.utc) - timedelta(days=2)).isoformat()
    if "昨天" in time_str:
        return (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
    m = re.match(r"(\d{2})-(\d{2})", time_str)
    if m:
        try:
            return datetime(datetime.now().year, int(m.group(1)), int(m.group(2)), tzinfo=timezone.utc).isoformat()
        except ValueError:
            pass
    try:
        return datetime.strptime(time_str, "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc).isoformat()
    except ValueError:
        pass
    return None


def extract_articles(soup, raw_html):
    articles = []
    for link in soup.find_all("a", href=re.compile(r"/zh/daily/\d+")):
        href = link.get("href", "")
        oid_match = re.search(r"/zh/daily/(\d+)", href)
        oid = oid_match.group(1) if oid_match else ""
        url = f"https://news.aibase.com{href}" if href.startswith("/") else href

        title_div = link.find("div", class_=lambda x: x and "font600" in x and "mainColor" in x)
        if not title_div:
            title_div = link.find("div", class_=re.compile(r"font600.*truncate2|truncate2.*font600"))
        if not title_div:
            continue
        title = title_div.get_text(strip=True)
        if not title:
            continue

        desc_div = link.find("div", class_=lambda x: x and "tipColor" in x and "truncate2" in x)
        description = desc_div.get_text(strip=True) if desc_div else ""
        if "欢迎来到【AI日报】栏目!" in description:
            parts = description.split("新鲜AI产品点击了解：https://app.aibase.com/zh")
            description = parts[1].strip() if len(parts) > 1 else description

        pub = None
        if oid:
            m = re.search(f'"oid":{oid}.*?"createTime":"([^"]+)"', raw_html)
            if m:
                try:
                    pub = datetime.strptime(m.group(1), "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc).isoformat()
                except ValueError:
                    pass
        if not pub:
            date_icon = link.find("i", class_=lambda x: x and "icon-rili" in str(x))
            if date_icon:
                date_div = date_icon.find_parent("div")
                if date_div:
                    pub = parse_relative_time(date_div.get_text(strip=True))
        if not pub:
            pub = datetime.now(timezone.utc).isoformat()

        item_id = hashlib.md5(f"aibase_{title}_{url}".encode()).hexdigest()
        articles.append(compact({
            "id": item_id, "source": "aibase", "type": "daily_news",
            "title": title, "url": url, "summary": description,
            "published_date": pub, "categories": ["AI Daily", "人工智能"],
            "organization": "AIBase",
        }))
    return articles


def main():
    config = load_feeds_config(ORG_KEY)
    page = config["pages"]["daily"]
    logging.info("Fetching %s: %s", page["label"], page["url"])
    html = fetch_page(page["url"])
    soup = BeautifulSoup(html, "html.parser")
    entries = extract_articles(soup, html)
    if not entries:
        logging.warning("No entries found")
        return
    entries = [json.loads(s) for s in {json.dumps(d) for d in entries}]
    entries.sort(key=lambda x: x.get("published_date", ""), reverse=True)
    write_atom_feed(FEEDS_DIR / page["output_file"], entries,
                    feed_title=page["label"], feed_link=page["url"],
                    feed_icon=config.get("favicon"))

if __name__ == "__main__":
    main()
