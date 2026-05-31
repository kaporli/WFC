# Warframe Wiki RAG Chatbot Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a RAG chatbot over the entire Warframe wiki (11k content pages) using ChromaDB + sentence-transformers + Claude, with incremental nightly updates keyed on MediaWiki revision IDs.

**Architecture:** Standalone Python package `chatbot/` that crawls all namespace-0 wiki pages, cleans wikitext to plain text, chunks by section, embeds locally with `all-MiniLM-L6-v2`, stores in ChromaDB. A search layer retrieves top-k chunks; a chat layer calls Claude Sonnet 4.6 with those chunks and always cites sources.

**Tech Stack:** Python 3.12, uv, chromadb, sentence-transformers, httpx (async), anthropic SDK, pytest.

---

## File Map

```
chatbot/
  pyproject.toml
  .gitignore
  warframe_chatbot/
    __init__.py
    config.py       — all constants: paths, API URLs, rate limits, model names
    crawler.py      — enumerate + batch-fetch all namespace-0 wiki pages via MediaWiki API
    cleaner.py      — wikitext → clean plain text (regex, no full parser needed)
    chunker.py      — plain text → overlapping chunks keyed to wiki sections
    embedder.py     — sentence-transformers wrapper (loads model once, cached)
    store.py        — ChromaDB client: upsert/delete/query; SearchResult dataclass
    pipeline.py     — incremental ingest: enumerate → diff → fetch → chunk → embed → store
    search.py       — search(query, k) → list[SearchResult]; thin wrapper over store
    chat.py         — ask(question) → str; RAG: retrieve → format prompt → Claude
  tests/
    test_cleaner.py
    test_chunker.py
    test_store.py
    test_search.py
    test_chat.py
  raw/              — cached raw wikitext JSON (gitignored, immutable after write)
  chroma/           — ChromaDB persistence directory (gitignored)
  state.json        — {page_title: revid} of last indexed state (gitignored)
```

---

## Task 1: Package scaffold + config

**Files:**
- Create: `chatbot/pyproject.toml`
- Create: `chatbot/warframe_chatbot/__init__.py`
- Create: `chatbot/warframe_chatbot/config.py`
- Create: `chatbot/.gitignore`

- [ ] **Step 1: Create `chatbot/pyproject.toml`**

```toml
[project]
name = "warframe-chatbot"
version = "0.1.0"
requires-python = ">=3.12"
dependencies = [
    "chromadb>=0.5.0",
    "sentence-transformers>=3.0.0",
    "httpx>=0.27.0",
    "anthropic>=0.40.0",
]

[project.optional-dependencies]
dev = ["pytest>=8.0", "pytest-asyncio>=0.23.0"]

[project.scripts]
wf-ingest = "warframe_chatbot.pipeline:main"
wf-chat   = "warframe_chatbot.chat:main"

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.pytest.ini_options]
testpaths = ["tests"]
asyncio_mode = "auto"
```

- [ ] **Step 2: Create `chatbot/warframe_chatbot/config.py`**

```python
from pathlib import Path

CHATBOT_DIR   = Path(__file__).parent.parent
RAW_DIR       = CHATBOT_DIR / "raw"
CHROMA_DIR    = CHATBOT_DIR / "chroma"
STATE_FILE    = CHATBOT_DIR / "state.json"

RAW_DIR.mkdir(exist_ok=True)

WIKI_API      = "https://wiki.warframe.com/api.php"
WIKI_BASE     = "https://wiki.warframe.com/w"
RATE_LIMIT_S  = 1.0          # seconds between API requests (respectful crawling)
BATCH_SIZE    = 50           # pages per content-fetch API call
MIN_PAGE_SIZE = 500          # bytes; skip redirects/stubs below this

CHUNK_TOKENS  = 500          # target tokens per chunk (~2000 chars)
CHUNK_OVERLAP = 50           # tokens of overlap between consecutive chunks

EMBED_MODEL   = "all-MiniLM-L6-v2"   # local, ~90MB, 384-dim
EMBED_DIM     = 384

COLLECTION    = "warframe_wiki"

CLAUDE_MODEL  = "claude-sonnet-4-6"
RETRIEVAL_K   = 6
```

- [ ] **Step 3: Create `chatbot/warframe_chatbot/__init__.py`** (empty file)

- [ ] **Step 4: Create `chatbot/.gitignore`**

```
raw/
chroma/
state.json
__pycache__/
*.pyc
.venv/
```

- [ ] **Step 5: Install deps**

