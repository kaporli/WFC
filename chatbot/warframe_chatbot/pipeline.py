"""
pipeline.py — embed all Warframe knowledge into ChromaDB.

Sources:
  1. Wiki article pages (namespace-0) — from raw/ cache populated by crawl.py
  2. data/*.json — build-planner output (warframes, mods, weapons, abilities, etc.)

In the unified ingest workflow, this runs AFTER:
  - crawl.py has populated raw/
  - TypeScript pipeline has written data/*.json
"""
from __future__ import annotations
import asyncio
import json
import time
from pathlib import Path

import httpx

from warframe_chatbot.chunker import chunk_page
from warframe_chatbot.config import STATE_FILE, RAW_DIR
from warframe_chatbot.crawler import enumerate_pages, crawl_all, PageMeta, PageContent
from warframe_chatbot.data_indexer import index_data_files
from warframe_chatbot.store import WikiStore


def load_state() -> dict[str, int]:
    return json.loads(STATE_FILE.read_text()) if STATE_FILE.exists() else {}


def save_state(state: dict[str, int]) -> None:
    STATE_FILE.write_text(json.dumps(state, indent=2))


def _load_from_raw_cache(page_title: str) -> PageContent | None:
    """Try to read a page from raw/ cache before hitting the wiki API."""
    slug = page_title.replace("/", "_").replace(" ", "_")[:80]
    path = RAW_DIR / f"{slug}.json"
    if path.exists():
        try:
            d = json.loads(path.read_text(encoding="utf-8"))
            return PageContent(title=d["title"], revid=d["revid"], wikitext=d["wikitext"])
        except Exception:
            pass
    return None


async def run_pipeline(store: WikiStore, *, force: bool = False, skip_data: bool = False) -> None:
    t0 = time.time()
    headers = {"User-Agent": "warframe-planner/0.1 (educational; github.com/warframe-planner)"}

    # ── Phase 1: Wiki article pages ───────────────────────────────────────────
    print("Enumerating wiki pages...")
    async with httpx.AsyncClient(headers=headers, timeout=30) as client:
        all_pages = await enumerate_pages(client)
    print(f"  {len(all_pages)} content pages found.")

    state = {} if force else load_state()
    current_titles = {p.title for p in all_pages}

    stale = set(state.keys()) - current_titles
    if stale:
        print(f"  Removing {len(stale)} deleted pages...")
        for title in stale:
            store.delete_page(title)
            state.pop(title, None)

    needs_fetch: list[PageMeta] = [
        p for p in all_pages
        if force or p.revid != state.get(p.title, -1)
    ]
    print(f"  {len(needs_fetch)} pages need (re-)indexing.")

    total_wiki_chunks = 0

    if needs_fetch:
        # Try serving from raw/ cache first (populated by crawl.py in Job 1)
        from_cache: list[PageContent] = []
        still_needs_fetch: list[PageMeta] = []
        for page_meta in needs_fetch:
            cached = _load_from_raw_cache(page_meta.title)
            if cached and cached.revid == page_meta.revid:
                from_cache.append(cached)
            else:
                still_needs_fetch.append(page_meta)

        if from_cache:
            print(f"  Serving {len(from_cache)} pages from raw/ cache.")
        if still_needs_fetch:
            print(f"  Fetching {len(still_needs_fetch)} pages from wiki API.")

        def progress(done: int, total: int) -> None:
            print(f"  [{done/total*100:4.0f}%] {done}/{total} pages, {total_wiki_chunks} chunks", end="\r", flush=True)

        # Embed from cache
        for content in from_cache:
            chunks = chunk_page(content)
            if chunks:
                store.delete_page(content.title)
                store.upsert(chunks)
                total_wiki_chunks += len(chunks)
            state[content.title] = content.revid

        # Fetch remaining from API
        if still_needs_fetch:
            async for content in crawl_all(still_needs_fetch, on_progress=progress):
                chunks = chunk_page(content)
                if chunks:
                    store.delete_page(content.title)
                    store.upsert(chunks)
                    total_wiki_chunks += len(chunks)
                state[content.title] = content.revid

    save_state(state)
    print(f"\n  Wiki: {total_wiki_chunks} chunks indexed.")

    # ── Phase 2: data/*.json from build-planner ───────────────────────────────
    if not skip_data:
        data_dir = Path(__file__).parent.parent.parent / "data"
        if data_dir.exists():
            print("Indexing data/*.json (build-planner output)...")
            total_data_chunks = index_data_files(store, data_dir=data_dir)
            print(f"  Data: {total_data_chunks} chunks indexed.")
        else:
            print("  data/ directory not found — skipping data/*.json indexing.")

    elapsed = time.time() - t0
    print(f"\nDone. Store total: {store.count()} chunks in {elapsed:.0f}s.")


def main() -> None:
    import argparse
    p = argparse.ArgumentParser(description="Embed Warframe wiki + data/*.json into ChromaDB")
    p.add_argument("--force", action="store_true", help="Re-index all pages ignoring state")
    p.add_argument("--skip-data", action="store_true", help="Skip data/*.json indexing")
    args = p.parse_args()
    asyncio.run(run_pipeline(WikiStore(), force=args.force, skip_data=args.skip_data))


if __name__ == "__main__":
    main()
