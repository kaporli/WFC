"""
crawl.py — fetches all namespace-0 wiki article pages and saves raw
wikitext to chatbot/raw/.  Does NOT embed anything into ChromaDB.

Run this as Job 1 in the unified ingest pipeline so the TypeScript
build-planner pipeline can read article pages from raw/ instead of
making separate API calls.
"""
from __future__ import annotations
import asyncio
import json
import time

import httpx

from warframe_chatbot.config import RAW_DIR, STATE_FILE, WIKI_API, RATE_LIMIT_S, BATCH_SIZE, MIN_PAGE_SIZE
from warframe_chatbot.crawler import enumerate_pages, fetch_content_batch, PageMeta

_CRAWL_STATE_FILE = RAW_DIR.parent / "crawl-state.json"
_HEADERS = {"User-Agent": "warframe-planner/0.1 (educational; github.com/warframe-planner)"}


def load_crawl_state() -> dict[str, int]:
    """Tracks {page_title: revid} of pages already saved to raw/."""
    return json.loads(_CRAWL_STATE_FILE.read_text()) if _CRAWL_STATE_FILE.exists() else {}


def save_crawl_state(state: dict[str, int]) -> None:
    _CRAWL_STATE_FILE.write_text(json.dumps(state, indent=2))


async def run_crawl(*, force: bool = False) -> int:
    """Fetch all namespace-0 wiki pages and save wikitext to raw/. Returns page count."""
    t0 = time.time()
    print("Enumerating wiki pages...")
    async with httpx.AsyncClient(headers=_HEADERS, timeout=30) as client:
        all_pages = await enumerate_pages(client)
    print(f"  {len(all_pages)} content pages found.")

    crawl_state = {} if force else load_crawl_state()
    current_titles = {p.title for p in all_pages}

    # Remove stale entries from state for deleted pages
    stale = set(crawl_state.keys()) - current_titles
    for title in stale:
        crawl_state.pop(title, None)

    # Only fetch pages not yet cached or whose revid changed
    needs_fetch: list[PageMeta] = [
        p for p in all_pages
        if force or p.revid != crawl_state.get(p.title, -1)
    ]
    print(f"  {len(needs_fetch)} pages need fetching.")

    if not needs_fetch:
        print("  Raw cache is up to date.")
        save_crawl_state(crawl_state)
        return 0

    fetched = 0
    async with httpx.AsyncClient(headers=_HEADERS, timeout=30) as client:
        for i in range(0, len(needs_fetch), BATCH_SIZE):
            batch = needs_fetch[i: i + BATCH_SIZE]
            result = await fetch_content_batch(client, [p.title for p in batch])
            for content in result.values():
                content.save()
                crawl_state[content.page_title] = content.revid
                fetched += 1
            pct = min(i + BATCH_SIZE, len(needs_fetch)) / len(needs_fetch) * 100
            print(f"  [{pct:4.0f}%] Fetched {min(i+BATCH_SIZE, len(needs_fetch))}/{len(needs_fetch)}", end="\r", flush=True)
            await asyncio.sleep(RATE_LIMIT_S)

    save_crawl_state(crawl_state)
    print(f"\nCrawl done. {fetched} pages saved to raw/ in {time.time()-t0:.0f}s.")
    return fetched


def main() -> None:
    import argparse
    p = argparse.ArgumentParser(description="Crawl Warframe wiki article pages to raw/")
    p.add_argument("--force", action="store_true", help="Re-fetch all pages ignoring cache")
    args = p.parse_args()
    asyncio.run(run_crawl(force=args.force))


if __name__ == "__main__":
    main()