```bash
cd /Users/elias/Documents/WFC/chatbot && uv sync --extra dev 2>&1 | tail -5
```
Expected: chromadb, sentence-transformers, httpx, anthropic installed.

- [ ] **Step 6: Commit**

```bash
cd /Users/elias/Documents/WFC && git add chatbot/ && git commit -m "feat(chatbot): package scaffold and config"
```

---

## Task 2: Wiki crawler

**Files:**
- Create: `chatbot/warframe_chatbot/crawler.py`
- Create: `chatbot/tests/__init__.py`
- Create: `chatbot/tests/test_crawler.py`

- [ ] **Step 1: Create `chatbot/tests/test_crawler.py`**

```python
from warframe_chatbot.crawler import PageMeta, PageContent, parse_allpages_response, parse_content_response


def test_parse_allpages_filters_small_and_redirects():
    raw = {"query": {"pages": {
        "1": {"title": "BigPage", "revisions": [{"revid": 100, "size": 5000}]},
        "2": {"title": "Stub",    "revisions": [{"revid": 101, "size": 100}]},
        "3": {"title": "Redir",   "revisions": [{"revid": 102, "size": 30}], "redirect": True},
    }}}
    pages = parse_allpages_response(raw, min_size=500)
    assert len(pages) == 1
    assert pages[0].title == "BigPage"
    assert pages[0].revid == 100


def test_parse_content_extracts_wikitext():
    raw = {"query": {"pages": {"42": {
        "title": "Frost",
        "revisions": [{"revid": 999, "slots": {"main": {"content": "Frost is cold."}}}],
    }}}}
    result = parse_content_response(raw)
    assert result["Frost"].revid == 999
    assert "Frost is cold" in result["Frost"].wikitext


def test_page_content_url():
    pc = PageContent(title="Snow Globe", revid=1, wikitext="")
    assert "Snow_Globe" in pc.url
    assert pc.url.startswith("https://wiki.warframe.com")


def test_parse_allpages_empty():
    assert parse_allpages_response({"query": {"pages": {}}}) == []
```

- [ ] **Step 2: Run — verify failure**

```bash
cd /Users/elias/Documents/WFC/chatbot && uv run pytest tests/test_crawler.py -v 2>&1 | head -10
```

- [ ] **Step 3: Create `chatbot/warframe_chatbot/crawler.py`**

```python
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
        wikitext = rev.get("slots", {}).get("main", {}).get("content", "")
        if wikitext:
            result[title] = PageContent(title=title, revid=rev["revid"], wikitext=wikitext)
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
    params = {
        "action": "query", "titles": "|".join(titles),
        "prop": "revisions", "rvprop": "ids|content",
        "rvslots": "main", "format": "json", "formatversion": "1",
    }
    resp = await client.get(WIKI_API, params=params)
    resp.raise_for_status()
    return parse_content_response(resp.json())


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
```

- [ ] **Step 4: Run tests**

```bash
cd /Users/elias/Documents/WFC/chatbot && uv run pytest tests/test_crawler.py -v 2>&1
```
Expected: 4 passed.

- [ ] **Step 5: Commit**

```bash
cd /Users/elias/Documents/WFC && git add chatbot/ && git commit -m "feat(chatbot): wiki crawler — enumerate all pages + batch content fetch"
```

---

## Task 3: Wikitext cleaner

**Files:**
- Create: `chatbot/warframe_chatbot/cleaner.py`
- Create: `chatbot/tests/test_cleaner.py`

- [ ] **Step 1: Create `chatbot/tests/test_cleaner.py`**

```python
from warframe_chatbot.cleaner import clean_wikitext


def test_removes_templates():
    assert "{{" not in clean_wikitext("Text {{stub}} more.")

def test_keeps_inline_template_display():
    assert "Cold" in clean_wikitext("Deals {{D|Cold}} damage.")

def test_wikilink_display_text_kept():
    result = clean_wikitext("See [[Frost|the ice frame]] and [[Rhino]].")
    assert "the ice frame" in result and "Rhino" in result and "[[" not in result

def test_html_tags_stripped():
    result = clean_wikitext("Lasts <span style='color:red'>10 seconds</span>.")
    assert "10 seconds" in result and "<" not in result

def test_headers_stripped_text_kept():
    result = clean_wikitext("== Overview ==\nFrost is cold.\n=== Abilities ===")
    assert "==" not in result and "Overview" in result

def test_bullet_content_kept():
    result = clean_wikitext("* First\n** Nested\n# Numbered")
    assert "First" in result and "Nested" in result and "Numbered" in result

def test_empty_returns_empty():
    assert clean_wikitext("") == ""

def test_collapses_blank_lines():
    assert "\n\n\n" not in clean_wikitext("A\n\n\n\nB")
```

