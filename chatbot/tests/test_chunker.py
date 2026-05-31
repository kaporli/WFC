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
