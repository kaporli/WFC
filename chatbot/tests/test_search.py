import pytest
from warframe_chatbot.chunker import Chunk
from warframe_chatbot.store import WikiStore
from warframe_chatbot.search import search


def test_search_returns_results(tmp_path):
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


def test_search_empty_store(tmp_path):
    store = WikiStore(persist_dir=str(tmp_path / "chroma2"))
    assert search("anything", store=store) == []


def test_search_result_has_url(tmp_path):
    store = WikiStore(persist_dir=str(tmp_path / "chroma3"))
    store.upsert([Chunk(page_title="Frost", section="", text="Frost is cold.",
                        url="https://wiki.warframe.com/w/Frost", revid=1, chunk_index=0)])
    results = search("Frost warframe", store=store, k=1)
    assert results[0].url.startswith("https://")
