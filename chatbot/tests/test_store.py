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