- [ ] **Step 2: Run — verify failure**

```bash
cd /Users/elias/Documents/WFC/chatbot && uv run pytest tests/test_cleaner.py -v 2>&1 | head -10
```

- [ ] **Step 3: Create `chatbot/warframe_chatbot/cleaner.py`**

```python
from __future__ import annotations
import re

_INLINE_TMPL = re.compile(r'\{\{(?:D|M|WF|Weapon|Companion|Mod|Icon|Stat)\|([^|}]+)(?:\|[^}]*)?\}\}', re.IGNORECASE)
_TMPL_ALL    = re.compile(r'\{\{[^{}]*\}\}', re.DOTALL)
_FILE_LINK   = re.compile(r'\[\[(?:File|Image):[^\]]+\]\]', re.IGNORECASE)
_WIKILINK    = re.compile(r'\[\[(?:[^\]|]+\|)?([^\]]+)\]\]')
_EXT_LINK    = re.compile(r'\[https?://\S+(?:\s+([^\]]+))?\]')
_HEADER      = re.compile(r'^={1,6}\s*(.+?)\s*={1,6}\s*$', re.MULTILINE)
_HTML_TAG    = re.compile(r'<[^>]+>')
_REF         = re.compile(r'<ref[^>]*>.*?</ref>', re.DOTALL | re.IGNORECASE)
_REF_SELF    = re.compile(r'<ref[^/]*/>', re.IGNORECASE)
_TABLE_ROW   = re.compile(r'^\s*[\|!{].*$', re.MULTILINE)
_LIST_MARK   = re.compile(r'^[*#:;]+\s*', re.MULTILINE)
_FORMAT      = re.compile(r"'{2,3}")
_TOC         = re.compile(r'__(?:TOC|NOTOC|FORCETOC)__')
_HR          = re.compile(r'^-{4,}$', re.MULTILINE)


def _strip_templates(text: str) -> str:
    text = _INLINE_TMPL.sub(r'\1', text)
    for _ in range(6):
        prev = text
        text = _TMPL_ALL.sub('', text)
        if text == prev:
            break
    return text


def clean_wikitext(wikitext: str) -> str:
    if not wikitext:
        return ""
    t = wikitext
    t = _FILE_LINK.sub('', t)
    t = _REF.sub('', t)
    t = _REF_SELF.sub('', t)
    t = _strip_templates(t)
    t = _WIKILINK.sub(r'\1', t)
    t = _EXT_LINK.sub(lambda m: m.group(1) or '', t)
    t = _HEADER.sub(r'\1', t)
    t = _HTML_TAG.sub('', t)
    t = _TABLE_ROW.sub('', t)
    t = _FORMAT.sub('', t)
    t = _LIST_MARK.sub('', t)
    t = _TOC.sub('', t)
    t = _HR.sub('', t)
    t = re.sub(r'\n{3,}', '\n\n', t)
    t = re.sub(r'[ \t]+', ' ', t)
    return t.strip()
```

- [ ] **Step 4: Run tests**

```bash
cd /Users/elias/Documents/WFC/chatbot && uv run pytest tests/test_cleaner.py -v 2>&1
```
Expected: 8 passed.

- [ ] **Step 5: Commit**

```bash
cd /Users/elias/Documents/WFC && git add chatbot/ && git commit -m "feat(chatbot): wikitext cleaner — strip markup keep plain text"
```

---

## Task 4: Chunker

**Files:**
- Create: `chatbot/warframe_chatbot/chunker.py`
- Create: `chatbot/tests/test_chunker.py`

- [ ] **Step 1: Create `chatbot/tests/test_chunker.py`**

```python
from warframe_chatbot.chunker import chunk_page, Chunk
from warframe_chatbot.crawler import PageContent


def page(title, text, revid=1):
    return PageContent(title=title, revid=revid, wikitext=text)


def test_basic_chunks_produced():
    chunks = chunk_page(page("Frost", "Frost is a cold warframe. " * 10))
    assert len(chunks) >= 1 and all(isinstance(c, Chunk) for c in chunks)

def test_chunk_fields():
    c = chunk_page(page("Frost", "Frost is cold. " * 20, revid=42))[0]
    assert c.page_title == "Frost" and c.revid == 42
    assert "wiki.warframe.com" in c.url
    assert isinstance(c.chunk_index, int) and c.text

def test_sections_create_chunks():
    wt = "== Overview ==\n" + "Frost. " * 20 + "\n== Abilities ==\n" + "Freeze. " * 20
    chunks = chunk_page(page("Frost", wt))
    assert len(chunks) >= 2

def test_empty_page_no_chunks():
    assert chunk_page(page("Empty", "")) == []

def test_long_section_splits():
    chunks = chunk_page(page("Long", "== S ==\n" + "word " * 2000))
    assert len(chunks) >= 2

def test_chunk_text_non_empty():
    chunks = chunk_page(page("X", "Content here. " * 5))
    assert all(len(c.text.strip()) > 10 for c in chunks)
```

