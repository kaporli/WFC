from __future__ import annotations
import asyncio
import json
from dataclasses import dataclass
from typing import AsyncGenerator

import httpx

from warframe_chatbot.config import WIKI_API, WIKI_BASE, RATE_LIMIT_S, BATCH_SIZE, MIN_PAGE_SIZE, RAW_DIR


@dataclass
class PageMeta:
    title: str
    revid: int
    size: int


@dataclass
class PageContent:
    title: str
    revid: int
    wikitext: str

    @property
    def url(self) -> str:
        return f"{WIKI_BASE}/{self.title.replace(' ', '_')}"

    def save(self) -> None:
        slug = self.title.replace("/", "_").replace(" ", "_")[:80]
        (RAW_DIR / f"{slug}.json").write_text(
            json.dumps({"title": self.title, "revid": self.revid, "wikitext": self.wikitext}),
            encoding="utf-8",
        )


def parse_allpages_response(raw: dict, min_size: int = MIN_PAGE_SIZE) -> list[PageMeta]:
    pages = []
    for _pid, page in raw.get("query", {}).get("pages", {}).items():
        if page.get("redirect"):
            continue
        revisions = page.get("revisions", [])
        if not revisions or revisions[0].get("size", 0) < min_size:
            continue
        rev = revisions[0]
        pages.append(PageMeta(title=page["title"], revid=rev["revid"], size=rev["size"]))
    return pages


def parse_content_response(raw: dict) -> dict[str, PageContent]:
    result = {}
    for _pid, page in raw.get("query", {}).get("pages", {}).items():
        title = page.get("title", "")
        revisions = page.get("revisions", [])
        if not revisions:
            continue
        rev = revisions[0]
        # formatversion=1 uses "*" as the content key; formatversion=2 uses "content"
        main = rev.get("slots", {}).get("main", {})
        wikitext = main.get("*", "") or main.get("content", "")
        if wikitext:
            result[title] = PageContent(title=title, revid=rev["revid"], wikitext=wikitext)
    return result


def parse_extracts_response(raw: dict) -> dict[str, PageContent]:
    """Parse TextExtracts API response (prop=extracts&explaintext=1).
    Returns plain-text extracts; falls back to empty string if unavailable."""
    result = {}
    for _pid, page in raw.get("query", {}).get("pages", {}).items():
        title = page.get("title", "")
        if page.get("missing") or not title:
            continue
        extract = page.get("extract", "").strip()
        if not extract:
            continue
        revisions = page.get("revisions", [])
        revid = revisions[0].get("revid", 0) if revisions else 0
        result[title] = PageContent(title=title, revid=revid, wikitext=extract)
    return result


async def enumerate_pages(client: httpx.AsyncClient) -> list[PageMeta]:
    all_pages: list[PageMeta] = []
    gap_continue: str | None = None
    while True:
        params: dict = {
            "action": "query", "generator": "allpages",
            "gapnamespace": "0", "gaplimit": "500",
            "prop": "revisions", "rvprop": "ids|size",
            "format": "json", "formatversion": "2",
        }
        if gap_continue:
            params["gapcontinue"] = gap_continue
        resp = await client.get(WIKI_API, params=params)
        resp.raise_for_status()
        data = resp.json()
        for page in data.get("query", {}).get("pages", []):
            if page.get("redirect"):
                continue
            revisions = page.get("revisions", [])
            if not revisions or revisions[0].get("size", 0) < MIN_PAGE_SIZE:
                continue
            rev = revisions[0]
            all_pages.append(PageMeta(title=page["title"], revid=rev["revid"], size=rev["size"]))
        gap_continue = data.get("continue", {}).get("gapcontinue")
        if not gap_continue:
            break
        await asyncio.sleep(RATE_LIMIT_S)
    return all_pages


async def fetch_content_batch(client: httpx.AsyncClient, titles: list[str]) -> dict[str, PageContent]:
    # TextExtracts with exintro=1 allows batches of up to 20 pages.
    # For full articles, exlimit is capped at 1 — intros are sufficient
    # since precise stats come from data/*.json (data_indexer).
    params = {
        "action": "query",
        "titles": "|".join(titles),
        "prop": "extracts|revisions",
        "explaintext": "1",        # clean plain text, no HTML or wikitext markup
        "exintro": "1",            # introductory section — template-rendered, rich content
        "exlimit": "max",          # up to 20 per request with exintro
        "rvprop": "ids",           # need revids for incremental state tracking
        "format": "json",
        "formatversion": "1",
    }
    resp = await client.get(WIKI_API, params=params)
    resp.raise_for_status()
    return parse_extracts_response(resp.json())


async def crawl_all(needs_fetch: list[PageMeta], *, on_progress=None) -> AsyncGenerator[PageContent, None]:
    headers = {"User-Agent": "warframe-planner/0.1 (educational; github.com/warframe-planner)"}
    async with httpx.AsyncClient(headers=headers, timeout=30) as client:
        for i in range(0, len(needs_fetch), BATCH_SIZE):
            batch = needs_fetch[i: i + BATCH_SIZE]
            result = await fetch_content_batch(client, [p.title for p in batch])
            for content in result.values():
                content.save()
                yield content
            if on_progress:
                on_progress(min(i + BATCH_SIZE, len(needs_fetch)), len(needs_fetch))
            await asyncio.sleep(RATE_LIMIT_S)
