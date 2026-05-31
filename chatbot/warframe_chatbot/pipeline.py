from __future__ import annotations
import asyncio
import json
import time

import httpx

from warframe_chatbot.chunker import chunk_page
from warframe_chatbot.config import STATE_FILE
from warframe_chatbot.crawler import enumerate_pages, crawl_all, PageMeta
from warframe_chatbot.store import WikiStore


def load_state() -> dict[str, int]:
    return json.loads(STATE_FILE.read_text()) if STATE_FILE.exists() else {}


def save_state(state: dict[str, int]) -> None:
    STATE_FILE.write_text(json.dumps(state, indent=2))


async def run_pipeline(store: WikiStore, *, force: bool = False) -> None:
    t0 = time.time()
    headers = {"User-Agent": "warframe-planner/0.1 (educational; github.com/warframe-planner)"}

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

    if not needs_fetch:
        print("  Index is up to date.")
        save_state(state)
        return

    total_chunks = 0

    def progress(done: int, total: int) -> None:
        print(f"  [{done/total*100:4.0f}%] {done}/{total} pages, {total_chunks} chunks", end="\r", flush=True)

    async for content in crawl_all(needs_fetch, on_progress=progress):
        chunks = chunk_page(content)
        if chunks:
            store.delete_page(content.page_title)
            store.upsert(chunks)
            total_chunks += len(chunks)
        state[content.page_title] = content.revid

    save_state(state)
    print(f"\nDone. {len(needs_fetch)} pages → {total_chunks} chunks in {time.time()-t0:.0f}s.")
    print(f"Store total: {store.count()} chunks.")


def main() -> None:
    import argparse
    p = argparse.ArgumentParser(description="Ingest Warframe wiki into ChromaDB")
    p.add_argument("--force", action="store_true", help="Re-index all pages ignoring state")
    args = p.parse_args()
    asyncio.run(run_pipeline(WikiStore(), force=args.force))


if __name__ == "__main__":
    main()