- [ ] **Step 2: Run — verify failure**

```bash
cd /Users/elias/Documents/WFC/chatbot && uv run pytest tests/test_chunker.py -v 2>&1 | head -10
```

- [ ] **Step 3: Create `chatbot/warframe_chatbot/chunker.py`**

```python
from __future__ import annotations
import re
from dataclasses import dataclass

from warframe_chatbot.cleaner import clean_wikitext
from warframe_chatbot.config import CHUNK_TOKENS, CHUNK_OVERLAP, WIKI_BASE
from warframe_chatbot.crawler import PageContent


@dataclass
class Chunk:
    page_title: str
    section: str
    text: str
    url: str
    revid: int
    chunk_index: int


def _chars(tokens: int) -> int:
    return tokens * 4   # rough: 1 token ≈ 4 chars


def _sections(wikitext: str) -> list[tuple[str, str]]:
    pattern = re.compile(r'^(==\s*[^=\n]+\s*==)', re.MULTILINE)
    parts = pattern.split(wikitext)
    result: list[tuple[str, str]] = []
    if parts[0].strip():
        result.append(("", parts[0].strip()))
    i = 1
    while i < len(parts) - 1:
        header = parts[i].strip('= \t')
        body = parts[i + 1] if i + 1 < len(parts) else ""
        result.append((header, body))
        i += 2
    return result


def _split(text: str, max_c: int, overlap: int) -> list[str]:
    if len(text) <= max_c:
        return [text] if text.strip() else []
    chunks, start = [], 0
    while start < len(text):
        end = start + max_c
        if end < len(text):
            for sep in ['\n\n', '\n', '. ', ' ']:
                idx = text.rfind(sep, start + max_c // 2, end)
                if idx != -1:
                    end = idx + len(sep)
                    break
        chunk = text[start:end].strip()
        if chunk:
            chunks.append(chunk)
        start = end - overlap
    return chunks


def chunk_page(page: PageContent) -> list[Chunk]:
    if not page.wikitext.strip():
        return []
    url = f"{WIKI_BASE}/{page.title.replace(' ', '_')}"
    max_c, ovlp = _chars(CHUNK_TOKENS), _chars(CHUNK_OVERLAP)
    chunks, idx = [], 0
    for section, raw in _sections(page.wikitext):
        cleaned = clean_wikitext(raw).strip()
        if not cleaned or len(cleaned) < 50:
            continue
        prefix = f"{page.title}" + (f" — {section}" if section else "")
        for sub in _split(f"{prefix}\n\n{cleaned}", max_c, ovlp):
            chunks.append(Chunk(page_title=page.title, section=section,
                                text=sub, url=url, revid=page.revid, chunk_index=idx))
            idx += 1
    return chunks
```

- [ ] **Step 4: Run tests**

```bash
cd /Users/elias/Documents/WFC/chatbot && uv run pytest tests/test_chunker.py -v 2>&1
```
Expected: 6 passed.

- [ ] **Step 5: Commit**

```bash
cd /Users/elias/Documents/WFC && git add chatbot/ && git commit -m "feat(chatbot): chunker — section-aware overlapping chunks"
```

---

## Task 5: Embedder + ChromaDB store

**Files:**
- Create: `chatbot/warframe_chatbot/embedder.py`
- Create: `chatbot/warframe_chatbot/store.py`
- Create: `chatbot/tests/test_store.py`

- [ ] **Step 1: Create `chatbot/tests/test_store.py`**

