"""Fetch Hugging Face trending models, datasets, and daily papers."""

import asyncio
import hashlib
import json
import logging
from datetime import datetime, timedelta, timezone

from curl_cffi.requests import AsyncSession

from common import (
    PARSED_DIR,
    fetch_with_retry,
    load_api_config,
    setup_logging,
    ensure_output_dir,
)

setup_logging()
ensure_output_dir()

ORG_KEY = "huggingface"


# ── Data-transform helpers ───────────────────────────────


def _build_trending_item(item_data: dict, item_type: str) -> dict | None:
    """Convert a raw Hugging Face trending API item into the standard format."""
    try:
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
        if pipeline_tag:
            description_parts.append(f"Type: {pipeline_tag}")
        if downloads > 0:
            description_parts.append(f"Downloads: {downloads:,}")
        if likes > 0:
            description_parts.append(f"Likes: {likes}")
        if tags:
            description_parts.append(f"Tags: {', '.join(tags[:3])}")

        return {
            "id": hashlib.md5(
                f"huggingface_{item_id}".encode()
            ).hexdigest(),
            "source": ORG_KEY,
            "type": item_type,
            "title": item_id,
            "description": "<br/>".join(description_parts),
            "url": (
                f"https://huggingface.co/datasets/{item_id}"
                if item_type == "dataset"
                else f"https://huggingface.co/{item_id}"
            ),
            "published_date": created_at or datetime.now(timezone.utc).isoformat(),
            "categories": [pipeline_tag] if pipeline_tag else [],
            "metadata": {
                "author": author,
                "item_name": item_name,
                "downloads": downloads,
                "likes": likes,
                "last_modified": repo_data.get("lastModified", ""),
                "all_tags": tags,
            },
        }
    except Exception as exc:
        logging.warning("Failed to build trending item: %s", exc)
        return None


def _build_paper_entry(raw_item: dict) -> dict | None:
    """Convert a raw daily-papers API item into the standard format."""
    try:
        paper_data = raw_item.get("paper", {})
        paper_id = paper_data.get("id", "")
        title = raw_item.get("title", "") or paper_data.get("title", "")
        summary = raw_item.get("summary", "") or paper_data.get("summary", "")
        authors_raw = paper_data.get("authors", [])
        upvotes = paper_data.get("upvotes", 0)
        github_stars = paper_data.get("githubStars", 0)
        github_url = paper_data.get("githubRepo", "")
        project_url = paper_data.get("projectPage", "")
        published_date = (
            raw_item.get("publishedAt", "")
            or paper_data.get("publishedAt", "")
            or raw_item.get("fetch_date", "")
        )

        description_parts = []
        if summary:
            description_parts.append(
                summary[:200] + "..." if len(summary) > 200 else summary
            )
        if upvotes > 0:
            description_parts.append(f"Upvotes: {upvotes}")
        if github_stars > 0:
            description_parts.append(f"GitHub Stars: {github_stars}")

        author_names = [
            a["name"] for a in authors_raw
            if isinstance(a, dict) and a.get("name")
        ]
        if author_names:
            description_parts.append(f"Authors: {', '.join(author_names[:3])}")

        description = "<br/>".join(description_parts)

        primary_url = (
            f"https://arxiv.org/abs/{paper_id}"
            if paper_id
            else project_url or github_url
            or f"https://huggingface.co/papers/{paper_id}"
        )

        additional_links = []
        if github_url and github_url != primary_url:
            additional_links.append(f'🔗 <a href="{github_url}">GitHub</a>')
        if project_url and project_url != primary_url:
            additional_links.append(f'🔗 <a href="{project_url}">Project Page</a>')
        arxiv_url = f"https://arxiv.org/abs/{paper_id}" if paper_id else ""
        if arxiv_url and arxiv_url != primary_url:
            additional_links.append(f'🔗 <a href="{arxiv_url}">ArXiv</a>')
        hf_paper_url = f"https://huggingface.co/papers/{paper_id}"
        if hf_paper_url != primary_url:
            additional_links.append(f'🔗 <a href="{hf_paper_url}">Hugging Face</a>')

        if additional_links:
            description += (
                "<br/>" if description else ""
            ) + "<br/>".join(additional_links)

        return {
            "id": hashlib.md5(
                f"huggingface_paper_{paper_id}".encode()
            ).hexdigest(),
            "source": ORG_KEY,
            "type": "paper",
            "title": title,
            "description": description,
            "url": primary_url,
            "external_url": (
                github_url
                if primary_url != github_url
                else project_url if project_url != primary_url else None
            ),
            "published_date": published_date or datetime.now(timezone.utc).isoformat(),
            "categories": ["research", "paper"],
            "metadata": {
                "paper_id": paper_id,
                "upvotes": upvotes,
                "github_stars": github_stars,
                "github_url": github_url,
                "project_url": project_url,
                "authors": author_names,
                "summary": summary,
                "fetch_date": raw_item.get("fetch_date", ""),
                "num_comments": raw_item.get("numComments", 0),
                "ai_summary": paper_data.get("ai_summary", ""),
                "ai_keywords": paper_data.get("ai_keywords", []),
            },
        }
    except Exception as exc:
        logging.warning("Failed to build paper entry: %s", exc)
        return None


