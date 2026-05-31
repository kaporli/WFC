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