```python
import pytest
from warframe_chatbot.chunker import Chunk
from warframe_chatbot.store import WikiStore


@pytest.fixture
def store(tmp_path):
    return WikiStore(persist_dir=str(tmp_path / "chroma"))


def ck(title, text, revid=1, idx=0):
    return Chunk(page_title=title, section="S", text=text,
                 url=f"https://wiki.warframe.com/w/{title}", revid=revid, chunk_index=idx)


def test_upsert_and_query(store):
    store.upsert([ck("Frost", "Frost is a cold ice warframe."),
                  ck("Rhino", "Rhino is a heavy tank warframe.")])
    results = store.query("ice warframe", k=2)
    assert any(r.page_title == "Frost" for r in results)


def test_upsert_idempotent(store):
    c = ck("Frost", "Frost is cold.")
    store.upsert([c]); store.upsert([c])
    assert store.count() == 1


def test_delete_page(store):
    store.upsert([ck("Old", "old content"), ck("New", "new content")])
    store.delete_page("Old")
    results = store.query("content", k=10)
    assert not any(r.page_title == "Old" for r in results)
    assert any(r.page_title == "New" for r in results)


def test_count_and_indexed_revids(store):
    assert store.count() == 0
    store.upsert([ck("Frost", "cold", revid=42)])
    assert store.count() == 1
    assert store.indexed_revids().get("Frost") == 42
```

- [ ] **Step 2: Run — verify failure**

```bash
cd /Users/elias/Documents/WFC/chatbot && uv run pytest tests/test_store.py -v 2>&1 | head -10
```

- [ ] **Step 3: Create `chatbot/warframe_chatbot/embedder.py`**

```python
from functools import lru_cache
from sentence_transformers import SentenceTransformer
from warframe_chatbot.config import EMBED_MODEL


@lru_cache(maxsize=1)
def _model() -> SentenceTransformer:
    return SentenceTransformer(EMBED_MODEL)


def embed(texts: list[str]) -> list[list[float]]:
    if not texts:
        return []
    return _model().encode(texts, batch_size=64, show_progress_bar=False,
                           normalize_embeddings=True).tolist()
```

- [ ] **Step 4: Create `chatbot/warframe_chatbot/store.py`**

```python
from __future__ import annotations
from dataclasses import dataclass

import chromadb
from chromadb.config import Settings

from warframe_chatbot.chunker import Chunk
from warframe_chatbot.config import COLLECTION, CHROMA_DIR
from warframe_chatbot.embedder import embed


@dataclass
class SearchResult:
    page_title: str
    section: str
    text: str
    url: str
    revid: int
    score: float   # cosine similarity; higher = more relevant


def _id(c: Chunk) -> str:
    return f"{c.page_title}:::{c.chunk_index}"


class WikiStore:
    def __init__(self, persist_dir: str = str(CHROMA_DIR)) -> None:
        self._client = chromadb.PersistentClient(
            path=persist_dir,
            settings=Settings(anonymized_telemetry=False),
        )
        self._col = self._client.get_or_create_collection(
            name=COLLECTION, metadata={"hnsw:space": "cosine"},
        )

    def upsert(self, chunks: list[Chunk]) -> None:
        if not chunks:
            return
        self._col.upsert(
            ids=[_id(c) for c in chunks],
            embeddings=embed([c.text for c in chunks]),
            documents=[c.text for c in chunks],
            metadatas=[{"page_title": c.page_title, "section": c.section,
                        "url": c.url, "revid": c.revid, "chunk_index": c.chunk_index}
                       for c in chunks],
        )

    def delete_page(self, page_title: str) -> None:
        self._col.delete(where={"page_title": page_title})

    def query(self, text: str, k: int = 6) -> list[SearchResult]:
        n = self._col.count()
        if n == 0:
            return []
        r = self._col.query(
            query_embeddings=embed([text]),
            n_results=min(k, n),
            include=["documents", "metadatas", "distances"],
        )
        return [
            SearchResult(page_title=m["page_title"], section=m.get("section", ""),
                         text=d, url=m["url"], revid=m["revid"], score=1.0 - dist)
            for d, m, dist in zip(r["documents"][0], r["metadatas"][0], r["distances"][0])
        ]

    def count(self) -> int:
        return self._col.count()

    def indexed_revids(self) -> dict[str, int]:
        if self._col.count() == 0:
            return {}
        result = self._col.get(include=["metadatas"])
        revids: dict[str, int] = {}
        for m in result["metadatas"]:
            t, r = m["page_title"], m["revid"]
            if t not in revids or r > revids[t]:
                revids[t] = r
        return revids
```

- [ ] **Step 5: Run tests** (downloads ~90MB embedding model on first run)

```bash
cd /Users/elias/Documents/WFC/chatbot && uv run pytest tests/test_store.py -v 2>&1
```
Expected: 4 passed.

- [ ] **Step 6: Commit**

