"""Fetch Hugging Face trending models, datasets, and daily papers."""

import asyncio
import hashlib
import logging
from datetime import datetime, timedelta, timezone

from curl_cffi.requests import AsyncSession

from utils import (
    FEEDS_DIR, setup_logging, ensure_output_dir,
    load_feeds_config, fetch_with_retry, write_atom_feed,
)

setup_logging()
ensure_output_dir()
ORG_KEY = "huggingface"


def _build_trending_item(item_data, item_type):
    repo_data = item_data.get("repoData", {})
    item_id = repo_data.get("id", "")
    if not item_id:
        return None
    author = repo_data.get("author", "")
    item_name = item_id.split("/")[-1] if "/" in item_id else item_id
    tags = repo_data.get("tags", [])
    downloads = repo_data.get("downloads", 0)
    likes = repo_data.get("likes", 0)
    created_at = repo_data.get("createdAt", "")
    pipeline_tag = repo_data.get("pipeline_tag", "")
    description_parts = []
    if pipeline_tag: description_parts.append(f"Type: {pipeline_tag}")
    if downloads > 0: description_parts.append(f"Downloads: {downloads:,}")
    if likes > 0: description_parts.append(f"Likes: {likes}")
    if tags: description_parts.append(f"Tags: {', '.join(tags[:3])}")
    summary = " \\u00b7 ".join(description_parts) if description_parts else ""
    return {
        "id": hashlib.md5(f"huggingface_{item_id}".encode()).hexdigest(),
        "source": ORG_KEY, "type": item_type,
        "title": item_id, "description": "<br/>".join(description_parts),
        "summary": summary,
        "url": f"https://huggingface.co/datasets/{item_id}" if item_type == "dataset" else f"https://huggingface.co/{item_id}",
        "published_date": created_at or datetime.now(timezone.utc).isoformat(),
        "categories": [pipeline_tag] if pipeline_tag else [],
        "metadata": {"author": author, "item_name": item_name, "downloads": downloads,
                     "likes": likes, "last_modified": repo_data.get("lastModified", ""),
                     "all_tags": tags},
    }


def _build_paper_entry(raw_item):
    paper_data = raw_item.get("paper", {})
    paper_id = paper_data.get("id", "")
    title = raw_item.get("title", "") or paper_data.get("title", "")
    summary = raw_item.get("summary", "") or paper_data.get("summary", "")
    authors_raw = paper_data.get("authors", [])
    upvotes = paper_data.get("upvotes", 0)
    github_stars = paper_data.get("githubStars", 0)
    github_url = paper_data.get("githubRepo", "")
    project_url = paper_data.get("projectPage", "")
    published_date = raw_item.get("publishedAt", "") or paper_data.get("publishedAt", "") or raw_item.get("fetch_date", "")

    description_parts = []
    if summary: description_parts.append(summary[:200] + "..." if len(summary) > 200 else summary)
    if upvotes > 0: description_parts.append(f"Upvotes: {upvotes}")
    if github_stars > 0: description_parts.append(f"GitHub Stars: {github_stars}")
    author_names = [a["name"] for a in authors_raw if isinstance(a, dict) and a.get("name")]
    if author_names: description_parts.append(f"Authors: {', '.join(author_names[:3])}")
    summary_text = " \\u00b7 ".join(description_parts) if description_parts else ""
    description = "<br/>".join(description_parts)

    primary_url = f"https://arxiv.org/abs/{paper_id}" if paper_id else project_url or github_url or f"https://huggingface.co/papers/{paper_id}"
    additional_links = []
    if github_url and github_url != primary_url: additional_links.append(f'\\U0001f517 <a href="{github_url}">GitHub</a>')
    if project_url and project_url != primary_url: additional_links.append(f'\\U0001f517 <a href="{project_url}">Project Page</a>')
    arxiv_url = f"https://arxiv.org/abs/{paper_id}" if paper_id else ""
    if arxiv_url and arxiv_url != primary_url: additional_links.append(f'\\U0001f517 <a href="{arxiv_url}">ArXiv</a>')
    hf_url = f"https://huggingface.co/papers/{paper_id}"
    if hf_url != primary_url: additional_links.append(f'\\U0001f517 <a href="{hf_url}">Hugging Face</a>')
    if additional_links: description += ("<br/>" if description else "") + "<br/>".join(additional_links)

    return {
        "id": hashlib.md5(f"huggingface_paper_{paper_id}".encode()).hexdigest(),
        "source": ORG_KEY, "type": "paper", "title": title,
        "description": description, "summary": summary_text,
        "url": primary_url,
        "published_date": published_date or datetime.now(timezone.utc).isoformat(),
        "categories": ["research", "paper"],
        "metadata": {"paper_id": paper_id, "upvotes": upvotes, "github_stars": github_stars,
                     "github_url": github_url, "project_url": project_url,
                     "authors": author_names, "summary": summary,
                     "fetch_date": raw_item.get("fetch_date", ""),
                     "num_comments": raw_item.get("numComments", 0)},
    }