# ── API fetchers ─────────────────────────────────────────


async def fetch_trending_items(
    base_url: str, page_config: dict
) -> list[dict]:
    """Fetch trending items (models or datasets) from the Hugging Face API.

    The *page_config* dict must contain ``endpoint``, ``params`` (with ``type``
    and ``limit``), etc.
    """
    endpoint = page_config["endpoint"]
    params = page_config.get("params", {})
    item_type = params.get("type", "model")
    limit = params.get("limit", 20)

    async with AsyncSession() as session:
        try:
            response = await fetch_with_retry(
                session,
                f"{base_url}{endpoint}",
                params=params,
                impersonate="chrome120",
                timeout=10,
            )
            items_data = response.json().get("recentlyTrending", [])

            items: list[dict] = []
            for item in items_data:
                entry = _build_trending_item(item, item_type)
                if entry:
                    items.append(entry)

            logging.info(
                "Fetched %d trending %s items (limit=%s)",
                len(items),
                item_type,
                limit,
            )
            return items

        except Exception as exc:
            logging.error("Failed to fetch trending %s: %s", item_type, exc)
            return []


async def fetch_daily_papers(base_url: str) -> list[dict]:
    """Fetch daily papers for the last 30 weekdays and return top picks.

    The top 6 by upvotes and top 6 by GitHub stars are combined and
    deduplicated.
    """
    async with AsyncSession() as session:
        all_papers: list[dict] = []
        today = datetime.now(timezone.utc)

        # Build list of dates (skip weekends)
        dates = [
            (today - timedelta(days=i)).strftime("%Y-%m-%d")
            for i in range(1, 31)
            if (today - timedelta(days=i)).weekday() < 5
        ]

        logging.info("Fetching daily papers for %d days…", len(dates))

        for date in dates:
            try:
                response = await fetch_with_retry(
                    session,
                    f"{base_url}/daily_papers",
                    params={"date": date},
                    impersonate="chrome120",
                    timeout=10,
                    max_retries=2,
                )
                papers_data = response.json()
                for paper in papers_data:
                    paper["fetch_date"] = date
                    all_papers.append(paper)

                logging.debug("Fetched %d papers for %s", len(papers_data), date)

            except Exception as exc:
                logging.warning("Failed to fetch papers for %s: %s", date, exc)
                continue

        if not all_papers:
            logging.error("No papers were fetched from any date")
            return []

        logging.info("Total papers collected: %d", len(all_papers))

        # Top 6 by upvotes
        by_upvotes = sorted(
            all_papers,
            key=lambda x: x.get("paper", {}).get("upvotes", 0),
            reverse=True,
        )[:6]

        # Top 6 by GitHub stars
        by_stars = sorted(
            all_papers,
            key=lambda x: x.get("paper", {}).get("githubStars", 0),
            reverse=True,
        )[:6]

        # Combine & deduplicate
        seen: set[str] = set()
        deduped = []
        for item in by_upvotes + by_stars:
            pid = item.get("paper", {}).get("id") or item.get("title", "")
            if pid and pid not in seen:
                seen.add(pid)
                deduped.append(item)

        logging.info("Deduplicated to %d unique papers", len(deduped))

        formatted = [
            entry for item in deduped
            if (entry := _build_paper_entry(item))
        ]
        return formatted


# ── Main ──────────────────────────────────────────────────


async def main() -> None:
    """Fetch all Hugging Face pages (trending models, datasets, daily papers)."""
    config = load_api_config(ORG_KEY)

    page_keys = ["trending_models", "trending_datasets", "daily_papers"]

    for key in page_keys:
        page_config = config["pages"].get(key)
        if not page_config:
            logging.warning("No config found for page '%s', skipping", key)
            continue

        logging.info("Fetching %s…", key.replace("_", " ").title())

        if key == "daily_papers":
            data = await fetch_daily_papers(config["base_url"])
        else:
            data = await fetch_trending_items(config["base_url"], page_config)

        if data:
            output_file = PARSED_DIR / page_config["output_file"]
            with open(output_file, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            logging.info(
                "Saved %d items to %s", len(data), output_file
            )
        else:
            logging.error("No data fetched for %s", key)


if __name__ == "__main__":
    asyncio.run(main())