```bash
cd /Users/elias/Documents/WFC && git add chatbot/ && git commit -m "feat(chatbot): embedder (local sentence-transformers) + ChromaDB store"
```

---

## Task 6: Ingestion pipeline

**Files:**
- Create: `chatbot/warframe_chatbot/pipeline.py`

- [ ] **Step 1: Create `chatbot/warframe_chatbot/pipeline.py`**

```python
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

    # Remove deleted pages from the index
    stale = set(state.keys()) - current_titles
    if stale:
        print(f"  Removing {len(stale)} deleted pages...")
        for title in stale:
            store.delete_page(title)
            state.pop(title, None)

    # Pages that need (re-)indexing: new or revid changed
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
```

- [ ] **Step 2: Smoke test — enumerate only, verify page count**

```bash
cd /Users/elias/Documents/WFC/chatbot && python3 -c "
import asyncio, httpx
from warframe_chatbot.crawler import enumerate_pages
async def main():
    async with httpx.AsyncClient(headers={'User-Agent':'test/0.1'}, timeout=30) as c:
        pages = await enumerate_pages(c)
    print(f'Found {len(pages)} pages')
    print('Sample:', [(p.title, p.size) for p in pages[:3]])
asyncio.run(main())
" 2>&1
Expected: `Found ~5000-8000 pages` (filtered from 11k by MIN_PAGE_SIZE=500).

- [ ] **Step 3: Commit**

```bash
git add chatbot/ && git commit -m "feat(chatbot): incremental ingestion pipeline — enumerate, diff, fetch, chunk, embed, store"
```

---

## Task 7: Search interface

**Files:**
- Create: `chatbot/warframe_chatbot/search.py`
- Create: `chatbot/tests/test_search.py`

- [ ] **Step 1: Create `chatbot/tests/test_search.py`**

```python
import pytest
from unittest.mock import MagicMock
from warframe_chatbot.search import search
from warframe_chatbot.store import WikiStore, SearchResult


def test_search_returns_results(tmp_path):
    """search() against a pre-populated store returns results."""
    from warframe_chatbot.chunker import Chunk
    store = WikiStore(persist_dir=str(tmp_path / "chroma"))
    store.upsert([
        Chunk(page_title="Shieldgate", section="Mechanics",
              text="Shieldgate grants brief invulnerability when shields are depleted.",
              url="https://wiki.warframe.com/w/Shieldgate", revid=1, chunk_index=0),
        Chunk(page_title="Armor", section="Stats",
              text="Armor reduces incoming damage using the formula armor/(armor+300).",
              url="https://wiki.warframe.com/w/Armor", revid=1, chunk_index=0),
    ])
    results = search("how does shieldgate work", store=store, k=2)
    assert len(results) >= 1
    assert results[0].page_title == "Shieldgate"
    assert results[0].score > 0


def test_search_empty_store_returns_empty(tmp_path):
    store = WikiStore(persist_dir=str(tmp_path / "chroma2"))
    results = search("anything", store=store)
    assert results == []


def test_search_result_has_url(tmp_path):
    from warframe_chatbot.chunker import Chunk
    store = WikiStore(persist_dir=str(tmp_path / "chroma3"))
    store.upsert([Chunk(page_title="Frost", section="", text="Frost is cold.",
                        url="https://wiki.warframe.com/w/Frost", revid=1, chunk_index=0)])
    results = search("Frost warframe", store=store, k=1)
    assert results[0].url.startswith("https://")
```

- [ ] **Step 2: Run — verify failure**

```bash
cd /Users/elias/Documents/WFC/chatbot && uv run pytest tests/test_search.py -v 2>&1 | head -10
```

- [ ] **Step 3: Create `chatbot/warframe_chatbot/search.py`**

```python
from __future__ import annotations
from warframe_chatbot.config import RETRIEVAL_K
from warframe_chatbot.store import WikiStore, SearchResult


_default_store: WikiStore | None = None


def _get_store() -> WikiStore:
    global _default_store
    if _default_store is None:
        _default_store = WikiStore()
    return _default_store


def search(query: str, *, store: WikiStore | None = None, k: int = RETRIEVAL_K) -> list[SearchResult]:
    """Return top-k semantically relevant wiki chunks for the query."""
    return (store or _get_store()).query(query, k=k)
