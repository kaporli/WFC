from __future__ import annotations
from dataclasses import dataclass

import chromadb
from chromadb.config import Settings

from warframe_chatbot.chunker import Chunk
from warframe_chatbot.config import COLLECTION, CHROMA_DIR, EMBED_DIM
from warframe_chatbot.embedder import embed


@dataclass
class SearchResult:
    page_title: str
    section: str
    text: str
    url: str
    revid: int
    score: float


def _id(c: Chunk) -> str:
    return f"{c.page_title}:::{c.chunk_index}"


class WikiStore:
    def __init__(self, persist_dir: str = str(CHROMA_DIR)) -> None:
        self._client = chromadb.PersistentClient(
            path=persist_dir,
            settings=Settings(anonymized_telemetry=False),
        )
        self._col = self._get_or_reset_collection()

    def _get_or_reset_collection(self):
        """Get the collection, resetting it if the embedding dimension changed."""
        try:
            col = self._client.get_or_create_collection(
                name=COLLECTION, metadata={"hnsw:space": "cosine"},
            )
            # Validate dimension matches current config by probing with a dummy vector
            if col.count() > 0:
                probe = col.get(limit=1, include=["embeddings"])
                embs = probe.get("embeddings")
                stored_dim = len(embs[0]) if embs is not None and len(embs) > 0 else EMBED_DIM
                if stored_dim != EMBED_DIM:
                    print(f"Embedding dimension changed ({len(probe['embeddings'][0])} → {EMBED_DIM}). Resetting collection.")
                    self._client.delete_collection(COLLECTION)
                    col = self._client.create_collection(
                        name=COLLECTION, metadata={"hnsw:space": "cosine"},
                    )
            return col
        except Exception:
            return self._client.get_or_create_collection(
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
