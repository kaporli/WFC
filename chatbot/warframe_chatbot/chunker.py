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