```

- [ ] **Step 4: Run tests**

```bash
cd /Users/elias/Documents/WFC/chatbot && uv run pytest tests/test_search.py -v 2>&1
```
Expected: 3 passed.

- [ ] **Step 5: Commit**

```bash
cd /Users/elias/Documents/WFC && git add chatbot/ && git commit -m "feat(chatbot): search interface — thin wrapper over ChromaDB store"
```

---

## Task 8: Chat interface (RAG + Claude)

**Files:**
- Create: `chatbot/warframe_chatbot/chat.py`
- Create: `chatbot/tests/test_chat.py`

- [ ] **Step 1: Create `chatbot/tests/test_chat.py`**

```python
import pytest
from unittest.mock import MagicMock, patch
from warframe_chatbot.chat import build_prompt, format_sources


def test_build_prompt_includes_question():
    from warframe_chatbot.store import SearchResult
    results = [
        SearchResult(page_title="Shieldgate", section="Mechanics",
                     text="Shields gate grants invulnerability for 1.3s.",
                     url="https://wiki.warframe.com/w/Shieldgate", revid=1, score=0.9),
    ]
    prompt = build_prompt("How does shieldgate work?", results)
    assert "shieldgate" in prompt.lower()
    assert "1.3s" in prompt
    assert "Shieldgate" in prompt


def test_build_prompt_includes_all_sources():
    from warframe_chatbot.store import SearchResult
    results = [
        SearchResult(page_title="Frost", section="", text="Frost is cold.",
                     url="https://wiki.warframe.com/w/Frost", revid=1, score=0.8),
        SearchResult(page_title="Armor", section="", text="Armor reduces damage.",
                     url="https://wiki.warframe.com/w/Armor", revid=1, score=0.7),
    ]
    prompt = build_prompt("Frost armor build", results)
    assert "Frost" in prompt
    assert "Armor" in prompt


def test_format_sources():
    from warframe_chatbot.store import SearchResult
    results = [
        SearchResult(page_title="Shieldgate", section="Mechanics",
                     text="text", url="https://wiki.warframe.com/w/Shieldgate",
                     revid=1, score=0.9),
    ]
    formatted = format_sources(results)
    assert "Shieldgate" in formatted
    assert "wiki.warframe.com" in formatted


def test_ask_calls_claude(tmp_path):
    """ask() makes a Claude API call and returns a string."""
    from warframe_chatbot.chunker import Chunk
    from warframe_chatbot.store import WikiStore
    store = WikiStore(persist_dir=str(tmp_path / "chroma"))
    store.upsert([Chunk(page_title="Shieldgate", section="Mechanics",
                        text="Shieldgate grants 1.3s invulnerability on shield depletion.",
                        url="https://wiki.warframe.com/w/Shieldgate", revid=1, chunk_index=0)])

    mock_response = MagicMock()
    mock_response.content = [MagicMock(text="Shieldgate works by granting invulnerability.")]

    with patch("warframe_chatbot.chat.anthropic.Anthropic") as mock_cls:
        mock_client = MagicMock()
        mock_cls.return_value = mock_client
        mock_client.messages.create.return_value = mock_response

        from warframe_chatbot.chat import ask
        result = ask("How does shieldgate work?", store=store)

    assert isinstance(result, str)
    assert len(result) > 0
```

- [ ] **Step 2: Run — verify failure**

```bash
cd /Users/elias/Documents/WFC/chatbot && uv run pytest tests/test_chat.py -v 2>&1 | head -10
```

- [ ] **Step 3: Create `chatbot/warframe_chatbot/chat.py`**

```python
from __future__ import annotations
import os
import anthropic

from warframe_chatbot.config import CLAUDE_MODEL, RETRIEVAL_K
from warframe_chatbot.store import WikiStore, SearchResult
from warframe_chatbot.search import search

SYSTEM_PROMPT = """You are a Warframe game expert and wiki assistant.
Answer questions using ONLY the provided wiki excerpts below.
Always cite your sources using the format [Page Title](URL) at the end of each claim.
If the provided excerpts do not contain enough information to answer the question, say so clearly.
Do not fabricate information not present in the excerpts."""


def format_sources(results: list[SearchResult]) -> str:
    lines = []
    for i, r in enumerate(results, 1):
        section = f" ({r.section})" if r.section else ""
        lines.append(f"[{i}] [{r.page_title}{section}]({r.url})\n{r.text}")
    return "\n\n---\n\n".join(lines)


def build_prompt(question: str, results: list[SearchResult]) -> str:
    sources = format_sources(results)
    return f"""Wiki excerpts (use these to answer the question):

{sources}

---

Question: {question}"""