async def fetch_trending_items(base_url, page_config):
    endpoint = page_config.get("endpoint", "/trending")
    item_type = page_config.get("item_type", "model")
    limit = page_config.get("limit", 20)
    async with AsyncSession() as session:
        response = await fetch_with_retry(session, f"{base_url}{endpoint}",
                                          params={"type": item_type, "limit": limit},
                                          impersonate="chrome120", timeout=10)
        items_data = response.json().get("recentlyTrending", [])
        items = [entry for item in items_data if (entry := _build_trending_item(item, item_type))]
        logging.info("Fetched %d trending %s items", len(items), item_type)
        return items


async def fetch_daily_papers(base_url):
    async with AsyncSession() as session:
        all_papers = []
        today = datetime.now(timezone.utc)
        dates = [(today - timedelta(days=i)).strftime("%Y-%m-%d")
                 for i in range(1, 31) if (today - timedelta(days=i)).weekday() < 5]
        logging.info("Fetching daily papers for %d days…", len(dates))
        for date in dates:
            try:
                response = await fetch_with_retry(session, f"{base_url}/daily_papers",
                                                  params={"date": date},
                                                  impersonate="chrome120", timeout=10, max_retries=2)
                papers = response.json()
                for p in papers: p["fetch_date"] = date
                all_papers.extend(papers)
            except Exception as exc:
                logging.warning("Failed to fetch papers for %s: %s", date, exc)
                continue
        if not all_papers: return []
        by_upvotes = sorted(all_papers, key=lambda x: x.get("paper", {}).get("upvotes", 0), reverse=True)[:6]
        by_stars = sorted(all_papers, key=lambda x: x.get("paper", {}).get("githubStars", 0), reverse=True)[:6]
        seen = set(); deduped = []
        for item in by_upvotes + by_stars:
            pid = item.get("paper", {}).get("id") or item.get("title", "")
            if pid and pid not in seen: seen.add(pid); deduped.append(item)
        return [entry for item in deduped if (entry := _build_paper_entry(item))]


async def main():
    config = load_feeds_config(ORG_KEY)
    favicon = config.get("favicon")
    base_url = config["base_url"]

    for page_key, page in config["pages"].items():
        logging.info("Fetching %s…", page["label"])
        if page_key == "daily_papers":
            entries = await fetch_daily_papers(base_url)
        else:
            page["item_type"] = "model" if page_key == "trending_models" else "dataset"
            page["endpoint"] = "/trending"
            page["limit"] = 20
            entries = await fetch_trending_items(base_url, page)

        if entries:
            write_atom_feed(FEEDS_DIR / page["output_file"], entries,
                            feed_title=page["label"],
                            feed_link=page.get("feed_link", page["url"]),
                            feed_icon=favicon)


if __name__ == "__main__":
    asyncio.run(main())