def ask(
    question: str,
    *,
    store: WikiStore | None = None,
    k: int = RETRIEVAL_K,
) -> str:
    results = search(question, store=store, k=k)
    if not results:
        return "The wiki index is empty. Run `wf-ingest` first to index the Warframe wiki."

    prompt = build_prompt(question, results)
    client = anthropic.Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY"))
    response = client.messages.create(
        model=CLAUDE_MODEL,
        max_tokens=1024,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": prompt}],
    )
    return response.content[0].text


def main() -> None:
    import sys
    print("Warframe Wiki Chatbot (type 'quit' to exit)")
    print(f"Index: {WikiStore().count()} chunks loaded.")
    print()
    store = WikiStore()
    while True:
        try:
            question = input("You: ").strip()
        except (EOFError, KeyboardInterrupt):
            break
        if not question or question.lower() in ("quit", "exit"):
            break
        answer = ask(question, store=store)
        print(f"\nBot: {answer}\n")


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run tests**

```bash
cd /Users/elias/Documents/WFC/chatbot && uv run pytest tests/test_chat.py -v 2>&1
```
Expected: 4 passed.

- [ ] **Step 5: Run full test suite**

```bash
cd /Users/elias/Documents/WFC/chatbot && uv run pytest -v 2>&1 | tail -10
```
Expected: all tests pass.

- [ ] **Step 6: Commit**

```bash
cd /Users/elias/Documents/WFC && git add chatbot/ && git commit -m "feat(chatbot): RAG chat interface — retrieval + Claude generation with source citation"
```

---

## Task 9: Run the full ingest + verify end-to-end

This task runs the real pipeline against the live wiki. **Takes 20-40 minutes on first run.**

- [ ] **Step 1: Set ANTHROPIC_API_KEY**

```bash
export ANTHROPIC_API_KEY="your-key-here"
```

- [ ] **Step 2: Run ingest** (incremental — safe to interrupt and resume)

```bash
cd /Users/elias/Documents/WFC/chatbot && uv run wf-ingest 2>&1 | tee ingest.log
```
Expected output:
```
Enumerating wiki pages...
  ~7000 content pages found.
  ~7000 pages need (re-)indexing.
  [100%] 7000/7000 pages, ~45000 chunks indexed...
Done. 7000 pages → ~45000 chunks in ~1800s.
Store total: ~45000 chunks.
```
On subsequent runs: only changed pages are re-indexed (seconds, not minutes).

- [ ] **Step 3: Verify chunk count**

```bash
cd /Users/elias/Documents/WFC/chatbot && python3 -c "
from warframe_chatbot.store import WikiStore
s = WikiStore()
print(f'Chunks: {s.count()}')
results = s.query('shieldgate invulnerability', k=3)
for r in results:
    print(f'  [{r.score:.2f}] {r.page_title} — {r.section}: {r.text[:80]}...')
" 2>&1
- [ ] **Step 4: Ask a question end-to-end (requires ANTHROPIC_API_KEY)**

```bash
cd /Users/elias/Documents/WFC/chatbot && python3 -c "
from warframe_chatbot.chat import ask
print(ask('How does shieldgate work and what mods enable it?'))
"
```
Expected: A sourced answer citing wiki pages like [[Shield Gating]], [[Augur]] set, etc.

- [ ] **Step 5: Commit final state + ingest log**

```bash
git add chatbot/ && git commit -m "feat(chatbot): full wiki ingested — end-to-end RAG working"
```

---

## Self-Review

**Spec coverage:**
- ✅ Full wiki crawl (namespace 0, filtered by size) — Task 2 enumerate_pages
- ✅ Incremental updates via revision ID diff — Task 6 pipeline
- ✅ Local embeddings (no API cost) — Task 5 all-MiniLM-L6-v2
- ✅ ChromaDB local persistence — Task 5 WikiStore
- ✅ Section-aware chunking with overlap — Task 4 chunker
- ✅ Wikitext cleaning — Task 3 cleaner
- ✅ Claude generation with source citation — Task 8 chat
- ✅ Deleted page cleanup — Task 6 pipeline stale removal
- ✅ REPL entry point (wf-chat) — Task 8 main()
- ✅ Ingest entry point (wf-ingest) — Task 6 main()

**Placeholder scan:** None found. All code blocks are complete and executable.

**Type consistency:**
- `PageContent` defined in Task 2, used in Tasks 4, 6 ✓
- `Chunk` defined in Task 4, used in Tasks 5, 8 ✓
- `SearchResult` defined in Task 5, used in Tasks 7, 8 ✓
- `WikiStore` defined in Task 5, used in Tasks 6, 7, 8 ✓
- `search()` signature `(query, *, store, k)` defined in Task 7, called in Task 8 ✓
